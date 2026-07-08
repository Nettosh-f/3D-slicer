# Renderer Streamlit GUI

The renderer GUI now uses **Streamlit** instead of Tkinter, so both main tools in the project share the same GUI technology.

## Launch

From the repository root:

```bat
launch_renderer_gui.bat
```

Or manually:

```bat
venv\Scripts\activate
python -m streamlit run "renderer\renderer_gui.py"
```

## Main features

- choose a single `.ply` file from `models/`
- choose a model folder from `models/`
- or enter a direct file/folder path
- default output folder: `output/renderer`
- render-density presets: preview / medium / default / full / custom
- classification modes: unclassified / manual / parent folder / labels CSV
- advanced renderer settings
- exact command preview
- live renderer log
- embedded `Renderer --help`
- embedded project workflow help

## Notes

- `launch_renderer_gui.bat` uses the shared root `venv`.
- If Streamlit is missing, the launcher reruns `setup_renderer_env.bat`.
- The GUI invokes `renderer/ply_spherical_renderer_windows.py` directly.
- On Windows, `visualizer` is often the safer explicit backend if `auto` behaves badly.
