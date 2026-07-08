@echo off
setlocal
cd /d "%~dp0"
call "%~dp0setup_renderer_env.bat" --no-pause
if errorlevel 1 exit /b 1

cmd /k "cd /d \"%~dp0\" && call \"%~dp0venv\Scripts\activate.bat\" && echo. && echo Virtual environment is active. && echo Try: render_model.bat \"HAD16_279_2916 FIGURINE.ply\" output -phi 20 -theta 20"
