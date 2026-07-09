#!/usr/bin/env python3
"""
Sherd profile pipeline (archaeology pottery fragments).

Steps:
  1. Segment the whole sherd (largest cluster, outlier removal).
  2. Separate fracture surfaces from finished ceramic surfaces (roughness + boundary cues).
  3. Estimate the vessel rotation axis (PCA — smallest spread direction).
  4. Extract an exterior profile (height vs radius) from finished outer surface only.

Dependencies:
  pip install open3d numpy scikit-learn

Example:
  python sherd_profile_pipeline.py models/HAD95_3579_1.ply output/sherd_analysis/HAD95_3579_1
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import numpy as np
import open3d as o3d
from sklearn.decomposition import PCA

SurfaceLabel = Literal["finished_exterior", "finished_interior", "fracture", "unknown"]


@dataclass
class AxisEstimate:
    center: np.ndarray
    axis: np.ndarray
    eigenvalues: np.ndarray

    def to_dict(self) -> dict:
        return {
            "center": self.center.tolist(),
            "axis": self.axis.tolist(),
            "eigenvalues": self.eigenvalues.tolist(),
        }


@dataclass
class PipelineResult:
    input_path: str
    output_dir: str
    point_count: int
    finished_exterior_count: int
    finished_interior_count: int
    fracture_count: int
    axis: AxisEstimate
    profile_points: int


def load_mesh(path: Path) -> o3d.geometry.TriangleMesh:
    mesh = o3d.io.read_triangle_mesh(str(path))
    if mesh.is_empty():
        raise ValueError(f"Could not load mesh: {path}")
    mesh.remove_duplicated_vertices()
    mesh.remove_duplicated_triangles()
    mesh.remove_degenerate_triangles()
    mesh.remove_non_manifold_edges()
    mesh.compute_vertex_normals()
    return mesh


def mesh_to_point_cloud(mesh: o3d.geometry.TriangleMesh, voxel_size: float) -> o3d.geometry.PointCloud:
    pcd = mesh.sample_points_poisson_disk(number_of_points=12000)
    if voxel_size > 0:
        pcd = pcd.voxel_down_sample(voxel_size)
    pcd, _ = pcd.remove_statistical_outlier(nb_neighbors=30, std_ratio=2.0)
    pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=voxel_size * 4, max_nn=30))
    pcd.orient_normals_consistent_tangent_plane(k=20)
    return pcd


def segment_whole_sherd(pcd: o3d.geometry.PointCloud, voxel_size: float) -> o3d.geometry.PointCloud:
    """Keep the largest spatial cluster — the sherd body without scan noise."""
    if len(pcd.points) == 0:
        raise ValueError("Point cloud is empty after preprocessing.")

    labels = np.array(pcd.cluster_dbscan(eps=max(voxel_size * 3.0, 1e-6), min_points=10))
    if labels.max() < 0:
        return pcd

    counts = np.bincount(labels[labels >= 0])
    largest_label = int(np.argmax(counts))
    indices = np.where(labels == largest_label)[0]
    return pcd.select_by_index(indices)


def boundary_vertex_mask(mesh: o3d.geometry.TriangleMesh) -> np.ndarray:
    """Vertices on open mesh edges — common at fracture breaks."""
    triangles = np.asarray(mesh.triangles)
    edge_count: dict[tuple[int, int], int] = {}
    for tri in triangles:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            key = (int(min(a, b)), int(max(a, b)))
            edge_count[key] = edge_count.get(key, 0) + 1

    boundary_vertices: set[int] = set()
    for (a, b), count in edge_count.items():
        if count == 1:
            boundary_vertices.add(a)
            boundary_vertices.add(b)

    mask = np.zeros(len(mesh.vertices), dtype=bool)
    for idx in boundary_vertices:
        mask[idx] = True
    return mask


def compute_roughness(mesh: o3d.geometry.TriangleMesh, k: int = 24) -> np.ndarray:
    """Per-vertex normal variation — fracture surfaces are rougher than wheel/finished surfaces."""
    vertices = np.asarray(mesh.vertices)
    normals = np.asarray(mesh.vertex_normals)
    if len(vertices) == 0:
        return np.array([])

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(vertices)
    tree = o3d.geometry.KDTreeFlann(pcd)

    roughness = np.zeros(len(vertices), dtype=np.float64)
    for i, point in enumerate(vertices):
        _, idx, _ = tree.search_knn_vector_3d(point, min(k, len(vertices)))
        neighbor_normals = normals[idx[1:] if len(idx) > 1 else idx]
        if len(neighbor_normals) == 0:
            roughness[i] = 0.0
            continue
        alignment = np.abs(neighbor_normals @ normals[i])
        roughness[i] = 1.0 - float(np.mean(alignment))
    return roughness


def label_points_by_surface(
    points: np.ndarray,
    normals: np.ndarray,
    center: np.ndarray,
    axis: np.ndarray,
    roughness: np.ndarray,
    boundary: np.ndarray,
    fracture_roughness_quantile: float = 0.72,
    boundary_weight: float = 0.35,
) -> np.ndarray:
    """
    Classify each point as finished_exterior, finished_interior, or fracture.

    Heuristic v1:
    - High roughness or open-boundary proximity → fracture
    - Otherwise use radial direction vs normal to split exterior / interior
    """
    n = len(points)
    labels = np.array(["unknown"] * n, dtype=object)

    axis_u = axis / np.linalg.norm(axis)
    rel = points - center
    z = rel @ axis_u
    radial_vec = rel - np.outer(z, axis_u)
    radial_dist = np.linalg.norm(radial_vec, axis=1)
    radial_dir = np.zeros_like(radial_vec)
    valid = radial_dist > 1e-9
    radial_dir[valid] = radial_vec[valid] / radial_dist[valid, None]

    rough_thresh = float(np.quantile(roughness, fracture_roughness_quantile))
    fracture_score = roughness.copy()
    fracture_score[boundary] += boundary_weight

    is_fracture = fracture_score >= rough_thresh
    labels[is_fracture] = "fracture"

    finished = ~is_fracture
    if np.any(finished):
        outward = np.einsum("ij,ij->i", normals[finished], radial_dir[finished])
        finished_idx = np.where(finished)[0]
        labels[finished_idx[outward >= 0.0]] = "finished_exterior"
        labels[finished_idx[outward < 0.0]] = "finished_interior"

    return labels


def transfer_vertex_labels_to_points(
    mesh: o3d.geometry.TriangleMesh,
    vertex_labels: np.ndarray,
    points: np.ndarray,
) -> np.ndarray:
    vertices = np.asarray(mesh.vertices)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(vertices)
    tree = o3d.geometry.KDTreeFlann(pcd)

    point_labels = np.array(["unknown"] * len(points), dtype=object)
    for i, point in enumerate(points):
        _, idx, _ = tree.search_knn_vector_3d(point, 1)
        point_labels[i] = vertex_labels[int(idx[0])]
    return point_labels


def estimate_vessel_axis(points: np.ndarray) -> AxisEstimate:
    """Vessel axis ≈ direction of least spread (PCA component with smallest eigenvalue)."""
    center = points.mean(axis=0)
    pca = PCA(n_components=3)
    pca.fit(points - center)
    axis = pca.components_[2]
    if axis[2] < 0:
        axis = -axis
    axis = axis / np.linalg.norm(axis)
    return AxisEstimate(center=center, axis=axis, eigenvalues=pca.explained_variance_)


def project_to_axis_coordinates(points: np.ndarray, center: np.ndarray, axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rel = points - center
    z = rel @ axis
    radial = rel - np.outer(z, axis)
    r = np.linalg.norm(radial, axis=1)
    return z, r


def extract_exterior_profile(
    points: np.ndarray,
    labels: np.ndarray,
    center: np.ndarray,
    axis: np.ndarray,
    bins: int = 160,
    percentile: float = 92.0,
) -> np.ndarray:
    """Outer radius profile from finished exterior points only."""
    mask = labels == "finished_exterior"
    if mask.sum() < 20:
        mask = labels != "fracture"
    if mask.sum() < 10:
        mask = np.ones(len(points), dtype=bool)

    z, r = project_to_axis_coordinates(points[mask], center, axis)
    order = np.argsort(z)
    z = z[order]
    r = r[order]

    z_bins = np.linspace(z.min(), z.max(), bins + 1)
    profile: list[tuple[float, float]] = []
    for i in range(bins):
        band = (z >= z_bins[i]) & (z < z_bins[i + 1])
        if band.sum() < 3:
            continue
        z_mid = 0.5 * (z_bins[i] + z_bins[i + 1])
        r_val = float(np.percentile(r[band], percentile))
        profile.append((z_mid, r_val))

    if len(profile) < 8:
        raise ValueError(f"Profile too sparse ({len(profile)} bins). Try a smaller --voxel size.")
    return np.asarray(profile, dtype=np.float64)


def color_mesh_by_label(mesh: o3d.geometry.TriangleMesh, vertex_labels: np.ndarray) -> o3d.geometry.TriangleMesh:
    palette = {
        "finished_exterior": [0.15, 0.55, 0.95],
        "finished_interior": [0.20, 0.75, 0.35],
        "fracture": [0.90, 0.25, 0.20],
        "unknown": [0.65, 0.65, 0.65],
    }
    colors = np.zeros((len(mesh.vertices), 3), dtype=np.float64)
    for i, label in enumerate(vertex_labels):
        colors[i] = palette.get(str(label), palette["unknown"])
    colored = o3d.geometry.TriangleMesh(mesh)
    colored.vertex_colors = o3d.utility.Vector3dVector(colors)
    return colored


def submesh_from_vertices(mesh: o3d.geometry.TriangleMesh, keep: np.ndarray) -> o3d.geometry.TriangleMesh:
    triangles = np.asarray(mesh.triangles)
    keep_set = set(int(i) for i in np.where(keep)[0])
    tri_mask = [all(int(v) in keep_set for v in tri) for tri in triangles]
    sub = o3d.geometry.TriangleMesh(mesh)
    sub.remove_triangles_by_mask(np.logical_not(tri_mask))
    sub.remove_unreferenced_vertices()
    sub.compute_vertex_normals()
    return sub


def save_profile_plot(profile: np.ndarray, path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return

    fig, ax = plt.subplots(figsize=(5, 7))
    ax.plot(profile[:, 1], profile[:, 0], "k-", linewidth=1.5)
    ax.set_xlabel("Radius")
    ax.set_ylabel("Height along vessel axis")
    ax.set_title("Sherd exterior profile")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def run_pipeline(
    input_path: Path,
    output_dir: Path,
    voxel_size: float = 1.0,
    bins: int = 160,
    profile_percentile: float = 92.0,
) -> PipelineResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    mesh = load_mesh(input_path)

    print("[1/4] Segmenting whole sherd…")
    pcd = mesh_to_point_cloud(mesh, voxel_size=voxel_size)
    pcd = segment_whole_sherd(pcd, voxel_size=voxel_size)
    points = np.asarray(pcd.points)
    normals = np.asarray(pcd.normals)
    print(f"      {len(points):,} points after sherd segmentation")

    print("[2/4] Estimating vessel axis (PCA)…")
    axis_est = estimate_vessel_axis(points)

    print("[3/4] Separating fracture vs finished surfaces…")
    roughness = compute_roughness(mesh)
    boundary = boundary_vertex_mask(mesh)
    vertex_labels = label_points_by_surface(
        points=np.asarray(mesh.vertices),
        normals=np.asarray(mesh.vertex_normals),
        center=axis_est.center,
        axis=axis_est.axis,
        roughness=roughness,
        boundary=boundary,
    )
    point_labels = transfer_vertex_labels_to_points(mesh, vertex_labels, points)

    n_ext = int(np.sum(point_labels == "finished_exterior"))
    n_int = int(np.sum(point_labels == "finished_interior"))
    n_frac = int(np.sum(point_labels == "fracture"))
    print(f"      exterior={n_ext:,}, interior={n_int:,}, fracture={n_frac:,}")

    print("[4/4] Extracting exterior profile…")
    profile = extract_exterior_profile(
        points=points,
        labels=point_labels,
        center=axis_est.center,
        axis=axis_est.axis,
        bins=bins,
        percentile=profile_percentile,
    )
    print(f"      {len(profile):,} profile samples")

    stem = input_path.stem
    colored_mesh = color_mesh_by_label(mesh, vertex_labels)
    o3d.io.write_triangle_mesh(str(output_dir / f"{stem}__labeled.ply"), colored_mesh)
    o3d.io.write_triangle_mesh(
        str(output_dir / f"{stem}__finished_exterior.ply"),
        submesh_from_vertices(mesh, vertex_labels == "finished_exterior"),
    )
    o3d.io.write_triangle_mesh(
        str(output_dir / f"{stem}__fracture.ply"),
        submesh_from_vertices(mesh, vertex_labels == "fracture"),
    )

    np.savetxt(output_dir / f"{stem}__profile.csv", profile, delimiter=",", header="height_along_axis,radius", comments="")
    np.savetxt(
        output_dir / f"{stem}__axis.txt",
        np.vstack((axis_est.center, axis_est.axis)),
        header="center_xyz\naxis_xyz",
    )

    profile_plot = output_dir / f"{stem}__profile.png"
    save_profile_plot(profile, profile_plot)

    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input": str(input_path.resolve()),
        "output_dir": str(output_dir.resolve()),
        "voxel_size": voxel_size,
        "bins": bins,
        "profile_percentile": profile_percentile,
        "point_count": len(points),
        "surface_counts": {
            "finished_exterior": n_ext,
            "finished_interior": n_int,
            "fracture": n_frac,
        },
        "axis": axis_est.to_dict(),
        "profile_points": len(profile),
        "artifacts": {
            "labeled_mesh": f"{stem}__labeled.ply",
            "finished_exterior_mesh": f"{stem}__finished_exterior.ply",
            "fracture_mesh": f"{stem}__fracture.ply",
            "profile_csv": f"{stem}__profile.csv",
            "profile_png": profile_plot.name if profile_plot.exists() else None,
            "axis_txt": f"{stem}__axis.txt",
        },
    }
    (output_dir / f"{stem}__report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    return PipelineResult(
        input_path=str(input_path),
        output_dir=str(output_dir),
        point_count=len(points),
        finished_exterior_count=n_ext,
        finished_interior_count=n_int,
        fracture_count=n_frac,
        axis=axis_est,
        profile_points=len(profile),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sherd segmentation, surface split, axis estimation, and profile extraction.")
    parser.add_argument("input", type=Path, help="Input sherd .ply mesh")
    parser.add_argument("output_dir", type=Path, help="Output directory for meshes, profile, and report")
    parser.add_argument("--voxel", type=float, default=1.0, help="Voxel size for downsampling (model units). Default: 1.0")
    parser.add_argument("--bins", type=int, default=160, help="Height bins for profile extraction. Default: 160")
    parser.add_argument(
        "--profile-percentile",
        type=float,
        default=92.0,
        help="Radius percentile within each height bin (outer wall). Default: 92",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = run_pipeline(
            input_path=args.input.expanduser().resolve(),
            output_dir=args.output_dir.expanduser().resolve(),
            voxel_size=args.voxel,
            bins=args.bins,
            profile_percentile=args.profile_percentile,
        )
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print("\nDone.")
    print(f"  Points:   {result.point_count:,}")
    print(f"  Profile:  {result.profile_points:,} samples")
    print(f"  Output:   {result.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
