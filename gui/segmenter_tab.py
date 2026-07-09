from __future__ import annotations

import io
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import streamlit as st

from gui.paths import RENDERER_IMAGES, SEGMENTER_OUTPUT, TAXONOMY_CONFIG, ensure_segmenter_import_path

ensure_segmenter_import_path()

from segmenter.pipeline import PipelineOptions, run_artifact_segmentation
from segmenter.taxonomy import Taxonomy
from segmenter.utils import IMAGE_EXTENSIONS, list_images


def scan_renderer_artifacts() -> dict[str, list[str]]:
    """Map classification folder -> sorted model_id folders under output/renderer/images."""
    if not RENDERER_IMAGES.exists():
        return {}
    result: dict[str, list[str]] = {}
    for class_dir in sorted(RENDERER_IMAGES.iterdir(), key=lambda p: p.name.casefold()):
        if not class_dir.is_dir():
            continue
        models = sorted(
            [d.name for d in class_dir.iterdir() if d.is_dir() and list_images(d)],
            key=str.casefold,
        )
        if models:
            result[class_dir.name] = models
    return result


def resolve_renderer_output_folder(classification: str, model_id: str) -> Path:
    return (RENDERER_IMAGES / classification / model_id).resolve()


def zip_folder(folder: Path) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as zf:
        for path in folder.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(folder))
    buffer.seek(0)
    return buffer.read()


def preview_grid(images: list[Path], limit: int = 48) -> None:
    if not images:
        st.info("No images loaded yet.")
        return
    cols = st.columns(6)
    for idx, img_path in enumerate(images[:limit]):
        with cols[idx % 6]:
            st.image(str(img_path), caption=img_path.name, use_container_width=True)
    if len(images) > limit:
        st.caption(f"Showing first {limit} of {len(images)} images.")


