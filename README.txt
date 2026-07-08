3D-slicer quick start
=====================

1) Put .ply files in models\
2) Run setup_renderer_env.bat once
3) Run one of:

   render_model.bat "my_model.ply" output -phi 20 -theta 20
   launch_renderer_gui.bat
   launch_segmenter_gui.bat

The project uses one shared venv in the repo root. Do not create a second venv inside segmentation tool.

For detailed docs, read README.md and docs\SHARED_VENV_WORKFLOW.md.
