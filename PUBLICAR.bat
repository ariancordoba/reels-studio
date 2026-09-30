@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Publica una versión nueva de Reels Studio (sólo para quien lo desarrolla).
rem Uso:  PUBLICAR.bat "qué cambió"
if "%~1"=="" (
  set /p NOTAS=¿Qué cambió en esta versión?
) else (
  set "NOTAS=%~1"
)
uv run python scripts/publicar.py --notas "%NOTAS%"
pause
