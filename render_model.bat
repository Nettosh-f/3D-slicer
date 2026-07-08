@echo off
setlocal
cd /d "%~dp0"
set "ROOT=%cd%"
set "VENV=%ROOT%\venv"
set "LAUNCHER=%ROOT%\renderer\renderer_launcher_v2.py"

if not exist "%VENV%\Scripts\python.exe" (
    echo Virtual environment not found. Running setup first...
    call "%ROOT%\setup_renderer_env.bat" --no-pause
    if errorlevel 1 exit /b 1
)

if not exist "%LAUNCHER%" (
    echo Launcher not found: "%LAUNCHER%"
    exit /b 1
)

"%VENV%\Scripts\python.exe" "%LAUNCHER%" %*
set "EXITCODE=%ERRORLEVEL%"
exit /b %EXITCODE%
