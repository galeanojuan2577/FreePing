@echo off
chcp 65001 >nul
title FreePing Build — Windows
echo === FreePing — Build para Windows ===
echo.
echo Requisitos:
echo   - Python 3.12+
echo   - PyInstaller (pip install pyinstaller)
echo   - Opcional: Inno Setup 6+ (https://jrsoftware.org/isdl.php)
echo.

REM ─── Verificar Python ─────────────────────────────────────────
where python >nul 2>nul || (
    echo ERROR: Python no encontrado
    pause
    exit /b 1
)
python --version

REM ─── Instalar dependencias ────────────────────────────────────
echo.
echo Instalando dependencias...
pip install pyinstaller PySide6 httpx PyYAML cryptography

REM ─── Generar icono ────────────────────────────────────────────
echo.
echo Generando icono...
python generate_icon.py

REM ─── Construir .exe ───────────────────────────────────────────
echo.
echo Construyendo ejecutable con PyInstaller...
cd /d "%~dp0"
pyinstaller freeping.spec

if %errorlevel% neq 0 (
    echo ERROR: PyInstaller fallo
    pause
    exit /b 1
)

echo.
echo OK: Ejecutable creado en dist\FreePing\FreePing.exe

REM ─── Construir instalador (Inno Setup) ────────────────────────
where iscc >nul 2>nul
if %errorlevel% equ 0 (
    echo.
    echo Construyendo instalador con Inno Setup...
    iscc installer.iss
    if %errorlevel% equ 0 (
        echo OK: Instalador creado en dist\FreePing_Setup_v0.1.0.exe
    ) else (
        echo ERROR: Inno Setup fallo
    )
) else (
    echo.
    echo NOTA: Inno Setup no encontrado. Para crear el instalador:
    echo   1. Descarga: https://jrsoftware.org/isdl.php
    echo   2. Ejecuta: iscc installer.iss
    echo.
    echo El ejecutable portable esta en: dist\FreePing\FreePing.exe
)

echo.
echo === Build Completo ===
pause