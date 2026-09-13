@echo off
setlocal
cd /d "%~dp0"

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
