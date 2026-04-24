@echo off

REM Run pytest through the project virtual environment.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m pytest %*
) else (
    python -m pytest %*
)

REM Pause to keep the window open (optional)
pause
