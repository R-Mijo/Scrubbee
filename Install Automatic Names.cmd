@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 -m venv .venv
) else (
  python -m venv .venv
)
if errorlevel 1 goto failed
:install
".venv\Scripts\python.exe" -m pip install ".[names]"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m spacy download en_core_web_sm
if errorlevel 1 goto failed
echo Automatic names are ready. Open Start Scrubbee.cmd.
pause
exit /b 0
:failed
echo Setup did not finish. Check the error above. Python 3.11 or newer and internet are required.
pause
exit /b 1
