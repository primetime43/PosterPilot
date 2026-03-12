@echo off
echo Building PosterPilot Windows EXE...
echo.

:: Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    pause
    exit /b 1
)

:: Install dependencies
echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

:: Build
echo.
echo Building with PyInstaller...
pyinstaller posterpilot.spec --clean

echo.
if exist "dist\PosterPilot.exe" (
    echo Build successful! EXE is at: dist\PosterPilot.exe
    echo.
    echo To run: dist\PosterPilot.exe
    echo The app will open at http://127.0.0.1:8888
) else (
    echo Build failed. Check the output above for errors.
)

pause
