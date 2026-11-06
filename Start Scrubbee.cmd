@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 -m scrubbee ui
) else (
  python -m scrubbee ui
)
if errorlevel 1 pause
