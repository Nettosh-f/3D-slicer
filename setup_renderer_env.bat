@echo off
setlocal
cd /d "%~dp0"
set "ROOT=%cd%"
set "VENV=%ROOT%\venv"
set "PYTHON_EXE=python"
set "NO_PAUSE=0"
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"

echo [1/4] Checking Python...
%PYTHON_EXE% --version >nul 2>&1
if errorlevel 1 (
    echo Python was not found in PATH.
    echo Install Python 3.10 or newer and ensure the "python" command works.
    if "%NO_PAUSE%"=="0" pause
    exit /b 1
)

echo [2/4] Creating virtual environment if needed...
if not exist "%VENV%\Scripts\python.exe" (
    %PYTHON_EXE% -m venv "%VENV%"
    if errorlevel 1 (
        echo Failed to create the virtual environment.
        if "%NO_PAUSE%"=="0" pause
        exit /b 1
    )
) else (
    echo Virtual environment already exists.
)

echo [3/4] Activating virtual environment...
call "%VENV%\Scripts\activate.bat"
if errorlevel 1 (
    echo Failed to activate the virtual environment.
    if "%NO_PAUSE%"=="0" pause
    exit /b 1
)

echo [4/4] Installing or updating requirements...
python -m pip install --upgrade pip
python -m pip install -r "%ROOT%\renderer\requirements.txt"
if errorlevel 1 (
    echo Failed to install requirements.
    if "%NO_PAUSE%"=="0" pause
    exit /b 1
)

echo.
echo Environment is ready.
if "%NO_PAUSE%"=="0" pause
exit /b 0
