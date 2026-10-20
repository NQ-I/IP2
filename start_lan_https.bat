@echo off
REM Starts the server for a multi-device test (HTTPS, reachable from other laptops).
REM Double-click this file from the project folder (it works from any location).
cd /d "%~dp0"
if exist venv\Scripts\activate.bat call venv\Scripts\activate.bat
python run.py --https --port 5000
pause
