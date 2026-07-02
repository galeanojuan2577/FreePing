from __future__ import annotations

import json
from pathlib import Path

from freeping.core.config import AppConfig
from freeping.core.models import OciCredentials, TunnelConfig


class TestAppConfig:
    def test_load_returns_defaults_when_no_file(self, temp_config_dir: Path) -> None:
        config = AppConfig.load()
        assert config.vps_ip == ""
        assert config.vps_id == ""
        assert not config.is_configured()

    def test_save_and_load(self, temp_config_dir: Path) -> None:
        config = AppConfig.load()
        config.vps_ip = "203.0.113.1"
        config.vps_id = "ocid1.instance.xxx"
        config.selected_game = "Valorant"
        config.tunnel.vps_ip = "203.0.113.1"
        config.save()

        loaded = AppConfig.load()
        assert loaded.vps_ip == "203.0.113.1"
        assert loaded.vps_id == "ocid1.instance.xxx"
        assert loaded.selected_game == "Valorant"
        assert loaded.is_configured()

    def test_save_credentials(self, temp_config_dir: Path) -> None:
        config = AppConfig.load()
        config.oci_credentials = OciCredentials(
            user_ocid="ocid1.user.oc1..test",
            tenancy_ocid="ocid1.tenancy.oc1..test",
            fingerprint="ab:cd:ef",
            region="sa-saopaulo-1",
        )
        config.save_credentials()

        loaded = AppConfig.load()
        assert loaded.oci_credentials.user_ocid == "ocid1.user.oc1..test"
        assert loaded.oci_credentials.region == "sa-saopaulo-1"

    def test_save_tunnel_conf(self, temp_config_dir: Path) -> None:
        config = AppConfig.load()
        config.tunnel = TunnelConfig(
            vps_ip="203.0.113.1",
            client_private_key="client_priv",
            public_key="server_pub",
            allowed_ips=["10.0.0.0/8"],
        )
        config.save_tunnel_conf()

        conf_path = AppConfig.tunnel_file()
        assert conf_path.exists()
        content = conf_path.read_text()
        assert "PrivateKey = client_priv" in content
        assert "Endpoint = 203.0.113.1:51820" in content

    def test_clear_removes_all_files(self, temp_config_dir: Path) -> None:
        config = AppConfig.load()
        config.vps_ip = "203.0.113.1"
        config.save()
        config.save_credentials()
        config.save_tunnel_conf()

        config.clear()
        assert not config.is_configured()
        assert not AppConfig.config_file().exists()
        assert not AppConfig.tunnel_file().exists()
        assert not AppConfig.credentials_file().exists()

    def test_is_configured_returns_false_when_no_vps(self, temp_config_dir: Path) -> None:
        config = AppConfig.load()
        assert not config.is_configured()

    def test_is_configured_returns_true_with_vps(self, temp_config_dir: Path) -> None:
        config = AppConfig.load()
        config.vps_ip = "203.0.113.1"
        config.save()

        loaded = AppConfig.load()
        assert loaded.is_configured()

    def test_corrupted_json_returns_defaults(self, temp_config_dir: Path) -> None:
        config_path = AppConfig.config_dir() / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("this is not json")

        config = AppConfig.load()
        assert config.vps_ip == ""

    def test_credentials_file_overrides_embedded(self, temp_config_dir: Path) -> None:
        config = AppConfig.load()
        config.oci_credentials.user_ocid = "ocid1.user.oc1..old"
        config.save()

        cred_path = AppConfig.credentials_file()
        cred_path.parent.mkdir(parents=True, exist_ok=True)
        cred_path.write_text(json.dumps({"user_ocid": "ocid1.user.oc1..new"}))

        loaded = AppConfig.load()
        assert loaded.oci_credentials.user_ocid == "ocid1.user.oc1..new"
