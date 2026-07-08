from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Iterable

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
DEFAULT_OUTPUT = ROOT / "output" / "renderer"
RENDERER_SCRIPT = ROOT / "renderer" / "ply_spherical_renderer_windows.py"
LABELS_TEMPLATE = ROOT / "renderer" / "labels_template.csv"

PRESETS = {
    "Preview 20° / 162 views": (20, 20),
    "Medium 10° / 648 views": (10, 10),
    "Default 2° / 16,200 views": (2, 2),
    "Full 1° / 64,800 views": (1, 1),
    "Custom": (None, None),
}


def scan_model_files() -> list[str]:
    if not MODELS_DIR.exists():
        return []
    return sorted(
        [str(p.relative_to(MODELS_DIR)) for p in MODELS_DIR.rglob("*.ply")],
        key=str.casefold,
    )


def scan_model_folders() -> list[str]:
    if not MODELS_DIR.exists():
        return []
    folders: set[str] = set()
    for p in MODELS_DIR.rglob("*.ply"):
        rel_parent = p.parent.relative_to(MODELS_DIR)
        if str(rel_parent) not in {".", ""}:
            folders.add(str(rel_parent))
    return sorted(folders, key=str.casefold)


def parse_rgba(text: str) -> list[str]:
    cleaned = text.replace(",", " ").split()
    if len(cleaned) != 4:
        return []
    return cleaned


def resolve_input(input_mode: str, model_file: str, model_folder: str, raw_path: str) -> str:
    if input_mode == "Model file from models/":
        return str((MODELS_DIR / model_file).resolve())
    if input_mode == "Model folder from models/":
        return str((MODELS_DIR / model_folder).resolve())
    return str(Path(raw_path).expanduser().resolve())


def build_command(
    input_path: str,
    output_path: str,
    phi: int,
    theta: int,
    width: int,
    height: int,
    class_mode: str,
    manual_label: str,
    labels_csv: str,
    class_from_parent: bool,
    overwrite: bool,
    dry_run: bool,
    no_recursive: bool,
    fov: float,
    margin: float,
    point_size: float,
    renderer_backend: str,
    background_rgba: str,
    base_color_rgba: str,
    progress_every: int,
    hash_source: bool,
    headless_cpu: bool,
) -> list[str]:
    cmd = [
        sys.executable,
        str(RENDERER_SCRIPT),
        input_path,
        output_path,
        "-phi",
        str(phi),
        "-theta",
        str(theta),
        "--width",
        str(width),
        "--height",
        str(height),
        "--fov",
        str(fov),
        "--margin",
        str(margin),
        "--point-size",
        str(point_size),
        "--progress-every",
        str(progress_every),
        "--renderer-backend",
        renderer_backend,
    ]

    bg = parse_rgba(background_rgba)
    if bg:
        cmd += ["--background", *bg]

    base = parse_rgba(base_color_rgba)
    if base:
        cmd += ["--base-color", *base]

    if class_mode == "Manual label" and manual_label.strip():
        cmd += ["--classification", manual_label.strip()]
    elif class_mode == "From parent folder" or class_from_parent:
        cmd += ["--class-from-parent"]
    elif class_mode == "Labels CSV" and labels_csv.strip():
        cmd += ["--labels-csv", labels_csv.strip()]

    if overwrite:
        cmd.append("--overwrite")
    if dry_run:
        cmd.append("--dry-run")
    if no_recursive:
        cmd.append("--no-recursive")
    if hash_source:
        cmd.append("--hash-source")
    if headless_cpu:
        cmd.append("--headless-cpu")

    return cmd


