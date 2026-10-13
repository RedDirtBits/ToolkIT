@echo off
REM run.bat - start ToolkIT. Double-click this file.
REM
REM Starts the app with the embedded Python in the "python" folder next to this
REM file. Close this window (or press Ctrl+C in it) to stop the app.

REM Run from the folder this file is in, wherever it was double-clicked from.
cd /d "%~dp0"

if not exist "python\python.exe" (
    echo Embedded Python was not found at "%~dp0python\python.exe".
    echo The folder looks incomplete: see "If something goes wrong" in GETTING-STARTED.html.
    pause
    exit /b 1
)

python\python.exe -m app

REM If the app stopped because of an error, keep the window open to read it.
pause
