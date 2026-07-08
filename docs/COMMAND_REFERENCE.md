# Command reference

## Setup

```bat
setup_renderer_env.bat
```

## Renderer CLI wrapper

```bat
render_model.bat <model_or_folder> [output_folder] [renderer arguments...]

Default renderer output: `output\renderer`
```

Examples:

```bat
render_model.bat "HAD16_279_2916 FIGURINE.ply" output\renderer -phi 20 -theta 20 --classification figurine
render_model.bat figurines output\renderer --class-from-parent -phi 10 -theta 10
render_model.bat models\pottery output\renderer --labels-csv renderer\labels_template.csv
```

## Renderer direct help

```bat
venv\Scripts\python.exe renderer\ply_spherical_renderer_windows.py --help
```

## Renderer GUI

```bat
launch_renderer_gui.bat
```

## Segmentation GUI

```bat
launch_segmenter_gui.bat
```

## Segmentation CLI

```bat
python "segmentation tool\run_segmenter.py" <image_folder> output\segmenter --artifact-class figurine
```


## Segmenter optional parts

The segmenter accepts optional visible parts:

```bat
python "segmentation tool\run_segmenter.py" "output\renderer\images\pottery\artifact_001" "output\segmenter" --artifact-class pottery --parts body
```

For a rim sherd:

```bat
python "segmentation tool\run_segmenter.py" "output\renderer\images\pottery\artifact_002" "output\segmenter" --artifact-class pottery --parts rim neck
```

Debug only:

```bat
python "segmentation tool\run_segmenter.py" "output\renderer\images\pottery\artifact_002" "output\segmenter" --artifact-class pottery --force-all-taxonomy-parts
```
