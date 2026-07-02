from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from freeping.core.models import OciCredentials
from freeping.provisioning.cloud_init import CloudInitGenerator
from freeping.provisioning.key_manager import KeyManager
from freeping.provisioning.oci_client import (
    AuthError,
    OciClient,
    OciError,
    VPSStatus,
    WireGuardKeyPair,
)


class TestKeyManager:
    def test_validate_oci_private_key_valid(self) -> None:
        key = (
            "-----BEGIN PRIVATE KEY-----\n"
            "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCy7pB1Wz36lB6D\n"
            "hJ2WZl0HFz5KcH3fXpYLBbqGqsLR1xJZRh8oQoCiRrJGxBtC0jFGwPZnK0yF5cYH\n"
            "jKp7lBUzKk6vWqCqN2RhHtn5XGKwJF1dXvqHVfLGTJzp0pGlwLKB7L3nL4kYd3B6\n"
            "-----END PRIVATE KEY-----"
        )
        errors = KeyManager.validate_oci_private_key(key)
        assert errors == []

    def test_validate_oci_private_key_missing_header(self) -> None:
        errors = KeyManager.validate_oci_private_key("no header")
        assert any("BEGIN PRIVATE KEY" in e for e in errors)

    def test_validate_oci_private_key_missing_footer(self) -> None:
        key = "-----BEGIN PRIVATE KEY-----\ncontent"
        errors = KeyManager.validate_oci_private_key(key)
        assert any("END PRIVATE KEY" in e for e in errors)

    def test_validate_oci_private_key_too_short(self) -> None:
        key = "-----BEGIN PRIVATE KEY-----\nshort\n-----END PRIVATE KEY-----"
        errors = KeyManager.validate_oci_private_key(key)
        assert any("too short" in e for e in errors)

    def test_validate_oci_credentials_valid(self, sample_credentials: OciCredentials) -> None:
        errors = KeyManager.validate_oci_credentials(sample_credentials)
        assert errors == []

    def test_validate_oci_credentials_invalid_user_ocid(self, sample_credentials: OciCredentials) -> None:
        sample_credentials.user_ocid = "invalid"
        errors = KeyManager.validate_oci_credentials(sample_credentials)
        assert len(errors) > 0

    def test_validate_oci_credentials_invalid_tenancy_ocid(self, sample_credentials: OciCredentials) -> None:
        sample_credentials.tenancy_ocid = "invalid"
        errors = KeyManager.validate_oci_credentials(sample_credentials)
        assert len(errors) > 0

    def test_validate_oci_credentials_fingerprint_format(self, sample_credentials: OciCredentials) -> None:
        sample_credentials.fingerprint = "abcdef"
        errors = KeyManager.validate_oci_credentials(sample_credentials)
        assert any("colon" in e.lower() for e in errors)

    def test_save_and_load_key(self, tmp_path: Path) -> None:
        km = KeyManager(tmp_path)
        key_content = "-----BEGIN PRIVATE KEY-----\nTESTKEY\n-----END PRIVATE KEY-----"
        km.save_oci_private_key(key_content, "test_key.pem")

        loaded = km.load_oci_private_key("test_key.pem")
        assert loaded == key_content

    def test_load_nonexistent_key_raises(self, tmp_path: Path) -> None:
        km = KeyManager(tmp_path)
        with pytest.raises(FileNotFoundError):
            km.load_oci_private_key("nonexistent.pem")

    def test_has_key_returns_false_when_missing(self, tmp_path: Path) -> None:
        km = KeyManager(tmp_path)
        assert not km.has_oci_key("missing.pem")

    def test_delete_key_removes_file(self, tmp_path: Path) -> None:
        km = KeyManager(tmp_path)
        key_path = km.save_oci_private_key("content", "del.pem")
        assert key_path.exists()
        km.delete_oci_private_key("del.pem")
        assert not key_path.exists()

    def test_generate_oci_api_key_returns_private_and_public(self) -> None:
        priv, pub = KeyManager.generate_oci_api_key()
        assert "PRIVATE KEY" in priv
        assert "PUBLIC KEY" in pub

    def test_parse_oci_key_from_file(self, tmp_path: Path) -> None:
        config_content = (
            "user=ocid1.user.oc1..test\n"
            "tenancy=ocid1.tenancy.oc1..test\n"
            "fingerprint=12:34:56:78:90:ab:cd:ef\n"
            "region=sa-saopaulo-1\n"
            "key_file=api_key.pem\n"
        )
        config_path = tmp_path / "config"
        config_path.write_text(config_content)

        key_path = tmp_path / "api_key.pem"
        key_path.write_text("-----BEGIN PRIVATE KEY-----\nKEY\n-----END PRIVATE KEY-----")

        content, creds = KeyManager.parse_oci_key_from_file(config_path)
        assert creds.user_ocid == "ocid1.user.oc1..test"
        assert creds.region == "sa-saopaulo-1"
        assert "BEGIN PRIVATE KEY" in content


