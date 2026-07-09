#!/usr/bin/env python3
"""
Render one or more PLY models from a full spherical set of camera positions.

Default angular sampling:
    phi gap   = 2 degrees (azimuth around +Z)
    theta gap = 2 degrees (polar angle measured down from +Z)

That produces 180 * 90 = 16,200 PNG files per PLY model.

The script supports both triangle-mesh PLY files and point-cloud PLY files.
It writes a CSV manifest containing one row per expected/rendered image.

Examples
--------
Single model, default 2-degree sampling:
    python ply_spherical_renderer.py model.ply output/renderer

Full 1-degree sampling:
    python ply_spherical_renderer.py model.ply output/renderer -phi 1 -theta 1

Directory of models, class inferred from each model's parent folder:
    python ply_spherical_renderer.py dataset output/renderer --class-from-parent

Faster test run, one image every 10 degrees:
    python ply_spherical_renderer.py dataset output/renderer --phi-step 10 --theta-step 10

Use a label CSV containing columns origin_file and classification:
    python ply_spherical_renderer.py dataset output/renderer --labels-csv labels.csv

Linux headless CPU rendering:
    python ply_spherical_renderer.py dataset output/renderer --headless-cpu
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np


SCRIPT_VERSION = "2.2-windows-cross-section"


MANIFEST_FIELDS = [
    "image_file",
    "image_relative_path",
    "image_absolute_path",
    "origin_file",
    "origin_relative_path",
    "origin_absolute_path",
    "model_id",
    "classification",
    "geometry_type",
    "renderer_backend",
    "phi_azimuth_deg",
    "theta_polar_deg",
    "elevation_deg",
    "camera_convention",
    "camera_x",
    "camera_y",
    "camera_z",
    "target_x",
    "target_y",
    "target_z",
    "up_x",
    "up_y",
    "up_z",
    "camera_distance",
    "vertical_fov_deg",
    "image_width_px",
    "image_height_px",
    "point_size_px",
    "vertex_count",
    "triangle_count",
    "point_count",
    "has_vertex_colors",
    "has_vertex_normals",
    "used_default_color",
    "computed_vertex_normals",
    "bbox_min_x",
    "bbox_min_y",
    "bbox_min_z",
    "bbox_max_x",
    "bbox_max_y",
    "bbox_max_z",
    "bbox_center_x",
    "bbox_center_y",
    "bbox_center_z",
    "bounding_sphere_radius",
    "origin_size_bytes",
    "origin_modified_utc",
    "origin_sha256",
    "render_status",
    "rendered_utc",
]

ERROR_FIELDS = ["origin_file", "origin_absolute_path", "error_type", "error_message"]

CROSS_SECTION_FIELDS = [
    "model_id",
    "classification",
    "origin_file",
    "origin_absolute_path",
    "cross_section_file",
    "cross_section_relative_path",
    "cross_section_absolute_path",
    "cross_section_axis",
    "cross_section_plane_normal",
    "cross_section_status",
    "image_width_px",
    "image_height_px",
]


@dataclass
class GeometryInfo:
    geometry: Any
    geometry_type: str
    center: np.ndarray
    bbox_min: np.ndarray
    bbox_max: np.ndarray
    radius: float
    vertex_count: int
    triangle_count: int
    point_count: int
    has_vertex_colors: bool
    has_vertex_normals: bool
    used_default_color: bool
    computed_vertex_normals: bool


@dataclass
class ModelRecord:
    source_path: Path
    source_relative_path: Path
    model_id: str
    classification: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render PLY meshes or point clouds from spherical camera angles and "
            "write a CSV manifest. Defaults to 16,200 images per model (2-degree gaps)."
        )
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {SCRIPT_VERSION}")
    parser.add_argument("input", type=Path, help="A .ply file or a directory containing .ply files.")
    parser.add_argument("output", type=Path, help="Output directory.")

    parser.add_argument("--width", type=positive_int, default=512, help="PNG width in pixels. Default: 512")
    parser.add_argument("--height", type=positive_int, default=512, help="PNG height in pixels. Default: 512")
    parser.add_argument(
        "-phi",
        "--phi-step",
        dest="phi_step",
        type=phi_step,
        default=2,
        metavar="INT",
        help="Azimuth gap in degrees over [0, 360). Default: 2",
    )
    parser.add_argument(
        "-theta",
        "--theta-step",
        dest="theta_step",
        type=theta_step,
        default=2,
        metavar="INT",
        help="Polar-angle gap in degrees over [0, 180). Default: 2",
    )
    parser.add_argument(
        "--fov",
        type=fov_value,
        default=45.0,
        help="Vertical camera field of view in degrees. Default: 45",
    )
    parser.add_argument(
        "--margin",
        type=margin_value,
        default=1.08,
        help="Camera-distance safety multiplier. Must be >= 1. Default: 1.08",
    )
    parser.add_argument(
        "--point-size",
        type=positive_float,
        default=3.0,
        help="Rendered point size for point-cloud PLY files. Default: 3",
    )
    parser.add_argument(
        "--background",
        type=unit_float,
        nargs=4,
        metavar=("R", "G", "B", "A"),
        default=(1.0, 1.0, 1.0, 1.0),
        help="RGBA background values in [0,1]. Default: 1 1 1 1",
    )
    parser.add_argument(
        "--base-color",
        type=unit_float,
        nargs=4,
        metavar=("R", "G", "B", "A"),
        default=(0.72, 0.72, 0.72, 1.0),
        help="RGBA color used when a model has no vertex colors. Default: 0.72 0.72 0.72 1",
    )

    parser.add_argument(
        "--classification",
        default=None,
        help="Apply one classification label to every input model.",
    )
    parser.add_argument(
        "--labels-csv",
        type=Path,
        default=None,
        help=(
            "Optional CSV mapping source models to classes. Accepted file columns: "
            "origin_file/source_file/file/filename/path; accepted class columns: "
            "classification/class/label/category."
        ),
    )
    parser.add_argument(
        "--class-from-parent",
        action="store_true",
        help="Use each PLY file's immediate parent-directory name as its classification.",
    )

    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="When input is a directory, search only that directory and not subdirectories.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Render PNGs even when they already exist. By default existing PNGs are reused.",
    )
    parser.add_argument(
        "--progress-every",
        type=positive_int,
        default=500,
        help="Print progress and flush the manifest every N images. Default: 500",
    )
    parser.add_argument(
        "--hash-source",
        action="store_true",
        help="Calculate SHA-256 for each source PLY and include it in the manifest.",
    )
    parser.add_argument(
        "--renderer-backend",
        choices=("auto", "visualizer", "offscreen"),
        default="auto",
        help=(
            "Rendering backend. 'auto' uses the hidden Visualizer on Windows and "
            "OffscreenRenderer on other platforms. Default: auto"
        ),
    )
    parser.add_argument(
        "--headless-cpu",
        action="store_true",
        help=(
            "Set EGL_PLATFORM=surfaceless before importing Open3D. Intended for "
            "headless Linux systems with Mesa; not a Windows software-rendering switch."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned image count and output locations without loading Open3D or rendering.",
    )
    parser.add_argument(
        "--no-cross-section",
        action="store_false",
        dest="cross_section",
        help="Skip exporting one mid-plane binary (black/white) cross-section PNG per model.",
    )
    parser.add_argument(
        "--cross-section-axis",
        choices=("auto", "x", "y", "z"),
        default="auto",
        help=(
            "Slice plane for the cross-section image. auto picks the thinnest bbox axis "
            "(typical sherd thickness direction). Default: auto"
        ),
    )
    parser.set_defaults(cross_section=True)
    return parser.parse_args()


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def phi_step(value: str) -> int:
    parsed = int(value)
    if not 1 <= parsed <= 360:
        raise argparse.ArgumentTypeError("must be an integer from 1 to 360")
    return parsed


def theta_step(value: str) -> int:
    parsed = int(value)
    if not 1 <= parsed <= 180:
        raise argparse.ArgumentTypeError("must be an integer from 1 to 180")
    return parsed


def fov_value(value: str) -> float:
    parsed = float(value)
    if not 1.0 <= parsed < 179.0:
        raise argparse.ArgumentTypeError("must be in [1, 179)")
    return parsed


def margin_value(value: str) -> float:
    parsed = float(value)
    if parsed < 1.0:
        raise argparse.ArgumentTypeError("must be at least 1.0")
    return parsed


def unit_float(value: str) -> float:
    parsed = float(value)
    if not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError("must be in [0, 1]")
    return parsed


def normalize_lookup_key(value: str | Path) -> str:
    text = str(value).strip().replace("\\", "/")
    return text.casefold()


def safe_component(value: str, fallback: str = "unnamed") -> str:
    value = value.strip()
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("._-")
    return value or fallback


def discover_ply_files(input_path: Path, recursive: bool) -> tuple[list[Path], Path]:
    input_path = input_path.expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input does not exist: {input_path}")

    if input_path.is_file():
        if input_path.suffix.casefold() != ".ply":
            raise ValueError(f"Input file must have a .ply extension: {input_path}")
        return [input_path], input_path.parent

    pattern = "**/*.ply" if recursive else "*.ply"
    files = sorted(
        (path.resolve() for path in input_path.glob(pattern) if path.is_file()),
        key=lambda path: normalize_lookup_key(path.relative_to(input_path)),
    )
    if not files:
        raise FileNotFoundError(f"No .ply files found under: {input_path}")
    return files, input_path


def load_label_map(labels_csv: Path | None) -> dict[str, str]:
    if labels_csv is None:
        return {}

    labels_csv = labels_csv.expanduser().resolve()
    if not labels_csv.is_file():
        raise FileNotFoundError(f"Labels CSV not found: {labels_csv}")

    file_candidates = {"origin_file", "source_file", "file", "filename", "path"}
    class_candidates = {"classification", "class", "label", "category"}
    mapping: dict[str, str] = {}

    with labels_csv.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"Labels CSV has no header: {labels_csv}")

        normalized_columns = {name.strip().casefold(): name for name in reader.fieldnames}
        file_column = next((normalized_columns[name] for name in file_candidates if name in normalized_columns), None)
        class_column = next((normalized_columns[name] for name in class_candidates if name in normalized_columns), None)

        if file_column is None or class_column is None:
            raise ValueError(
                "Labels CSV requires one file column "
                "(origin_file/source_file/file/filename/path) and one class column "
                "(classification/class/label/category)."
            )

        for row_number, row in enumerate(reader, start=2):
            raw_file = (row.get(file_column) or "").strip()
            raw_class = (row.get(class_column) or "").strip()
            if not raw_file:
                print(f"Warning: labels CSV row {row_number} has no source file; skipped.", file=sys.stderr)
                continue
            mapping[normalize_lookup_key(raw_file)] = raw_class

    return mapping


def classification_from_map(
    source_path: Path,
    source_relative_path: Path,
    label_map: dict[str, str],
) -> str | None:
    candidates = [
        source_path,
        source_path.as_posix(),
        source_relative_path,
        source_relative_path.as_posix(),
        source_path.name,
        source_path.stem,
    ]
    for candidate in candidates:
        key = normalize_lookup_key(candidate)
        if key in label_map:
            return label_map[key]
    return None


def build_model_records(
    files: Sequence[Path],
    input_root: Path,
    explicit_classification: str | None,
    label_map: dict[str, str],
    class_from_parent: bool,
) -> list[ModelRecord]:
    base_ids: list[str] = []
    relative_paths: list[Path] = []

    for source in files:
        try:
            relative = source.relative_to(input_root)
        except ValueError:
            relative = Path(source.name)
        relative_paths.append(relative)
        without_suffix = relative.with_suffix("")
        parts = [safe_component(part) for part in without_suffix.parts]
        base_ids.append("__".join(parts) or safe_component(source.stem))

    id_counts: dict[str, int] = {}
    for base_id in base_ids:
        id_counts[base_id] = id_counts.get(base_id, 0) + 1

    records: list[ModelRecord] = []
    for source, relative, base_id in zip(files, relative_paths, base_ids):
        if id_counts[base_id] > 1:
            suffix = hashlib.sha1(relative.as_posix().encode("utf-8")).hexdigest()[:8]
            model_id = f"{base_id}__{suffix}"
        else:
            model_id = base_id

        mapped_class = classification_from_map(source, relative, label_map)
        if explicit_classification is not None:
            classification = explicit_classification.strip()
        elif mapped_class is not None:
            classification = mapped_class.strip()
        elif class_from_parent:
            classification = source.parent.name.strip()
        else:
            classification = ""

        records.append(
            ModelRecord(
                source_path=source,
                source_relative_path=relative,
                model_id=model_id,
                classification=classification,
            )
        )

    return records


def spherical_camera(
    center: np.ndarray,
    distance: float,
    phi_deg: int,
    theta_deg: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Return camera eye and up vectors using ISO-style spherical coordinates.

    phi: azimuth in the XY plane, 0 degrees at +X, increasing toward +Y.
    theta: polar angle from +Z, 0 degrees at +Z, 90 in the XY plane.

    The up vector is tangent to the sphere toward decreasing theta, which avoids
    the usual world-up singularity at the poles and gives each polar view a
    deterministic camera roll.
    """
    phi = math.radians(phi_deg)
    theta = math.radians(theta_deg)

    radial = np.array(
        [
            math.sin(theta) * math.cos(phi),
            math.sin(theta) * math.sin(phi),
            math.cos(theta),
        ],
        dtype=np.float32,
    )
    up = np.array(
        [
            -math.cos(theta) * math.cos(phi),
            -math.cos(theta) * math.sin(phi),
            math.sin(theta),
        ],
        dtype=np.float32,
    )

    eye = center.astype(np.float32) + np.float32(distance) * radial
    up_norm = float(np.linalg.norm(up))
    if up_norm == 0.0:
        raise RuntimeError(f"Calculated zero-length camera up vector for phi={phi_deg}, theta={theta_deg}")
    up /= up_norm
    return eye, up


