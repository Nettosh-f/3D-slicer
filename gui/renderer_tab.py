from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import streamlit as st

from gui.paths import LABELS_TEMPLATE, MODELS_DIR, RENDERER_OUTPUT, RENDERER_SCRIPT, ROOT

PRESETS = {
    "Preview 20° / 162 views": (20, 20),
    "Medium 10° / 648 views": (10, 10),
    "Default 2° / 16,200 views": (2, 2),
    "Full 1° / 64,800 views": (1, 1),
    "Custom": (2, 2),
}

CLASSIFICATION_MODES = ["Unclassified", "Manual label", "From parent folder", "Labels CSV"]


def _init_renderer_state() -> None:
    default_preset = "Preview 20° / 162 views"
    default_phi, default_theta = PRESETS[default_preset]
    st.session_state.setdefault("renderer_preset", default_preset)
    st.session_state.setdefault("renderer_phi", default_phi)
    st.session_state.setdefault("renderer_theta", default_theta)
    st.session_state.setdefault("renderer_classification_mode", "Unclassified")
    st.session_state.setdefault("renderer_manual_label", "")


def _resolve_sampling_values() -> tuple[str, int, int, bool]:
    preset = st.session_state.renderer_preset
    custom = preset == "Custom"
    if custom:
        return preset, int(st.session_state.renderer_phi), int(st.session_state.renderer_theta), True

    phi, theta = PRESETS[preset]
    phi = int(phi)
    theta = int(theta)
    st.session_state.renderer_phi = phi
    st.session_state.renderer_theta = theta
    return preset, phi, theta, False


def _on_manual_label_change() -> None:
    if str(st.session_state.get("renderer_manual_label", "")).strip():
        st.session_state.renderer_classification_mode = "Manual label"


def _effective_classification(manual_label: str) -> str:
    if manual_label.strip():
        return "Manual label"
    return str(st.session_state.get("renderer_classification_mode", "Unclassified"))


def scan_model_files() -> list[str]:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted([str(path.relative_to(MODELS_DIR)) for path in MODELS_DIR.rglob("*.ply")], key=str.casefold)


def scan_model_folders() -> list[str]:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    folders: set[str] = set()
    for path in MODELS_DIR.rglob("*.ply"):
        if path.parent != MODELS_DIR:
            folders.add(str(path.parent.relative_to(MODELS_DIR)))
    return sorted(folders, key=str.casefold)


def parse_rgba(text: str) -> list[str]:
    parts = text.replace(",", " ").split()
    if len(parts) != 4:
        return []
    return parts


def resolve_input(input_mode: str, model_file: str, model_folder: str, direct_path: str) -> Path:
    if input_mode == "Model file from models/":
        return (MODELS_DIR / model_file).resolve()
    if input_mode == "Model folder from models/":
        return (MODELS_DIR / model_folder).resolve()
    return Path(direct_path).expanduser().resolve()


