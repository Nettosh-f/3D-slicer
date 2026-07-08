@echo off
setlocal
cd /d "%~dp0"

set "ROOT=%cd%"
set "VENV=%ROOT%\venv"
set "PYTHON_EXE=python"
set "PAUSE_ON_END=1"
if /I "%~1"=="--no-pause" set "PAUSE_ON_END=0"

echo ============================================================
echo 3D-slicer shared Python environment setup
echo ============================================================
echo This creates/updates one shared venv for renderer + segmentation.
echo.

echo [1/6] Checking Python...
%PYTHON_EXE% --version
if errorlevel 1 goto :python_error

echo.
echo [2/6] Creating virtual environment if needed...
if not exist "%VENV%\Scripts\python.exe" (
    %PYTHON_EXE% -m venv "%VENV%"
    if errorlevel 1 goto :venv_error
) else (
    echo Virtual environment already exists: "%VENV%"
)

echo.
echo [3/6] Activating virtual environment...
call "%VENV%\Scripts\activate.bat"
if errorlevel 1 goto :activate_error

echo.
echo [4/6] Updating pip...
python -m pip install --upgrade pip
if errorlevel 1 goto :pip_error

echo.
echo [5/6] Installing renderer requirements...
if exist "%ROOT%\renderer\requirements.txt" (
    python -m pip install -r "%ROOT%\renderer\requirements.txt"
    if errorlevel 1 goto :requirements_error
) else (
    echo No renderer\requirements.txt found. Skipping renderer requirements.
)

echo.
echo [6/6] Installing segmentation requirements...
if exist "%ROOT%\segmentation tool\requirements.txt" (
    python -m pip install -r "%ROOT%\segmentation tool\requirements.txt"
    if errorlevel 1 goto :requirements_error
) else (
    echo No "segmentation tool\requirements.txt" found.
    echo Installing minimum segmentation GUI requirements directly...
    python -m pip install streamlit opencv-python numpy pillow pandas pyyaml
    if errorlevel 1 goto :requirements_error
)

echo.
echo Verifying Streamlit...
python -c "import streamlit; print('Streamlit OK:', streamlit.__version__)"
if errorlevel 1 goto :requirements_error

echo.
echo Environment is ready.
echo.
echo Use:
echo   render_model.bat my_model.ply output\renderer -phi 20 -theta 20
echo   launch_renderer_gui.bat
echo   launch_segmenter_gui.bat
echo   open_renderer_shell.bat
echo.
goto :success

:python_error
echo.
echo ERROR: Python was not found in PATH.
echo Install Python 3.10+ and make sure python works in Command Prompt.
goto :fail

:venv_error
echo.
echo ERROR: Failed to create the virtual environment.
goto :fail

:activate_error
echo.
echo ERROR: Failed to activate the virtual environment.
goto :fail

:pip_error
echo.
echo ERROR: Failed to upgrade pip.
goto :fail

:requirements_error
echo.
echo ERROR: Failed to install or verify one or more requirements.
goto :fail

:success
if "%PAUSE_ON_END%"=="1" pause
exit /b 0

:fail
if "%PAUSE_ON_END%"=="1" pause
exit /b 1
