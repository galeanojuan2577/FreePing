from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from freeping.core.models import LatencyResult
from freeping.core.ping import PingManager


class TestPingManager:
    @pytest.mark.asyncio
    async def test_measure_returns_none_on_exception(self) -> None:
        pm = PingManager()
        with patch.object(pm, "_ping_posix", side_effect=RuntimeError("unexpected")):
            result = await pm.measure("10.0.0.1")
            assert result is None

    @pytest.mark.asyncio
    async def test_measure_returns_none_for_invalid_host(self) -> None:
        pm = PingManager()
        result = await pm.measure("192.0.2.999", count=1)
        assert result is None

    @pytest.mark.asyncio
    async def test_measure_game_server_returns_none_for_empty_list(self) -> None:
        pm = PingManager()
        result = await pm.measure_game_server([])
        assert result is None

    @pytest.mark.asyncio
    async def test_measure_game_server_early_exit_on_low_latency(self) -> None:
        pm = PingManager()
        with patch.object(pm, "measure", side_effect=[2.0, 100.0, 50.0]):
            result = await pm.measure_game_server(["10.0.0.1", "10.0.0.2", "10.0.0.3"])
            assert result == 2.0
        pm = PingManager()
        result = await pm.measure_game_server([])
        assert result is None

    @pytest.mark.asyncio
    async def test_compare_returns_latency_result(self) -> None:
        pm = PingManager()
        result = await pm.compare(
            vps_ip="203.0.113.1",
            game_ips=["10.0.0.1"],
            tunnel_active=False,
        )
        assert isinstance(result, LatencyResult)

    @pytest.mark.asyncio
    async def test_compare_with_tunnel_active(self) -> None:
        pm = PingManager()
        result = await pm.compare(
            vps_ip="203.0.113.1",
            game_ips=["10.0.0.1"],
            tunnel_active=True,
        )
        assert isinstance(result, LatencyResult)

    @pytest.mark.asyncio
    async def test_measure_no_crash_on_localhost(self) -> None:
        pm = PingManager()
        result = await pm.measure("127.0.0.1", count=1)
        assert result is None or isinstance(result, float)

    @pytest.mark.asyncio
    async def test_posix_ping_parser(self) -> None:
        pm = PingManager()
        output = (
            "PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.\n"
            "64 bytes from 8.8.8.8: icmp_seq=1 ttl=118 time=12.3 ms\n"
            "64 bytes from 8.8.8.8: icmp_seq=2 ttl=118 time=11.8 ms\n"
            "64 bytes from 8.8.8.8: icmp_seq=3 ttl=118 time=12.1 ms\n"
            "\n"
            "--- 8.8.8.8 ping statistics ---\n"
            "3 packets transmitted, 3 received, 0% packet loss, time 2002ms\n"
            "rtt min/avg/max/mdev = 11.800/12.066/12.300/0.204 ms\n"
        )

        async def mock_ping(*args, **kwargs):
            proc = AsyncMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(output.encode(), b""))
            return proc

        with patch("asyncio.create_subprocess_exec", mock_ping):
            result = await pm.measure("8.8.8.8", count=3)
            assert result == pytest.approx(12.066, rel=0.01)

    @pytest.mark.asyncio
    async def test_posix_ping_parser_unknown_output_returns_none(self) -> None:
        pm = PingManager()
        output = b"PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.\n---\nsome weird output\n"

        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(output, b""))

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await pm.measure("8.8.8.8", count=1)
            assert result is None

    @pytest.mark.asyncio
    async def test_measure_game_server_all_pings_fail(self) -> None:
        pm = PingManager()
        with patch.object(pm, "measure", return_value=None):
            result = await pm.measure_game_server(["10.0.0.1", "10.0.0.2"])
            assert result is None

    @pytest.mark.asyncio
    async def test_measure_game_server_returns_best_latency(self) -> None:
        pm = PingManager()
        with patch.object(pm, "measure", side_effect=[50.0, 20.0, 30.0]):
            result = await pm.measure_game_server(["10.0.0.1", "10.0.0.2", "10.0.0.3"])
            assert result == 20.0

    @pytest.mark.asyncio
    async def test_posix_ping_parser_alternate_format(self) -> None:
        pm = PingManager()
        output = (
            "PING example.com (93.184.216.34) 56(84) bytes of data.\n"
            "64 bytes from 93.184.216.34: icmp_seq=1 ttl=55 time=20.5 ms\n"
            "64 bytes from 93.184.216.34: icmp_seq=2 ttl=55 time=19.8 ms\n"
            "\n"
            "--- example.com ping statistics ---\n"
            "2 packets transmitted, 2 received, 0% packet loss, time 1001ms\n"
            "rtt min/avg/max/mdev = 19.800/20.150/20.500/0.350 ms\n"
        )

        async def mock_ping(*args, **kwargs):
            proc = AsyncMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(output.encode(), b""))
            return proc

        with patch("asyncio.create_subprocess_exec", mock_ping):
            result = await pm.measure("example.com", count=2)
            assert result == pytest.approx(20.150, rel=0.01)

    @pytest.mark.asyncio
    async def test_compare_with_tunnel_sets_both_measurements(self) -> None:
        pm = PingManager()
        with patch.object(pm, "measure_game_server", side_effect=[30.0, 100.0]):
            result = await pm.compare(
                vps_ip="203.0.113.1",
                game_ips=["10.0.0.1"],
                tunnel_active=True,
            )
            assert result.with_tunnel_ms == 30.0
            assert result.without_tunnel_ms == 100.0

    @pytest.mark.asyncio
    async def test_measure_returns_none_on_ping_failure(self) -> None:
        async def mock_failure(*args, **kwargs):
            proc = AsyncMock()
            proc.returncode = 1
            proc.communicate = AsyncMock(return_value=(b"", b"ping failed"))
            return proc

        with patch("asyncio.create_subprocess_exec", mock_failure):
            pm = PingManager()
            result = await pm.measure("10.0.0.1", count=1)
            assert result is None


class TestLatencyResult:
    def test_improvement_calculation(self) -> None:
        result = LatencyResult(without_tunnel_ms=150.0, with_tunnel_ms=50.0)
        assert result.improvement_ms == 100.0
        assert result.improvement_pct == pytest.approx(66.67, rel=0.01)

    def test_no_improvement_when_same(self) -> None:
        result = LatencyResult(without_tunnel_ms=100.0, with_tunnel_ms=100.0)
        assert result.improvement_ms == 0.0
        assert result.improvement_pct == 0.0

    def test_worse_with_tunnel(self) -> None:
        result = LatencyResult(without_tunnel_ms=50.0, with_tunnel_ms=150.0)
        assert result.improvement_ms == -100.0
        assert result.improvement_pct == -200.0

    def test_to_dict(self) -> None:
        result = LatencyResult(without_tunnel_ms=100.0, with_tunnel_ms=60.0)
        data = result.to_dict()
        assert data["without_tunnel_ms"] == 100.0
        assert data["with_tunnel_ms"] == 60.0
        assert data["improvement_ms"] == 40.0
