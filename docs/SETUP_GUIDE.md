# FreePing - Setup Guide

## Prerequisites

1. **Oracle Cloud Account** (Always Free Tier)
   - Go to https://cloud.oracle.com
   - Sign up for the Always Free Tier (no credit card required)
   - Note: Some regions may require a credit card for verification

2. **API Key Configuration**
   - In OCI Console: Profile → API Keys → Add API Key
   - Download the PEM file and configuration
   - Save both files securely

## Installation

### Windows

1. Download the latest `FreePing-Setup.exe` from Releases
2. Run the installer
3. Launch FreePing from the Start Menu

### Linux

```bash
# Download AppImage
wget https://github.com/diegogaleano/FreePing/releases/latest/download/FreePing-x86_64.AppImage
chmod +x FreePing-x86_64.AppImage
./FreePing-x86_64.AppImage
```

### From Source

```bash
git clone https://github.com/diegogaleano/FreePing.git
cd FreePing
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[gui,dev]"
freeping-gui
```

## First-Time Setup

1. Launch FreePing
2. Click "Run Setup Wizard"
3. Follow the 6-step wizard:
   - Welcome
   - Select Region (closest to you)
   - Upload API Key or paste credentials
   - Review configuration
   - Wait for provisioning (~3-5 minutes)
   - Done!

4. Select your game from the dropdown
5. Click "Activate Tunnel"
6. Launch your game and enjoy lower ping!

## Manual Setup (Alternative)

If the automated wizard doesn't work:

1. Create a VM in OCI Console:
   - Shape: VM.Standard.A1.Flex (1 OCPU, 6 GB RAM)
   - Image: Ubuntu 24.04
   - Open port 51820/UDP in security list

2. SSH into the VM and run:
   ```bash
   curl -sL https://raw.githubusercontent.com/diegogaleano/FreePing/main/provisioning/manual_script.sh | sudo bash
   ```

3. Copy the server public key and configure your client

## Troubleshooting

- **"VPS not configured"**: Run the setup wizard
- **Tunnel won't activate**: Check WireGuard is installed
- **High ping**: Try a different region closer to you
- **Instance stopped**: Use the "Restart VPS" option in Settings