def calculate_camera_distance(
    radius: float,
    width: int,
    height: int,
    vertical_fov_deg: float,
    margin: float,
) -> float:
    vertical_half = math.radians(vertical_fov_deg / 2.0)
    aspect = width / height
    horizontal_half = math.atan(math.tan(vertical_half) * aspect)
    limiting_half_angle = min(vertical_half, horizontal_half)
    return float((radius / math.sin(limiting_half_angle)) * margin)


def load_geometry(o3d: Any, source_path: Path, base_color: Sequence[float]) -> GeometryInfo:
    mesh = o3d.io.read_triangle_mesh(str(source_path), print_progress=False)

    if len(mesh.vertices) > 0 and len(mesh.triangles) > 0:
        has_vertex_colors = bool(mesh.has_vertex_colors())
        has_vertex_normals = bool(mesh.has_vertex_normals())
        used_default_color = not has_vertex_colors
        computed_vertex_normals = not has_vertex_normals

        if computed_vertex_normals:
            mesh.compute_vertex_normals()
        if used_default_color:
            mesh.paint_uniform_color(list(base_color[:3]))

        geometry = mesh
        geometry_type = "triangle_mesh"
        vertex_count = len(mesh.vertices)
        triangle_count = len(mesh.triangles)
        point_count = 0
    else:
        point_cloud = o3d.io.read_point_cloud(
            str(source_path),
            remove_nan_points=True,
            remove_infinite_points=True,
            print_progress=False,
        )
        if len(point_cloud.points) == 0:
            raise ValueError(
                "PLY contains neither a non-empty triangle mesh nor a non-empty point cloud."
            )
        has_vertex_colors = bool(point_cloud.has_colors())
        has_vertex_normals = bool(point_cloud.has_normals())
        used_default_color = not has_vertex_colors
        computed_vertex_normals = False

        if used_default_color:
            point_cloud.paint_uniform_color(list(base_color[:3]))

        geometry = point_cloud
        geometry_type = "point_cloud"
        vertex_count = 0
        triangle_count = 0
        point_count = len(point_cloud.points)

    bbox = geometry.get_axis_aligned_bounding_box()
    bbox_min = np.asarray(bbox.get_min_bound(), dtype=np.float64)
    bbox_max = np.asarray(bbox.get_max_bound(), dtype=np.float64)
    center = np.asarray(bbox.get_center(), dtype=np.float64)
    radius = float(np.linalg.norm(bbox_max - bbox_min) / 2.0)

    if not np.all(np.isfinite(center)) or not math.isfinite(radius) or radius <= 0.0:
        raise ValueError(f"Invalid or zero-size model bounds: center={center.tolist()}, radius={radius}")

    return GeometryInfo(
        geometry=geometry,
        geometry_type=geometry_type,
        center=center,
        bbox_min=bbox_min,
        bbox_max=bbox_max,
        radius=radius,
        vertex_count=vertex_count,
        triangle_count=triangle_count,
        point_count=point_count,
        has_vertex_colors=has_vertex_colors,
        has_vertex_normals=has_vertex_normals,
        used_default_color=used_default_color,
        computed_vertex_normals=computed_vertex_normals,
    )


