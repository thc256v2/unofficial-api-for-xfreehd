@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0.."
set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"
set "API_DIR=%~dp0backend"
set "UI_DIR=%~dp0frontend"

rem Fresh Explorer/cmd sessions often miss Node; prepend common install dirs.
set "PATH=C:\Program Files\nodejs;%LOCALAPPDATA%\Programs\nodejs;%APPDATA%\npm;%PATH%"

where node >nul 2>&1
if errorlevel 1 (
  echo [!] node.exe not found. Install Node.js LTS from https://nodejs.org/
  echo     or add it to PATH, then re-run this script.
  pause
  exit /b 1
)

if not exist "%VENV_PY%" (
  echo [!] Venv not found at %VENV_PY%
  echo     Run from repo root: uv sync --group gui --group dev
  pause
  exit /b 1
)

if not exist "%UI_DIR%\node_modules\" (
  echo [*] Installing frontend deps...
  pushd "%UI_DIR%"
  call npm.cmd install
  if errorlevel 1 (
    echo [!] npm install failed
    popd
    pause
    exit /b 1
  )
  popd
)

if not exist "%UI_DIR%\node_modules\vite\bin\vite.js" (
  echo [!] Vite is missing under node_modules. Try: cd web\frontend ^&^& npm install
  pause
  exit /b 1
)

echo [*] Starting API on http://127.0.0.1:8787
start "Media Browser API" /D "%API_DIR%" cmd /k ""%VENV_PY%" -m uvicorn main:app --reload --host 127.0.0.1 --port 8787"

echo [*] Starting UI on http://127.0.0.1:5173
rem Call Vite via node.exe directly — avoids npm.cmd PATH/quoting breakage
start "Media Browser UI" /D "%UI_DIR%" cmd /k "set PATH=C:\Program Files\nodejs;%LOCALAPPDATA%\Programs\nodejs;%PATH% && node node_modules\vite\bin\vite.js --host 127.0.0.1 --port 5173"

timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:5173"

echo Done. Close the API / UI windows to stop the servers.
endlocal
