@echo off
setlocal
cd /d "%~dp0"

if not exist "%~dp0venv\Scripts\python.exe" (
    call "%~dp0setup_renderer_env.bat" --no-pause
    if errorlevel 1 exit /b 1
)

cmd /k "cd /d ""%~dp0"" && call ""%~dp0venv\Scripts\activate.bat"" && echo. && echo Shared 3D-slicer venv is active. && echo Try: render_model.bat my_model.ply output -phi 20 -theta 20 && echo Or: launch_renderer_gui.bat && echo Or: launch_segmenter_gui.bat"
