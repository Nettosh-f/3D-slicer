# Renderer GUI wrong-app fix

This patch fixes the case where `launch_renderer_gui.bat` opens the Archaeological Part Segmenter.

Correct apps:

```text
Renderer GUI:  renderer\renderer_gui.py
Segmenter GUI: segmentation tool\app.py
```

Run:

```bat
launch_renderer_gui.bat
```

The launcher now verifies that `renderer\renderer_gui.py` contains the title:

```text
PLY Spherical Renderer
```

If it was overwritten with the segmenter app, the launcher stops with a clear error.
