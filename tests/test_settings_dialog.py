from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QDialog

from freeping.core.config import AppConfig
from freeping.gui.settings_dialog import SettingsDialog


@pytest.fixture
def mock_config() -> MagicMock:
    cfg = MagicMock(spec=AppConfig)
    cfg.vps_ip = "203.0.113.1"
    cfg.auto_reconnect = True
    cfg.minimize_to_tray = False
    cfg.start_on_boot = True
    cfg.tunnel = MagicMock()
    cfg.tunnel.vps_port = 51820
    return cfg


class TestSettingsDialogInit:
    def test_window_title(self, qtbot, mock_config: MagicMock) -> None:
        dialog = SettingsDialog(mock_config)
        qtbot.add_widget(dialog)
        assert "Configuración" in dialog.windowTitle()

    def test_minimum_width(self, qtbot, mock_config: MagicMock) -> None:
        dialog = SettingsDialog(mock_config)
        qtbot.add_widget(dialog)
        assert dialog.minimumWidth() >= 450

    def test_loads_vps_ip(self, qtbot, mock_config: MagicMock) -> None:
        dialog = SettingsDialog(mock_config)
        qtbot.add_widget(dialog)
        assert dialog.vps_ip.text() == "203.0.113.1"

    def test_loads_vps_port(self, qtbot, mock_config: MagicMock) -> None:
        dialog = SettingsDialog(mock_config)
        qtbot.add_widget(dialog)
        assert dialog.vps_port.value() == 51820

    def test_loads_auto_reconnect(self, qtbot, mock_config: MagicMock) -> None:
        dialog = SettingsDialog(mock_config)
        qtbot.add_widget(dialog)
        assert dialog.auto_reconnect.isChecked() is True

    def test_loads_minimize_to_tray(self, qtbot, mock_config: MagicMock) -> None:
        dialog = SettingsDialog(mock_config)
        qtbot.add_widget(dialog)
        assert dialog.minimize_tray.isChecked() is False

    def test_loads_start_on_boot(self, qtbot, mock_config: MagicMock) -> None:
        dialog = SettingsDialog(mock_config)
        qtbot.add_widget(dialog)
        assert dialog.start_boot.isChecked() is True

    def test_spinbox_range(self, qtbot, mock_config: MagicMock) -> None:
        dialog = SettingsDialog(mock_config)
        qtbot.add_widget(dialog)
        assert dialog.vps_port.minimum() == 1024
        assert dialog.vps_port.maximum() == 65535

    def test_default_port_when_not_configured(self, qtbot) -> None:
        cfg = MagicMock(spec=AppConfig)
        cfg.vps_ip = ""
        cfg.auto_reconnect = False
        cfg.minimize_to_tray = False
        cfg.start_on_boot = False
        cfg.tunnel = MagicMock()
        cfg.tunnel.vps_port = 51820
        dialog = SettingsDialog(cfg)
        qtbot.add_widget(dialog)
        assert dialog.vps_port.value() == 51820


class TestSettingsDialogSave:
    def test_accept_saves_config(self, qtbot, mock_config: MagicMock) -> None:
        dialog = SettingsDialog(mock_config)
        qtbot.add_widget(dialog)

        dialog.vps_ip.setText("10.0.0.1")
        dialog.vps_port.setValue(1194)
        dialog.auto_reconnect.setChecked(False)
        dialog.minimize_tray.setChecked(True)
        dialog.start_boot.setChecked(False)

        dialog._save_and_accept()

        assert mock_config.vps_ip == "10.0.0.1"
        assert mock_config.tunnel.vps_port == 1194
        assert mock_config.auto_reconnect is False
        assert mock_config.minimize_to_tray is True
        assert mock_config.start_on_boot is False
        mock_config.save.assert_called_once()

    def test_accept_button_triggers_save(self, qtbot, mock_config: MagicMock) -> None:
        dialog = SettingsDialog(mock_config)
        qtbot.add_widget(dialog)

        with patch.object(dialog, "_save_and_accept") as mock_save:
            dialog.accept()
            mock_save.assert_not_called()

    def test_accept_closes_dialog(self, qtbot, mock_config: MagicMock) -> None:
        dialog = SettingsDialog(mock_config)
        qtbot.add_widget(dialog)

        dialog._save_and_accept()

        assert dialog.result() == QDialog.DialogCode.Accepted

    def test_cancel_does_not_save(self, qtbot, mock_config: MagicMock) -> None:
        dialog = SettingsDialog(mock_config)
        qtbot.add_widget(dialog)

        dialog.reject()

        mock_config.save.assert_not_called()

    def test_ip_trimmed_on_save(self, qtbot, mock_config: MagicMock) -> None:
        dialog = SettingsDialog(mock_config)
        qtbot.add_widget(dialog)

        dialog.vps_ip.setText("  10.0.0.1  ")
        dialog._save_and_accept()

        assert mock_config.vps_ip == "10.0.0.1"


