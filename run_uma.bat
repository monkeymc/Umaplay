@echo off
setlocal ENABLEDELAYEDEXPANSION

title Umaplay Launcher

:: --- cd to script folder ---
cd /d "%~dp0"

:: --- ensure Python exists ---
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
if not defined PY_VER (
  echo [Error] Python not found on PATH.
  echo Please install Python 3.10 or newer from: https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

echo Detected Python version %PY_VER%

:: --- create venv if missing ---
if not exist .venv (
  echo [Setup] Creating virtual environment...
  python -m venv .venv
)

:: --- activate venv ---
call ".venv\Scripts\activate.bat"

:: --- install deps only once ---
if not exist .venv\.deps_installed (
  echo [Setup] Installing requirements (first run may take a minute)...
  python -m pip install -U pip
  if exist requirements.txt (
    pip install -r requirements.txt || (
      echo [Error] Failed to install requirements.
      pause
      exit /b 1
    )
  )
  echo done > .venv\.deps_installed
)

:: --- open Web UI ---
start "" "http://127.0.0.1:8000/"

:: --- run app ---
echo [Run] Launching Umaplay...
python main.py

echo [Exit] Umaplay stopped.
pause
