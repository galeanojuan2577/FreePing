@echo off
REM FreePing Build Script — Windows
echo === FreePing Windows Build ===
echo.

REM Check Python
where python >nul 2>nul || (
    echo ERROR: Python not found
    exit /b 1
)

REM Create venv if needed
if not exist "venv" (
    echo Creating build virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
pip install --quiet pyinstaller PySide6 httpx PyYAML cryptography

REM Install FreePing
pip install -e ..

REM Build
echo Building executable...
pyinstaller freeping.spec

echo.
echo === Build Complete ===
echo Output: dist\FreePing\
