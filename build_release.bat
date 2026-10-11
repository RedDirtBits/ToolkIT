@echo off
REM build_release.bat - build a zip of this app that's safe to share with colleagues.
REM Double-click this file. The zip appears in the "build" folder.
REM Only the app, the embedded Python, the launcher and GETTING-STARTED.html go in:
REM never your data, inventory CSV, tests or development files.
REM (See tools\build_release.py for exactly what's included and checked.)

cd /d "%~dp0"

if not exist "python\python.exe" (
    echo Embedded Python was not found at "%~dp0python\python.exe".
    echo See "Getting started" in README.md.
    pause
    exit /b 1
)

python\python.exe tools\build_release.py
pause
