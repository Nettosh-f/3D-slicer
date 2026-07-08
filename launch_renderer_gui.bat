@echo off
setlocal
cd /d "%~dp0"
set "ROOT=%cd%"
set "VENV=%ROOT%\venv"

if not exist "%VENV%\Scripts\python.exe" (
    echo Virtual environment not found. Running setup first...
    call "%ROOT%\setup_renderer_env.bat"
    if errorlevel 1 exit /b 1
)

call "%VENV%\Scripts\activate.bat"
if errorlevel 1 (
    echo Failed to activate the virtual environment.
    pause
    exit /b 1
)

python "%ROOT%\renderer\renderer_gui.py"
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
    echo.
    echo GUI exited with code %EXITCODE%.
    pause
)
exit /b %EXITCODE%
