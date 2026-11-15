@echo off
chcp 65001 >nul
title YAKU v06 - Bofedales con NISAR
cd /d "%~dp0"

if not exist "Yaku_v06.py" (
  echo.
  echo  No encuentro el archivo Yaku_v06.py en esta carpeta:
  echo  %~dp0
  echo  Ponga INICIAR_YAKU_v06.bat y Yaku_v06.py en la MISMA carpeta.
  echo.
  pause
  exit /b
)

set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if exist "%PY%" goto correr

set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist "%PY%" goto correr

where py >nul 2>nul
if %errorlevel%==0 (
  py -3.13 -c "print()" >nul 2>nul && (set "PY=py -3.13" & goto correr)
  py -3.12 -c "print()" >nul 2>nul && (set "PY=py -3.12" & goto correr)
)

echo.
echo  No encontre Python 3.13 ni 3.12 en esta computadora.
echo  Instale Python 3.13 desde https://www.python.org/downloads/
echo  (marque la casilla "Add python.exe to PATH") y vuelva a abrir este archivo.
echo.
pause
exit /b

:correr
%PY% Yaku_v06.py
echo.
pause
