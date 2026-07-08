# 3D-slicer

A three-stage archaeology computer-vision pipeline for turning 3D artifact models into structured visual data for later recognition/classification.

## Current tools

```text
3D-slicer/
├── renderer/             # Tool 1: PLY model/folder → multi-angle PNGs + manifest.csv
├── "segmentation tool"/    # Tool 2: rendered image folder → part masks/crops/JSON
├── models/               # local PLY inputs; usually not committed
├── output/
│   ├── renderer/        # renderer outputs; usually not committed
│   └── segmenter/       # segmentation outputs; usually not committed
├── docs/                 # workflow and data-contract notes
└── venv/                 # shared local Python environment; not committed
```

Tool 3, the final recognition/type-period classifier, is planned for later. The segmentation tool already exports ML-friendly per-part crops and manifests so Tool 3 can consume them directly.

## Setup

Run once from the repository root:

```bat
setup_renderer_env.bat
```

This creates/updates one shared root environment:

```text
venv/
```

and installs both:

```text
renderer/requirements.txt
"segmentation tool"/requirements.txt
```

## Renderer CLI

Put PLY files under `models/`, then run:

```bat
render_model.bat "HAD16_279_2916 FIGURINE.ply" output\renderer -phi 20 -theta 20 --classification figurine
```

Useful renderer arguments:

```text
-phi N                  azimuth step in degrees, default 2
-theta N                polar-angle step in degrees, default 2
--classification NAME   assign one class label to the whole run
--class-from-parent      use each model's parent folder as classification
--labels-csv FILE        read classifications from CSV
--width N --height N     PNG dimensions, default 512 x 512
--renderer-backend NAME  auto, visualizer, or offscreen
--dry-run                preview planned work without rendering
--overwrite              re-render existing PNGs
```

Full renderer help:

```bat
venv\Scripts\python.exe renderer\ply_spherical_renderer_windows.py --help
```

## Renderer GUI

```bat
launch_renderer_gui.bat
```

The GUI now reads the renderer CLI help live from `ply_spherical_renderer_windows.py --help`, so the Help menu should stay synced with the actual renderer arguments.

## Segmentation GUI

```bat
launch_segmenter_gui.bat
```

Or manually:

```bat
venv\Scripts\activate
streamlit run "segmentation tool\app.py"
```

## Segmentation CLI

```bat
python "segmentation tool\run_segmenter.py" "output\renderer\images\figurine\HAD16_279_2916_FIGURINE" "output\segmenter" --artifact-class figurine --artifact-id HAD16_279_2916
```

## Git workflow

Generated images, local models, and the shared venv are ignored by `.gitignore`.

Normal update cycle:

```bash
git add .
git commit -m "Describe the change"
git push
```


## Segmenter GUI troubleshooting

If the segmenter GUI closes instantly, run `launch_segmenter_gui.bat` from a Command Prompt instead of double-clicking it. The launcher now keeps the console open and prints the error. See `docs/SEGMENTER_GUI_TROUBLESHOOTING.md`.


## Segmenter part-presence behavior

The segmenter does **not** assume every artifact has every taxonomy part. A class taxonomy is a list of possible labels. For fragments, use the GUI's part-presence mode and select only the visible/expected parts. This prevents false crops such as rim/neck/base being created for a body-only pottery sherd.
