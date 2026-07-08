@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo 3D-slicer segmentation GUI launcher
echo ============================================================
echo Repo root: "%cd%"
echo.

if not exist "%~dp0venv\Scripts\python.exe" (
    echo Shared venv not found. Running setup first...
    call "%~dp0setup_renderer_env.bat" --no-pause
    if errorlevel 1 (
        echo.
        echo Setup failed.
        pause
        exit /b 1
    )
)

echo Activating shared venv...
call "%~dp0venv\Scripts\activate.bat"
if errorlevel 1 (
    echo.
    echo Failed to activate shared venv.
    pause
    exit /b 1
)

echo Python:
python --version
echo.

if not exist "%~dp0segmentation tool\app.py" (
    echo ERROR: Could not find:
    echo   "%~dp0segmentation tool\app.py"
    echo.
    echo Make sure the folder is named exactly:
    echo   segmentation tool
    echo and that it is inside the repo root.
    pause
    exit /b 1
)

echo Checking Streamlit installation...
python -c "import streamlit; print('Streamlit OK:', streamlit.__version__)"
if errorlevel 1 (
    echo.
    echo Streamlit is missing. Installing shared project requirements...
    call "%~dp0setup_renderer_env.bat" --no-pause
    if errorlevel 1 (
        echo.
        echo Setup failed while installing Streamlit.
        pause
        exit /b 1
    )
)

echo.
echo Launching segmentation GUI...
echo If the browser does not open automatically, copy the local URL shown below.
echo.
python -m streamlit run "%~dp0segmentation tool\app.py"
set "EXITCODE=%ERRORLEVEL%"

echo.
if "%EXITCODE%"=="0" (
    echo Streamlit closed normally.
) else (
    echo Streamlit exited with error code %EXITCODE%.
)
pause
exit /b %EXITCODE%
