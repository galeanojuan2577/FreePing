#!/usr/bin/env bash
# FreePing Build Script — Linux
set -euo pipefail

echo "=== FreePing — Build para Linux ==="
echo ""

cd "$(dirname "$0")"

# Check prerequisites
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found"; exit 1; }

# Install dependencies
echo "Instalando dependencias..."
pip install --quiet pyinstaller PySide6 httpx PyYAML cryptography

# Generate icon
echo "Generando icono..."
python3 generate_icon.py

# Build
echo ""
echo "Construyendo ejecutable con PyInstaller..."
pyinstaller freeping.spec

echo ""
echo "=== Build Complete ==="
echo "Output: dist/freeping"
ls -lh dist/ 2>/dev/null || true