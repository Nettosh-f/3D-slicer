from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np


@dataclass(frozen=True)
class CrossSectionPlane:
    center: np.ndarray
    normal: np.ndarray
    axis_label: str


def choose_cross_section_plane(
    bbox_min: np.ndarray,
    bbox_max: np.ndarray,
    center: np.ndarray,
    axis: str = "auto",
) -> CrossSectionPlane:
    extents = bbox_max - bbox_min
    axis = axis.strip().casefold()
    labels = ("x", "y", "z")
    if axis == "auto":
        idx = int(np.argmin(extents))
        label = labels[idx]
    elif axis in labels:
        label = axis
    else:
        raise ValueError(f"Unsupported cross-section axis: {axis!r} (use auto, x, y, or z)")

    normal = np.zeros(3, dtype=np.float64)
    normal[labels.index(label)] = 1.0
    return CrossSectionPlane(center=center.astype(np.float64), normal=normal, axis_label=label)


def _plane_basis(normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = normal / np.linalg.norm(normal)
    helper = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    if abs(float(np.dot(helper, n))) > 0.9:
        helper = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    u = np.cross(n, helper)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    v /= np.linalg.norm(v)
    return u, v


def project_to_plane(points: np.ndarray, center: np.ndarray, normal: np.ndarray) -> np.ndarray:
    if len(points) == 0:
        return np.empty((0, 2), dtype=np.float64)
    u, v = _plane_basis(normal)
    rel = points - center
    return np.column_stack((rel @ u, rel @ v))


def _triangle_plane_segment(
    v0: np.ndarray,
    v1: np.ndarray,
    v2: np.ndarray,
    center: np.ndarray,
    normal: np.ndarray,
    eps: float,
) -> tuple[np.ndarray, np.ndarray] | None:
    verts = (v0, v1, v2)
    dists = [float(np.dot(v - center, normal)) for v in verts]
    points: list[np.ndarray] = []

    for i in range(3):
        j = (i + 1) % 3
        di, dj = dists[i], dists[j]
        if abs(di) <= eps and abs(dj) <= eps:
            continue
        if abs(di) <= eps:
            points.append(verts[i])
            continue
        if abs(dj) <= eps:
            points.append(verts[j])
            continue
        if di * dj < 0.0:
            t = di / (di - dj)
            points.append(verts[i] + t * (verts[j] - verts[i]))

    if len(points) < 2:
        return None

    unique: list[np.ndarray] = []
    for point in points:
        if not any(np.linalg.norm(point - existing) < eps for existing in unique):
            unique.append(point)
    if len(unique) < 2:
        return None
    return unique[0], unique[1]


def collect_cross_section_points(
    geometry: Any,
    geometry_type: str,
    center: np.ndarray,
    normal: np.ndarray,
    thickness: float,
) -> np.ndarray:
    center = np.asarray(center, dtype=np.float64)
    normal = np.asarray(normal, dtype=np.float64)
    normal_unit = normal / np.linalg.norm(normal)
    eps = max(thickness * 0.5, 1e-9)
    segments: list[np.ndarray] = []

    if geometry_type == "triangle_mesh":
        vertices = np.asarray(geometry.vertices, dtype=np.float64)
        triangles = np.asarray(geometry.triangles, dtype=np.int64)
        for tri in triangles:
            v0, v1, v2 = vertices[int(tri[0])], vertices[int(tri[1])], vertices[int(tri[2])]
            segment = _triangle_plane_segment(v0, v1, v2, center, normal_unit, eps)
            if segment is not None:
                segments.extend(segment)

        if len(vertices):
            dist = np.abs((vertices - center) @ normal_unit)
            near = vertices[dist <= thickness]
            if len(near):
                segments.extend(near)
    else:
        points = np.asarray(geometry.points, dtype=np.float64)
        if len(points):
            dist = np.abs((points - center) @ normal_unit)
            near = points[dist <= thickness]
            segments.extend(near)

    if not segments:
        return np.empty((0, 3), dtype=np.float64)
    return np.asarray(segments, dtype=np.float64)


def rasterize_binary_cross_section(
    points_3d: np.ndarray,
    center: np.ndarray,
    normal: np.ndarray,
    width: int,
    height: int,
    margin_fraction: float = 0.08,
    point_radius: int = 2,
) -> np.ndarray:
    """Return HxW uint8 image: 0 = material (black), 255 = background (white)."""
    image = np.full((height, width), 255, dtype=np.uint8)
    if len(points_3d) == 0:
        return image

    points_2d = project_to_plane(points_3d, center, normal)
    min_u, min_v = points_2d.min(axis=0)
    max_u, max_v = points_2d.max(axis=0)
    span_u = max(max_u - min_u, 1e-9)
    span_v = max(max_v - min_v, 1e-9)
    pad_u = span_u * margin_fraction
    pad_v = span_v * margin_fraction
    min_u -= pad_u
    max_u += pad_u
    min_v -= pad_v
    max_v += pad_v

    xs = ((points_2d[:, 0] - min_u) / (max_u - min_u) * (width - 1)).astype(np.int32)
    ys = ((points_2d[:, 1] - min_v) / (max_v - min_v) * (height - 1)).astype(np.int32)

    for x, y in zip(xs, ys):
        for dy in range(-point_radius, point_radius + 1):
            for dx in range(-point_radius, point_radius + 1):
                if dx * dx + dy * dy > point_radius * point_radius:
                    continue
                yy, xx = y + dy, x + dx
                if 0 <= yy < height and 0 <= xx < width:
                    image[yy, xx] = 0
    return image


def write_binary_png(o3d: Any, image: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gray = np.ascontiguousarray(image.astype(np.uint8))
    o3d_image = o3d.geometry.Image(gray)
    if not o3d.io.write_image(str(path), o3d_image, quality=9):
        raise IOError(f"Failed to write cross-section PNG: {path}")


def export_cross_section(
    o3d: Any,
    geometry_info: Any,
    model_id: str,
    class_folder: str,
    output_root: Path,
    width: int,
    height: int,
    axis: str = "auto",
    overwrite: bool = False,
) -> dict[str, str]:
    plane = choose_cross_section_plane(
        geometry_info.bbox_min,
        geometry_info.bbox_max,
        geometry_info.center,
        axis=axis,
    )
    extents = geometry_info.bbox_max - geometry_info.bbox_min
    thickness = max(float(np.min(extents)) * 0.04, float(np.max(extents)) * 0.002, 1e-6)

    class_folder = class_folder or "unclassified"
    out_dir = output_root / "cross_sections" / class_folder / model_id
    file_name = f"{model_id}__cross_section_{plane.axis_label}.png"
    out_path = out_dir / file_name

    if out_path.exists() and not overwrite:
        return {
            "cross_section_file": file_name,
            "cross_section_relative_path": out_path.relative_to(output_root).as_posix(),
            "cross_section_absolute_path": str(out_path.resolve()),
            "cross_section_axis": plane.axis_label,
            "cross_section_status": "existing",
            "cross_section_plane_normal": " ".join(f"{v:.6g}" for v in plane.normal),
        }

    points_3d = collect_cross_section_points(
        geometry_info.geometry,
        geometry_info.geometry_type,
        plane.center,
        plane.normal,
        thickness,
    )
    image = rasterize_binary_cross_section(
        points_3d,
        plane.center,
        plane.normal,
        width=width,
        height=height,
    )
    write_binary_png(o3d, image, out_path)

    return {
        "cross_section_file": file_name,
        "cross_section_relative_path": out_path.relative_to(output_root).as_posix(),
        "cross_section_absolute_path": str(out_path.resolve()),
        "cross_section_axis": plane.axis_label,
        "cross_section_status": "rendered",
        "cross_section_plane_normal": " ".join(f"{v:.6g}" for v in plane.normal),
    }
