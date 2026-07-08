# Segmentation Manifest Schema

This tool exports one combined `segmentation_manifest.json` per artifact folder.

## Why one combined JSON?

Tool 3 will likely train or infer over many views of the same artifact. A single artifact-level manifest avoids expensive re-matching between images, crops, masks, and broad class labels. Per-image JSON files are also written for debugging/inspection, but the combined manifest is the recommended Tool 3 contract.

## Top-level fields

- `artifact_id`: stable ID for the artifact folder.
- `artifact_class`: known broad class label supplied to the tool.
- `taxonomy_version`: version of `configs/taxonomy.json`.
- `crop_size_px`: target size of normalized per-part crops.
- `processing_scope`: always `per_image_independent` in v1.
- `images`: list of segmented render images.
- `best_views_by_part`: ranked crop candidates for each part.

## Part record

- `part_name`
- `confidence`
- `low_confidence`
- `quality_score`
- `bbox_xywh`
- `mask_area_px`
- `mask_rle`
- `crop_file`
- `method`

## Downstream recognition recommendation

Tool 3 should start with normalized part crops rather than full renders only. A simple first architecture could use one CNN/ViT encoder shared across part crops, aggregate crop embeddings per artifact, then classify type/period. Use `best_views_by_part` to prioritize high-quality views.


## v0.2 optional-part behavior

The taxonomy is a list of **possible** parts for each broad artifact class, not a list of parts that must be present.

This matters for fragments and partial artifacts:
- a pottery sherd may be only `body`;
- another sherd may be `rim` + `neck`;
- a figurine may have no visible arms or legs;
- a lithic image may expose only one face.

The manifest therefore includes:

- `part_presence_policy`: records whether the run used conservative fallback, user-selected visible parts, or force-all debug mode.
- `taxonomy_parts`: the full list of possible parts for the class.
- `parts`: only parts actually exported for that image.
- `possible_parts_not_exported`: possible taxonomy parts that were not selected, not requested, or attempted but below threshold.

For Tool 3, use `parts` as actual crop/mask records. Do not assume missing taxonomy parts are labeling errors. They may simply be absent from the artifact or not visible in that view.
