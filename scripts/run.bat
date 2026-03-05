@echo off
REM run.bat - Windows startup script
REM Double-click to start the app

pushd "%~dp0\.."
python launcher.py
popd
pause
