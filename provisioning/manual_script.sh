#!/bin/bash
# FreePing - Manual VPS Setup Script
# Run this on your Oracle Cloud Ubuntu 24.04 instance
# Usage: curl -sL https://raw.githubusercontent.com/diegogaleano/FreePing/main/provisioning/manual_script.sh | sudo bash

set -e

echo "=== FreePing VPS Setup ==="

# 1. Install WireGuard
apt-get update
apt-get install -y wireguard ufw net-tools

# 2. Generate server keys
wg genkey | tee /etc/wireguard/server_private.key | wg pubkey > /etc/wireguard/server_public.key
SERVER_PRIV=$(cat /etc/wireguard/server_private.key)
SERVER_PUB=$(cat /etc/wireguard/server_public.key)

echo "Server Public Key: $SERVER_PUB"

# 3. Prompt for client public key
read -p "Enter your client public key: " CLIENT_PUB

# 4. Configure WireGuard
cat > /etc/wireguard/wg0.conf << WGEOF
[Interface]
PrivateKey = $SERVER_PRIV
Address = 10.0.0.1/24
ListenPort = 51820
SaveConfig = false
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o ens3 -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o ens3 -j MASQUERADE

[Peer]
PublicKey = $CLIENT_PUB
AllowedIPs = 10.0.0.2/32
WGEOF

# 5. Enable IP forwarding
sysctl -w net.ipv4.ip_forward=1
echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf

# 6. Configure firewall
ufw allow 51820/udp comment 'WireGuard'
ufw --force enable

# 7. Enable and start WireGuard
systemctl enable wg-quick@wg0
systemctl start wg-quick@wg0

echo ""
echo "=== Setup Complete ==="
echo "Server Public Key: $SERVER_PUB"
echo "WireGuard is running on port 51820/udp"
echo ""
echo "Add this to your client config:"
echo "[Interface]"
echo "PrivateKey = <your-client-private-key>"
echo "Address = 10.0.0.2/32"
echo "DNS = 1.1.1.1"
echo ""
echo "[Peer]"
echo "PublicKey = $SERVER_PUB"
echo "Endpoint = $(curl -s ifconfig.me):51820"
echo "AllowedIPs = <game-server-ips>"
echo "PersistentKeepalive = 25"
