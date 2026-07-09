@echo off
setlocal
cd /d "%~dp0\.."

if not exist "venv\Scripts\python.exe" (
    echo Shared venv not found. Run setup_renderer_env.bat first.
    pause
    exit /b 1
)

call "venv\Scripts\activate.bat"

pip install -q -r "tool completer\requirements.txt"

python "tool completer\sherd_profile_pipeline.py" %*
exit /b %ERRORLEVEL%
