@echo off
setlocal
cd /d "%~dp0"

rem ============================================================
rem  PyInstaller build
rem  Default: single-file exe (onefile).
rem  To build a folder instead, set ONEFILE_FLAG to empty below.
rem  Output: dist_pyinstaller\
rem ============================================================

set "APP_NAME=GeneralChatbot"
set "ONEFILE_FLAG=--onefile"

echo [1/3] Checking Python...
python --version || goto :error

echo [2/3] Installing dependencies...
python -m pip install --disable-pip-version-check -r requirements.txt || goto :error

if not exist "build" mkdir "build"

echo [3/3] Building with PyInstaller...
python -m PyInstaller --noconfirm --clean --windowed ^
  --name "%APP_NAME%" ^
  %ONEFILE_FLAG% ^
  --collect-all winrt ^
  --hidden-import=winrt.windows.media.ocr ^
  --hidden-import=winrt.windows.graphics.imaging ^
  --hidden-import=winrt.windows.storage.streams ^
  --hidden-import=winrt.windows.globalization ^
  --hidden-import=winrt.windows.foundation ^
  --distpath "dist_pyinstaller" ^
  --workpath "build\pyinstaller" ^
  --specpath "build" ^
  main.py || goto :error

echo.
echo Build OK.
if defined ONEFILE_FLAG (
  set "OUT_DIR=dist_pyinstaller"
) else (
  set "OUT_DIR=dist_pyinstaller\%APP_NAME%"
)

if exist "settings.json" copy /Y "settings.json" "%OUT_DIR%\" >nul
if exist "memory.json" copy /Y "memory.json" "%OUT_DIR%\" >nul

if defined ONEFILE_FLAG (
  echo Output: dist_pyinstaller\%APP_NAME%.exe
) else (
  echo Output: dist_pyinstaller\%APP_NAME%\%APP_NAME%.exe
)
goto :eof

:error
echo.
echo Build FAILED.
exit /b 1