def build_material(o3d: Any, geometry_type: str, base_color: Sequence[float], point_size: float) -> Any:
    material = o3d.visualization.rendering.MaterialRecord()
    material.base_color = list(base_color)

    if geometry_type == "triangle_mesh":
        material.shader = "defaultLit"
        material.base_roughness = 0.85
        material.base_reflectance = 0.1
    else:
        material.shader = "defaultUnlit"
        material.point_size = float(point_size)

    return material


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def iso_utc_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def format_vector_component(value: float) -> str:
    return f"{float(value):.10g}"


def write_run_config(args: argparse.Namespace, records: Sequence[ModelRecord], image_count_per_model: int) -> None:
    args.output.mkdir(parents=True, exist_ok=True)
    config = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input": str(args.input.expanduser().resolve()),
        "output": str(args.output.expanduser().resolve()),
        "model_count": len(records),
        "images_per_model": image_count_per_model,
        "total_expected_images": len(records) * image_count_per_model,
        "phi_values_deg": list(range(0, 360, args.phi_step)),
        "theta_values_deg": list(range(0, 180, args.theta_step)),
        "camera_convention": (
            "phi is azimuth: 0=+X, 90=+Y; theta is polar angle from +Z; "
            "camera looks at the model bounding-box center"
        ),
        "width": args.width,
        "height": args.height,
        "vertical_fov_deg": args.fov,
        "margin": args.margin,
        "point_size_px": args.point_size,
        "background_rgba": list(args.background),
        "base_color_rgba": list(args.base_color),
        "overwrite": args.overwrite,
        "hash_source": args.hash_source,
        "renderer_backend_requested": args.renderer_backend,
        "renderer_backend_selected": select_renderer_backend(args),
        "cross_section_enabled": args.cross_section,
        "cross_section_axis": args.cross_section_axis,
    }
    config_path = args.output / "run_config.json"
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def select_renderer_backend(args: argparse.Namespace) -> str:
    """Choose a renderer that works on the current platform."""
    if args.renderer_backend != "auto":
        return args.renderer_backend
    return "visualizer" if sys.platform.startswith("win") else "offscreen"


