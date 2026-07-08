# Shared venv setup fix

This patch fixes the shared root `venv` setup for a repo containing:

```text
segmentation tool/
```

with a space in the folder name.

## Immediate manual install

From the repo root:

```bat
venv\Scripts\activate
python -m pip install -r "segmentation tool\requirements.txt"
python -m streamlit run "segmentation tool\app.py"
```

## Normal setup

From the repo root:

```bat
setup_renderer_env.bat
launch_segmenter_gui.bat
```

The setup script now verifies Streamlit at the end.
