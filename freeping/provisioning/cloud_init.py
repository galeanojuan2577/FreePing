from __future__ import annotations

import textwrap

import yaml


class CloudInitGenerator:
    def __init__(
        self,
        server_private_key: str,
        server_public_key: str,
        client_public_key: str,
        vps_port: int = 51820,
        vps_network: str = "10.0.0.0/24",
        vps_address: str = "10.0.0.1/24",
    ) -> None:
        self.server_private_key = server_private_key
        self.server_public_key = server_public_key
        self.client_public_key = client_public_key
        self.vps_port = vps_port
        self.vps_network = vps_network
        self.vps_address = vps_address

    def render(self) -> str:
        cloud_cfg = {
            "package_update": True,
            "package_upgrade": False,
            "packages": ["wireguard", "ufw", "net-tools"],
            "write_files": [
                {
                    "path": "/etc/wireguard/wg0.conf",
                    "content": self._wg_conf(),
                    "permissions": "0600",
                },
                {
                    "path": "/usr/local/bin/freeping-keepalive.sh",
                    "content": self._keepalive_script(),
                    "permissions": "0755",
                },
            ],
            "runcmd": [
                ["sysctl", "-w", "net.ipv4.ip_forward=1"],
                ["sh", "-c", "echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf"],
                ["sysctl", "-p"],
                ["ufw", "allow", str(self.vps_port), "comment", "WireGuard"],
                ["ufw", "--force", "enable"],
                ["systemctl", "enable", "wg-quick@wg0"],
                ["systemctl", "start", "wg-quick@wg0"],
                ["sh", "-c",
                 "(crontab -l 2>/dev/null; "
                 "echo '*/30 * * * * /usr/local/bin/freeping-keepalive.sh "
                 ">/dev/null 2>&1') | crontab -"],
            ],
        }
        return "#cloud-config\n" + yaml.dump(cloud_cfg, default_flow_style=False, sort_keys=False)

    def _wg_conf(self) -> str:
        return textwrap.dedent(f"""[Interface]
PrivateKey = {self.server_private_key}
Address = {self.vps_address}
ListenPort = {self.vps_port}
SaveConfig = false
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o ens3 -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o ens3 -j MASQUERADE

[Peer]
PublicKey = {self.client_public_key}
AllowedIPs = {self.vps_address.split('/')[0]}/32
""")

    def _keepalive_script(self) -> str:
        return textwrap.dedent("""\
            #!/bin/bash
            # FreePing Keep-Alive: previene que Oracle reclame instancias inactivas
            # Genera CPU ligero + tráfico de red cada 30 minutos

            # CPU load: calcular primos por 10 segundos
            timeout 10 python3 -c "
            import math
            for i in range(2, 50000):
                is_prime = True
                for j in range(2, int(math.sqrt(i)) + 1):
                    if i % j == 0:
                        is_prime = False
                        break
            " 2>/dev/null

            # Network activity: consultar metadata de Oracle
            curl -sf -H \"Authorization: Bearer Oracle\" \
                http://169.254.169.254/opc/v2/instance/ >/dev/null 2>&1 || true

            logger -t freeping-keepalive \"Keep-alive cycle completed at $(date -u +%Y-%m-%dT%H:%M:%SZ)\"
        """)
