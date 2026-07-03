from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from freeping.core.models import TunnelConfig, TunnelState
from freeping.core.tunnel import TunnelError, TunnelManager


class TestTunnelManagerAdvanced:

    @pytest.mark.asyncio
    async def test_start_linux_success(
        self, sample_tunnel_config: TunnelConfig, tmp_path: Path
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = False
        conf_path = tmp_path / "wg0.conf"
        with patch("freeping.core.tunnel.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            await mgr.start(conf_path)
        assert mgr.state == TunnelState.ACTIVE
        mock_run.assert_called_once_with(
            ["wg-quick", "up", str(conf_path)],
            capture_output=True, text=True, timeout=30,
        )

    @pytest.mark.asyncio
    async def test_start_linux_failure(
        self, sample_tunnel_config: TunnelConfig, tmp_path: Path
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = False
        conf_path = tmp_path / "wg0.conf"
        with patch("freeping.core.tunnel.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = "wg-quick: error"
            with pytest.raises(TunnelError, match="wg-quick up failed"):
                await mgr.start(conf_path)
        assert mgr.state == TunnelState.ERROR

    @pytest.mark.asyncio
    async def test_stop_linux_success(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = False
        with patch("freeping.core.tunnel.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            await mgr.stop()
        assert mgr.state == TunnelState.INACTIVE
        mock_run.assert_called_once_with(
            ["wg-quick", "down", "freeping"],
            capture_output=True, text=True, timeout=30,
        )

    @pytest.mark.asyncio
    async def test_stop_linux_fallback_ip_link_delete(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = False
        with patch("freeping.core.tunnel.subprocess.run") as mock_run:
            mock_run.side_effect = [
                subprocess.CalledProcessError(1, "wg-quick down"),
                MagicMock(returncode=0),
            ]
            await mgr.stop()
        assert mgr.state == TunnelState.INACTIVE
        assert mock_run.call_count == 2
        assert mock_run.call_args_list[1][0][0] == ["ip", "link", "delete", "freeping"]

    @pytest.mark.asyncio
    async def test_stop_linux_double_fallback(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = False
        with patch("freeping.core.tunnel.subprocess.run") as mock_run:
            mock_run.side_effect = [
                subprocess.CalledProcessError(1, "wg-quick down"),
                subprocess.CalledProcessError(1, "ip link delete"),
            ]
            await mgr.stop()
        assert mgr.state == TunnelState.INACTIVE
        assert mock_run.call_count == 2

    @pytest.mark.asyncio
    async def test_stop_linux_raises_unexpected_error(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = False
        with patch("freeping.core.tunnel.subprocess.run") as mock_run:
            mock_run.side_effect = RuntimeError("wg-quick not found")
            with pytest.raises(TunnelError, match="Failed to stop tunnel"):
                await mgr.stop()
        assert mgr.state == TunnelState.ERROR

    def test_check_linux_interface_returns_true(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = False
        with patch("freeping.core.tunnel.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = mgr.is_active()
        assert result is True
        mock_run.assert_called_once_with(
            ["ip", "link", "show", "freeping"],
            capture_output=True, text=True, timeout=30,
        )

    def test_check_linux_interface_returns_false(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = False
        with patch("freeping.core.tunnel.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            result = mgr.is_active()
        assert result is False

    def test_check_linux_interface_file_not_found(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = False
        with patch("freeping.core.tunnel.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = mgr.is_active()
        assert result is False

    @pytest.mark.asyncio
    async def test_start_windows_with_wireguard_exe_success(
        self, sample_tunnel_config: TunnelConfig, tmp_path: Path
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = True
        conf_path = tmp_path / "wg0.conf"
        with (
            patch.object(
                TunnelManager, "_find_wireguard_windows",
                return_value="C:\\Program Files\\WireGuard\\wireguard.exe",
            ),
            patch("freeping.core.tunnel.subprocess.run") as mock_run,
        ):
            mock_run.return_value.returncode = 0
            await mgr.start(conf_path)
        assert mgr.state == TunnelState.ACTIVE
        assert mock_run.call_count == 2
        mock_run.assert_any_call(
            ["C:\\Program Files\\WireGuard\\wireguard.exe", "/installtunnelservice", str(conf_path)],
            capture_output=True, text=True, timeout=30,
        )
        mock_run.assert_any_call(
            ["net", "start", "WireGuardTunnel$freeping"],
            capture_output=True, text=True, timeout=30,
        )

    @pytest.mark.asyncio
    async def test_start_windows_with_wireguard_exe_failure(
        self, sample_tunnel_config: TunnelConfig, tmp_path: Path
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = True
        conf_path = tmp_path / "wg0.conf"
        with (
            patch.object(
                TunnelManager, "_find_wireguard_windows",
                return_value="C:\\Program Files\\WireGuard\\wireguard.exe",
            ),
            patch("freeping.core.tunnel.subprocess.run") as mock_run,
        ):
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = "install failed"
            with pytest.raises(TunnelError, match="WireGuard install failed"):
                await mgr.start(conf_path)
        assert mgr.state == TunnelState.ERROR

    @pytest.mark.asyncio
    async def test_start_windows_without_wireguard_exe_success(
        self, sample_tunnel_config: TunnelConfig, tmp_path: Path
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = True
        conf_path = tmp_path / "wg0.conf"
        with (
            patch.object(TunnelManager, "_find_wireguard_windows", return_value=None),
            patch("freeping.core.tunnel.subprocess.run") as mock_run,
        ):
            mock_run.return_value.returncode = 0
            await mgr.start(conf_path)
        assert mgr.state == TunnelState.ACTIVE
        mock_run.assert_called_once_with(
            ["wg-quick", "up", str(conf_path)],
            capture_output=True, text=True, timeout=30,
        )

    @pytest.mark.asyncio
    async def test_start_windows_without_wireguard_exe_failure(
        self, sample_tunnel_config: TunnelConfig, tmp_path: Path
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = True
        conf_path = tmp_path / "wg0.conf"
        with (
            patch.object(TunnelManager, "_find_wireguard_windows", return_value=None),
            patch("freeping.core.tunnel.subprocess.run") as mock_run,
        ):
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = "wg-quick error"
            with pytest.raises(TunnelError, match="wg-quick up failed"):
                await mgr.start(conf_path)
        assert mgr.state == TunnelState.ERROR

    @pytest.mark.asyncio
    async def test_stop_windows_with_wireguard_exe(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = True
        with (
            patch.object(
                TunnelManager, "_find_wireguard_windows",
                return_value="C:\\Program Files\\WireGuard\\wireguard.exe",
            ),
            patch("freeping.core.tunnel.subprocess.run") as mock_run,
        ):
            await mgr.stop()
        assert mgr.state == TunnelState.INACTIVE
        assert mock_run.call_count == 2
        mock_run.assert_any_call(
            ["net", "stop", "WireGuardTunnel$freeping"],
            capture_output=True, text=True, timeout=30,
        )
        mock_run.assert_any_call(
            ["C:\\Program Files\\WireGuard\\wireguard.exe", "/uninstalltunnelservice", "freeping"],
            capture_output=True, text=True, timeout=30,
        )

    @pytest.mark.asyncio
    async def test_stop_windows_without_wireguard_exe(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = True
        with (
            patch.object(TunnelManager, "_find_wireguard_windows", return_value=None),
            patch("freeping.core.tunnel.subprocess.run") as mock_run,
        ):
            await mgr.stop()
        assert mgr.state == TunnelState.INACTIVE
        mock_run.assert_called_once_with(
            ["wg-quick", "down", "freeping"],
            capture_output=True, text=True, timeout=30,
        )

    def test_check_windows_interface_returns_true(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = True
        with patch("freeping.core.tunnel.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = mgr.is_active()
        assert result is True
        mock_run.assert_called_once_with(
            ["wg", "show", "freeping"],
            capture_output=True, text=True, timeout=30,
        )

    def test_check_windows_interface_returns_false(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = True
        with patch("freeping.core.tunnel.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            result = mgr.is_active()
        assert result is False

    def test_check_windows_interface_file_not_found(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = True
        with patch("freeping.core.tunnel.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = mgr.is_active()
        assert result is False

    def test_find_wireguard_windows_found_first_path(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        with patch("freeping.core.tunnel.Path.exists") as mock_exists:
            mock_exists.return_value = True
            result = mgr._find_wireguard_windows()
        assert result == "C:\\Program Files\\WireGuard\\wireguard.exe"

    def test_find_wireguard_windows_found_second_path(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        with patch("freeping.core.tunnel.Path.exists") as mock_exists:
            mock_exists.side_effect = [False, True]
            result = mgr._find_wireguard_windows()
        assert result == "C:\\Program Files (x86)\\WireGuard\\wireguard.exe"

    def test_find_wireguard_windows_not_found(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        with patch("freeping.core.tunnel.Path.exists") as mock_exists:
            mock_exists.return_value = False
            result = mgr._find_wireguard_windows()
        assert result is None

    def test_get_interface_stats_parsed(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        with patch("freeping.core.tunnel.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "1024 2048 100 200\n"
            stats = mgr.get_interface_stats()
        assert stats == {
            "received_bytes": 1024,
            "sent_bytes": 2048,
            "received_packets": 100,
            "sent_packets": 200,
        }

    def test_get_interface_stats_no_match(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        with patch("freeping.core.tunnel.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "no transfer data here"
            stats = mgr.get_interface_stats()
        assert stats == {}

    def test_get_interface_stats_non_zero_returncode(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        with patch("freeping.core.tunnel.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            stats = mgr.get_interface_stats()
        assert stats == {}

    def test_get_interface_stats_exception(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        with patch("freeping.core.tunnel.subprocess.run") as mock_run:
            mock_run.side_effect = RuntimeError("wg not available")
            stats = mgr.get_interface_stats()
        assert stats == {}

    @pytest.mark.asyncio
    async def test_update_game_ips_restarts_when_active(
        self, sample_tunnel_config: TunnelConfig, tmp_path: Path
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._state = TunnelState.ACTIVE
        conf_path = tmp_path / "wg0.conf"
        mock_stop = AsyncMock()
        mock_start = AsyncMock()
        with (
            patch.object(TunnelManager, "stop", mock_stop),
            patch.object(TunnelManager, "start", mock_start),
        ):
            await mgr.update_game_ips(["10.0.0.0/8"], conf_path)
        mock_stop.assert_awaited_once()
        mock_start.assert_awaited_once_with(conf_path)
        assert mgr.config.allowed_ips == ["10.0.0.0/8"]

    @pytest.mark.asyncio
    async def test_update_game_ips_no_restart_when_inactive(
        self, sample_tunnel_config: TunnelConfig, tmp_path: Path
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        assert mgr.state == TunnelState.INACTIVE
        conf_path = tmp_path / "wg0.conf"
        mock_stop = AsyncMock()
        mock_start = AsyncMock()
        with (
            patch.object(TunnelManager, "stop", mock_stop),
            patch.object(TunnelManager, "start", mock_start),
        ):
            await mgr.update_game_ips(["10.0.0.0/8"], conf_path)
        mock_stop.assert_not_called()
        mock_start.assert_not_called()
        assert mgr.config.allowed_ips == ["10.0.0.0/8"]

    def test_is_active_dispatches_to_linux(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = False
        with patch.object(
            TunnelManager, "_check_linux_interface", return_value=True
        ) as mock_check:
            result = mgr.is_active()
        assert result is True
        mock_check.assert_called_once()

    def test_is_active_dispatches_to_windows(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = True
        with patch.object(
            TunnelManager, "_check_windows_interface", return_value=True
        ) as mock_check:
            result = mgr.is_active()
        assert result is True
        mock_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_transitions_through_connecting_on_linux(
        self, sample_tunnel_config: TunnelConfig, tmp_path: Path
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = False
        conf_path = tmp_path / "wg0.conf"
        with patch("freeping.core.tunnel.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            assert mgr.state == TunnelState.INACTIVE
            await mgr.start(conf_path)
            assert mgr.state == TunnelState.ACTIVE

    @pytest.mark.asyncio
    async def test_stop_windows_with_wireguard_exe_failure_still_inactive(
        self, sample_tunnel_config: TunnelConfig
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = True
        with (
            patch.object(
                TunnelManager, "_find_wireguard_windows",
                return_value="C:\\Program Files\\WireGuard\\wireguard.exe",
            ),
            patch("freeping.core.tunnel.subprocess.run") as mock_run,
        ):
            mock_run.side_effect = RuntimeError("access denied")
            with pytest.raises(TunnelError, match="Failed to stop tunnel"):
                await mgr.stop()
        assert mgr.state == TunnelState.ERROR

    def test_generate_conf_file_skips_chmod_on_windows(
        self, sample_tunnel_config: TunnelConfig, tmp_path: Path
    ) -> None:
        mgr = TunnelManager(sample_tunnel_config)
        mgr._is_windows = True
        conf_path = tmp_path / "freeping.conf"
        mgr.generate_conf_file(conf_path)
        assert conf_path.exists()
        content = conf_path.read_text()
        assert "[Interface]" in content
        assert "[Peer]" in content
