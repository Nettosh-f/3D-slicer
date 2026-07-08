# Project overview

## Tool 1: Renderer

Input: one `.ply` file or a folder of `.ply` files.

Output:

```text
output/renderer/images/<classification>/<model_id>/*.png
output/renderer/manifest.csv
output/renderer/run_config.json
```

Default sampling is 2 degrees for phi and theta. Use `-phi` and `-theta` to change it.

## Tool 2: Segmentation

Input: one artifact folder of rendered PNG/JPEG views and a known broad artifact class.

Output:

```text
output/segmenter/<artifact_id>/
├── annotated/
├── clean_visual/
├── part_crops/
├── json/
└── segmentation_manifest.json
```

The current v0.1 segmentation engine is geometric/heuristic and designed to run out-of-the-box on clean renderer outputs. SAM/SAM2/GroundingDINO integration is a planned upgrade.

## Tool 3: Recognition

Not built yet. The segmentation JSON schema and per-part crop export are designed to make Tool 3 easier to train and run later.
