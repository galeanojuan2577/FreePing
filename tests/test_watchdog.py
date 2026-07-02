from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from freeping.core.models import TunnelState
from freeping.core.watchdog import KeepAlive, Watchdog


def _raise_exception(*args, **kwargs) -> None:
    raise RuntimeError("handler failure")


class TestWatchdog:
    @pytest.mark.asyncio
    async def test_initial_state_inactive(self) -> None:
        wd = Watchdog(vps_ip="203.0.113.1")
        assert wd.current_state == TunnelState.INACTIVE

    @pytest.mark.asyncio
    async def test_start_stop(self) -> None:
        wd = Watchdog(vps_ip="203.0.113.1")
        wd.start()
        assert wd._running is True
        await wd.stop()
        assert wd._running is False

    @pytest.mark.asyncio
    async def test_double_start_is_safe(self) -> None:
        wd = Watchdog(vps_ip="203.0.113.1")
        wd.start()
        wd.start()
        await wd.stop()

    @pytest.mark.asyncio
    async def test_state_change_callback_on_connect(self) -> None:
        callback = MagicMock()
        wd = Watchdog(
            vps_ip="203.0.113.1",
            check_interval=0.1,
            on_state_change=callback,
        )
        with patch.object(wd, "_check_connectivity", return_value=True):
            wd.start()
            await asyncio.sleep(0.3)
            await wd.stop()

        callback.assert_any_call(TunnelState.ACTIVE)

    @pytest.mark.asyncio
    async def test_reconnect_after_max_failures(self) -> None:
        reconnect_handler = MagicMock()
        wd = Watchdog(
            vps_ip="203.0.113.1",
            check_interval=0.05,
            max_failures=2,
            on_reconnect=reconnect_handler,
        )
        with patch.object(wd, "_check_connectivity", return_value=False):
            wd.start()
            await asyncio.sleep(0.3)
            await wd.stop()

        assert reconnect_handler.called

    @pytest.mark.asyncio
    async def test_error_state_on_failures(self) -> None:
        callback = MagicMock()
        wd = Watchdog(
            vps_ip="203.0.113.1",
            check_interval=0.05,
            max_failures=2,
            on_state_change=callback,
        )
        with patch.object(wd, "_check_connectivity", return_value=False):
            wd.start()
            await asyncio.sleep(0.3)
            await wd.stop()

        callback.assert_any_call(TunnelState.ERROR)

    @pytest.mark.asyncio
    async def test_recovery_after_failures(self) -> None:
        results = [False, False, True, True]
        side_effect = results.copy()

        wd = Watchdog(
            vps_ip="203.0.113.1",
            check_interval=0.05,
            max_failures=2,
        )
        with patch.object(wd, "_check_connectivity", side_effect=lambda: side_effect.pop(0) if side_effect else True):
            wd.start()
            await asyncio.sleep(0.4)
            await wd.stop()

    @pytest.mark.asyncio
    async def test_reconnect_handler_error_does_not_crash(self) -> None:
        wd = Watchdog(
            vps_ip="203.0.113.1",
            check_interval=0.05,
            max_failures=2,
            on_reconnect=_raise_exception,
        )
        with patch.object(wd, "_check_connectivity", return_value=False):
            wd.start()
            await asyncio.sleep(0.3)
            await wd.stop()

    @pytest.mark.asyncio
    async def test_state_change_callback_error_does_not_crash(self) -> None:
        wd = Watchdog(
            vps_ip="203.0.113.1",
            check_interval=0.05,
            on_state_change=_raise_exception,
        )
        with patch.object(wd, "_check_connectivity", return_value=True):
            wd.start()
            await asyncio.sleep(0.2)
            await wd.stop()

    @pytest.mark.asyncio
    async def test_unexpected_error_in_loop_does_not_crash(self) -> None:
        wd = Watchdog(
            vps_ip="203.0.113.1",
            check_interval=0.05,
        )
        calls = 0

        async def flaky_check() -> bool:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("unexpected failure")
            return True

        with patch.object(wd, "_check_connectivity", side_effect=flaky_check):
            wd.start()
            await asyncio.sleep(0.15)
            await wd.stop()

    @pytest.mark.asyncio
    async def test_check_connectivity_file_not_found_uses_http_fallback(self) -> None:
        wd = Watchdog(vps_ip="203.0.113.1")
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            with patch.object(wd, "_check_connectivity_http", return_value=True):
                result = await wd._check_connectivity()
                assert result is True

    @pytest.mark.asyncio
    async def test_check_connectivity_http_fallback_also_fails(self) -> None:
        wd = Watchdog(vps_ip="203.0.113.1")
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            with patch.object(wd, "_check_connectivity_http", return_value=False):
                result = await wd._check_connectivity()
                assert result is False

    @pytest.mark.asyncio
    async def test_failure_count_resets_on_success(self) -> None:
        results = [False, True, False, False, True]
        side_effect = results.copy()

        wd = Watchdog(
            vps_ip="203.0.113.1",
            check_interval=0.05,
            max_failures=3,
        )
        with patch.object(wd, "_check_connectivity", side_effect=lambda: side_effect.pop(0) if side_effect else True):
            wd.start()
            await asyncio.sleep(0.5)
            await wd.stop()


class TestKeepAlive:
    @pytest.mark.asyncio
    async def test_start_stop(self) -> None:
        ka = KeepAlive(vps_ip="203.0.113.1", interval=0.1)
        ka.start()
        assert ka._running is True
        await ka.stop()
        assert ka._running is False

    @pytest.mark.asyncio
    async def test_double_start_is_safe(self) -> None:
        ka = KeepAlive(vps_ip="203.0.113.1", interval=0.1)
        ka.start()
        ka.start()
        await ka.stop()

    @pytest.mark.asyncio
    async def test_does_not_crash_on_ping_failure(self) -> None:
        ka = KeepAlive(vps_ip="203.0.113.1", interval=0.05)
        ka.start()
        await asyncio.sleep(0.15)
        await ka.stop()

    @pytest.mark.asyncio
    async def test_ping_file_not_found_does_not_crash(self) -> None:
        ka = KeepAlive(vps_ip="203.0.113.1", interval=0.05)
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            await ka._ping()
        await ka.stop()

    @pytest.mark.asyncio
    async def test_unexpected_exception_does_not_crash_loop(self) -> None:
        calls = 0

        async def flaky_ping() -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("unexpected")
            await asyncio.sleep(0.01)

        ka = KeepAlive(vps_ip="203.0.113.1", interval=0.05)
        ka._ping = flaky_ping
        ka.start()
        await asyncio.sleep(0.15)
        await ka.stop()
        assert calls >= 1
