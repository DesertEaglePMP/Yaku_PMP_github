@echo off
chcp 65001 >nul
title YAKU - Vista previa local
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=py"
echo.
echo  ============================================================
echo   YAKU - vista previa en su computadora
echo  ============================================================
echo   Se abrira el navegador en:  http://localhost:8000
echo.
echo   Para verla en un CELULAR conectado al MISMO Wi-Fi, abra en el celular:
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do echo        http://%%a:8000  (sin espacios)
echo   (en el celular se ve completa; el boton "Instalar" aparece recien
echo    cuando la app este publicada en GitHub Pages con https)
echo.
echo   Para terminar: cierre esta ventana.
echo  ============================================================
start "" http://localhost:8000
"%PY%" -m http.server 8000
pause
