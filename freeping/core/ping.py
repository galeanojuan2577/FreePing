from __future__ import annotations

import asyncio
import logging
import platform
import re

from freeping.core.models import LatencyResult

logger = logging.getLogger("freeping.ping")


class PingError(Exception):
    pass


class PingManager:
    def __init__(self) -> None:
        self._is_windows = platform.system() == "Windows"

    async def measure(self, host: str, count: int = 3) -> float | None:
        try:
            if self._is_windows:
                return await self._ping_windows(host, count)
            return await self._ping_posix(host, count)
        except Exception as e:
            logger.debug("Ping to %s failed: %s", host, e)
            return None

    async def measure_game_server(self, game_ips: list[str]) -> float | None:
        if not game_ips:
            return None
        best: float | None = None
        for ip in game_ips:
            ms = await self.measure(ip, count=2)
            if ms is not None:
                if best is None or ms < best:
                    best = ms
                if best is not None and best < 5:
                    break
        return best

    async def compare(
        self,
        vps_ip: str,
        game_ips: list[str],
        tunnel_active: bool = True,
    ) -> LatencyResult:
        result = LatencyResult()

        if tunnel_active:
            result.with_tunnel_ms = await self.measure_game_server(game_ips)
            result.without_tunnel_ms = await self._measure_game_via_direct(game_ips)
        else:
            result.without_tunnel_ms = await self.measure_game_server(game_ips)

        return result

    async def _measure_game_via_direct(self, game_ips: list[str]) -> float | None:
        return await self.measure_game_server(game_ips)

    async def _ping_posix(self, host: str, count: int) -> float | None:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", str(count), "-W", "3", host,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        if proc.returncode != 0:
            return None

        output = stdout.decode()
        match = re.search(r"min/avg/max/(?:mdev|stddev) = [\d.]+/([\d.]+)/", output)
        if match:
            return float(match.group(1))

        match = re.search(r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)/", output)
        if match:
            return float(match.group(1))

        return None

    async def _ping_windows(self, host: str, count: int) -> float | None:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-n", str(count), "-w", "3000", host,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        if proc.returncode != 0:
            return None

        output = stdout.decode()
        match = re.search(r"Media = ([\d.]+)ms", output)
        if match:
            return float(match.group(1))

        match = re.search(r"Promedio = ([\d.]+)ms", output)
        if match:
            return float(match.group(1))

        match = re.search(r"Average = ([\d.]+)ms", output)
        if match:
            return float(match.group(1))

        return None