def set_visualizer_camera(
    o3d: Any,
    view_control: Any,
    width: int,
    height: int,
    vertical_fov_deg: float,
    eye: np.ndarray,
    target: np.ndarray,
    up: np.ndarray,
) -> None:
    """Set an exact pinhole camera for Open3D's legacy Visualizer.

    Open3D pinhole camera coordinates use +X right, +Y down and +Z forward.
    The resulting 4x4 extrinsic matrix transforms world coordinates into the
    camera coordinate system.
    """
    eye64 = np.asarray(eye, dtype=np.float64)
    target64 = np.asarray(target, dtype=np.float64)
    up64 = np.asarray(up, dtype=np.float64)

    forward = target64 - eye64
    forward_norm = float(np.linalg.norm(forward))
    if forward_norm <= 0.0:
        raise RuntimeError("Camera eye and target are identical.")
    forward /= forward_norm

    up_norm = float(np.linalg.norm(up64))
    if up_norm <= 0.0:
        raise RuntimeError("Camera up vector has zero length.")
    up64 /= up_norm

    right = np.cross(forward, up64)
    right_norm = float(np.linalg.norm(right))
    if right_norm <= 1e-12:
        raise RuntimeError("Camera up vector is parallel to the viewing direction.")
    right /= right_norm

    # Re-orthogonalize up so accumulated floating-point error cannot skew R.
    true_up = np.cross(right, forward)
    true_up /= float(np.linalg.norm(true_up))
    down = -true_up

    rotation = np.vstack((right, down, forward))
    extrinsic = np.eye(4, dtype=np.float64)
    extrinsic[:3, :3] = rotation
    extrinsic[:3, 3] = -rotation @ eye64

    fy = float(height) / (2.0 * math.tan(math.radians(vertical_fov_deg) / 2.0))
    fx = fy
    cx = (float(width) - 1.0) / 2.0
    cy = (float(height) - 1.0) / 2.0

    parameters = o3d.camera.PinholeCameraParameters()
    parameters.intrinsic = o3d.camera.PinholeCameraIntrinsic(
        int(width), int(height), fx, fy, cx, cy
    )
    parameters.extrinsic = extrinsic

    accepted = view_control.convert_from_pinhole_camera_parameters(
        parameters, allow_arbitrary=True
    )
    if accepted is False:
        raise RuntimeError("Open3D rejected the requested pinhole camera parameters.")


