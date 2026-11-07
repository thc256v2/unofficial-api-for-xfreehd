@echo off
setlocal
cd /d "%~dp0"

set "ROOT=%~dp0.."
set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"
set "API_DIR=%~dp0backend"
set "UI_DIR=%~dp0frontend"

if not exist "%VENV_PY%" (
  echo [!] Venv not found at %VENV_PY%
  echo     Run from repo root: uv sync --group gui --group dev
  pause
  exit /b 1
)

if not exist "%UI_DIR%\node_modules\" (
  echo [*] Installing frontend deps...
  pushd "%UI_DIR%"
  call npm install
  if errorlevel 1 (
    echo [!] npm install failed
    popd
    pause
    exit /b 1
  )
  popd
)

echo [*] Starting API on http://127.0.0.1:8787
start "Media Browser API" /D "%API_DIR%" cmd /k ""%VENV_PY%" -m uvicorn main:app --reload --host 127.0.0.1 --port 8787"

echo [*] Starting UI on http://127.0.0.1:5173
start "Media Browser UI" /D "%UI_DIR%" cmd /k "npm run dev"

timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:5173"

echo Done. Close the API / UI windows to stop the servers.
endlocal
