@echo off
chcp 65001 >nul
title YAKU - Prueba privada en celular
cd /d "%~dp0"

rem --- Python 3.13 / 3.12 para el servidor local ---
set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=py"

rem --- cloudflared (se descarga una sola vez, desde el sitio oficial de Cloudflare en GitHub) ---
if not exist "cloudflared.exe" (
  echo Descargando cloudflared - solo la primera vez, unos 60 MB...
  curl -L -o cloudflared.exe https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
  if errorlevel 1 (
    echo No se pudo descargar. Revise su internet y vuelva a intentar.
    pause
    exit /b
  )
)

echo.
echo  ===================================================================
echo   YAKU - PRUEBA PRIVADA (solo entran los correos que usted autorice)
echo  ===================================================================
echo   Escriba los correos del equipo separados por coma, por ejemplo:
echo     ana@gmail.com,luis@gmail.com
echo.
set /p CORREOS=  Correos permitidos: 
if "%CORREOS%"=="" (
  echo Debe escribir al menos un correo.
  pause
  exit /b
)

rem --- servidor local en otra ventana ---
start "YAKU servidor local (no cerrar)" "%PY%" -m http.server 8000
timeout /t 2 >nul

echo.
echo   En unos segundos aparecera abajo un enlace como:
echo       https://palabra-palabra-palabra.trycloudflare.com
echo   1) Abra ese enlace en el celular (Chrome o Safari).
echo   2) Escriba su correo y el codigo que le llega por email.
echo   3) Toque "Instalar app" (iPhone: Compartir - Agregar a inicio).
echo   El enlace funciona mientras estas ventanas esten abiertas.
echo   Para terminar: cierre esta ventana y la del servidor.
echo  ===================================================================
echo.
cloudflared.exe tunnel --url http://localhost:8000 --allowed-mail "%CORREOS%"
pause