def render_model(
    o3d: Any,
    args: argparse.Namespace,
    output_root: Path,
    model: ModelRecord,
    manifest_writer: csv.DictWriter,
    manifest_handle: Any,
) -> tuple[int, int, dict[str, str] | None]:
    source_stat = model.source_path.stat()
    source_hash = sha256_file(model.source_path) if args.hash_source else ""

    geometry_info = load_geometry(o3d, model.source_path, args.base_color)
    cross_section_info: dict[str, str] | None = None
    if args.cross_section:
        from cross_section import export_cross_section

        class_folder = safe_component(model.classification, fallback="unclassified")
        cross_section_info = export_cross_section(
            o3d=o3d,
            geometry_info=geometry_info,
            model_id=model.model_id,
            class_folder=class_folder,
            output_root=output_root,
            width=args.width,
            height=args.height,
            axis=args.cross_section_axis,
            overwrite=args.overwrite,
        )
        print(
            f"    cross-section ({cross_section_info['cross_section_status']}): "
            f"{cross_section_info['cross_section_relative_path']}",
            flush=True,
        )

    camera_distance = calculate_camera_distance(
        geometry_info.radius,
        args.width,
        args.height,
        args.fov,
        args.margin,
    )

    backend = select_renderer_backend(args)
    renderer = None
    visualizer = None
    view_control = None

    if backend == "offscreen":
        if sys.platform.startswith("win"):
            raise RuntimeError(
                "Open3D OffscreenRenderer uses unsupported EGL headless rendering on "
                "Windows. Use --renderer-backend visualizer or leave the backend as auto."
            )
        renderer = o3d.visualization.rendering.OffscreenRenderer(args.width, args.height)
        renderer.scene.set_background(np.asarray(args.background, dtype=np.float32))
        renderer.scene.show_axes(False)
        renderer.scene.show_skybox(False)
        renderer.scene.set_lighting(
            o3d.visualization.rendering.Open3DScene.LightingProfile.NO_SHADOWS,
            np.array([0.577, -0.577, -0.577], dtype=np.float32),
        )
        material = build_material(
            o3d, geometry_info.geometry_type, args.base_color, args.point_size
        )
        renderer.scene.add_geometry("model", geometry_info.geometry, material)
    else:
        visualizer = o3d.visualization.Visualizer()
        created = visualizer.create_window(
            window_name="PLY spherical renderer",
            width=args.width,
            height=args.height,
            visible=False,
        )
        if created is False:
            raise RuntimeError(
                "Open3D could not create a hidden OpenGL window. Update the graphics "
                "driver and run the script from a normal Windows desktop session."
            )

        render_option = visualizer.get_render_option()
        render_option.background_color = np.asarray(args.background[:3], dtype=np.float64)
        render_option.point_size = float(args.point_size)
        render_option.light_on = geometry_info.geometry_type == "triangle_mesh"
        if hasattr(render_option, "mesh_show_back_face"):
            render_option.mesh_show_back_face = True

        if not visualizer.add_geometry(geometry_info.geometry, reset_bounding_box=True):
            visualizer.destroy_window()
            raise RuntimeError("Open3D Visualizer failed to add the model geometry.")
        view_control = visualizer.get_view_control()

    class_folder = safe_component(model.classification, fallback="unclassified")
    model_output_dir = output_root / "images" / class_folder / model.model_id
    model_output_dir.mkdir(parents=True, exist_ok=True)

    rendered_count = 0
    reused_count = 0
    processed_count = 0
    phi_values = range(0, 360, args.phi_step)
    theta_values = range(0, 180, args.theta_step)
    expected_count = len(phi_values) * len(theta_values)

    try:
        for theta_deg in theta_values:
            elevation_deg = 90 - theta_deg
            for phi_deg in phi_values:
                image_name = f"{model.model_id}__phi_{phi_deg:03d}__theta_{theta_deg:03d}.png"
                image_path = model_output_dir / image_name
                image_relative_path = image_path.relative_to(output_root)

                eye, up = spherical_camera(
                    center=geometry_info.center,
                    distance=camera_distance,
                    phi_deg=phi_deg,
                    theta_deg=theta_deg,
                )

                rendered_utc = ""
                if image_path.exists() and not args.overwrite:
                    render_status = "existing"
                    reused_count += 1
                else:
                    if backend == "offscreen":
                        assert renderer is not None
                        renderer.setup_camera(
                            float(args.fov),
                            geometry_info.center.astype(np.float32),
                            eye.astype(np.float32),
                            up.astype(np.float32),
                        )
                        image = renderer.render_to_image()
                        if not o3d.io.write_image(str(image_path), image, 9):
                            raise IOError(f"Open3D failed to write PNG: {image_path}")
                    else:
                        assert visualizer is not None and view_control is not None
                        set_visualizer_camera(
                            o3d=o3d,
                            view_control=view_control,
                            width=args.width,
                            height=args.height,
                            vertical_fov_deg=args.fov,
                            eye=eye,
                            target=geometry_info.center,
                            up=up,
                        )
                        visualizer.poll_events()
                        visualizer.update_renderer()
                        captured = visualizer.capture_screen_image(
                            str(image_path), do_render=True
                        )
                        if captured is False or not image_path.is_file():
                            raise IOError(
                                f"Open3D Visualizer failed to write PNG: {image_path}"
                            )

                    render_status = "rendered"
                    rendered_utc = datetime.now(timezone.utc).isoformat()
                    rendered_count += 1

                row = {
                    "image_file": image_name,
                    "image_relative_path": image_relative_path.as_posix(),
                    "image_absolute_path": str(image_path.resolve()),
                    "origin_file": model.source_path.name,
                    "origin_relative_path": model.source_relative_path.as_posix(),
                    "origin_absolute_path": str(model.source_path),
                    "model_id": model.model_id,
                    "classification": model.classification,
                    "geometry_type": geometry_info.geometry_type,
                    "renderer_backend": backend,
                    "phi_azimuth_deg": phi_deg,
                    "theta_polar_deg": theta_deg,
                    "elevation_deg": elevation_deg,
                    "camera_convention": "phi: +X toward +Y; theta: down from +Z",
                    "camera_x": format_vector_component(eye[0]),
                    "camera_y": format_vector_component(eye[1]),
                    "camera_z": format_vector_component(eye[2]),
                    "target_x": format_vector_component(geometry_info.center[0]),
                    "target_y": format_vector_component(geometry_info.center[1]),
                    "target_z": format_vector_component(geometry_info.center[2]),
                    "up_x": format_vector_component(up[0]),
                    "up_y": format_vector_component(up[1]),
                    "up_z": format_vector_component(up[2]),
                    "camera_distance": format_vector_component(camera_distance),
                    "vertical_fov_deg": args.fov,
                    "image_width_px": args.width,
                    "image_height_px": args.height,
                    "point_size_px": args.point_size if geometry_info.geometry_type == "point_cloud" else "",
                    "vertex_count": geometry_info.vertex_count,
                    "triangle_count": geometry_info.triangle_count,
                    "point_count": geometry_info.point_count,
                    "has_vertex_colors": geometry_info.has_vertex_colors,
                    "has_vertex_normals": geometry_info.has_vertex_normals,
                    "used_default_color": geometry_info.used_default_color,
                    "computed_vertex_normals": geometry_info.computed_vertex_normals,
                    "bbox_min_x": format_vector_component(geometry_info.bbox_min[0]),
                    "bbox_min_y": format_vector_component(geometry_info.bbox_min[1]),
                    "bbox_min_z": format_vector_component(geometry_info.bbox_min[2]),
                    "bbox_max_x": format_vector_component(geometry_info.bbox_max[0]),
                    "bbox_max_y": format_vector_component(geometry_info.bbox_max[1]),
                    "bbox_max_z": format_vector_component(geometry_info.bbox_max[2]),
                    "bbox_center_x": format_vector_component(geometry_info.center[0]),
                    "bbox_center_y": format_vector_component(geometry_info.center[1]),
                    "bbox_center_z": format_vector_component(geometry_info.center[2]),
                    "bounding_sphere_radius": format_vector_component(geometry_info.radius),
                    "origin_size_bytes": source_stat.st_size,
                    "origin_modified_utc": iso_utc_from_timestamp(source_stat.st_mtime),
                    "origin_sha256": source_hash,
                    "render_status": render_status,
                    "rendered_utc": rendered_utc,
                }
                manifest_writer.writerow(row)
                processed_count += 1
                if processed_count % args.progress_every == 0 or processed_count == expected_count:
                    manifest_handle.flush()
                    print(
                        f"    progress={processed_count:,}/{expected_count:,} "
                        f"({processed_count / expected_count:.1%})",
                        flush=True,
                    )
    finally:
        if renderer is not None:
            renderer.scene.clear_geometry()
            del renderer
        if visualizer is not None:
            visualizer.destroy_window()

    return rendered_count, reused_count, cross_section_info

