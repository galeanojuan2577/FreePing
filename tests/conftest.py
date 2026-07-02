from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from freeping.core.config import AppConfig
from freeping.core.models import (
    OciCredentials,
    TunnelConfig,
)


@pytest.fixture
def sample_game_data() -> dict:
    return {
        "name": "TestGame",
        "protocols": ["udp"],
        "ports": ["7000-7500"],
        "ip_ranges": ["192.168.1.0/24", "10.0.0.0/8"],
    }


@pytest.fixture
def sample_games_list_data() -> dict:
    return {
        "version": 1,
        "games": [
            {"name": "Game1", "protocols": ["udp"], "ip_ranges": ["10.0.0.0/8"]},
            {"name": "Game2", "protocols": ["tcp"], "ip_ranges": ["192.168.0.0/16"]},
        ],
    }


@pytest.fixture
def sample_tunnel_config() -> TunnelConfig:
    return TunnelConfig(
        vps_ip="203.0.113.1",
        vps_port=51820,
        private_key="server_priv_key",
        public_key="server_pub_key",
        client_private_key="client_priv_key",
        allowed_ips=["10.0.0.0/8"],
    )


@pytest.fixture
def sample_credentials() -> OciCredentials:
    return OciCredentials(
        user_ocid="ocid1.user.oc1..aaaaaaaaxxxxxxxxxxxxxx",
        tenancy_ocid="ocid1.tenancy.oc1..aaaaaaaaxxxxxxxxxxxxxx",
        fingerprint="12:34:56:78:90:ab:cd:ef:01:23:45:67:89:0a:bc:de",
        private_key="-----BEGIN PRIVATE KEY-----\nMOCKKEY\n-----END PRIVATE KEY-----",
        region="sa-saopaulo-1",
    )


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Generator[Path, None, None]:
    original = AppConfig._config_dir
    AppConfig._config_dir = tmp_path / ".config" / "freeping"
    yield AppConfig._config_dir
    AppConfig._config_dir = original


@pytest.fixture
def app_config(temp_config_dir: Path) -> AppConfig:
    return AppConfig.load()


@pytest.fixture
def rsa_oci_credentials() -> OciCredentials:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    return OciCredentials(
        user_ocid="ocid1.user.oc1..test",
        tenancy_ocid="ocid1.tenancy.oc1..test",
        fingerprint="00:00:00:00",
        private_key=pem,
        region="sa-saopaulo-1",
    )
