PLY Renderer Starter Kit for Windows
====================================

Folder structure
----------------
models/      Put .ply files or subfolders here.
output/      Default output location.
renderer/    Renderer, launcher, requirements, and labels template.

First use
---------
1. Put your .ply file into models\
2. Double-click setup_renderer_env.bat once.
3. Open Command Prompt in this folder.
4. Run:

   render_model.bat "HAD16_279_2916 FIGURINE.ply" output -phi 20 -theta 20

The wrapper accepts quoted filenames containing spaces.

Input examples
--------------
A filename located in models\:
   render_model.bat "HAD16_279_2916 FIGURINE.ply"

A folder located in models\:
   render_model.bat figurines

A direct path:
   render_model.bat "C:\data\model.ply" "C:\data\renders"

Important arguments
-------------------
-phi N                  Azimuth step in degrees. Default: 2
-theta N                Polar-angle step in degrees. Default: 2
--classification NAME   Apply one classification to all models in the run
--class-from-parent      Use parent-folder names as classifications
--labels-csv FILE        Read classifications from a CSV
--width N                PNG width. Default: 512
--height N               PNG height. Default: 512
--overwrite              Re-render existing images
--dry-run                Preview planned work without rendering

Examples
--------
Small test:
   render_model.bat "HAD16_279_2916 FIGURINE.ply" output -phi 20 -theta 20

With classification:
   render_model.bat "HAD16_279_2916 FIGURINE.ply" output -phi 20 -theta 20 --classification figurine

Folder input with classes inferred from subfolders:
   render_model.bat pottery output --class-from-parent -phi 10 -theta 10
