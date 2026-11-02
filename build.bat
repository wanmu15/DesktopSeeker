@echo off
setlocal
cd /d "%~dp0"

if not exist ".pack-venv\Scripts\python.exe" (
    echo [1/3] creating packaging environment...
    python -m venv ".pack-venv" || goto :error
    ".pack-venv\Scripts\python.exe" -m pip install --no-cache-dir --disable-pip-version-check "pyside6-essentials" pyinstaller || goto :error
) else (
    echo [1/3] reusing packaging environment.
)

rem 构建配置（精简组件、ffi.dll、图标）统一在 DesktopSeeker.spec 中维护
echo [2/3] building DesktopSeeker.exe...
".pack-venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean DesktopSeeker.spec || goto :error

echo [3/3] packing zip...
powershell -NoProfile -Command "Compress-Archive -Path '.\dist\DesktopSeeker.exe' -DestinationPath '.\dist\DesktopSeeker_v2.0.zip' -CompressionLevel Optimal -Force" || goto :error

echo.
echo Done: dist\DesktopSeeker.exe and dist\DesktopSeeker_v2.0.zip
exit /b 0

:error
echo.
echo Build failed.
exit /b 1
