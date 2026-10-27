@echo off
setlocal
cd /d "%~dp0"

rem ============================================================
rem  Nuitka build
rem  Default: single-file exe.
rem  Requires MSVC Build Tools or MinGW64. Nuitka may download
rem  MinGW64 automatically because of --assume-yes-for-downloads.
rem  Output: dist_nuitka\
rem
rem  For a folder build, replace --mode=onefile with --mode=standalone.
rem ============================================================

echo [1/3] Checking Python...
python --version || goto :error

echo [2/3] Installing dependencies...
python -m pip install --disable-pip-version-check -r requirements.txt || goto :error

echo [3/3] Building with Nuitka (this can take several minutes)...
python -m nuitka main.py ^
  --mode=onefile ^
  --enable-plugin=tk-inter ^
  --windows-console-mode=disable ^
  --include-package=winrt ^
  --include-package-data=winrt ^
  --include-module=winrt.windows.media.ocr ^
  --include-module=winrt.windows.graphics.imaging ^
  --include-module=winrt.windows.storage.streams ^
  --include-module=winrt.windows.globalization ^
  --include-module=winrt.windows.foundation ^
  --output-dir=dist_nuitka ^
  --output-filename=GeneralChatbot.exe ^
  --remove-output ^
  --assume-yes-for-downloads || goto :error

echo.
echo Build OK.
rem Onefile mode: copy the config next to the exe for convenience.
if exist "settings.json" copy /Y "settings.json" "dist_nuitka\" >nul
if exist "memory.json" copy /Y "memory.json" "dist_nuitka\" >nul
echo Output: dist_nuitka\GeneralChatbot.exe
goto :eof

:error
echo.
echo Build FAILED.
exit /b 1
