from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

logger = logging.getLogger("freeping.keepalive")


class OracleKeepAlive:
    def __init__(
        self,
        oci_api_call: Callable[[], object],
        interval: float = 14400.0,
        on_success: Callable[[], None] | None = None,
        on_failure: Callable[[Exception], None] | None = None,
    ) -> None:
        self._api_call = oci_api_call
        self.interval = interval
        self._on_success = on_success
        self._on_failure = on_failure
        self._running = False
        self._task: asyncio.Task | None = None
        self._cycles = 0

    @property
    def cycles(self) -> int:
        return self._cycles

    @property
    def is_running(self) -> bool:
        return self._running

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
                await asyncio.to_thread(self._api_call)
                self._cycles += 1
                logger.info(
                    f"OracleKeepAlive: cycle {self._cycles} completed successfully"
                )
                if self._on_success:
                    self._on_success()
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"OracleKeepAlive: cycle failed: {e}")
                if self._on_failure:
                    try:
                        self._on_failure(e)
                    except Exception as cb_err:
                        logger.error(f"OracleKeepAlive: failure callback error: {cb_err}")
                await asyncio.sleep(self.interval)
