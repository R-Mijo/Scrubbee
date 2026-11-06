@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m scrubbee ui
  if errorlevel 1 pause
  exit /b
)
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 -m scrubbee ui
) else (
  python -m scrubbee ui
)
if errorlevel 1 pause
