@echo off
setlocal
title AOP seed kernel
cd /d "%~dp0"
echo AOP seed kernel - starting control panel
echo.
where py >nul 2>&1 && (set "PY=py -3") || (where python >nul 2>&1 && (set "PY=python") || (set "PY="))
if "%PY%"=="" (
  echo Python 3 was not found. Installing Python 3.12 with winget ^(you may be asked to confirm^)...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  if errorlevel 1 (
    echo Automatic install failed. Install Python 3.12 from https://www.python.org/downloads/windows/ ^(tick "Add python.exe to PATH"^), then run this file again.
    pause & exit /b 1
  )
  set "PY=py -3"
  echo Python installed. If the next step says python is not found, close this window and run this file again.
)
%PY% -c "import sys; assert sys.version_info >= (3, 10), sys.version" 2>nul || (echo Python 3.10 or newer is required. & pause & exit /b 1)
%PY% -c "import pytest" 2>nul || (echo Installing the test dependency ^(pytest^)... & %PY% -m pip install --quiet pytest)
%PY% -c "import tomllib" 2>nul || %PY% -c "import tomli" 2>nul || %PY% -m pip install --quiet tomli
if not exist state (
  echo First start: running the self-tests once ^(about 30 seconds^)...
  %PY% -m pytest -q -p no:cacheprovider
  if errorlevel 1 (echo Self-tests failed; the kernel will not start. Send the output above to the reviewer. & pause & exit /b 1)
  %PY% -m kernel init >nul
)
echo.
echo Opening the control panel in your browser at http://127.0.0.1:8765/
echo Keep this window open while you work. Close it ^(or press Ctrl-C^) to stop the panel.
echo.
%PY% -m kernel ui
pause
