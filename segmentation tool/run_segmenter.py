from __future__ import annotations
import argparse
from pathlib import Path
from segmenter.pipeline import PipelineOptions, run_artifact_segmentation

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run automatic archaeological part segmentation on one artifact image folder.")
    p.add_argument("image_folder", type=Path)
    p.add_argument("output_dir", type=Path)
    p.add_argument("--artifact-class", required=True, help="Known broad artifact class, e.g. pottery, figurine, lithic.")
    p.add_argument("--artifact-id", default=None)
    p.add_argument("--taxonomy", type=Path, default=Path("configs/taxonomy.json"))
    p.add_argument("--engine", default="geometric", choices=["geometric", "sam2_placeholder", "vlm_assisted_placeholder"])
    p.add_argument("--confidence-threshold", type=float, default=0.35)
    p.add_argument("--low-confidence-threshold", type=float, default=0.55)
    p.add_argument("--crop-size", type=int, default=224)
    p.add_argument("--max-images", type=int, default=0)
    p.add_argument(
        "--parts",
        nargs="*",
        default=None,
        help='Visible/expected parts to export, e.g. --parts rim body handle. If omitted, v0.2 uses conservative primary fallback only.',
    )
    p.add_argument(
        "--force-all-taxonomy-parts",
        action="store_true",
        help="Debug mode: attempt every possible taxonomy part. This can create false labels on fragments.",
    )
    p.add_argument("--no-annotated", action="store_true")
    p.add_argument("--no-crops", action="store_true")
    p.add_argument("--no-json", action="store_true")
    p.add_argument("--no-clean", action="store_true")
    return p.parse_args()

def main() -> None:
    a = parse_args()
    opts = PipelineOptions(
        image_folder=a.image_folder,
        output_dir=a.output_dir,
        artifact_class=a.artifact_class,
        artifact_id=a.artifact_id,
        taxonomy_path=a.taxonomy,
        engine=a.engine,
        confidence_threshold=a.confidence_threshold,
        low_confidence_threshold=a.low_confidence_threshold,
        crop_size=a.crop_size,
        generate_annotated=not a.no_annotated,
        generate_crops=not a.no_crops,
        generate_json=not a.no_json,
        generate_clean=not a.no_clean,
        max_images=a.max_images if a.max_images > 0 else None,
        selected_parts=a.parts,
        force_all_taxonomy_parts=a.force_all_taxonomy_parts,
    )
    manifest = run_artifact_segmentation(opts, log=print)
    print(f"Combined output root: {manifest['output_root']}")

if __name__ == "__main__":
    main()
