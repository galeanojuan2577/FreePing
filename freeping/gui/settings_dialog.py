from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from freeping.core.config import AppConfig


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self._original = config
        self.setWindowTitle("FreePing Settings")
        self.setMinimumWidth(450)

        self._setup_ui()
        self._load_config(config)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        vps_group = QGroupBox("VPS Configuration")
        vps_layout = QFormLayout(vps_group)

        self.vps_ip = QLineEdit()
        self.vps_ip.setPlaceholderText("Public IP address")
        vps_layout.addRow("VPS IP:", self.vps_ip)

        self.vps_port = QSpinBox()
        self.vps_port.setRange(1024, 65535)
        self.vps_port.setValue(51820)
        vps_layout.addRow("WireGuard Port:", self.vps_port)

        layout.addWidget(vps_group)

        general_group = QGroupBox("General")
        general_layout = QVBoxLayout(general_group)

        self.auto_reconnect = QCheckBox("Auto-reconnect on disconnect")
        general_layout.addWidget(self.auto_reconnect)

        self.minimize_tray = QCheckBox("Minimize to system tray on close")
        general_layout.addWidget(self.minimize_tray)

        self.start_boot = QCheckBox("Start on system boot")
        general_layout.addWidget(self.start_boot)

        layout.addWidget(general_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_config(self, config: AppConfig) -> None:
        self.vps_ip.setText(config.vps_ip)
        self.vps_port.setValue(config.tunnel.vps_port)
        self.auto_reconnect.setChecked(config.auto_reconnect)
        self.minimize_tray.setChecked(config.minimize_to_tray)
        self.start_boot.setChecked(config.start_on_boot)

    def _save_and_accept(self) -> None:
        self._original.vps_ip = self.vps_ip.text().strip()
        self._original.tunnel.vps_port = self.vps_port.value()
        self._original.auto_reconnect = self.auto_reconnect.isChecked()
        self._original.minimize_to_tray = self.minimize_tray.isChecked()
        self._original.start_on_boot = self.start_boot.isChecked()
        self._original.save()
        self.accept()
