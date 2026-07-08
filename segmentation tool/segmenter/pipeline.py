from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Any
import numpy as np
from PIL import Image
from .export import ensure_dirs, save_image_outputs, write_json
from .masks import area_from_mask, bbox_from_mask, encode_binary_mask_rle
from .segmentation import generate_geometric_part_masks, make_object_mask
from .taxonomy import Taxonomy
from .utils import infer_angle_metadata, list_images, safe_name

LogFn = Callable[[str], None]

@dataclass
class PipelineOptions:
    image_folder: Path
    output_dir: Path
    artifact_class: str
    artifact_id: str | None = None
    taxonomy_path: Path = Path("configs/taxonomy.json")
    engine: str = "geometric"
    confidence_threshold: float = 0.35
    low_confidence_threshold: float = 0.55
    crop_size: int = 224
    generate_annotated: bool = True
    generate_crops: bool = True
    generate_json: bool = True
    generate_clean: bool = True
    mask_granularity: int = 32
    max_images: int | None = None
    selected_parts: list[str] | None = None
    force_all_taxonomy_parts: bool = False


def _quality_score(mask: np.ndarray, confidence: float, object_area: int) -> float:
    area = area_from_mask(mask)
    area_score = min(1.0, area / max(1, object_area) * 8.0)
    # v0.2 quality intentionally favors useful crop size + confidence.
    return float(round(0.65 * confidence + 0.35 * area_score, 4))


def _part_to_dict(part: Any) -> dict[str, Any]:
    return {
        "name": part.name,
        "zone": part.zone,
        "y_range": list(part.y_range),
        "optional": getattr(part, "optional", True),
        "primary_fallback": getattr(part, "primary_fallback", False),
    }