def print_plan(args: argparse.Namespace, records: Sequence[ModelRecord]) -> None:
    phi_values = list(range(0, 360, args.phi_step))
    theta_values = list(range(0, 180, args.theta_step))
    per_model = len(phi_values) * len(theta_values)
    total = per_model * len(records)

    print(f"Models:              {len(records):,}")
    print(f"Phi samples/model:   {len(phi_values):,} ({phi_values[0]}..{phi_values[-1]} degrees)")
    print(f"Theta samples/model: {len(theta_values):,} ({theta_values[0]}..{theta_values[-1]} degrees)")
    print(f"Images/model:        {per_model:,}")
    print(f"Total images:        {total:,}")
    print(f"Image size:          {args.width} x {args.height} px")
    print(f"Renderer backend:    {select_renderer_backend(args)}")
    print(f"Cross-section PNG:   {'yes' if args.cross_section else 'no'} (axis={args.cross_section_axis})")
    print(f"Output directory:    {args.output.expanduser().resolve()}")
    print(f"Manifest:            {(args.output.expanduser().resolve() / 'manifest.csv')}")


def main() -> int:
    args = parse_args()
    print(f"Script: {Path(__file__).resolve()}")
    print(f"Version: {SCRIPT_VERSION}")
    args.output = args.output.expanduser().resolve()

    try:
        files, input_root = discover_ply_files(args.input, recursive=not args.no_recursive)
        label_map = load_label_map(args.labels_csv)
        records = build_model_records(
            files=files,
            input_root=input_root,
            explicit_classification=args.classification,
            label_map=label_map,
            class_from_parent=args.class_from_parent,
        )
    except Exception as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2

    print_plan(args, records)
    if args.dry_run:
        return 0

    # Open3D software/headless EGL rendering is Linux-only. On Windows, clear
    # variables that can force EGL mode and use the hidden Visualizer backend.
    if sys.platform.startswith("win"):
        if args.headless_cpu:
            print(
                "Warning: --headless-cpu is Linux-only and will be ignored on Windows.",
                file=sys.stderr,
            )
        for variable in ("EGL_PLATFORM", "OPEN3D_CPU_RENDERING", "LIBGL_ALWAYS_SOFTWARE"):
            if variable in os.environ:
                print(
                    f"Warning: removing {variable} for Windows rendering.",
                    file=sys.stderr,
                )
                os.environ.pop(variable, None)
    elif args.headless_cpu:
        os.environ.setdefault("EGL_PLATFORM", "surfaceless")
        os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")

    try:
        import open3d as o3d
    except ImportError:
        print(
            "Open3D is not installed. Install dependencies with:\n"
            "    python -m pip install open3d numpy",
            file=sys.stderr,
        )
        return 3

    args.output.mkdir(parents=True, exist_ok=True)
    image_count_per_model = len(range(0, 360, args.phi_step)) * len(range(0, 180, args.theta_step))
    write_run_config(args, records, image_count_per_model)

    manifest_path = args.output / "manifest.csv"
    cross_sections_path = args.output / "cross_sections.csv"
    errors_path = args.output / "errors.csv"
    total_rendered = 0
    total_reused = 0
    failed_models = 0

    with (
        manifest_path.open("w", newline="", encoding="utf-8-sig") as manifest_handle,
        cross_sections_path.open("w", newline="", encoding="utf-8-sig") as cross_sections_handle,
        errors_path.open("w", newline="", encoding="utf-8-sig") as errors_handle,
    ):
        manifest_writer = csv.DictWriter(manifest_handle, fieldnames=MANIFEST_FIELDS)
        manifest_writer.writeheader()
        cross_sections_writer = csv.DictWriter(cross_sections_handle, fieldnames=CROSS_SECTION_FIELDS)
        cross_sections_writer.writeheader()
        error_writer = csv.DictWriter(errors_handle, fieldnames=ERROR_FIELDS)
        error_writer.writeheader()

        for index, model in enumerate(records, start=1):
            class_display = model.classification or "unclassified"
            print(
                f"[{index}/{len(records)}] Rendering {model.source_relative_path} "
                f"(class={class_display})",
                flush=True,
            )
            try:
                rendered, reused, cross_info = render_model(
                    o3d=o3d,
                    args=args,
                    output_root=args.output,
                    model=model,
                    manifest_writer=manifest_writer,
                    manifest_handle=manifest_handle,
                )
                manifest_handle.flush()
                total_rendered += rendered
                total_reused += reused
                if cross_info is not None:
                    cross_sections_writer.writerow(
                        {
                            "model_id": model.model_id,
                            "classification": model.classification,
                            "origin_file": model.source_path.name,
                            "origin_absolute_path": str(model.source_path),
                            "image_width_px": args.width,
                            "image_height_px": args.height,
                            **cross_info,
                        }
                    )
                    cross_sections_handle.flush()
                print(f"    rendered={rendered:,}, existing={reused:,}", flush=True)
            except Exception as exc:
                failed_models += 1
                error_writer.writerow(
                    {
                        "origin_file": model.source_path.name,
                        "origin_absolute_path": str(model.source_path),
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                )
                errors_handle.flush()
                print(f"    ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
                traceback.print_exc()

    if failed_models == 0:
        try:
            errors_path.unlink()
        except OSError:
            pass

    print("\nFinished.")
    print(f"New PNGs rendered: {total_rendered:,}")
    print(f"Existing PNGs reused: {total_reused:,}")
    print(f"Failed models: {failed_models:,}")
    print(f"Manifest: {manifest_path}")
    if failed_models:
        print(f"Errors:   {errors_path}")

    return 1 if failed_models else 0


if __name__ == "__main__":
    raise SystemExit(main())
