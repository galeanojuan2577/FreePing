from __future__ import annotations

import json
import os
import platform
from pathlib import Path

from freeping.core.models import OciCredentials, TunnelConfig


class AppConfig:
    _config_dir: Path | None = None

    @classmethod
    def config_dir(cls) -> Path:
        if cls._config_dir is not None:
            return cls._config_dir
        if platform.system() == "Windows":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        else:
            base = Path.home() / ".config"
        return base / "freeping"

    @classmethod
    def config_file(cls) -> Path:
        return cls.config_dir() / "config.json"

    @classmethod
    def tunnel_file(cls) -> Path:
        return cls.config_dir() / "tunnel.conf"

    @classmethod
    def credentials_file(cls) -> Path:
        return cls.config_dir() / "credentials.json"

    def __init__(self) -> None:
        self.vps_ip: str = ""
        self.vps_id: str = ""
        self.vps_region: str = ""
        self.selected_game: str = ""
        self.tunnel: TunnelConfig = TunnelConfig()
        self.oci_credentials: OciCredentials = OciCredentials()
        self.auto_reconnect: bool = True
        self.minimize_to_tray: bool = True
        self.start_on_boot: bool = False

    @classmethod
    def load(cls) -> AppConfig:
        config = cls()
        if cls.config_file().exists():
            try:
                data = json.loads(cls.config_file().read_text())
                config.vps_ip = data.get("vps_ip", "")
                config.vps_id = data.get("vps_id", "")
                config.vps_region = data.get("vps_region", "")
                config.selected_game = data.get("selected_game", "")
                config.auto_reconnect = data.get("auto_reconnect", True)
                config.minimize_to_tray = data.get("minimize_to_tray", True)
                config.start_on_boot = data.get("start_on_boot", False)

                tunnel_data = data.get("tunnel", {})
                if tunnel_data:
                    config.tunnel = TunnelConfig(**tunnel_data)

                cred_data = data.get("oci_credentials", {})
                if cred_data:
                    config.oci_credentials = OciCredentials(**cred_data)
            except (json.JSONDecodeError, KeyError):
                pass
        if cls.credentials_file().exists():
            try:
                cred_data = json.loads(cls.credentials_file().read_text())
                config.oci_credentials = OciCredentials(**cred_data)
            except (json.JSONDecodeError, KeyError):
                pass
        return config

    def save(self) -> None:
        self.config_dir().mkdir(parents=True, exist_ok=True)
        data = {
            "vps_ip": self.vps_ip,
            "vps_id": self.vps_id,
            "vps_region": self.vps_region,
            "selected_game": self.selected_game,
            "auto_reconnect": self.auto_reconnect,
            "minimize_to_tray": self.minimize_to_tray,
            "start_on_boot": self.start_on_boot,
            "tunnel": self.tunnel.to_dict(),
        }
        self.config_file().write_text(json.dumps(data, indent=2))

    def save_credentials(self) -> None:
        self.config_dir().mkdir(parents=True, exist_ok=True)
        creds = self.oci_credentials.to_dict()
        self.credentials_file().write_text(json.dumps(creds, indent=2))
        if platform.system() != "Windows":
            os.chmod(self.credentials_file(), 0o600)

    def save_tunnel_conf(self) -> None:
        self.config_dir().mkdir(parents=True, exist_ok=True)
        conf = self.tunnel.to_wireguard_conf()
        self.tunnel_file().write_text(conf)

    def is_configured(self) -> bool:
        return bool(self.vps_ip)

    def clear(self) -> None:
        self.vps_ip = ""
        self.vps_id = ""
        self.vps_region = ""
        self.selected_game = ""
        self.tunnel = TunnelConfig()
        self.oci_credentials = OciCredentials()
        if self.config_file().exists():
            self.config_file().unlink()
        if self.tunnel_file().exists():
            self.tunnel_file().unlink()
        if self.credentials_file().exists():
            self.credentials_file().unlink()

    def get_oci_private_key_path(self) -> Path | None:
        key_path = self.config_dir() / "oci_api_key.pem"
        if key_path.exists():
            return key_path
        return None
