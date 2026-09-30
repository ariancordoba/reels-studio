@echo off
chcp 65001 >nul
title Reels Studio - Desinstalar
echo.
echo  Esto borra el programa Reels Studio de esta compu.
echo  Tus proyectos, clientes y videos NO se borran (quedan en tu carpeta de OneDrive/Documentos).
echo.
choice /C SN /M "¿Seguro que querés desinstalar"
if errorlevel 2 exit /b 0
taskkill /F /IM pythonw.exe /FI "WINDOWTITLE eq Reels Studio" >nul 2>nul
del "%USERPROFILE%\Desktop\Reels Studio.lnk" >nul 2>nul
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Reels Studio.lnk" >nul 2>nul
rmdir /S /Q "%LOCALAPPDATA%\ReelsStudio\cache" >nul 2>nul
echo  Listo. Borrá esta carpeta para terminar: %~dp0
pause
