from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import pytest

from freeping.core.models import LatencyResult
from freeping.core.ping import PingError, PingManager


class TestPingManagerAdvanced:
    @pytest.mark.asyncio
    async def test_compare_without_tunnel_sets_only_without_tunnel_ms(self) -> None:
        pm = PingManager()
        with patch.object(pm, "measure_game_server", return_value=45.0):
            result = await pm.compare(
                vps_ip="203.0.113.1",
                game_ips=["10.0.0.1"],
                tunnel_active=False,
            )
            assert result.with_tunnel_ms is None
            assert result.without_tunnel_ms == 45.0
            assert isinstance(result, LatencyResult)

    @pytest.mark.asyncio
    async def test_posix_ping_second_regex_fallback(self) -> None:
        output = (
            "PING host (1.2.3.4) 56(84) bytes of data.\n"
            "64 bytes from 1.2.3.4: icmp_seq=1 ttl=55 time=10.0 ms\n"
            "\n"
            "--- host ping statistics ---\n"
            "1 packets transmitted, 1 received, 0% packet loss\n"
            "rtt min/avg/max/mdev = 10.000/10.000/10.000/0.000 ms\n"
        )
        original_search = re.search

        def mock_search(pattern, string, flags=0):
            if "min/avg/max/(?:mdev|stddev)" in pattern:
                return None
            return original_search(pattern, string, flags)

        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(output.encode(), b""))
        pm = PingManager()
        with patch("freeping.core.ping.re.search", mock_search):
            with patch("asyncio.create_subprocess_exec", return_value=proc):
                result = await pm.measure("1.2.3.4", count=1)
                assert result == pytest.approx(10.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_windows_ping_media_regex(self) -> None:
        output = (
            b"\r\n"
            b"Respuesta desde 10.0.0.1: bytes=32 tiempo=12ms TTL=55\r\n"
            b"\r\n"
            b"Estadisticas de ping para 10.0.0.1:\r\n"
            b"    Paquetes: enviados = 1, recibidos = 1, perdidos = 0\r\n"
            b"    (0% perdidos)\r\n"
            b"Tiempos aproximados del ida y vuelta:\r\n"
            b"    Media = 12ms\r\n"
        )
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(output, b""))
        with patch("freeping.core.ping.platform.system", return_value="Windows"):
            pm = PingManager()
            with patch("asyncio.create_subprocess_exec", return_value=proc):
                result = await pm.measure("10.0.0.1", count=1)
                assert result == 12.0

    @pytest.mark.asyncio
    async def test_windows_ping_media_decimal_regex(self) -> None:
        output = (
            b"\r\n"
            b"Respuesta desde 10.0.0.1: bytes=32 tiempo=10.5ms TTL=55\r\n"
            b"\r\n"
            b"Estadisticas de ping para 10.0.0.1:\r\n"
            b"    Paquetes: enviados = 3, recibidos = 3, perdidos = 0\r\n"
            b"    (0% perdidos)\r\n"
            b"Tiempos aproximados del ida y vuelta:\r\n"
            b"    Media = 10.5ms\r\n"
        )
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(output, b""))
        with patch("freeping.core.ping.platform.system", return_value="Windows"):
            pm = PingManager()
            with patch("asyncio.create_subprocess_exec", return_value=proc):
                result = await pm.measure("10.0.0.1", count=3)
                assert result == 10.5

    @pytest.mark.asyncio
    async def test_windows_ping_promedio_regex(self) -> None:
        output = (
            b"\r\n"
            b"Datos de 10.0.0.1: bytes=32 tiempo=25ms TTL=55\r\n"
            b"\r\n"
            b"Estadisticas de ping para 10.0.0.1:\r\n"
            b"    Paquetes: enviados = 2, recibidos = 2, perdidos = 0\r\n"
            b"    (0% perdidos)\r\n"
            b"Tiempos aproximados del ida y vuelta:\r\n"
            b"    Promedio = 25ms\r\n"
        )
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(output, b""))
        with patch("freeping.core.ping.platform.system", return_value="Windows"):
            pm = PingManager()
            with patch("asyncio.create_subprocess_exec", return_value=proc):
                result = await pm.measure("10.0.0.1", count=2)
                assert result == 25.0

    @pytest.mark.asyncio
    async def test_windows_ping_average_regex(self) -> None:
        output = (
            b"\r\n"
            b"Reply from 10.0.0.1: bytes=32 time=8ms TTL=55\r\n"
            b"\r\n"
            b"Ping statistics for 10.0.0.1:\r\n"
            b"    Packets: Sent = 1, Received = 1, Lost = 0 (0% loss),\r\n"
            b"Approximate round trip times in milli-seconds:\r\n"
            b"    Minimum = 8ms, Maximum = 8ms, Average = 8ms\r\n"
        )
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(output, b""))
        with patch("freeping.core.ping.platform.system", return_value="Windows"):
            pm = PingManager()
            with patch("asyncio.create_subprocess_exec", return_value=proc):
                result = await pm.measure("10.0.0.1", count=1)
                assert result == 8.0

    @pytest.mark.asyncio
    async def test_windows_ping_non_zero_returncode(self) -> None:
        proc = AsyncMock()
        proc.returncode = 1
        proc.communicate = AsyncMock(return_value=(b"", b"General failure."))
        with patch("freeping.core.ping.platform.system", return_value="Windows"):
            pm = PingManager()
            with patch("asyncio.create_subprocess_exec", return_value=proc):
                result = await pm.measure("10.0.0.1", count=1)
                assert result is None

    @pytest.mark.asyncio
    async def test_windows_ping_exception_returns_none(self) -> None:
        with patch("freeping.core.ping.platform.system", return_value="Windows"):
            pm = PingManager()
            with patch(
                "asyncio.create_subprocess_exec",
                side_effect=OSError("Permission denied"),
            ):
                result = await pm.measure("10.0.0.1", count=1)
                assert result is None

    @pytest.mark.asyncio
    async def test_windows_ping_unknown_output_returns_none(self) -> None:
        output = b"Some completely unexpected output format\n"
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(output, b""))
        with patch("freeping.core.ping.platform.system", return_value="Windows"):
            pm = PingManager()
            with patch("asyncio.create_subprocess_exec", return_value=proc):
                result = await pm.measure("10.0.0.1", count=1)
                assert result is None

    @pytest.mark.asyncio
    async def test_measure_game_server_with_none_and_valid(self) -> None:
        pm = PingManager()
        with patch.object(pm, "measure", side_effect=[None, 30.0]):
            result = await pm.measure_game_server(["10.0.0.1", "10.0.0.2"])
            assert result == 30.0

    @pytest.mark.asyncio
    async def test_measure_game_server_all_none_returns_none(self) -> None:
        pm = PingManager()
        with patch.object(pm, "measure", return_value=None):
            result = await pm.measure_game_server(["10.0.0.1", "10.0.0.2"])
            assert result is None

    @pytest.mark.asyncio
    async def test_posix_ping_stddev_regex(self) -> None:
        output = (
            "PING host (1.2.3.4) 56(84) bytes of data.\n"
            "64 bytes from 1.2.3.4: icmp_seq=1 ttl=55 time=20.0 ms\n"
            "64 bytes from 1.2.3.4: icmp_seq=2 ttl=55 time=22.0 ms\n"
            "\n"
            "--- host ping statistics ---\n"
            "2 packets transmitted, 2 received, 0% packet loss, time 1001ms\n"
            "min/avg/max/stddev = 20.000/21.000/22.000/1.000 ms\n"
        )
        prod = b""
        for _ in range(257):
            prod += b"A" * 2000

        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(output.encode(), b""))
        pm = PingManager()
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await pm.measure("1.2.3.4", count=2)
            assert result == pytest.approx(21.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_posix_ping_unknown_output_returns_none(self) -> None:
        output = b"strange output without statistics\n"
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(output, b""))
        pm = PingManager()
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await pm.measure("1.2.3.4", count=1)
            assert result is None

    @pytest.mark.asyncio
    async def test_posix_ping_empty_output_returns_none(self) -> None:
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        pm = PingManager()
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await pm.measure("1.2.3.4", count=1)
            assert result is None

    @pytest.mark.asyncio
    async def test_posix_ping_exception_returns_none(self) -> None:
        pm = PingManager()
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("ping not found"),
        ):
            result = await pm.measure("1.2.3.4", count=1)
            assert result is None

    @pytest.mark.asyncio
    async def test_measure_game_server_does_not_ping_beyond_early_exit(self) -> None:
        calls: list[str] = []

        async def tracking_measure(host: str, count: int = 2) -> float | None:
            calls.append(host)
            if host == "10.0.0.1":
                return 3.0
            return 100.0

        pm = PingManager()
        with patch.object(pm, "measure", tracking_measure):
            result = await pm.measure_game_server(
                ["10.0.0.1", "10.0.0.2", "10.0.0.3"]
            )
            assert result == 3.0
            assert len(calls) == 1

    def test_ping_error_is_exception_subclass(self) -> None:
        assert issubclass(PingError, Exception)

    def test_ping_error_can_be_raised_and_caught(self) -> None:
        with pytest.raises(PingError):
            raise PingError("test error")

    def test_ping_error_default_message(self) -> None:
        with pytest.raises(PingError):
            raise PingError()

    @pytest.mark.asyncio
    async def test_compare_with_tunnel_measure_game_returns_none(self) -> None:
        pm = PingManager()
        with patch.object(pm, "measure_game_server", return_value=None):
            result = await pm.compare(
                vps_ip="203.0.113.1",
                game_ips=["10.0.0.1"],
                tunnel_active=True,
            )
            assert result.with_tunnel_ms is None
            assert result.without_tunnel_ms is None

    @pytest.mark.asyncio
    async def test_compare_without_tunnel_returns_latency_result(self) -> None:
        pm = PingManager()
        with patch.object(pm, "measure_game_server", return_value=50.0):
            result = await pm.compare(
                vps_ip="10.0.0.1",
                game_ips=["10.0.0.2"],
                tunnel_active=False,
            )
            assert result.without_tunnel_ms == 50.0
            assert result.with_tunnel_ms is None
            assert isinstance(result, LatencyResult)

    @pytest.mark.asyncio
    async def test_measure_game_server_returns_none_no_servers(self) -> None:
        pm = PingManager()
        result = await pm.measure_game_server([])
        assert result is None

    @pytest.mark.asyncio
    async def test_windows_ping_average_decimal_regex(self) -> None:
        output = (
            b"\r\n"
            b"Reply from 10.0.0.1: bytes=32 time=42.5ms TTL=55\r\n"
            b"\r\n"
            b"Ping statistics for 10.0.0.1:\r\n"
            b"    Packets: Sent = 1, Received = 1, Lost = 0 (0% loss),\r\n"
            b"Approximate round trip times in milli-seconds:\r\n"
            b"    Minimum = 42ms, Maximum = 43ms, Average = 42.5ms\r\n"
        )
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(output, b""))
        with patch("freeping.core.ping.platform.system", return_value="Windows"):
            pm = PingManager()
            with patch("asyncio.create_subprocess_exec", return_value=proc):
                result = await pm.measure("10.0.0.1", count=1)
                assert result == 42.5

    @pytest.mark.asyncio
    async def test_windows_ping_all_regexes_fail_returns_none(self) -> None:
        output = (
            b"\r\n"
            b"Reply from 10.0.0.1: bytes=32 time=15ms TTL=55\r\n"
            b"\r\n"
            b"Ping statistics for 10.0.0.1:\r\n"
            b"    Packets: Sent = 1, Received = 1, Lost = 0 (0% loss),\r\n"
            b"Approximate round trip times:\r\n"
            b"    Custom = 15ms\r\n"
        )
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(output, b""))
        with patch("freeping.core.ping.platform.system", return_value="Windows"):
            pm = PingManager()
            with patch("asyncio.create_subprocess_exec", return_value=proc):
                result = await pm.measure("10.0.0.1", count=1)
                assert result is None

    @pytest.mark.asyncio
    async def test_posix_ping_communicate_error_returns_none(self) -> None:
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(side_effect=RuntimeError("pipe broken"))
        pm = PingManager()
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await pm.measure("1.2.3.4", count=1)
            assert result is None