def run_artifact_segmentation(options: PipelineOptions, log: LogFn | None = None) -> dict[str, Any]:
    log = log or (lambda msg: None)
    image_folder = Path(options.image_folder).expanduser().resolve()
    output_dir = Path(options.output_dir).expanduser().resolve()
    taxonomy_path = Path(options.taxonomy_path)
    if not taxonomy_path.is_absolute():
        taxonomy_path = Path(__file__).resolve().parent.parent / taxonomy_path

    log(f"Loading taxonomy: {taxonomy_path}")
    taxonomy = Taxonomy(taxonomy_path)
    class_spec = taxonomy.get(options.artifact_class)

    image_paths = list_images(image_folder)
    if options.max_images:
        image_paths = image_paths[:options.max_images]
    if not image_paths:
        raise FileNotFoundError(f"No image files found in {image_folder}")

    artifact_id = safe_name(options.artifact_id or image_folder.name)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_output = output_dir / artifact_id
    paths = ensure_dirs(run_output)

    selected_parts = [p.strip() for p in (options.selected_parts or []) if p.strip()]
    selected_set = set(selected_parts)

    log(f"Artifact ID: {artifact_id}")
    log(f"Artifact class: {class_spec.artifact_class}")
    log(f"Images found: {len(image_paths)}")
    log(f"Output directory: {run_output}")
    if selected_parts:
        log(f"Visible/expected parts selected by user: {', '.join(selected_parts)}")
    elif options.force_all_taxonomy_parts:
        log("Force all taxonomy parts: ON. This is mainly for debugging and can create false labels.")
    else:
        primary = [p.name for p in class_spec.parts if p.primary_fallback]
        log("No visible parts selected. Using conservative primary fallback only: " + (", ".join(primary) or "none"))

    if options.engine != "geometric":
        log(f"Warning: engine={options.engine!r} is an extension point in v1. Falling back to geometric.")

    manifest: dict[str, Any] = {
        "schema_version": "0.2",
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "artifact_id": artifact_id,
        "artifact_class": class_spec.artifact_class,
        "taxonomy_version": taxonomy.version,
        "source_image_folder": str(image_folder),
        "output_root": str(run_output),
        "crop_size_px": options.crop_size,
        "engine": options.engine,
        "processing_scope": "per_image_independent",
        "part_presence_policy": {
            "taxonomy_parts_are_optional": True,
            "selected_parts": selected_parts,
            "force_all_taxonomy_parts": options.force_all_taxonomy_parts,
            "default_behavior": "primary_fallback_only_when_no_parts_are_selected",
        },
        "taxonomy_parts": [_part_to_dict(p) for p in class_spec.parts],
        "images": [],
    }

    taxonomy_parts = [_part_to_dict(p) for p in class_spec.parts]

    for index, img_path in enumerate(image_paths, start=1):
        log(f"Processing image {index}/{len(image_paths)}: {img_path.name}")
        image = Image.open(img_path).convert("RGBA")
        object_mask = make_object_mask(image)
        object_area = area_from_mask(object_mask)
        log(f"  Object mask area: {object_area} px")

        candidates, skipped_possible_parts = generate_geometric_part_masks(
            object_mask=object_mask,
            taxonomy_parts=taxonomy_parts,
            selected_part_names=selected_set if selected_set else None,
            force_all_parts=options.force_all_taxonomy_parts,
        )

        parts: list[dict[str, Any]] = []
        for candidate in candidates:
            area = area_from_mask(candidate.mask)
            if candidate.confidence < options.confidence_threshold or area == 0:
                skipped_possible_parts.append({
                    "part_name": candidate.name_hint,
                    "presence_status": candidate.presence_status,
                    "reason": f"Attempted but below confidence/area threshold: confidence={candidate.confidence:.2f}, area={area}",
                })
                log(f"  Not exported {candidate.name_hint!r}: confidence={candidate.confidence:.2f}, area={area}")
                continue

            bbox = bbox_from_mask(candidate.mask)
            quality = _quality_score(candidate.mask, candidate.confidence, object_area)
            low_conf = candidate.confidence < options.low_confidence_threshold
            part_record = {
                "part_name": candidate.name_hint,
                "confidence": round(candidate.confidence, 4),
                "low_confidence": bool(low_conf),
                "quality_score": quality,
                "bbox_xywh": bbox,
                "mask_area_px": area,
                "mask_rle": encode_binary_mask_rle(candidate.mask),
                "method": candidate.method,
                "presence_status": candidate.presence_status,
                "_mask": candidate.mask,
            }
            parts.append(part_record)
            log(f"  Exported {candidate.name_hint!r}: status={candidate.presence_status}, confidence={candidate.confidence:.2f}, quality={quality:.2f}")

        image_stem = safe_name(img_path.stem)
        annotated_path, clean_path, crop_refs = save_image_outputs(
            image, image_stem, parts, paths, options.crop_size,
            options.generate_annotated, options.generate_clean, options.generate_crops
        )

        export_parts = []
        for idx, part in enumerate(parts):
            record = {k: v for k, v in part.items() if k != "_mask"}
            record["crop_file"] = crop_refs.get(idx)
            export_parts.append(record)

        image_record = {
            "image_filename": img_path.name,
            "image_path": str(img_path),
            "angle_metadata": infer_angle_metadata(img_path.name),
            "width": image.width,
            "height": image.height,
            "annotated_file": annotated_path,
            "clean_visual_file": clean_path,
            "parts": export_parts,
            "possible_parts_not_exported": skipped_possible_parts,
        }

        if options.generate_json:
            per_image_json = paths["json"] / f"{image_stem}.json"
            write_json(per_image_json, {
                "schema_version": "0.2",
                "artifact_id": artifact_id,
                "artifact_class": class_spec.artifact_class,
                "image": image_record,
            })
            image_record["per_image_json"] = str(per_image_json)

        manifest["images"].append(image_record)

    best_views: dict[str, list[dict[str, Any]]] = {}
    for image_record in manifest["images"]:
        for part in image_record["parts"]:
            best_views.setdefault(part["part_name"], []).append({
                "image_filename": image_record["image_filename"],
                "crop_file": part.get("crop_file"),
                "quality_score": part.get("quality_score", 0.0),
                "confidence": part.get("confidence", 0.0),
                "low_confidence": part.get("low_confidence", True),
                "presence_status": part.get("presence_status", "unknown"),
            })
    for rows in best_views.values():
        rows.sort(key=lambda r: (r["low_confidence"], -float(r["quality_score"]), -float(r["confidence"])))
    manifest["best_views_by_part"] = best_views

    combined_json = run_output / "segmentation_manifest.json"
    if options.generate_json:
        write_json(combined_json, manifest)
        log(f"Wrote combined manifest: {combined_json}")

    log("Segmentation run complete.")
    return manifest