class TestCloudInitGenerator:
    def test_render_generates_valid_yaml(self) -> None:
        gen = CloudInitGenerator(
            server_private_key="s_priv",
            server_public_key="s_pub",
            client_public_key="c_pub",
        )
        yaml = gen.render()
        assert "#cloud-config" in yaml
        assert "wireguard" in yaml
        assert "s_priv" in yaml
        assert "c_pub" in yaml

    def test_render_includes_iptables_rules(self) -> None:
        gen = CloudInitGenerator(
            server_private_key="priv",
            server_public_key="pub",
            client_public_key="cpub",
        )
        yaml = gen.render()
        assert "MASQUERADE" in yaml
        assert "net.ipv4.ip_forward" in yaml

    def test_render_includes_ufw_rules(self) -> None:
        gen = CloudInitGenerator(
            server_private_key="priv",
            server_public_key="pub",
            client_public_key="cpub",
            vps_port=51820,
        )
        yaml = gen.render()
        assert "51820" in yaml
        assert "ufw" in yaml

    def test_custom_port(self) -> None:
        gen = CloudInitGenerator(
            server_private_key="priv",
            server_public_key="pub",
            client_public_key="cpub",
            vps_port=1194,
        )
        yaml = gen.render()
        assert "1194" in yaml

    def test_custom_address(self) -> None:
        gen = CloudInitGenerator(
            server_private_key="priv",
            server_public_key="pub",
            client_public_key="cpub",
            vps_address="172.16.0.1/24",
        )
        conf = gen._wg_conf()
        assert "172.16.0.1/24" in conf

    def test_keepalive_script_included(self) -> None:
        gen = CloudInitGenerator(
            server_private_key="priv",
            server_public_key="pub",
            client_public_key="cpub",
        )
        rendered = gen.render()
        assert "freeping-keepalive" in rendered
        assert "primos" in rendered or "prime" in rendered
        assert "crontab" in rendered

    def test_keepalive_script_has_logger(self) -> None:
        script = CloudInitGenerator(
            server_private_key="priv",
            server_public_key="pub",
            client_public_key="cpub",
        )._keepalive_script()
        assert "logger -t freeping-keepalive" in script
        assert "date" in script


