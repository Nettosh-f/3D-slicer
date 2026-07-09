# sherd_revolver.py
# pip install open3d numpy scipy scikit-learn
import sys
from pathlib import Path
import argparse
import numpy as np
import open3d as o3d
from sklearn.decomposition import PCA


def load_mesh(path: str) -> o3d.geometry.TriangleMesh:
    mesh = o3d.io.read_triangle_mesh(path)
    if mesh.is_empty():
        raise ValueError(f"Could not load mesh: {path}")
    mesh.compute_vertex_normals()
    return mesh


def clean_mesh(mesh: o3d.geometry.TriangleMesh, voxel_size=1.0):
    # Remove texture/colors visually by keeping geometry only
    mesh.vertex_colors = o3d.utility.Vector3dVector(
        np.ones((len(mesh.vertices), 3)) * 0.75
    )

    mesh.remove_duplicated_vertices()
    mesh.remove_duplicated_triangles()
    mesh.remove_degenerate_triangles()
    mesh.remove_non_manifold_edges()
    mesh.compute_vertex_normals()

    pcd = mesh.sample_points_poisson_disk(number_of_points=8000)
    pcd = pcd.voxel_down_sample(voxel_size=voxel_size)
    pcd, _ = pcd.remove_statistical_outlier(
        nb_neighbors=30,
        std_ratio=2.0
    )

    return pcd


def estimate_axis_from_pca(pcd):
    """
    Approximation:
    - PCA finds the main orientation of the sherd.
    - For rim/edge sherds, this is not perfect, but gives a stable starting axis.
    """
    pts = np.asarray(pcd.points)
    center = pts.mean(axis=0)

    pca = PCA(n_components=3)
    pca.fit(pts - center)

    # Usually the axis of rotation is close to the direction with least spread
    axis = pca.components_[2]
    axis = axis / np.linalg.norm(axis)

    return center, axis


def project_to_axis_coordinates(points, center, axis):
    """
    Converts 3D points into:
    z = height along axis
    r = distance from axis
    """
    rel = points - center
    z = rel @ axis
    closest = np.outer(z, axis)
    radial_vec = rel - closest
    r = np.linalg.norm(radial_vec, axis=1)
    return z, r


def extract_profile(z, r, bins=160, percentile=90):
    """
    Extracts an outer profile by taking high-radius points per height bin.
    This gives a rough vessel profile from the sherd surface.
    """
    order = np.argsort(z)
    z = z[order]
    r = r[order]

    z_bins = np.linspace(z.min(), z.max(), bins + 1)
    profile = []

    for i in range(bins):
        mask = (z >= z_bins[i]) & (z < z_bins[i + 1])
        if mask.sum() < 5:
            continue

        z_mid = 0.5 * (z_bins[i] + z_bins[i + 1])
        r_val = np.percentile(r[mask], percentile)
        profile.append((z_mid, r_val))

    profile = np.array(profile)

    if len(profile) < 10:
        raise ValueError("Could not extract enough profile points.")

    return profile


def revolve_profile(profile, center, axis, radial_reference, steps=180):
    """
    Revolves the 2D profile around the estimated axis.
    """
    z_vals = profile[:, 0]
    r_vals = profile[:, 1]

    axis = axis / np.linalg.norm(axis)

    # Create two perpendicular vectors to the rotation axis
    u = radial_reference - np.dot(radial_reference, axis) * axis
    if np.linalg.norm(u) < 1e-6:
        u = np.array([1.0, 0.0, 0.0])
        u = u - np.dot(u, axis) * axis

    u = u / np.linalg.norm(u)
    v = np.cross(axis, u)
    v = v / np.linalg.norm(v)

    vertices = []
    faces = []

    for i, (z, r) in enumerate(zip(z_vals, r_vals)):
        for j in range(steps):
            theta = 2 * np.pi * j / steps
            radial = np.cos(theta) * u + np.sin(theta) * v
            point = center + z * axis + r * radial
            vertices.append(point)

    for i in range(len(z_vals) - 1):
        for j in range(steps):
            a = i * steps + j
            b = i * steps + (j + 1) % steps
            c = (i + 1) * steps + j
            d = (i + 1) * steps + (j + 1) % steps

            faces.append([a, c, b])
            faces.append([b, c, d])

    revolved = o3d.geometry.TriangleMesh()
    revolved.vertices = o3d.utility.Vector3dVector(np.array(vertices))
    revolved.triangles = o3d.utility.Vector3iVector(np.array(faces))
    revolved.compute_vertex_normals()

    return revolved


def process(input_path, output_path, voxel_size=1.0, bins=160, steps=180):
    mesh = load_mesh(input_path)
    pcd = clean_mesh(mesh, voxel_size=voxel_size)

    center, axis = estimate_axis_from_pca(pcd)

    pts = np.asarray(pcd.points)
    z, r = project_to_axis_coordinates(pts, center, axis)
    profile = extract_profile(z, r, bins=bins)

    radial_reference = pts[np.argmax(r)] - center

    revolved = revolve_profile(
        profile=profile,
        center=center,
        axis=axis,
        radial_reference=radial_reference,
        steps=steps
    )

    o3d.io.write_triangle_mesh(output_path, revolved)

    axis_file = Path(output_path).with_suffix(".axis.txt")
    np.savetxt(axis_file, np.array([center, axis]), header="center\naxis")

    print(f"Saved revolved model: {output_path}")
    print(f"Saved estimated axis: {axis_file}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Input .ply sherd scan")
    parser.add_argument("output", help="Output revolved .ply model")
    parser.add_argument("--voxel", type=float, default=1.0)
    parser.add_argument("--bins", type=int, default=160)
    parser.add_argument("--steps", type=int, default=180)

    args = parser.parse_args()

    process(
        input_path=args.input,
        output_path=args.output,
        voxel_size=args.voxel,
        bins=args.bins,
        steps=args.steps
    )


if __name__ == "__main__":
    print(sys.executable)