def render_help_text() -> str:
    try:
        out = subprocess.run(
            [sys.executable, str(RENDERER_SCRIPT), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        return out.stdout or out.stderr or "No help text returned."
    except Exception as exc:
        return f"Failed to load renderer help: {type(exc).__name__}: {exc}"


def workflow_text() -> str:
    return (
        "Shared venv workflow\n"
        "--------------------\n"
        "1. Run setup_renderer_env.bat once from the repo root.\n"
        "2. Put .ply files under models/.\n"
        "3. Use this Streamlit renderer GUI or render_model.bat.\n"
        "4. Renderer outputs now go to output/renderer by default.\n"
        "5. Segmenter outputs go to output/segmenter.\n\n"
        "Comfortable CLI examples\n"
        "------------------------\n"
        'render_model.bat "HAD16_279_2916 FIGURINE.ply" output\\renderer -phi 20 -theta 20 --classification figurine\n'
        'python "segmentation tool\\run_segmenter.py" "output\\renderer\\images\\figurine\\HAD16_279_2916_FIGURINE" output\\segmenter --artifact-class figurine\n'
    )


def preview_command(cmd: list[str]) -> str:
    return subprocess.list2cmdline(cmd)


def main() -> None:
    st.set_page_config(page_title="PLY Renderer GUI", layout="wide")
    st.title("PLY Spherical Renderer")
    st.caption("Streamlit GUI for the 3D-slicer renderer: choose a model or folder, configure render settings, preview the exact command, and run the renderer.")

    if not RENDERER_SCRIPT.exists():
        st.error(f"Renderer script not found: {RENDERER_SCRIPT}")
        return

    files = scan_model_files()
    folders = scan_model_folders()

    with st.sidebar:
        st.header("Input")
        input_mode = st.radio(
            "Input source",
            ["Model file from models/", "Model folder from models/", "Direct file or folder path"],
            index=0,
        )
        if st.button("Refresh models list", use_container_width=True):
            st.rerun()

        model_file = st.selectbox("Model file", files, index=0 if files else None, disabled=not files or input_mode != "Model file from models/")
        model_folder = st.selectbox("Model folder", folders, index=0 if folders else None, disabled=not folders or input_mode != "Model folder from models/")
        raw_path = st.text_input("Direct path", value="", disabled=input_mode != "Direct file or folder path")

        st.header("Output")
        output_dir = st.text_input("Output folder", value=str(DEFAULT_OUTPUT))
        st.caption("Default renderer output folder: output/renderer")

        st.header("View density")
        preset = st.selectbox("Preset", list(PRESETS), index=0)
        default_phi, default_theta = PRESETS[preset]
        phi = st.number_input("Phi step (azimuth degrees)", min_value=1, max_value=180, value=default_phi or 2, step=1)
        theta = st.number_input("Theta step (polar degrees)", min_value=1, max_value=180, value=default_theta or 2, step=1)

        st.header("Classification")
        class_mode = st.radio("Classification mode", ["Unclassified", "Manual label", "From parent folder", "Labels CSV"], index=0)
        manual_label = st.text_input("Manual label", value="")
        if manual_label.strip() and class_mode != "Manual label":
            st.caption("Manual label is filled. Use classification mode = Manual label to apply it.")
        labels_csv_default = str(LABELS_TEMPLATE) if LABELS_TEMPLATE.exists() else ""
        labels_csv = st.text_input("Labels CSV", value=labels_csv_default, disabled=class_mode != "Labels CSV")

        st.header("Outputs")
        overwrite = st.checkbox("Overwrite existing PNGs", value=False)
        dry_run = st.checkbox("Dry run only", value=False)
        no_recursive = st.checkbox("No recursive folder search", value=False)

        with st.expander("Advanced settings", expanded=False):
            width = st.number_input("PNG width", min_value=64, max_value=4096, value=512, step=64)
            height = st.number_input("PNG height", min_value=64, max_value=4096, value=512, step=64)
            fov = st.number_input("Field of view (degrees)", min_value=1.0, max_value=179.0, value=35.0, step=1.0)
            margin = st.number_input("Auto-fit margin", min_value=0.0, max_value=10.0, value=1.05, step=0.01, format="%.2f")
            point_size = st.number_input("Point size", min_value=0.1, max_value=50.0, value=3.0, step=0.1)
            renderer_backend = st.selectbox("Renderer backend", ["auto", "visualizer", "offscreen"], index=0)
            progress_every = st.number_input("Progress log every N renders", min_value=1, max_value=100000, value=50, step=1)
            background_rgba = st.text_input("Background RGBA", value="255 255 255 255", help="Four integers separated by spaces or commas.")
            base_color_rgba = st.text_input("Base model color RGBA", value="180 180 180 255", help="Four integers separated by spaces or commas.")
            hash_source = st.checkbox("Hash source file path into output metadata", value=False)
            headless_cpu = st.checkbox("Linux headless CPU mode", value=False, help="Normally leave this off on Windows.")
            class_from_parent = st.checkbox("Force class from parent folder", value=False)

    # Safe defaults if lists are empty
    model_file = model_file if files else ""
    model_folder = model_folder if folders else ""
    width = int(width)
    height = int(height)
    phi = int(phi)
    theta = int(theta)
    progress_every = int(progress_every)

    input_path = ""
    input_error = None
    try:
        if input_mode == "Model file from models/" and not model_file:
            input_error = "No .ply files were found under models/."
        elif input_mode == "Model folder from models/" and not model_folder:
            input_error = "No model folders containing .ply files were found under models/."
        elif input_mode == "Direct file or folder path" and not raw_path.strip():
            input_error = "Enter a direct file or folder path."
        else:
            input_path = resolve_input(input_mode, model_file, model_folder, raw_path)
    except Exception as exc:
        input_error = f"Could not resolve input: {type(exc).__name__}: {exc}"

    if input_error:
        st.warning(input_error)

    col_left, col_right = st.columns([1.2, 1])

    with col_left:
        st.subheader("Run renderer")
        if input_path:
            st.write(f"**Resolved input:** `{input_path}`")
        st.write(f"**Resolved output:** `{Path(output_dir).expanduser()}`")
        view_count = (360 // max(phi, 1)) * (180 // max(theta, 1))
        st.info(f"Estimated view count: approximately **{view_count:,}** images.")

        cmd: list[str] | None = None
        if not input_error and input_path:
            cmd = build_command(
                input_path=input_path,
                output_path=str(Path(output_dir).expanduser()),
                phi=phi,
                theta=theta,
                width=width,
                height=height,
                class_mode=class_mode,
                manual_label=manual_label,
                labels_csv=labels_csv,
                class_from_parent=class_from_parent,
                overwrite=overwrite,
                dry_run=dry_run,
                no_recursive=no_recursive,
                fov=float(fov),
                margin=float(margin),
                point_size=float(point_size),
                renderer_backend=renderer_backend,
                background_rgba=background_rgba,
                base_color_rgba=base_color_rgba,
                progress_every=progress_every,
                hash_source=hash_source,
                headless_cpu=headless_cpu,
            )
            st.text_area("Exact renderer command", preview_command(cmd), height=120)

        run_clicked = st.button("Run renderer", type="primary", disabled=cmd is None)
        if run_clicked and cmd is not None:
            st.subheader("Renderer log")
            log_placeholder = st.empty()
            status_placeholder = st.empty()
            lines: list[str] = []
            try:
                process = subprocess.Popen(
                    cmd,
                    cwd=ROOT,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                assert process.stdout is not None
                for line in process.stdout:
                    lines.append(line.rstrip())
                    log_placeholder.code("\n".join(lines[-500:]), language="text")
                exit_code = process.wait()
                if exit_code == 0:
                    status_placeholder.success("Renderer finished successfully.")
                else:
                    status_placeholder.error(f"Renderer exited with code {exit_code}.")
            except Exception as exc:
                status_placeholder.error(f"Failed to start renderer: {type(exc).__name__}: {exc}")

    with col_right:
        st.subheader("Help")
        with st.expander("Renderer --help", expanded=False):
            st.code(render_help_text(), language="text")
        with st.expander("Project workflow", expanded=False):
            st.code(workflow_text(), language="text")
        with st.expander("Important settings", expanded=True):
            st.markdown(
                """
- **Phi step / Theta step**: smaller values create more images.
- **Manual label**: use with **Classification mode = Manual label** to write `--classification`.
- **From parent folder**: useful when `models/figurine/...` or `models/pottery/...` determines the class.
- **Labels CSV**: lets you map file names to class labels.
- **Renderer backend**: `auto` is recommended. On Windows, `visualizer` is often safer than `offscreen`.
- **Dry run**: preview what will be rendered without generating PNGs.
- **Linux headless CPU mode**: leave off on Windows.
                """
            )


if __name__ == "__main__":
    main()
