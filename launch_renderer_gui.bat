@echo off
setlocal
cd /d "%~dp0"
set "ROOT=%cd%"
set "VENV=%ROOT%\venv"

if not exist "%VENV%\Scripts\python.exe" (
    echo Shared virtual environment not found. Running setup first...
    call "%ROOT%\setup_renderer_env.bat" --no-pause
    if errorlevel 1 exit /b 1
)

"%VENV%\Scripts\python.exe" "%ROOT%\renderer\renderer_gui.py"
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
    echo.
    echo Renderer GUI exited with code %EXITCODE%.
    pause
)
exit /b %EXITCODE%
