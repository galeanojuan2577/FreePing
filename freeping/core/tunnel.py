from __future__ import annotations

import logging
import platform
import re
import subprocess
from pathlib import Path

from freeping.core.models import TunnelConfig, TunnelState

logger = logging.getLogger("freeping.tunnel")

_SUBPROCESS_TIMEOUT = 30


class TunnelError(Exception):
    pass


class TunnelManager:
    def __init__(self, config: TunnelConfig) -> None:
        self.config = config
        self._state = TunnelState.INACTIVE
        self._process: subprocess.Popen | None = None
        self._interface_name = "freeping"
        self._is_windows = platform.system() == "Windows"

    @property
    def state(self) -> TunnelState:
        return self._state

    def generate_conf_file(self, conf_path: Path) -> None:
        conf_path.parent.mkdir(parents=True, exist_ok=True)
        conf_path.write_text(self.config.to_wireguard_conf())
        if not self._is_windows:
            conf_path.chmod(0o600)

    async def start(self, conf_path: Path) -> None:
        self._state = TunnelState.CONNECTING
        try:
            self.generate_conf_file(conf_path)

            if self._is_windows:
                self._start_windows(conf_path)
            else:
                self._start_linux(conf_path)

            self._state = TunnelState.ACTIVE
        except Exception as e:
            self._state = TunnelState.ERROR
            if conf_path.exists():
                conf_path.unlink()
            raise TunnelError(f"Failed to start tunnel: {e}")

    async def stop(self) -> None:
        try:
            if self._is_windows:
                self._stop_windows()
            else:
                self._stop_linux()
            self._state = TunnelState.INACTIVE
        except Exception as e:
            self._state = TunnelState.ERROR
            raise TunnelError(f"Failed to stop tunnel: {e}")

    async def update_game_ips(self, ips: list[str], conf_path: Path) -> None:
        was_active = self._state == TunnelState.ACTIVE
        if was_active:
            await self.stop()
        self.config.allowed_ips = ips
        if was_active:
            await self.start(conf_path)

    def is_active(self) -> bool:
        if self._is_windows:
            return self._check_windows_interface()
        return self._check_linux_interface()

    def _start_linux(self, conf_path: Path) -> None:
        try:
            result = subprocess.run(
                ["wg-quick", "up", str(conf_path)],
                capture_output=True, text=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise TunnelError("wg-quick up timed out")
        if result.returncode != 0:
            raise TunnelError(f"wg-quick up failed: {result.stderr.strip()}")

    def _stop_linux(self) -> None:
        try:
            subprocess.run(
                ["wg-quick", "down", self._interface_name],
                capture_output=True, text=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.warning("wg-quick down failed: %s", e)
            try:
                subprocess.run(
                    ["ip", "link", "delete", self._interface_name],
                    capture_output=True, text=True,
                    timeout=_SUBPROCESS_TIMEOUT,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e2:
                logger.warning("ip link delete failed: %s", e2)

    def _check_linux_interface(self) -> bool:
        try:
            result = subprocess.run(
                ["ip", "link", "show", self._interface_name],
                capture_output=True, text=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.debug("Interface check failed: %s", e)
            return False

    def _start_windows(self, conf_path: Path) -> None:
        wg_exe = self._find_wireguard_windows()
        if wg_exe:
            try:
                result = subprocess.run(
                    [wg_exe, "/installtunnelservice", str(conf_path)],
                    capture_output=True, text=True,
                    timeout=_SUBPROCESS_TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                raise TunnelError("WireGuard install timed out")
            if result.returncode != 0:
                raise TunnelError(f"WireGuard install failed: {result.stderr.strip()}")

            try:
                subprocess.run(
                    ["net", "start", f"WireGuardTunnel${self._interface_name}"],
                    capture_output=True, text=True,
                    timeout=_SUBPROCESS_TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                raise TunnelError("WireGuard service start timed out")
        else:
            try:
                result = subprocess.run(
                    ["wg-quick", "up", str(conf_path)],
                    capture_output=True, text=True,
                    timeout=_SUBPROCESS_TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                raise TunnelError("wg-quick up timed out")
            if result.returncode != 0:
                raise TunnelError(f"wg-quick up failed: {result.stderr.strip()}")

    def _stop_windows(self) -> None:
        wg_exe = self._find_wireguard_windows()
        if wg_exe:
            try:
                subprocess.run(
                    ["net", "stop", f"WireGuardTunnel${self._interface_name}"],
                    capture_output=True, text=True,
                    timeout=_SUBPROCESS_TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                logger.warning("WireGuard service stop timed out")
            try:
                subprocess.run(
                    [wg_exe, "/uninstalltunnelservice", self._interface_name],
                    capture_output=True, text=True,
                    timeout=_SUBPROCESS_TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                logger.warning("WireGuard uninstall timed out")
        else:
            try:
                subprocess.run(
                    ["wg-quick", "down", self._interface_name],
                    capture_output=True, text=True,
                    timeout=_SUBPROCESS_TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                logger.warning("wg-quick down timed out")

    def _check_windows_interface(self) -> bool:
        try:
            result = subprocess.run(
                ["wg", "show", self._interface_name],
                capture_output=True, text=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.debug("Windows interface check failed: %s", e)
            return False

    @staticmethod
    def _find_wireguard_windows() -> str | None:
        candidates = [
            "C:\\Program Files\\WireGuard\\wireguard.exe",
            "C:\\Program Files (x86)\\WireGuard\\wireguard.exe",
        ]
        for path in candidates:
            if Path(path).exists():
                return path
        return None

    def get_interface_stats(self) -> dict:
        try:
            result = subprocess.run(
                ["wg", "show", self._interface_name, "transfer"],
                capture_output=True, text=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
            if result.returncode == 0:
                match = re.search(
                    r"(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
                    result.stdout,
                )
                if match:
                    return {
                        "received_bytes": int(match.group(1)),
                        "sent_bytes": int(match.group(2)),
                        "received_packets": int(match.group(3)),
                        "sent_packets": int(match.group(4)),
                    }
        except subprocess.TimeoutExpired:
            logger.warning("wg show transfer timed out")
        except Exception as e:
            logger.debug("Failed to get interface stats: %s", e)
        return {}
