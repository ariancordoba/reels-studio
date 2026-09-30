@echo off
rem Abre Reels Studio sin ventana de consola (lo usa el acceso directo).
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Falta instalar. Corre INSTALAR.bat primero.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m app.main