def render() -> None:
    st.subheader("Archaeological Part Segmenter")
    st.caption("Multi-angle renderer images → part masks, crops, overlays, and ML-friendly JSON.")

    if not TAXONOMY_CONFIG.exists():
        st.error(f"Taxonomy config not found: {TAXONOMY_CONFIG}")
        return

    taxonomy = Taxonomy(TAXONOMY_CONFIG)
    renderer_artifacts = scan_renderer_artifacts()

    col_settings, col_body = st.columns([1, 2.4])
    picked_model = ""

    with col_settings:
        st.header("Input")
        input_mode = st.radio(
            "Input mode",
            ["From renderer output", "Folder path", "Upload files"],
            horizontal=False,
            key="segmenter_input_mode",
        )
        artifact_id = st.text_input("Artifact ID", value="", key="segmenter_artifact_id")
        image_folder: Path | None = None

        if input_mode == "From renderer output":
            if renderer_artifacts:
                classes = list(renderer_artifacts.keys())
                default_class_idx = classes.index("figurine") if "figurine" in classes else 0
                picked_class = st.selectbox(
                    "Renderer classification",
                    classes,
                    index=default_class_idx,
                    key="segmenter_renderer_class",
                )
                models = renderer_artifacts[picked_class]
                picked_model = st.selectbox("Rendered model folder", models, key="segmenter_renderer_model")
                image_folder = resolve_renderer_output_folder(picked_class, picked_model)
                st.caption(f"Using `{image_folder}`")
                if st.button("Refresh renderer outputs", use_container_width=True, key="segmenter_refresh_renderer"):
                    st.rerun()
            else:
                st.warning("No renderer outputs found under output/renderer/images/. Run the Renderer tab first.")

        elif input_mode == "Folder path":
            folder_text = st.text_input("Image folder path", value="", key="segmenter_folder_path")
            if folder_text.strip():
                image_folder = Path(folder_text).expanduser().resolve()
        else:
            uploaded = st.file_uploader(
                "Upload one artifact's render images",
                type=[e.lstrip(".") for e in sorted(IMAGE_EXTENSIONS)],
                accept_multiple_files=True,
                key="segmenter_upload",
            )
            if uploaded:
                temp_dir = tempfile.TemporaryDirectory()
                image_folder = Path(temp_dir.name)
                st.session_state["_segmenter_temp_dir"] = temp_dir
                for file in uploaded:
                    (image_folder / file.name).write_bytes(file.getbuffer())

        output_dir = Path(
            st.text_input("Output directory", value=str(SEGMENTER_OUTPUT), key="segmenter_output_dir")
        ).expanduser()

        st.header("Class & parts")
        classes = taxonomy.class_names
        default_idx = classes.index("pottery") if "pottery" in classes else 0
        artifact_class = st.selectbox("Artifact class", classes, index=default_idx, key="segmenter_artifact_class")
        class_spec = taxonomy.get(artifact_class)
        possible_parts = [p.name for p in class_spec.parts]
        primary_parts = [p.name for p in class_spec.parts if getattr(p, "primary_fallback", False)]

        part_mode = st.radio(
            "Part presence mode",
            [
                "Conservative default",
                "I know which parts are visible",
                "Force all taxonomy parts",
            ],
            index=0,
            help=(
                "Taxonomy parts are possible labels, not mandatory labels. "
                "For fragments, choose only the parts you believe are visible."
            ),
            key="segmenter_part_mode",
        )

        selected_parts: list[str] = []
        force_all_taxonomy_parts = False
        if part_mode == "Conservative default":
            st.caption(
                "Exports only primary fallback part(s): "
                f"{', '.join(primary_parts) if primary_parts else 'none'}."
            )
        elif part_mode == "I know which parts are visible":
            selected_parts = st.multiselect(
                "Select visible parts to export",
                options=possible_parts,
                default=primary_parts[:1],
                key="segmenter_selected_parts",
            )
        else:
            force_all_taxonomy_parts = True
            st.warning("Force-all can produce false labels on fragments. Use for debugging only.")

        st.header("Outputs")
        generate_annotated = st.checkbox("Annotated images", value=True, key="segmenter_gen_annotated")
        generate_crops = st.checkbox("Per-part crops", value=True, key="segmenter_gen_crops")
        generate_json = st.checkbox("JSON export", value=True, key="segmenter_gen_json")
        generate_clean = st.checkbox("Clean presentation images", value=True, key="segmenter_gen_clean")

        with st.expander("Segmenter advanced options", expanded=False):
            engine = st.selectbox(
                "Segmentation engine",
                ["geometric", "sam2_placeholder", "vlm_assisted_placeholder"],
                help="v0.2 runs geometric segmentation out of the box.",
                key="segmenter_engine",
            )
            confidence_threshold = st.slider(
                "Confidence threshold", 0.0, 1.0, 0.35, 0.01, key="segmenter_confidence"
            )
            low_confidence_threshold = st.slider(
                "Low-confidence flag threshold", 0.0, 1.0, 0.55, 0.01, key="segmenter_low_confidence"
            )
            mask_granularity = st.slider(
                "Mask granularity / points per side", 8, 128, 32, 8, key="segmenter_mask_granularity"
            )
            crop_size = st.selectbox(
                "Per-part crop target resolution", [224, 384, 512], index=0, key="segmenter_crop_size"
            )
            max_images = st.number_input(
                "Max images for test run, 0 = all", min_value=0, value=0, step=1, key="segmenter_max_images"
            )

        run_button = st.button("Run segmentation", type="primary", use_container_width=True, key="segmenter_run")

    resolved_artifact_id = artifact_id.strip() or picked_model.strip() or None

    with col_body:
        col_a, col_b = st.columns([1.15, 1])

        with col_a:
            st.markdown("**Input thumbnail grid**")
            images: list[Path] = []
            if image_folder and image_folder.exists():
                images = list_images(image_folder)
                st.write(f"Loaded **{len(images)}** image(s).")
                preview_grid(images)
            elif image_folder:
                st.warning(f"Folder does not exist: {image_folder}")
            else:
                st.info("Choose renderer output, a folder path, or upload files.")

        with col_b:
            st.markdown("**Console / log**")
            log_box = st.empty()
            result_box = st.empty()

        if run_button:
            if not image_folder or not image_folder.exists():
                st.error("Please choose a valid input folder or upload images.")
                return

            if part_mode == "I know which parts are visible" and not selected_parts:
                st.error("Select at least one visible part, or switch back to Conservative default.")
                return

            logs: list[str] = []

            def log(msg: str) -> None:
                logs.append(msg)
                log_box.code("\n".join(logs[-250:]), language="text")

            try:
                opts = PipelineOptions(
                    image_folder=image_folder,
                    output_dir=output_dir,
                    artifact_class=artifact_class,
                    artifact_id=resolved_artifact_id,
                    taxonomy_path=TAXONOMY_CONFIG,
                    engine=engine,
                    confidence_threshold=confidence_threshold,
                    low_confidence_threshold=low_confidence_threshold,
                    crop_size=int(crop_size),
                    generate_annotated=generate_annotated,
                    generate_crops=generate_crops,
                    generate_json=generate_json,
                    generate_clean=generate_clean,
                    mask_granularity=int(mask_granularity),
                    max_images=int(max_images) if int(max_images) > 0 else None,
                    selected_parts=selected_parts,
                    force_all_taxonomy_parts=force_all_taxonomy_parts,
                )
                manifest = run_artifact_segmentation(opts, log=log)
                artifact_output = Path(manifest["output_root"])
                result_box.success(f"Done. Output: {artifact_output}")

                st.markdown("**Results**")
                annotated_dir = artifact_output / "annotated"
                if annotated_dir.exists():
                    preview_grid(list_images(annotated_dir), limit=72)

                if artifact_output.exists():
                    st.download_button(
                        "Download full output ZIP",
                        data=zip_folder(artifact_output),
                        file_name=f"{artifact_output.name}_segmentation_output.zip",
                        mime="application/zip",
                        key="segmenter_download_zip",
                    )

                manifest_path = artifact_output / "segmentation_manifest.json"
                if manifest_path.exists():
                    st.download_button(
                        "Download combined JSON manifest",
                        data=manifest_path.read_bytes(),
                        file_name="segmentation_manifest.json",
                        mime="application/json",
                        key="segmenter_download_manifest",
                    )
            except Exception as exc:
                log(f"ERROR: {type(exc).__name__}: {exc}")
                st.exception(exc)
