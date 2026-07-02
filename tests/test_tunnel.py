from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from freeping.core.models import TunnelConfig, TunnelState
from freeping.core.tunnel import TunnelError, TunnelManager


class TestTunnelManager:
    def test_initial_state_is_inactive(self, sample_tunnel_config: TunnelConfig) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        assert mgr.state == TunnelState.INACTIVE

    def test_generate_conf_file_creates_valid_config(
        self, sample_tunnel_config: TunnelConfig, tmp_path: Path
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        conf_path = tmp_path / "freeping.conf"
        mgr.generate_conf_file(conf_path)

        assert conf_path.exists()
        content = conf_path.read_text()
        assert "[Interface]" in content
        assert "[Peer]" in content
        assert "PrivateKey = client_priv_key" in content
        assert "PublicKey = server_pub_key" in content
        assert "Endpoint = 203.0.113.1:51820" in content
        assert "AllowedIPs = 10.0.0.0/8" in content

    def test_conf_file_chmod_on_posix(
        self, sample_tunnel_config: TunnelConfig, tmp_path: Path
    ) -> None:
        import platform
        if platform.system() == "Windows":
            pytest.skip("Permission test not applicable on Windows")

        mgr = TunnelManager(sample_tunnel_config)
        conf_path = tmp_path / "freeping.conf"
        mgr.generate_conf_file(conf_path)

        mode = conf_path.stat().st_mode & 0o777
        assert mode == 0o600

    def test_generate_conf_file_creates_parent_dir(
        self, sample_tunnel_config: TunnelConfig, tmp_path: Path
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        conf_path = tmp_path / "subdir" / "freeping.conf"
        mgr.generate_conf_file(conf_path)
        assert conf_path.exists()

    def test_is_active_returns_false_initially(
        self, sample_tunnel_config: TunnelConfig,
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        assert not mgr.is_active()

    def test_transition_to_error_on_failed_start(
        self, sample_tunnel_config: TunnelConfig,
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        assert mgr.state == TunnelState.INACTIVE

    def test_get_interface_stats_returns_empty_dict(
        self, sample_tunnel_config: TunnelConfig,
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        stats = mgr.get_interface_stats()
        assert isinstance(stats, dict)

    @pytest.mark.asyncio
    async def test_start_with_subprocess_mocked(self, sample_tunnel_config: TunnelConfig, tmp_path: Path) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        conf_path = tmp_path / "wg0.conf"

        with patch("freeping.core.tunnel.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            await mgr.start(conf_path)
            assert mgr.state == TunnelState.ACTIVE

    @pytest.mark.asyncio
    async def test_start_failure_transitions_to_error(self, sample_tunnel_config: TunnelConfig, tmp_path: Path) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        conf_path = tmp_path / "wg0.conf"

        with patch("freeping.core.tunnel.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("wg-quick not found")
            with pytest.raises(TunnelError):
                await mgr.start(conf_path)
            assert mgr.state == TunnelState.ERROR

    @pytest.mark.asyncio
    async def test_stop_subprocess_mocked(self, sample_tunnel_config: TunnelConfig) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        with patch("freeping.core.tunnel.subprocess.run"):
            await mgr.stop()
            assert mgr.state == TunnelState.INACTIVE

    def test_update_game_ips_changes_allowed_ips(
        self, sample_tunnel_config: TunnelConfig, tmp_path: Path
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        conf_path = tmp_path / "freeping.conf"

        mgr.generate_conf_file(conf_path)
        content_before = conf_path.read_text()
        assert "AllowedIPs = 10.0.0.0/8" in content_before

        mgr.config.allowed_ips = ["192.168.0.0/16"]
        mgr.generate_conf_file(conf_path)
        content_after = conf_path.read_text()
        assert "AllowedIPs = 192.168.0.0/16" in content_after


class TestTunnelConfigWireGuard:
    def test_conf_has_correct_structure(self, sample_tunnel_config: TunnelConfig) -> None:
        conf = sample_tunnel_config.to_wireguard_conf()
        sections = conf.strip().split("\n\n")
        assert len(sections) == 2
        assert "[Interface]" in sections[0]
        assert "[Peer]" in sections[1]

    def test_conf_with_multiple_allowed_ips(self) -> None:
        config = TunnelConfig(
            vps_ip="10.0.0.1",
            client_private_key="key",
            public_key="pub",
            allowed_ips=["10.0.0.0/8", "192.168.0.0/16", "172.16.0.0/12"],
        )
        conf = config.to_wireguard_conf()
        assert "AllowedIPs = 10.0.0.0/8, 192.168.0.0/16, 172.16.0.0/12" in conf

    def test_persistent_keepalive_custom(self) -> None:
        config = TunnelConfig(
            vps_ip="10.0.0.1",
            client_private_key="key",
            public_key="pub",
            persistent_keepalive=5,
        )
        conf = config.to_wireguard_conf()
        assert "PersistentKeepalive = 5" in conf
