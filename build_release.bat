@echo off
setlocal
cd /d "%~dp0"

REM Build a release exe into .eleases and bump the version number.
REM   build_release.bat              patch bump  (1.0.0 -> 1.0.1)
REM   build_release.bat minor        minor bump  (1.0.3 -> 1.1.0)
REM   build_release.bat major        major bump  (1.4.2 -> 2.0.0)
REM   build_release.bat --set 2.0.0  use an exact version
REM   build_release.bat --no-bump    rebuild the current version
REM   build_release.bat --dry-run    show the plan only
REM   build_release.bat patch --tag  also create a git tag

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

echo [MCLauncher] starting release build ^(this takes several minutes^)...
uv run python tools/release.py %*
if errorlevel 1 (
  echo.
  echo [MCLauncher] release FAILED - version numbers were rolled back.
  pause
  exit /b 1
)

echo.
echo [MCLauncher] done. The executable is in the releases folder.
pause
