from __future__ import annotations

import asyncio
import logging
import platform
from collections.abc import Callable

from freeping.core.models import TunnelState

logger = logging.getLogger("freeping.watchdog")


class Watchdog:
    def __init__(
        self,
        vps_ip: str,
        check_interval: float = 10.0,
        max_failures: int = 3,
        on_state_change: Callable[[TunnelState], None] | None = None,
        on_reconnect: Callable[[], None] | None = None,
    ) -> None:
        self.vps_ip = vps_ip
        self.check_interval = check_interval
        self.max_failures = max_failures
        self.on_state_change = on_state_change
        self.on_reconnect = on_reconnect

        self._running = False
        self._task: asyncio.Task | None = None
        self._failures = 0
        self._current_state = TunnelState.INACTIVE

    @property
    def current_state(self) -> TunnelState:
        return self._current_state

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _run(self) -> None:
        while self._running:
            try:
                connected = await self._check_connectivity()

                if connected:
                    if self._current_state != TunnelState.ACTIVE:
                        self._set_state(TunnelState.ACTIVE)
                    self._failures = 0
                else:
                    self._failures += 1
                    logger.warning(f"Watchdog: connectivity check failed ({self._failures}/{self.max_failures})")

                    if self._failures >= self.max_failures:
                        logger.info("Watchdog: max failures reached, triggering reconnect")
                        self._set_state(TunnelState.ERROR)
                        if self.on_reconnect:
                            try:
                                await asyncio.to_thread(self.on_reconnect)
                            except Exception as e:
                                logger.error(f"Watchdog: reconnect handler failed: {e}")
                        self._failures = 0

                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Watchdog: unexpected error: {e}")
                await asyncio.sleep(self.check_interval)

    async def _check_connectivity(self) -> bool:
        try:
            ping_cmd = [*self._ping_cmd(), self.vps_ip]
            proc = await asyncio.create_subprocess_exec(
                *ping_cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
            return proc.returncode == 0
        except FileNotFoundError:
            return await self._check_connectivity_http()

    @staticmethod
    def _ping_cmd(timeout_sec: int = 3) -> list[str]:
        if platform.system() == "Windows":
            return ["ping", "-n", "1", "-w", str(timeout_sec * 1000)]
        return ["ping", "-c", "1", "-W", str(timeout_sec)]

    async def _check_connectivity_http(self) -> bool:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.get(f"http://{self.vps_ip}:51820", timeout=5.0)
                return True
        except Exception:
            return False

    def _set_state(self, state: TunnelState) -> None:
        self._current_state = state
        if self.on_state_change:
            try:
                self.on_state_change(state)
            except Exception as e:
                logger.error(f"Watchdog: state change handler error: {e}")


class KeepAlive:
    def __init__(
        self,
        vps_ip: str,
        interval: float = 300.0,
    ) -> None:
        self.vps_ip = vps_ip
        self.interval = interval
        self._running = False
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while self._running:
            try:
                await self._ping()
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(self.interval)

    async def _ping(self) -> None:
        try:
            args = Watchdog._ping_cmd(timeout_sec=5) + [self.vps_ip]
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
        except FileNotFoundError:
            pass
