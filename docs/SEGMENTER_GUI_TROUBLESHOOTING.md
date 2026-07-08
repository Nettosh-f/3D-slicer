# Segmenter GUI troubleshooting

If `launch_segmenter_gui.bat` opens and instantly closes, use the patched launcher in this folder.

The launcher now keeps the window open and prints:
- repo root
- Python version
- whether Streamlit imports correctly
- the exact app path

## Manual test

From the repo root:

```bat
venv\Scripts\activate
python -m streamlit run "segmentation tool\app.py"
```

## Reinstall shared requirements

```bat
setup_renderer_env.bat
```

This installs both:

```text
renderer\requirements.txt
segmentation tool\requirements.txt
```

into the root `venv`.

## Common causes

1. The folder is named differently, for example `segmentation_tool` instead of `segmentation tool`.
2. Streamlit is not installed because setup did not finish.
3. The launcher was run from an old copy.
4. The root `venv` was deleted or corrupted.
