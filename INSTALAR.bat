@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Reels Studio - Instalador

rem 0. La app vive en una carpeta fija; asi el zip se puede descomprimir en cualquier lado (Descargas, etc.)
set "DEST=%LOCALAPPDATA%\Programs\ReelsStudio"
if exist "%~dp0tests\" goto :instalar_aca
if /I "%~dp0"=="%DEST%\" goto :instalar_aca
echo  Copiando Reels Studio a %DEST% ...
robocopy "%~dp0." "%DEST%" /E /XD .venv __pycache__ /NFL /NDL /NJH /NJS >nul
if errorlevel 8 goto :error
call "%DEST%\INSTALAR.bat"
exit /b %errorlevel%
:instalar_aca
echo.
echo  Reels Studio - instalacion
echo  (se puede correr de nuevo para reparar)
echo.

rem 1. uv (instala Python y dependencias sin tocar nada a mano)
where uv >nul 2>nul
if errorlevel 1 (
  if exist "%USERPROFILE%\.local\bin\uv.exe" (
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
  ) else (
    echo [1/5] Instalando uv...
    powershell -NoProfile -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex" || goto :error
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
  )
)
echo [1/5] uv listo

rem 2. Python 3.12 + dependencias
echo [2/5] Instalando dependencias (la primera vez tarda unos minutos)...
uv sync --no-dev || goto :error

rem 3. Chromium para los textos
echo [3/5] Instalando Chromium para los textos...
uv run --no-dev playwright install chromium || goto :error

rem 4. Claude Code: se instala y se conecta desde la app (Ajustes > Conectar Claude), sin terminal
echo [4/5] Claude Code: lo vas a conectar desde la app la primera vez que la abras.

rem 5. Accesos directos (escritorio y menu Inicio), sin ventana de consola
echo [5/5] Creando accesos directos...
powershell -NoProfile -ExecutionPolicy ByPass -c ^
  "$w = New-Object -ComObject WScript.Shell;" ^
  "$targets = @([Environment]::GetFolderPath('Desktop'), (Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs'));" ^
  "foreach ($d in $targets) { $s = $w.CreateShortcut((Join-Path $d 'Reels Studio.lnk'));" ^
  "  $s.TargetPath = '%~dp0.venv\Scripts\pythonw.exe'; $s.Arguments = '-m app.main';" ^
  "  $s.WorkingDirectory = '%~dp0'; $s.IconLocation = '%~dp0assets\icono.ico';" ^
  "  $s.Description = 'Reels Studio'; $s.Save() }" || goto :error

echo.
uv run --no-dev reels --help >nul || goto :error
echo  Listo. Abri "Reels Studio" desde el escritorio.
echo  En la laptop: corre este mismo instalador y en la primera apertura elegi la misma carpeta de OneDrive.
pause
exit /b 0

:error
echo.
echo  Algo fallo durante la instalacion. Sacale una captura a esta ventana y mandala.
pause
exit /b 1
