from __future__ import annotations

import platform
import re
import subprocess
from pathlib import Path

from freeping.core.models import TunnelConfig, TunnelState


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
        result = subprocess.run(
            ["wg-quick", "up", str(conf_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise TunnelError(f"wg-quick up failed: {result.stderr.strip()}")

    def _stop_linux(self) -> None:
        try:
            subprocess.run(
                ["wg-quick", "down", self._interface_name],
                capture_output=True, text=True,
            )
        except subprocess.CalledProcessError:
            try:
                subprocess.run(
                    ["ip", "link", "delete", self._interface_name],
                    capture_output=True, text=True,
                )
            except subprocess.CalledProcessError:
                pass

    def _check_linux_interface(self) -> bool:
        try:
            result = subprocess.run(
                ["ip", "link", "show", self._interface_name],
                capture_output=True, text=True,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def _start_windows(self, conf_path: Path) -> None:
        wg_exe = self._find_wireguard_windows()
        if wg_exe:
            result = subprocess.run(
                [wg_exe, "/installtunnelservice", str(conf_path)],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                raise TunnelError(f"WireGuard install failed: {result.stderr.strip()}")

            subprocess.run(
                ["net", "start", f"WireGuardTunnel${self._interface_name}"],
                capture_output=True, text=True,
            )
        else:
            result = subprocess.run(
                ["wg-quick", "up", str(conf_path)],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                raise TunnelError(f"wg-quick up failed: {result.stderr.strip()}")

    def _stop_windows(self) -> None:
        wg_exe = self._find_wireguard_windows()
        if wg_exe:
            subprocess.run(
                ["net", "stop", f"WireGuardTunnel${self._interface_name}"],
                capture_output=True, text=True,
            )
            subprocess.run(
                [wg_exe, "/uninstalltunnelservice", self._interface_name],
                capture_output=True, text=True,
            )
        else:
            subprocess.run(
                ["wg-quick", "down", self._interface_name],
                capture_output=True, text=True,
            )

    def _check_windows_interface(self) -> bool:
        try:
            result = subprocess.run(
                ["wg", "show", self._interface_name],
                capture_output=True, text=True,
            )
            return result.returncode == 0
        except FileNotFoundError:
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
        except Exception:
            pass
        return {}
