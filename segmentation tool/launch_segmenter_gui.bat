@echo off
setlocal
cd /d "%~dp0\.."

if exist "launch_segmenter_gui.bat" (
    call "launch_segmenter_gui.bat"
    exit /b %ERRORLEVEL%
) else (
    echo Could not find root launch_segmenter_gui.bat.
    echo Run from the repository root instead:
    echo   launch_segmenter_gui.bat
    pause
    exit /b 1
)
