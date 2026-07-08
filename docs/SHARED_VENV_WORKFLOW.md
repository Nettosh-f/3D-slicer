# Shared venv workflow

The whole project uses one root-level virtual environment:

```text
3D-slicer/venv/
```

Do not create `segmentation tool/venv` or `renderer/venv`.

## Setup

```bat
setup_renderer_env.bat
```

This installs:

```text
renderer/requirements.txt
"segmentation tool"/requirements.txt
```

## Launch commands

```bat
render_model.bat "model.ply" output\renderer -phi 20 -theta 20
launch_renderer_gui.bat
launch_segmenter_gui.bat
open_renderer_shell.bat
```

## Manual shell use

```bat
open_renderer_shell.bat
```

Then:

```bat
python renderer\ply_spherical_renderer_windows.py --help
streamlit run "segmentation tool\app.py"
```
