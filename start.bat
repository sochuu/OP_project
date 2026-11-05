@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Prognoz nalogov

:menu
cls
echo ========================================
echo  Prognoz nalogov — lokal'nyy zapusk
echo ========================================
echo  1. Ustanovit' (venv + pip)
echo  2. Sozdat' kod dostupa
echo  3. Zapustit' server  http://127.0.0.1:8000
echo  4. Ustanovit' + kod + server
echo  0. Vykhod
echo ========================================
set /p CHOICE="Nomer: "

if "%CHOICE%"=="1" goto install
if "%CHOICE%"=="2" goto code
if "%CHOICE%"=="3" goto run
if "%CHOICE%"=="4" goto all
if "%CHOICE%"=="0" exit /b 0
goto menu

:findpy
where py >nul 2>&1
if %ERRORLEVEL%==0 (
  set "PY=py -3"
  exit /b 0
)
where python >nul 2>&1
if %ERRORLEVEL%==0 (
  set "PY=python"
  exit /b 0
)
echo Python 3 ne nayden. Postav'te python.org i otmet'te "Add to PATH".
pause
exit /b 1

:install
echo === Ustanovka: venv + zavisimosti ===
call :findpy
if errorlevel 1 goto menu
if not exist ".venv\Scripts\python.exe" (
  echo Sozdayu .venv ...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Ne udalos' sozdat' venv.
    pause
    goto menu
  )
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo pip install ne udalsya.
  pause
  goto menu
)
if not exist ".env" (
  if exist ".env.example" copy /Y ".env.example" ".env" >nul
  echo Sozdan .env iz .env.example
)
if not exist "data" mkdir data
echo Gotovo.
pause
goto menu

:needvenv
if exist ".venv\Scripts\python.exe" exit /b 0
echo Snachala vyberite punkt 1 (ustanovka).
pause
exit /b 1

:code
call :needvenv
if errorlevel 1 goto menu
echo === Novyy produktovyy kod ===
echo Heshe: data\product_codes.txt
echo Kod vvedite na /login
echo.
".venv\Scripts\python.exe" scripts\issue_code.py
if errorlevel 1 (
  echo Oshibka generacii.
  pause
  goto menu
)
echo.
echo Skopiruyte kod.
pause
goto menu

:run
call :needvenv
if errorlevel 1 goto menu
echo http://127.0.0.1:8000
echo Ostanovka: Ctrl+C
echo.
".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
pause
goto menu

:all
call :findpy
if errorlevel 1 goto menu
if not exist ".venv\Scripts\python.exe" (
  echo Sozdayu .venv ...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Ne udalos' sozdat' venv.
    pause
    goto menu
  )
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo pip install ne udalsya.
  pause
  goto menu
)
if not exist ".env" (
  if exist ".env.example" copy /Y ".env.example" ".env" >nul
)
if not exist "data" mkdir data
echo.
".venv\Scripts\python.exe" scripts\issue_code.py
echo.
echo http://127.0.0.1:8000   Ctrl+C — stop
echo.
".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
pause
goto menu
