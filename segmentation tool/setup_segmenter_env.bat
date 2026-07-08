@echo off
setlocal
cd /d "%~dp0\.."

if exist "setup_renderer_env.bat" (
    call "setup_renderer_env.bat"
) else (
    echo Could not find root setup_renderer_env.bat.
    echo Run setup from the repository root.
    pause
    exit /b 1
)
