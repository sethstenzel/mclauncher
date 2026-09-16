@echo off
REM Build a release .exe for this Windows machine into .\releases.
REM
REM   packaging\windows\build-release.bat              patch bump (1.1.3 -> 1.1.4)
REM   packaging\windows\build-release.bat minor        1.1.3 -> 1.2.0
REM   packaging\windows\build-release.bat major        1.1.3 -> 2.0.0
REM   packaging\windows\build-release.bat --set 2.0.0  exact version
REM   packaging\windows\build-release.bat --no-bump    rebuild the current version
REM   packaging\windows\build-release.bat --dry-run    show the plan only
REM   packaging\windows\build-release.bat patch --tag  also create a git tag
REM
REM The result is releases\MCLauncher-<version>-windows-<arch>.exe, a single
REM self-contained file. There is nothing to install: copy it where you like.
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

if not exist "src\mclauncher\assets\icon.ico" goto makeicons
if not exist "src\mclauncher\assets\icon.png" goto makeicons
goto build

:makeicons
echo [MCLauncher] generating icons...
uv run --with pillow python tools\make_icon.py

:build
echo [MCLauncher] starting release build ^(this takes several minutes^)...
uv run python tools\release.py %*
if errorlevel 1 (
  echo.
  echo [MCLauncher] release FAILED - version numbers were rolled back.
  pause
  exit /b 1
)

echo.
echo [MCLauncher] done. The executable is in the releases folder.
pause
