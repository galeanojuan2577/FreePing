from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from freeping.core.keepalive import OracleKeepAlive


class TestOracleKeepAlive:
    def test_initial_state(self) -> None:
        ka = OracleKeepAlive(oci_api_call=lambda: {"ok": True})
        assert ka.cycles == 0
        assert not ka.is_running

    @pytest.mark.asyncio
    async def test_double_start_is_safe(self) -> None:
        ka = OracleKeepAlive(oci_api_call=lambda: {"ok": True}, interval=0.01)
        ka.start()
        assert ka.is_running
        ka.start()
        assert ka._task is not None
        await ka.stop()
        assert not ka.is_running

    @pytest.mark.asyncio
    async def test_successful_cycle_increments_counter(self) -> None:
        api_mock = MagicMock(return_value={"id": "test"})
        ka = OracleKeepAlive(oci_api_call=api_mock, interval=0.01)
        ka.start()
        await asyncio.sleep(0.05)
        assert ka.cycles >= 1
        await ka.stop()

    @pytest.mark.asyncio
    async def test_on_success_callback(self) -> None:
        callback = MagicMock()
        ka = OracleKeepAlive(
            oci_api_call=lambda: {"ok": True},
            interval=0.01,
            on_success=callback,
        )
        ka.start()
        await asyncio.sleep(0.05)
        assert callback.called
        await ka.stop()

    @pytest.mark.asyncio
    async def test_on_failure_callback(self) -> None:
        callback = MagicMock()
        ka = OracleKeepAlive(
            oci_api_call=_raise_error,
            interval=0.01,
            on_failure=callback,
        )
        ka.start()
        await asyncio.sleep(0.05)
        assert callback.called
        await ka.stop()

    @pytest.mark.asyncio
    async def test_does_not_crash_on_api_failure(self) -> None:
        ka = OracleKeepAlive(oci_api_call=_raise_error, interval=0.01)
        ka.start()
        await asyncio.sleep(0.05)
        assert ka.cycles == 0
        assert ka.is_running
        await ka.stop()

    @pytest.mark.asyncio
    async def test_stop_stops_loop(self) -> None:
        api_mock = MagicMock(return_value={"id": "test"})
        ka = OracleKeepAlive(oci_api_call=api_mock, interval=0.01)
        ka.start()
        await asyncio.sleep(0.05)
        await ka.stop()
        assert not ka.is_running
        prev_cycles = ka.cycles
        await asyncio.sleep(0.05)
        assert ka.cycles == prev_cycles

    @pytest.mark.asyncio
    async def test_start_stop_multiple_times(self) -> None:
        ka = OracleKeepAlive(oci_api_call=lambda: {"ok": True}, interval=0.01)
        ka.start()
        await asyncio.sleep(0.05)
        assert ka.is_running
        await ka.stop()
        assert not ka.is_running
        cycles_first = ka.cycles

        ka.start()
        await asyncio.sleep(0.05)
        assert ka.is_running
        assert ka.cycles >= cycles_first
        await ka.stop()

    @pytest.mark.asyncio
    async def test_stop_twice_is_safe(self) -> None:
        ka = OracleKeepAlive(oci_api_call=lambda: {"ok": True})
        await ka.stop()
        assert not ka.is_running
        await ka.stop()
        assert not ka.is_running

    @pytest.mark.asyncio
    async def test_stop_without_start_is_safe(self) -> None:
        ka = OracleKeepAlive(oci_api_call=lambda: {"ok": True})
        await ka.stop()
        assert not ka.is_running


def _raise_error() -> object:
    raise ValueError("API failure")
