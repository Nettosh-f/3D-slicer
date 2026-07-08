# Archaeological Part Segmenter

Middle-stage tool for the 3D-slicer pipeline:

1. Renderer creates multi-angle PNG/JPEG views.
2. This tool segments each view into class-conditioned artifact parts.
3. A future recognition model consumes the masks, crops, and JSON manifest.

## Status

This is v0.2. It runs out-of-the-box with a geometric/positional engine intended for clean renderer outputs. SAM/SAM2/GroundingDINO/VLM-assisted labeling are planned extension points, but not bundled in this lightweight starter version.

## Environment

Use the shared root venv. From the repository root:

```bat
setup_renderer_env.bat
```

Do **not** create a separate `segmentation tool/venv`.

## Run GUI

From the repository root:

```bat
launch_segmenter_gui.bat
```

or:

```bat
venv\Scripts\activate
streamlit run "segmentation tool\app.py"
```

## Run CLI

```bat
python "segmentation tool\run_segmenter.py" "path\to\artifact_png_folder" "output\segmenter" --artifact-class figurine --artifact-id HAD16_279_2916
```

Quick test on first 10 images:

```bat
python "segmentation tool\run_segmenter.py" "path\to\artifact_png_folder" "output\segmenter" --artifact-class pottery --max-images 10
```

## Output

Per artifact:

```text
output/segmenter/
└── artifact_id/
    ├── annotated/
    ├── clean_visual/
    ├── part_crops/
    ├── json/
    └── segmentation_manifest.json
```

## Taxonomy

Edit:

```text
"segmentation tool"/configs/taxonomy.json
```

to add artifact classes or parts without changing code.

## Known v0.1 failure modes

- Pottery: handles/spouts can be merged into the body because the geometric engine lacks true semantic recognition.
- Figurines: broken or occluded limbs may be mislabeled as torso/arms/legs bands.
- Lithics: retouch and ventral/dorsal distinctions are often too subtle without a trained or VLM-assisted model.
- Metalwork: corrosion/patina may not segment cleanly from the object body.
- Organic material: bone/wood/shell part names depend strongly on orientation and species/object type.


## Part presence model

Taxonomy parts are now treated as **optional possible parts**, not mandatory outputs.

Default behavior is conservative:
- If no parts are selected, the geometric engine exports only the class's primary fallback part, such as `body` for pottery or `torso` for figurines.
- For fragments, choose **I know which parts are visible** in the GUI and select only the parts you want exported.
- **Force all taxonomy parts** exists only for debugging and can create false labels.