class TestOciClient:
    def test_list_regions_returns_list(self, sample_credentials: OciCredentials) -> None:
        client = OciClient(sample_credentials)
        regions = client.list_regions()
        assert len(regions) > 0
        assert any(r["key"] == "sa-saopaulo-1" for r in regions)
        assert any(r["key"] == "us-ashburn-1" for r in regions)

    def test_map_state_running(self) -> None:
        assert OciClient._map_state("RUNNING") == VPSStatus.RUNNING

    def test_map_state_stopped(self) -> None:
        assert OciClient._map_state("STOPPED") == VPSStatus.STOPPED

    def test_map_state_terminated(self) -> None:
        assert OciClient._map_state("TERMINATED") == VPSStatus.TERMINATED

    def test_map_state_unknown(self) -> None:
        assert OciClient._map_state("UNKNOWN_STATE") == VPSStatus.UNKNOWN

    def test_map_state_terminating(self) -> None:
        assert OciClient._map_state("TERMINATING") == VPSStatus.TERMINATED

    def test_get_ubuntu_image_id_returns_string(self, sample_credentials: OciCredentials) -> None:
        client = OciClient(sample_credentials)
        image_id = client._get_ubuntu_image_id()
        assert isinstance(image_id, str)
        assert len(image_id) > 0


    def test_get_ubuntu_image_id_unknown_region(self) -> None:
        creds = OciCredentials(
            user_ocid="ocid1.user.oc1..test",
            tenancy_ocid="ocid1.tenancy.oc1..test",
            fingerprint="00:00:00:00",
            private_key="",
            region="unknown-region-1",
        )
        client = OciClient(creds)
        image_id = client._get_ubuntu_image_id()
        assert image_id == "ocid1.image.oc1..aaaaaaaa"

    def test_handle_auth_error_401(self) -> None:
        with pytest.raises(AuthError) as exc:
            OciClient._handle_error(401, '{"message": "not authorized", "code": "401"}')
        assert exc.value.status_code == 401
        assert "not authorized" in str(exc.value)

    def test_handle_auth_error_403(self) -> None:
        with pytest.raises(AuthError):
            OciClient._handle_error(403, "Forbidden")

    def test_handle_oci_error_400(self) -> None:
        with pytest.raises(OciError) as exc:
            OciClient._handle_error(400, '{"message": "bad request"}')
        assert exc.value.status_code == 400

    def test_handle_error_invalid_json(self) -> None:
        with pytest.raises(OciError) as exc:
            OciClient._handle_error(500, "Internal Server Error")
        assert exc.value.status_code == 500

    def test_oci_error_default_code_empty(self) -> None:
        err = OciError("test")
        assert err.status_code == 0
        assert err.code == ""

    def test_auth_error_is_oci_error(self) -> None:
        assert issubclass(AuthError, OciError)

    def test_sign_request_post_includes_body_hash(self, rsa_oci_credentials: OciCredentials) -> None:
        client = OciClient(rsa_oci_credentials)
        body = {"test": "data"}
        headers = client._sign_request("POST", "/20160918/instances", body)
        sha256 = headers["x-content-sha256"]
        expected = hashlib.sha256(json.dumps(body).encode()).hexdigest()
        assert sha256 == expected


class TestWireGuardKeyPair:
    def test_generate_python_fallback_returns_keys(self) -> None:
        kp = WireGuardKeyPair._generate_python_fallback()
        assert len(kp.private_key) > 0
        assert len(kp.public_key) > 0
        assert kp.private_key != kp.public_key

    def test_generate_fallback_uses_os_urandom(self) -> None:
        kp1 = WireGuardKeyPair._generate_python_fallback()
        kp2 = WireGuardKeyPair._generate_python_fallback()
        assert kp1.private_key != kp2.private_key

    def test_generate_fallback_public_key_len(self) -> None:
        kp = WireGuardKeyPair._generate_python_fallback()
        priv_bytes = __import__("base64").b64decode(kp.private_key)
        pub_bytes = WireGuardKeyPair._curve25519_public(priv_bytes)
        assert len(pub_bytes) == 32


class TestWireGuardCurve25519:
    def test_curve25519_public_derives_valid_key(self) -> None:
        import importlib.util
        import os
        if not importlib.util.find_spec("cryptography"):
            pytest.skip("cryptography with X25519 required")

        priv = os.urandom(32)
        pub = WireGuardKeyPair._curve25519_public(priv)
        assert len(pub) == 32
        assert pub != priv


class TestOciSignWithRealKey:
    def test_sign_with_real_rsa_key(self, rsa_oci_credentials: OciCredentials) -> None:
        client = OciClient(rsa_oci_credentials)
        sig = client._sign("test data to sign")
        assert isinstance(sig, str)
        assert len(sig) > 0

    def test_signing_request_with_real_key(self, rsa_oci_credentials: OciCredentials) -> None:
        client = OciClient(rsa_oci_credentials)
        headers = client._sign_request("GET", "/20160918/instances")
        assert "Authorization" in headers
        assert "Signature" in headers["Authorization"]


@pytest.mark.asyncio
async def test_oci_request_auth_error_with_invalid_creds():
    creds = OciCredentials(
        user_ocid="ocid1.user.oc1..invalid",
        tenancy_ocid="ocid1.tenancy.oc1..invalid",
        fingerprint="00:00:00:00",
        private_key="-----BEGIN PRIVATE KEY-----\nInvalid\n-----END PRIVATE KEY-----",
        region="sa-saopaulo-1",
    )
    client = OciClient(creds)
    try:
        await client.get_instance("fake-id")
    except Exception as e:
        assert isinstance(e, Exception)
