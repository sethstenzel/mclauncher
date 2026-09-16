@echo off
REM Run MCLauncher from source, for development.
REM
REM   packaging\windows\run.bat            open the launcher window
REM   packaging\windows\run.bat --web      open it in your normal browser instead
REM   packaging\windows\run.bat --port N   pin the server port
setlocal
cd /d "%~dp0..\.."

where uv >nul 2>nul
if errorlevel 1 (
  echo [MCLauncher] uv is not installed or not on PATH.
  echo Install it from https://docs.astral.sh/uv/ then run this file again.
  pause
  exit /b 1
)

echo [MCLauncher] syncing environment...
uv sync --quiet
if errorlevel 1 (
  echo [MCLauncher] uv sync failed.
  pause
  exit /b 1
)

echo [MCLauncher] starting...
uv run --quiet python -m mclauncher %*
if errorlevel 1 (
  echo [MCLauncher] exited with an error.
  pause
)
