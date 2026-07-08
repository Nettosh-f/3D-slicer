from __future__ import annotations
import io
import tempfile
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import streamlit as st
from segmenter.pipeline import PipelineOptions, run_artifact_segmentation
from segmenter.taxonomy import Taxonomy
from segmenter.utils import IMAGE_EXTENSIONS, list_images

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "configs" / "taxonomy.json"
DEFAULT_OUTPUT = ROOT.parent / "output" / "segmenter"

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

def main() -> None:
    st.set_page_config(page_title="Archaeological Part Segmenter", layout="wide")
    st.title("Archaeological Part Segmenter")
    st.caption("Multi-angle renderer images → optional class-conditioned part masks, crops, overlays, and ML-friendly JSON.")
    taxonomy = Taxonomy(CONFIG)

    with st.sidebar:
        st.header("Upload / input")
        input_mode = st.radio("Input mode", ["Folder path", "Upload files"], horizontal=True)
        artifact_id = st.text_input("Artifact ID", value="")
        image_folder = None

        if input_mode == "Folder path":
            folder_text = st.text_input("Image folder path", value="")
            if folder_text.strip():
                image_folder = Path(folder_text).expanduser().resolve()
        else:
            uploaded = st.file_uploader(
                "Upload one artifact's render images",
                type=[e.lstrip(".") for e in sorted(IMAGE_EXTENSIONS)],
                accept_multiple_files=True,
            )
            if uploaded:
                temp_dir = tempfile.TemporaryDirectory()
                image_folder = Path(temp_dir.name)
                st.session_state["_temp_dir"] = temp_dir
                for file in uploaded:
                    (image_folder / file.name).write_bytes(file.getbuffer())

        output_dir = Path(st.text_input("Output directory", value=str(DEFAULT_OUTPUT))).expanduser()

        st.header("Options")
        classes = taxonomy.class_names
        default_idx = classes.index("pottery") if "pottery" in classes else 0
        artifact_class = st.selectbox("Artifact class", classes, index=default_idx)
        class_spec = taxonomy.get(artifact_class)
        possible_parts = [p.name for p in class_spec.parts]
        primary_parts = [p.name for p in class_spec.parts if getattr(p, 'primary_fallback', False)]

        st.subheader("Visible / expected parts")
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
                "For fragments, choose only the parts you believe are visible. "
                "Force-all is mainly for debugging and can create false labels."
            ),
        )

        selected_parts: list[str] = []
        force_all_taxonomy_parts = False
        if part_mode == "Conservative default":
            st.caption(
                "No parts are assumed present. The geometric v0.2 engine exports only the class primary fallback "
                f"part(s): {', '.join(primary_parts) if primary_parts else 'none'}."
            )
        elif part_mode == "I know which parts are visible":
            selected_parts = st.multiselect(
                "Select visible parts to export",
                options=possible_parts,
                default=primary_parts[:1],
                help="Use this for fragments or partial artifacts. Example: a pottery sherd may be only body, only rim, or rim + shoulder.",
            )
        else:
            force_all_taxonomy_parts = True
            st.warning("Force-all can produce false labels on fragments. Use it for debugging, not for training data.")

        run_button = st.button("Run segmentation", type="primary", use_container_width=True)

        st.subheader("Generate outputs")
        generate_annotated = st.checkbox("Annotated images", value=True)
        generate_crops = st.checkbox("Per-part crops", value=True)
        generate_json = st.checkbox("JSON export", value=True)
        generate_clean = st.checkbox("Clean presentation images", value=True)

        with st.expander("Advanced options", expanded=False):
            engine = st.selectbox(
                "Segmentation engine",
                ["geometric", "sam2_placeholder", "vlm_assisted_placeholder"],
                help="v0.2 runs geometric segmentation out of the box. SAM/VLM engines are extension points.",
            )
            confidence_threshold = st.slider("Confidence threshold", 0.0, 1.0, 0.35, 0.01)
            low_confidence_threshold = st.slider("Low-confidence flag threshold", 0.0, 1.0, 0.55, 0.01)
            mask_granularity = st.slider("Mask granularity / points per side", 8, 128, 32, 8)
            crop_size = st.selectbox("Per-part crop target resolution", [224, 384, 512], index=0)
            max_images = st.number_input("Max images for test run, 0 = all", min_value=0, value=0, step=1)

    col_a, col_b = st.columns([1.15, 1])

    with col_a:
        st.subheader("Input thumbnail grid")
        images = []
        if image_folder and image_folder.exists():
            images = list_images(image_folder)
            st.write(f"Loaded **{len(images)}** image(s).")
            preview_grid(images)
        elif image_folder:
            st.warning(f"Folder does not exist: {image_folder}")
        else:
            st.info("Choose a folder or upload files.")

    with col_b:
        st.subheader("Console / log")
        log_box = st.empty()
        result_box = st.empty()

    if run_button:
        if not image_folder or not image_folder.exists():
            st.error("Please choose a valid input folder or upload images.")
            return

        if part_mode == "I know which parts are visible" and not selected_parts:
            st.error("Select at least one visible part, or switch back to Conservative default.")
            return

        logs = []
        def log(msg: str) -> None:
            logs.append(msg)
            log_box.code("\n".join(logs[-250:]), language="text")

        try:
            opts = PipelineOptions(
                image_folder=image_folder,
                output_dir=output_dir,
                artifact_class=artifact_class,
                artifact_id=artifact_id.strip() or None,
                taxonomy_path=CONFIG,
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

            st.subheader("Results")
            annotated_dir = artifact_output / "annotated"
            if annotated_dir.exists():
                preview_grid(list_images(annotated_dir), limit=72)

            if artifact_output.exists():
                st.download_button(
                    "Download full output ZIP",
                    data=zip_folder(artifact_output),
                    file_name=f"{artifact_output.name}_segmentation_output.zip",
                    mime="application/zip",
                )

            manifest_path = artifact_output / "segmentation_manifest.json"
            if manifest_path.exists():
                st.download_button(
                    "Download combined JSON manifest",
                    data=manifest_path.read_bytes(),
                    file_name="segmentation_manifest.json",
                    mime="application/json",
                )
        except Exception as exc:
            log(f"ERROR: {type(exc).__name__}: {exc}")
            st.exception(exc)

if __name__ == "__main__":
    main()
