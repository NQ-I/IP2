@echo off
REM Local-only start (this computer only): http://localhost:5000
REM For other laptops on the LAN use start_lan_https.bat instead (camera/microphone need HTTPS).
cd /d "%~dp0"
if exist venv\Scripts\activate.bat call venv\Scripts\activate.bat
echo.
echo   Proctor / admin dashboard : http://localhost:5000
echo   Student on THIS computer  : http://127.0.0.1:5000/exam
echo   (two different addresses = two separate logins in the same browser;
echo    logging the student in at localhost would log the proctor out)
echo.
start "" http://localhost:5000
python run.py --port 5000
pause
