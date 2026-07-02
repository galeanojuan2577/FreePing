from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, StrEnum


class VPSStatus(Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    TERMINATED = "terminated"
    UNKNOWN = "unknown"


class TunnelState(Enum):
    INACTIVE = "inactive"
    CONNECTING = "connecting"
    ACTIVE = "active"
    ERROR = "error"


class GameProtocol(StrEnum):
    UDP = "udp"
    TCP = "tcp"
    BOTH = "both"


@dataclass
class Game:
    name: str
    ip_ranges: list[str] = field(default_factory=list)
    protocols: list[GameProtocol] = field(default_factory=lambda: [GameProtocol.UDP])
    ports: list[str] = field(default_factory=list)

    @classmethod
    def load_from_json(cls, data: dict) -> Game:
        raw = data.get("protocols", ["udp"])
        protocols = []
        for p in raw:
            if isinstance(p, GameProtocol):
                protocols.append(p)
            else:
                protocols.append(GameProtocol(p))

        return cls(
            name=data["name"],
            ip_ranges=data.get("ip_ranges", []),
            protocols=protocols,
            ports=data.get("ports", []),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ip_ranges": self.ip_ranges,
            "protocols": [p.value for p in self.protocols],
            "ports": self.ports,
        }


@dataclass
class GamesList:
    version: int
    games: list[Game] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: dict) -> GamesList:
        games = [Game.load_from_json(g) for g in data.get("games", [])]
        return cls(version=data.get("version", 1), games=games)

    def find_game(self, name: str) -> Game | None:
        for game in self.games:
            if game.name.lower() == name.lower():
                return game
        return None

    def all_ip_ranges(self) -> list[str]:
        result: list[str] = []
        for game in self.games:
            result.extend(game.ip_ranges)
        return result


@dataclass
class TunnelConfig:
    vps_ip: str = ""
    vps_port: int = 51820
    private_key: str = ""
    public_key: str = ""
    client_private_key: str = ""
    client_address: str = "10.0.0.2/32"
    allowed_ips: list[str] = field(default_factory=list)
    dns: str = "1.1.1.1"
    persistent_keepalive: int = 25

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.vps_ip and not self._is_valid_ip_or_hostname(self.vps_ip):
            errors.append(f"Invalid VPS IP: {self.vps_ip}")
        if not (1 <= self.vps_port <= 65535):
            errors.append(f"Invalid port: {self.vps_port}")
        return errors

    @staticmethod
    def _is_valid_ip_or_hostname(value: str) -> bool:
        import ipaddress
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            return "." in value and len(value) > 3

    def to_wireguard_conf(self) -> str:
        allowed = ", ".join(self.allowed_ips) if self.allowed_ips else "0.0.0.0/0"
        return f"""[Interface]
PrivateKey = {self.client_private_key}
Address = {self.client_address}
DNS = {self.dns}

[Peer]
PublicKey = {self.public_key}
Endpoint = {self.vps_ip}:{self.vps_port}
AllowedIPs = {allowed}
PersistentKeepalive = {self.persistent_keepalive}
"""

    def to_dict(self) -> dict:
        return {
            "vps_ip": self.vps_ip,
            "vps_port": self.vps_port,
            "private_key": self.private_key,
            "public_key": self.public_key,
            "client_private_key": self.client_private_key,
            "client_address": self.client_address,
            "allowed_ips": self.allowed_ips,
            "dns": self.dns,
            "persistent_keepalive": self.persistent_keepalive,
        }


@dataclass
class OciCredentials:
    user_ocid: str = ""
    tenancy_ocid: str = ""
    fingerprint: str = ""
    private_key: str = ""
    region: str = "sa-saopaulo-1"

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.user_ocid.startswith("ocid1.user.oc1.."):
            errors.append("Invalid user OCID format")
        if not self.tenancy_ocid.startswith("ocid1.tenancy.oc1.."):
            errors.append("Invalid tenancy OCID format")
        if not self.fingerprint:
            errors.append("Fingerprint is required")
        if "BEGIN PRIVATE KEY" not in self.private_key:
            errors.append("Invalid private key format")
        if not self.region:
            errors.append("Region is required")
        return errors

    def to_dict(self) -> dict:
        return {
            "user_ocid": self.user_ocid,
            "tenancy_ocid": self.tenancy_ocid,
            "fingerprint": self.fingerprint,
            "region": self.region,
        }


@dataclass
class LatencyResult:
    without_tunnel_ms: float | None = None
    with_tunnel_ms: float | None = None

    @property
    def improvement_ms(self) -> float | None:
        if self.without_tunnel_ms is not None and self.with_tunnel_ms is not None:
            return self.without_tunnel_ms - self.with_tunnel_ms
        return None

    @property
    def improvement_pct(self) -> float | None:
        if self.without_tunnel_ms and self.with_tunnel_ms:
            return ((self.without_tunnel_ms - self.with_tunnel_ms) / self.without_tunnel_ms) * 100
        return None

    def to_dict(self) -> dict:
        return {
            "without_tunnel_ms": self.without_tunnel_ms,
            "with_tunnel_ms": self.with_tunnel_ms,
            "improvement_ms": self.improvement_ms,
            "improvement_pct": self.improvement_pct,
        }