def build_command(
    input_path: Path,
    output_path: Path,
    phi: int,
    theta: int,
    width: int,
    height: int,
    classification_mode: str,
    manual_label: str,
    labels_csv: str,
    overwrite: bool,
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
        "-u",
        str(RENDERER_SCRIPT),
        str(input_path),
        str(output_path),
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

    if manual_label.strip():
        cmd += ["--classification", manual_label.strip()]
    elif classification_mode == "From parent folder":
        cmd += ["--class-from-parent"]
    elif classification_mode == "Labels CSV" and labels_csv.strip():
        cmd += ["--labels-csv", labels_csv.strip()]

    if overwrite:
        cmd.append("--overwrite")
    if no_recursive:
        cmd.append("--no-recursive")
    if hash_source:
        cmd.append("--hash-source")
    if headless_cpu:
        cmd.append("--headless-cpu")

    return cmd


def renderer_help() -> str:
    try:
        completed = subprocess.run(
            [sys.executable, str(RENDERER_SCRIPT), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        return completed.stdout or completed.stderr or "No help text returned."
    except Exception as exc:
        return f"Could not load renderer help: {type(exc).__name__}: {exc}"


def _parse_render_summary(lines: list[str]) -> dict[str, str | int | None]:
    text = "\n".join(lines)
    summary: dict[str, str | int | None] = {
        "new_pngs": None,
        "reused_pngs": None,
        "failed_models": None,
        "output_dir": None,
    }
    for key, pattern in (
        ("new_pngs", r"New PNGs rendered:\s*(\d+)"),
        ("reused_pngs", r"Existing PNGs reused:\s*(\d+)"),
        ("failed_models", r"Failed models:\s*(\d+)"),
        ("output_dir", r"Output directory:\s*(.+)"),
    ):
        match = re.search(pattern, text)
        if match:
            summary[key] = int(match.group(1)) if key != "output_dir" else match.group(1).strip()
    return summary


def _run_renderer_subprocess(cmd: list[str]) -> tuple[int, list[str]]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(
        cmd,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    lines: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        lines.append(line.rstrip())
    return process.wait(), lines


def render() -> None:
    st.subheader("Settings")

    if not RENDERER_SCRIPT.exists():
        st.error(f"Renderer script not found: {RENDERER_SCRIPT}")
        return

    files = scan_model_files()
    folders = scan_model_folders()

    col_settings, col_body = st.columns([1, 2.4])

    with col_settings:
        st.header("Input")
        input_mode = st.radio(
            "Input source",
            ["Model file from models/", "Model folder from models/", "Direct file or folder path"],
            index=0,
            key="renderer_input_mode",
        )

        if st.button("Refresh model list", use_container_width=True, key="renderer_refresh_models"):
            st.rerun()

        model_file = ""
        model_folder = ""
        direct_path = ""

        if input_mode == "Model file from models/":
            if files:
                model_file = st.selectbox("PLY file", files, key="renderer_model_file")
            else:
                st.warning("No .ply files found in models/.")
        elif input_mode == "Model folder from models/":
            if folders:
                model_folder = st.selectbox("PLY folder", folders, key="renderer_model_folder")
            else:
                st.warning("No subfolders containing .ply files found in models/.")
        else:
            direct_path = st.text_input("Direct path", value="", key="renderer_direct_path")

        st.header("Output")
        output_dir = st.text_input("Output folder", value=str(RENDERER_OUTPUT), key="renderer_output_dir")

        st.header("Camera sampling")
        _init_renderer_state()

        preset = st.selectbox("Preset", list(PRESETS), key="renderer_preset")
        _, preset_phi, preset_theta, custom_sampling = _resolve_sampling_values()

        if custom_sampling:
            phi = st.number_input(
                "Phi step / azimuth gap",
                min_value=1,
                max_value=360,
                step=1,
                key="renderer_phi",
            )
            theta = st.number_input(
                "Theta step / polar gap",
                min_value=1,
                max_value=180,
                step=1,
                key="renderer_theta",
            )
        else:
            phi_col, theta_col = st.columns(2)
            phi_col.metric("Phi step / azimuth gap", preset_phi)
            theta_col.metric("Theta step / polar gap", preset_theta)
            phi, theta = preset_phi, preset_theta
            st.caption("Choose **Custom** in Preset to edit phi/theta manually.")

        st.header("Classification")
        manual_label = st.text_input(
            "Manual label",
            help="Type a classification (e.g. figurine). Switches mode to Manual label and passes --classification.",
            key="renderer_manual_label",
            on_change=_on_manual_label_change,
        )
        manual_label_active = bool(manual_label.strip())
        if manual_label_active:
            st.session_state.renderer_classification_mode = "Manual label"

        st.radio(
            "Classification mode",
            CLASSIFICATION_MODES,
            key="renderer_classification_mode",
            disabled=manual_label_active,
        )
        classification_mode = _effective_classification(manual_label)
        if manual_label_active:
            st.caption(f"Manual label active — `--classification {manual_label.strip()}` will be passed.")
        labels_csv = st.text_input(
            "Labels CSV",
            value=str(LABELS_TEMPLATE) if LABELS_TEMPLATE.exists() else "",
            disabled=classification_mode != "Labels CSV" or manual_label_active,
            key="renderer_labels_csv",
        )

        phi = int(phi)
        theta = int(theta)

        st.header("Run options")
        overwrite = st.checkbox("Overwrite existing PNGs", value=False, key="renderer_overwrite")
        no_recursive = st.checkbox("No recursive folder search", value=False, key="renderer_no_recursive")

        with st.expander("Renderer advanced settings", expanded=False):
            width = st.number_input("PNG width", min_value=64, max_value=4096, value=512, step=64, key="renderer_width")
            height = st.number_input(
                "PNG height", min_value=64, max_value=4096, value=512, step=64, key="renderer_height"
            )
            fov = st.number_input("Vertical FOV", min_value=1.0, max_value=178.0, value=45.0, step=1.0, key="renderer_fov")
            margin = st.number_input(
                "Camera margin", min_value=1.0, max_value=5.0, value=1.08, step=0.01, key="renderer_margin"
            )
            point_size = st.number_input(
                "Point size", min_value=0.1, max_value=50.0, value=3.0, step=0.1, key="renderer_point_size"
            )
            backend_options = ["auto", "visualizer", "offscreen"]
            backend_default = 1 if sys.platform.startswith("win") else 0
            renderer_backend = st.selectbox(
                "Renderer backend",
                backend_options,
                index=backend_default,
                key="renderer_backend",
                help="On Windows use auto or visualizer. Offscreen/EGL is Linux-only in this project.",
            )
            if sys.platform.startswith("win") and renderer_backend == "offscreen":
                st.error("Offscreen backend does not work on Windows. Use visualizer or auto.")
            progress_every = st.number_input(
                "Progress every N images",
                min_value=1,
                max_value=100000,
                value=500,
                step=1,
                key="renderer_progress_every",
            )
            background_rgba = st.text_input("Background RGBA", value="1 1 1 1", key="renderer_bg_rgba")
            base_color_rgba = st.text_input("Base color RGBA", value="0.72 0.72 0.72 1", key="renderer_base_rgba")
            hash_source = st.checkbox("Hash source PLY", value=False, key="renderer_hash_source")
            headless_cpu = st.checkbox("Linux headless CPU mode", value=False, key="renderer_headless_cpu")

    input_path: Path | None = None
    input_error = None
    try:
        if input_mode == "Model file from models/":
            if not model_file:
                input_error = "Choose a PLY file or put one inside models/."
            else:
                input_path = resolve_input(input_mode, model_file, model_folder, direct_path)
        elif input_mode == "Model folder from models/":
            if not model_folder:
                input_error = "Choose a model folder or create one under models/."
            else:
                input_path = resolve_input(input_mode, model_file, model_folder, direct_path)
        else:
            if not direct_path.strip():
                input_error = "Enter a direct file or folder path."
            else:
                input_path = resolve_input(input_mode, model_file, model_folder, direct_path)
    except Exception as exc:
        input_error = f"Could not resolve input: {type(exc).__name__}: {exc}"

    output_path = Path(output_dir).expanduser()
    if not output_path.is_absolute():
        output_path = ROOT / output_path

    with col_body:
        col_main, col_help = st.columns([1.25, 1])

        with col_main:
            st.markdown("**Renderer command**")
            cmd: list[str] | None = None
            if input_error:
                st.warning(input_error)
            elif input_path is None:
                st.warning("No input selected.")
            else:
                st.write(f"**Input:** `{input_path}`")
                st.write(f"**Output:** `{output_path}`")
                estimated_views = len(range(0, 360, int(phi))) * len(range(0, 180, int(theta)))
                st.write(f"**Estimated views per model:** `{estimated_views:,}`")

                cmd = build_command(
                    input_path=input_path,
                    output_path=output_path,
                    phi=int(phi),
                    theta=int(theta),
                    width=int(width),
                    height=int(height),
                    classification_mode=classification_mode,
                    manual_label=manual_label,
                    labels_csv=labels_csv,
                    overwrite=overwrite,
                    no_recursive=no_recursive,
                    fov=float(fov),
                    margin=float(margin),
                    point_size=float(point_size),
                    renderer_backend=renderer_backend,
                    background_rgba=background_rgba,
                    base_color_rgba=base_color_rgba,
                    progress_every=int(progress_every),
                    hash_source=hash_source,
                    headless_cpu=headless_cpu,
                )
                st.text_area("Exact command", subprocess.list2cmdline(cmd), height=120, key="renderer_cmd_preview")

            run_disabled = cmd is None or (sys.platform.startswith("win") and renderer_backend == "offscreen")
            run = st.button("Run renderer", type="primary", disabled=run_disabled, key="renderer_run")

            if run and cmd is not None:
                if sys.platform.startswith("win") and renderer_backend == "offscreen":
                    st.error("Cannot run offscreen backend on Windows. Switch to visualizer or auto.")
                else:
                    st.markdown("**Renderer log**")
                    log_box = st.empty()
                    status_box = st.empty()
                    log_box.info("Running renderer… this can take a while for large view counts.")

                    try:
                        code, lines = _run_renderer_subprocess(cmd)
                        summary = _parse_render_summary(lines)
                        log_box.code("\n".join(lines[-600:]) if lines else "(no output captured)", language="text")

                        st.session_state["renderer_last_log"] = lines
                        st.session_state["renderer_last_summary"] = summary
                        st.session_state["renderer_last_code"] = code

                        if code != 0:
                            status_box.error(f"Renderer exited with code {code}. See log above.")
                        elif summary.get("new_pngs", 0) == 0 and summary.get("reused_pngs", 0) == 0:
                            status_box.warning(
                                "Renderer finished but wrote 0 PNGs. Check failed models in the log, "
                                "or enable **Overwrite existing PNGs** if files already exist."
                            )
                        else:
                            out = summary.get("output_dir") or str(output_path)
                            new_count = summary.get("new_pngs", "?")
                            reused_count = summary.get("reused_pngs", 0)
                            status_box.success(
                                f"Rendered **{new_count}** new PNG(s)"
                                + (f", reused **{reused_count}** existing" if reused_count else "")
                                + f". Output: `{out}`"
                            )
                    except Exception as exc:
                        status_box.error(f"Could not run renderer: {type(exc).__name__}: {exc}")

            elif st.session_state.get("renderer_last_log"):
                st.markdown("**Last renderer log**")
                st.code("\n".join(st.session_state["renderer_last_log"][-600:]), language="text")
                last_summary = st.session_state.get("renderer_last_summary") or {}
                last_code = st.session_state.get("renderer_last_code")
                if last_code == 0:
                    st.caption(
                        f"Last run: {last_summary.get('new_pngs', '?')} new PNG(s), "
                        f"{last_summary.get('reused_pngs', 0)} reused."
                    )

        with col_help:
            st.markdown("**Renderer help**")
            with st.expander("Renderer --help", expanded=False):
                st.code(renderer_help(), language="text")

            with st.expander("Renderer CLI example", expanded=False):
                st.code(
                    'render_model.bat "HAD16_279_2916 FIGURINE.ply" output\\renderer '
                    "-phi 20 -theta 20 --classification figurine",
                    language="bat",
                )
