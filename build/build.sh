#!/usr/bin/env bash
# FreePing Build Script — Linux
set -euo pipefail

echo "=== FreePing Linux Build ==="
echo ""

# Check prerequisites
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found"; exit 1; }

# Create venv if needed
if [ ! -d "venv" ]; then
    echo "Creating build virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --quiet pyinstaller PySide6 httpx PyYAML cryptography

# Install FreePing
pip install -e ..

# Build
echo "Building executable..."
pyinstaller freeping.spec

echo ""
echo "=== Build Complete ==="
echo "Output: dist/freeping"
ls -lh dist/ 2>/dev/null || true
