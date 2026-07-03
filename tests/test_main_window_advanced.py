# ruff: noqa: F821
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PySide6.QtGui import QCloseEvent, QShowEvent
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from freeping.core.config import AppConfig
from freeping.core.models import LatencyResult, TunnelState


@pytest.fixture
def window(qtbot: QtBot, temp_config_dir: Path) -> FreePingWindow:
    from freeping.gui.main_window import FreePingWindow

    mock_tray = MagicMock()
    mock_tray.isVisible.return_value = True
    patcher = patch("freeping.gui.main_window.TrayIcon", return_value=mock_tray)
    patcher.start()

    win = FreePingWindow()
    qtbot.addWidget(win)
    win._first_show = False
    win._mock_tray = mock_tray

    yield win

    patcher.stop()
    win.close()


@pytest.fixture
def configured_window(window: FreePingWindow, temp_config_dir: Path) -> FreePingWindow:
    temp_config_dir.mkdir(parents=True, exist_ok=True)
    config_file = temp_config_dir / "config.json"
    config_file.write_text(json.dumps({"vps_ip": "203.0.113.1"}))
    window.config = AppConfig.load()
    window._update_ui_state()
    return window


class TestAutoRunWizard:
    def test_offscreen_mode_returns_early(self, window: FreePingWindow) -> None:
        window._auto_run_wizard()
        assert "No configurado" in window.status_text.text()

    def test_offscreen_sets_status_log(self, window: FreePingWindow) -> None:
        window._auto_run_wizard()
        assert "No configurado" in window.status_text.text()
        assert "Asistente" in window.log_output.toPlainText()

    def test_non_offscreen_declines_wizard(self, window: FreePingWindow) -> None:
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "xcb"}, clear=False):
            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
                with patch.object(window, "_run_wizard") as mock_wiz:
                    window._auto_run_wizard()
                    mock_wiz.assert_not_called()

    def test_non_offscreen_accepts_wizard(self, window: FreePingWindow) -> None:
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "xcb"}, clear=False):
            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
                with patch.object(window, "_run_wizard") as mock_wiz:
                    window._auto_run_wizard()
                    mock_wiz.assert_called_once()


class TestSetupMenu:
    def test_creates_all_actions(self, window: FreePingWindow) -> None:
        assert hasattr(window, "action_setup")
        assert hasattr(window, "action_quit")
        assert hasattr(window, "action_toggle")
        assert hasattr(window, "action_test")
        assert hasattr(window, "action_about")

    def test_action_setup_has_tooltip(self, window: FreePingWindow) -> None:
        assert "Aprovisionar" in window.action_setup.toolTip()

    def test_action_quit_has_shortcut(self, window: FreePingWindow) -> None:
        assert window.action_quit.shortcut().toString() == "Ctrl+Q"

    def test_action_toggle_has_shortcut(self, window: FreePingWindow) -> None:
        assert window.action_toggle.shortcut().toString() == "Ctrl+T"

    def test_action_test_has_shortcut(self, window: FreePingWindow) -> None:
        assert window.action_test.shortcut().toString() == "Ctrl+R"


class TestConnectSignals:
    def test_toggle_button_triggers_toggle(self, window: FreePingWindow) -> None:
        with patch.object(window, "_toggle_tunnel") as mock_toggle:
            window.btn_toggle.clicked.emit()
            mock_toggle.assert_called_once()

    def test_toggle_action_triggers_toggle(self, window: FreePingWindow) -> None:
        with patch.object(window, "_toggle_tunnel") as mock_toggle:
            window.action_toggle.trigger()
            mock_toggle.assert_called_once()

    def test_test_button_triggers_run_test(self, window: FreePingWindow) -> None:
        with patch.object(window, "_run_test") as mock_test:
            window.btn_test.clicked.emit()
            mock_test.assert_called_once()

    def test_test_action_triggers_run_test(self, window: FreePingWindow) -> None:
        with patch.object(window, "_run_test") as mock_test:
            window.action_test.trigger()
            mock_test.assert_called_once()

    def test_settings_button_triggers_open_settings(self, window: FreePingWindow) -> None:
        with patch.object(window, "_open_settings") as mock_settings:
            window.btn_settings.clicked.emit()
            mock_settings.assert_called_once()

    def test_setup_action_triggers_run_wizard(self, window: FreePingWindow) -> None:
        with patch.object(window, "_run_wizard") as mock_wizard:
            window.action_setup.trigger()
            mock_wizard.assert_called_once()

    def test_quit_action_created(self, window: FreePingWindow) -> None:
        assert window.action_quit.text() == "Salir"
        assert window.action_quit.shortcut().toString() == "Ctrl+Q"
        assert not window.action_quit.isSeparator()

    def test_about_action_triggers_show_about(self, window: FreePingWindow) -> None:
        with patch.object(window, "_show_about") as mock_about:
            window.action_about.trigger()
            mock_about.assert_called_once()

    def test_game_combo_triggers_on_game_changed(self, window: FreePingWindow) -> None:
        with patch.object(window, "_on_game_changed") as mock_changed:
            window.game_combo.currentIndexChanged.emit(1)
            mock_changed.assert_called_once()


class TestEventLoop:
    def test_start_event_loop_creates_loop_and_timer(self, window: FreePingWindow) -> None:
        assert window._event_loop is not None
        assert window._timer is not None
        assert window._timer.isActive()

    def test_process_async_tasks_when_loop_not_running(self, window: FreePingWindow) -> None:
        window._process_async_tasks()

    def test_process_async_tasks_stops_running_loop(self, window: FreePingWindow) -> None:
        async def dummy():
            pass

        window._event_loop.run_until_complete(dummy())
        assert window._event_loop.is_running() is False

    def test_process_async_tasks_with_active_loop(self, window: FreePingWindow) -> None:
        window._event_loop.call_soon(window._process_async_tasks)
        window._event_loop.call_soon(window._event_loop.stop)
        window._event_loop.run_forever()
        assert not window._event_loop.is_running()

    def test_start_event_loop_handles_exception(self, window: FreePingWindow, monkeypatch) -> None:
        def crash():
            raise RuntimeError("fail")

        monkeypatch.setattr("asyncio.new_event_loop", crash)
        from freeping.gui.main_window import FreePingWindow

        win = FreePingWindow()
        assert win._event_loop is None


class TestToggleTunnel:
    def test_toggle_not_configured_shows_wizard_prompt(self, window: FreePingWindow) -> None:
        window.config.vps_ip = ""
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            with patch.object(window, "_run_wizard") as mock_wizard:
                window._toggle_tunnel()
                mock_wizard.assert_called_once()

    def test_toggle_not_configured_decline(self, window: FreePingWindow) -> None:
        window.config.vps_ip = ""
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            with patch.object(window, "_run_wizard") as mock_wizard:
                window._toggle_tunnel()
                mock_wizard.assert_not_called()

    def test_toggle_when_active_deactivates(self, configured_window: FreePingWindow) -> None:
        configured_window._tunnel_state = TunnelState.ACTIVE
        with patch.object(configured_window, "_deactivate_tunnel") as mock_deact:
            configured_window._toggle_tunnel()
            mock_deact.assert_called_once()

    def test_toggle_when_inactive_activates(self, configured_window: FreePingWindow, temp_config_dir: Path) -> None:
        configured_window._tunnel_state = TunnelState.INACTIVE
        with patch.object(AppConfig, "CONFIG_DIR", temp_config_dir, create=True):
            with patch.object(configured_window, "_activate_tunnel") as mock_act:
                configured_window._toggle_tunnel()
                mock_act.assert_called_once()


class TestActivateDeactivateTunnel:
    @patch("freeping.core.tunnel.TunnelManager")
    def test_activate_tunnel_async_success(
        self, mock_tunnel_cls,
        configured_window: FreePingWindow,
        temp_config_dir: Path,
    ) -> None:
        mock_tunnel = MagicMock()
        mock_tunnel.start = AsyncMock()
        mock_tunnel_cls.return_value = mock_tunnel

        with patch.object(AppConfig, "CONFIG_DIR", temp_config_dir, create=True):
            configured_window._event_loop.run_until_complete(
                configured_window._activate_tunnel_async()
            )

        assert configured_window._tunnel_state == TunnelState.ACTIVE
        mock_tunnel.start.assert_awaited_once()
        assert "activado exitosamente" in configured_window.log_output.toPlainText().lower()

    @patch("freeping.core.tunnel.TunnelManager")
    def test_activate_tunnel_async_failure(
        self, mock_tunnel_cls,
        configured_window: FreePingWindow,
        temp_config_dir: Path,
    ) -> None:
        mock_tunnel = MagicMock()
        mock_tunnel.start = AsyncMock(side_effect=RuntimeError("Connection refused"))
        mock_tunnel_cls.return_value = mock_tunnel

        with patch.object(AppConfig, "CONFIG_DIR", temp_config_dir, create=True):
            with patch.object(QMessageBox, "critical"):
                configured_window._event_loop.run_until_complete(
                    configured_window._activate_tunnel_async()
                )

        assert configured_window._tunnel_state == TunnelState.ERROR
        assert "Error al activar" in configured_window.log_output.toPlainText()

    @patch("freeping.core.tunnel.TunnelManager")
    def test_activate_tunnel_auto_run_test_with_ips(
        self, mock_tunnel_cls,
        configured_window: FreePingWindow,
        temp_config_dir: Path,
    ) -> None:
        mock_tunnel = MagicMock()
        mock_tunnel.start = AsyncMock()
        mock_tunnel_cls.return_value = mock_tunnel

        configured_window.custom_ip_input.setPlainText("1.2.3.4")

        with patch.object(AppConfig, "CONFIG_DIR", temp_config_dir, create=True):
            with patch.object(configured_window, "_run_test"):
                configured_window._event_loop.run_until_complete(
                    configured_window._activate_tunnel_async()
                )

        assert configured_window._tunnel_state == TunnelState.ACTIVE
        assert "Probando mejora de ping" in configured_window.log_output.toPlainText()

    @patch("freeping.core.tunnel.TunnelManager")
    def test_activate_tunnel_sync_wrapper(
        self, mock_tunnel_cls,
        configured_window: FreePingWindow,
        temp_config_dir: Path,
    ) -> None:
        mock_tunnel = MagicMock()
        mock_tunnel.start = AsyncMock()
        mock_tunnel_cls.return_value = mock_tunnel

        with patch.object(AppConfig, "CONFIG_DIR", temp_config_dir, create=True):
            configured_window._activate_tunnel()

        assert configured_window._tunnel_state == TunnelState.ACTIVE

    @patch("freeping.core.tunnel.TunnelManager")
    def test_deactivate_tunnel_async_success(self, mock_tunnel_cls, configured_window: FreePingWindow) -> None:
        mock_tunnel = MagicMock()
        mock_tunnel.stop = AsyncMock()
        mock_tunnel_cls.return_value = mock_tunnel

        configured_window._ping_without = 50.0
        configured_window._ping_with = 30.0

        configured_window._event_loop.run_until_complete(
            configured_window._deactivate_tunnel_async()
        )

        assert configured_window._tunnel_state == TunnelState.INACTIVE
        mock_tunnel.stop.assert_awaited_once()
        assert configured_window._ping_without is None
        assert configured_window._ping_with is None

    @patch("freeping.core.tunnel.TunnelManager")
    def test_deactivate_tunnel_async_failure(self, mock_tunnel_cls, configured_window: FreePingWindow) -> None:
        mock_tunnel = MagicMock()
        mock_tunnel.stop = AsyncMock(side_effect=RuntimeError("Stop failed"))
        mock_tunnel_cls.return_value = mock_tunnel

        configured_window._event_loop.run_until_complete(
            configured_window._deactivate_tunnel_async()
        )

        assert "Error al desactivar" in configured_window.log_output.toPlainText()

    @patch("freeping.core.tunnel.TunnelManager")
    def test_deactivate_tunnel_sync_wrapper(self, mock_tunnel_cls, configured_window: FreePingWindow) -> None:
        mock_tunnel = MagicMock()
        mock_tunnel.stop = AsyncMock()
        mock_tunnel_cls.return_value = mock_tunnel

        configured_window._deactivate_tunnel()

        assert configured_window._tunnel_state == TunnelState.INACTIVE


class TestRunTest:
    @patch("freeping.core.ping.PingManager")
    def test_run_test_full_flow(self, mock_ping_cls, configured_window: FreePingWindow, qtbot: QtBot) -> None:
        mock_pm = MagicMock()
        mock_pm.compare = AsyncMock(
            return_value=LatencyResult(without_tunnel_ms=50.0, with_tunnel_ms=30.0)
        )
        mock_ping_cls.return_value = mock_pm

        configured_window.custom_ip_input.setPlainText("1.2.3.4\n5.6.7.8")

        with patch.object(QMessageBox, "information"):
            configured_window._run_test()

        assert configured_window._ping_without == 50.0
        assert configured_window._ping_with == 30.0
        mock_pm.compare.assert_called_once()

    def test_run_test_not_configured(self, window: FreePingWindow) -> None:
        window._run_test()
        assert "Configura tu VPS primero" in window.log_output.toPlainText()

    def test_run_test_no_game_selected(self, configured_window: FreePingWindow) -> None:
        configured_window._run_test()
        assert "Selecciona un juego" in configured_window.log_output.toPlainText()

    @patch("freeping.core.ping.PingManager")
    def test_run_test_logs_results(self, mock_ping_cls, configured_window: FreePingWindow, qtbot: QtBot) -> None:
        mock_pm = MagicMock()
        mock_pm.compare = AsyncMock(
            return_value=LatencyResult(without_tunnel_ms=50.0, with_tunnel_ms=30.0)
        )
        mock_ping_cls.return_value = mock_pm

        configured_window.custom_ip_input.setPlainText("1.2.3.4")

        with patch.object(QMessageBox, "information"):
            configured_window._run_test()

        log = configured_window.log_output.toPlainText()
        assert "50" in log
        assert "30" in log
        assert "Mejora" in log


class TestShowTestResultDialog:
    def test_with_improvement_shows_success(self, window: FreePingWindow) -> None:
        result = LatencyResult(without_tunnel_ms=100.0, with_tunnel_ms=60.0)
        with patch.object(QMessageBox, "information") as mock_info:
            window._show_test_result_dialog(result)
            mock_info.assert_called_once()
            args = mock_info.call_args[0]
            assert "Mejora" in args[2]
            assert "40" in args[2]

    def test_without_improvement_shows_no_gain(self, window: FreePingWindow) -> None:
        result = LatencyResult(without_tunnel_ms=60.0, with_tunnel_ms=60.0)
        with patch.object(QMessageBox, "information") as mock_info:
            window._show_test_result_dialog(result)
            mock_info.assert_called_once()
            args = mock_info.call_args[0]
            assert "No se detectó" in args[2]

    def test_worse_improvement_shows_no_gain(self, window: FreePingWindow) -> None:
        result = LatencyResult(without_tunnel_ms=50.0, with_tunnel_ms=80.0)
        with patch.object(QMessageBox, "information") as mock_info:
            window._show_test_result_dialog(result)
            mock_info.assert_called_once()
            args = mock_info.call_args[0]
            assert "No se detectó" in args[2]

    def test_no_comparison_no_message_box(self, window: FreePingWindow) -> None:
        result = LatencyResult(without_tunnel_ms=None, with_tunnel_ms=60.0)
        with patch.object(QMessageBox, "information") as mock_info:
            window._show_test_result_dialog(result)
            mock_info.assert_not_called()

    def test_no_comparison_logs_unavailable(self, window: FreePingWindow) -> None:
        result = LatencyResult(without_tunnel_ms=100.0, with_tunnel_ms=None)
        window._show_test_result_dialog(result)
        assert "No se pudo medir" in window.log_output.toPlainText()


class TestUpdatePingDisplay:
    def test_both_none(self, window: FreePingWindow) -> None:
        window._ping_without = None
        window._ping_with = None
        window._update_ping_display()
        assert window.ping_without.text() == "--- ms"
        assert window.ping_with.text() == "--- ms"
        assert window.ping_improvement.text() == "-- ms (--%)"

    def test_without_only(self, window: FreePingWindow) -> None:
        window._ping_without = 80.0
        window._ping_with = None
        window._update_ping_display()
        assert "80" in window.ping_without.text()
        assert window.ping_with.text() == "--- ms"

    def test_with_only(self, window: FreePingWindow) -> None:
        window._ping_without = None
        window._ping_with = 50.0
        window._update_ping_display()
        assert window.ping_without.text() == "--- ms"
        assert "50" in window.ping_with.text()

    def test_positive_improvement(self, window: FreePingWindow) -> None:
        window._ping_without = 100.0
        window._ping_with = 60.0
        window._update_ping_display()
        assert "40" in window.ping_improvement.text()
        assert "4CAF50" in window.ping_improvement.styleSheet()

    def test_negative_improvement(self, window: FreePingWindow) -> None:
        window._ping_without = 50.0
        window._ping_with = 80.0
        window._update_ping_display()
        assert "peor" in window.ping_improvement.text()
        assert "e74c3c" in window.ping_improvement.styleSheet()

    def test_zero_improvement(self, window: FreePingWindow) -> None:
        window._ping_without = 70.0
        window._ping_with = 70.0
        window._update_ping_display()
        assert "sin cambio" in window.ping_improvement.text()
        assert "666" in window.ping_improvement.styleSheet()


class TestGetSelectedIps:
    def test_custom_ips_returns_list(self, window: FreePingWindow) -> None:
        window.custom_ip_input.setPlainText("192.168.1.1\n10.0.0.1\n")
        ips = window._get_selected_ips()
        assert ips == ["192.168.1.1", "10.0.0.1"]

    def test_custom_ips_skips_empty_lines(self, window: FreePingWindow) -> None:
        window.custom_ip_input.setPlainText("1.1.1.1\n\n\n2.2.2.2")
        ips = window._get_selected_ips()
        assert ips == ["1.1.1.1", "2.2.2.2"]

    def test_custom_ips_trims_whitespace(self, window: FreePingWindow) -> None:
        window.custom_ip_input.setPlainText("  8.8.8.8  \n  1.1.1.1  ")
        ips = window._get_selected_ips()
        assert ips == ["8.8.8.8", "1.1.1.1"]

    @patch("freeping.data.games_list.load_games")
    def test_game_selected_returns_ip_ranges(self, mock_load_games, window: FreePingWindow) -> None:
        from freeping.core.models import Game, GamesList

        mock_games_list = GamesList(
            version=1,
            games=[Game(name="TestGame", ip_ranges=["10.0.0.0/8", "192.168.0.0/16"])],
        )
        mock_load_games.return_value = mock_games_list

        window.custom_ip_input.clear()
        window.game_combo.clear()
        window.game_combo.addItem("Select a game...")
        window.game_combo.addItem("TestGame")
        window.game_combo.setCurrentIndex(1)

        ips = window._get_selected_ips()
        assert ips == ["10.0.0.0/8", "192.168.0.0/16"]

    @patch("freeping.data.games_list.load_games")
    def test_game_not_found_returns_empty(self, mock_load_games, window: FreePingWindow) -> None:
        from freeping.core.models import GamesList

        mock_load_games.return_value = GamesList(version=1, games=[])

        window.custom_ip_input.clear()
        window.game_combo.clear()
        window.game_combo.addItem("Select a game...")
        window.game_combo.addItem("UnknownGame")
        window.game_combo.setCurrentIndex(1)

        ips = window._get_selected_ips()
        assert ips == []

    def test_empty_returns_empty_list(self, window: FreePingWindow) -> None:
        window.custom_ip_input.clear()
        window.game_combo.setCurrentIndex(0)
        ips = window._get_selected_ips()
        assert ips == []


class TestOnGameChanged:
    def test_clears_custom_ip_when_game_selected(self, window: FreePingWindow) -> None:
        window.custom_ip_input.setPlainText("1.2.3.4")
        window._on_game_changed(1)
        assert window.custom_ip_input.toPlainText() == ""

    def test_does_not_clear_custom_ip_for_select(self, window: FreePingWindow) -> None:
        window.custom_ip_input.setPlainText("1.2.3.4")
        window._on_game_changed(0)
        assert window.custom_ip_input.toPlainText() == "1.2.3.4"


class TestRunWizard:
    def test_run_wizard_accepted(self, window: FreePingWindow, temp_config_dir: Path) -> None:
        temp_config_dir.mkdir(parents=True, exist_ok=True)
        config_file = temp_config_dir / "config.json"
        config_file.write_text(json.dumps({"vps_ip": "203.0.113.1"}))

        with patch("freeping.gui.main_window.SetupWizard") as mock_wizard_cls:
            mock_wizard = MagicMock()
            mock_wizard_cls.DialogCode = type("DialogCode", (), {"Accepted": 1})
            mock_wizard.exec.return_value = 1
            mock_wizard_cls.return_value = mock_wizard

            with patch.object(QMessageBox, "information"):
                window._run_wizard()

            assert "Configuración completada" in window.log_output.toPlainText()
            assert "203.0.113.1" in window.vps_label.text()

    def test_run_wizard_not_accepted(self, window: FreePingWindow) -> None:
        with patch("freeping.gui.main_window.SetupWizard") as mock_wizard_cls:
            mock_wizard = MagicMock()
            mock_wizard_cls.DialogCode = type("DialogCode", (), {"Accepted": 1})
            mock_wizard.exec.return_value = 2
            mock_wizard_cls.return_value = mock_wizard

            window._run_wizard()

            assert "Setup completed" not in window.log_output.toPlainText()


class TestOpenSettings:
    def test_open_settings_accepted(self, window: FreePingWindow, temp_config_dir: Path) -> None:
        temp_config_dir.mkdir(parents=True, exist_ok=True)
        config_file = temp_config_dir / "config.json"
        config_file.write_text(json.dumps({"vps_ip": "203.0.113.1"}))

        with patch("freeping.gui.settings_dialog.SettingsDialog") as mock_dialog_cls:
            mock_dialog = MagicMock()
            mock_dialog_cls.DialogCode = type("DialogCode", (), {"Accepted": 1})
            mock_dialog.exec.return_value = 1
            mock_dialog_cls.return_value = mock_dialog

            window._open_settings()

            assert "Configuración guardada" in window.log_output.toPlainText()

    def test_open_settings_cancelled(self, window: FreePingWindow) -> None:
        with patch("freeping.gui.settings_dialog.SettingsDialog") as mock_dialog_cls:
            mock_dialog = MagicMock()
            mock_dialog_cls.DialogCode = type("DialogCode", (), {"Accepted": 1})
            mock_dialog.exec.return_value = 2
            mock_dialog_cls.return_value = mock_dialog

            window._open_settings()

            assert "Settings saved" not in window.log_output.toPlainText()


class TestShowAbout:
    def test_show_about(self, window: FreePingWindow) -> None:
        with patch.object(QMessageBox, "about") as mock_about:
            window._show_about()
            mock_about.assert_called_once()
            args = mock_about.call_args[0]
            assert "FreePing" in args[1]


class TestShowCloseEvents:
    def test_show_event_first_and_not_configured(self, window: FreePingWindow) -> None:
        window._first_show = True
        window.config.vps_ip = ""

        with patch.object(window, "_auto_run_wizard") as mock_auto:
            event = QShowEvent()
            window.showEvent(event)
            assert window._first_show is False
            mock_auto.assert_not_called()

    def test_show_event_first_and_configured(self, configured_window: FreePingWindow) -> None:
        configured_window._first_show = True

        with patch.object(configured_window, "_auto_run_wizard") as mock_auto:
            event = QShowEvent()
            configured_window.showEvent(event)
            assert configured_window._first_show is True
            mock_auto.assert_not_called()

    def test_show_event_not_first(self, window: FreePingWindow) -> None:
        window._first_show = False

        with patch.object(window, "_auto_run_wizard") as mock_auto:
            event = QShowEvent()
            window.showEvent(event)
            mock_auto.assert_not_called()

    def test_close_event_minimize_to_tray(self, configured_window: FreePingWindow) -> None:
        configured_window._mock_tray.isVisible.return_value = True
        configured_window.config.minimize_to_tray = True

        event = QCloseEvent()
        configured_window.closeEvent(event)
        assert configured_window.isVisible() is False

    def test_close_event_quit_without_minimize(self, window: FreePingWindow) -> None:
        window.config.minimize_to_tray = False

        event = QCloseEvent()
        window.closeEvent(event)

    def test_close_event_quit_tray_not_visible(self, configured_window: FreePingWindow) -> None:
        configured_window._mock_tray.isVisible.return_value = False
        configured_window.config.minimize_to_tray = True

        event = QCloseEvent()
        configured_window.closeEvent(event)


class TestLog:
    def test_log_appends_timestamped_message(self, window: FreePingWindow) -> None:
        window.log("Hello World")
        text = window.log_output.toPlainText()
        assert "Hello World" in text
        assert "[" in text
        assert "]" in text

    def test_log_scrolls_to_bottom(self, window: FreePingWindow) -> None:
        for i in range(20):
            window.log(f"Message {i}")
        sb = window.log_output.verticalScrollBar()
        assert sb.value() == sb.maximum()


class TestUpdateUiState:
    def test_active_state(self, configured_window: FreePingWindow) -> None:
        configured_window._tunnel_state = TunnelState.ACTIVE
        configured_window._update_ui_state()
        assert "●" in configured_window.status_icon.text()
        assert "Conectado" in configured_window.status_label.text()
        assert "Desactivar" in configured_window.btn_toggle.text()
        assert "4CAF50" in configured_window.status_icon.styleSheet()

    def test_error_state(self, configured_window: FreePingWindow) -> None:
        configured_window._tunnel_state = TunnelState.ERROR
        configured_window._update_ui_state()
        assert "●" in configured_window.status_icon.text()
        assert "Error" in configured_window.status_label.text()
        assert "Reintentar" in configured_window.btn_toggle.text()
        assert "f44336" in configured_window.status_icon.styleSheet()

    def test_inactive_state(self, configured_window: FreePingWindow) -> None:
        configured_window._tunnel_state = TunnelState.INACTIVE
        configured_window._update_ui_state()
        assert "○" in configured_window.status_icon.text()
        assert "Inactivo" in configured_window.status_label.text()
        assert "Activar Túnel" in configured_window.btn_toggle.text()
        assert "888" in configured_window.status_icon.styleSheet()

    def test_configured_vps_label(self, configured_window: FreePingWindow) -> None:
        configured_window._update_ui_state()
        assert "203.0.113.1" in configured_window.vps_label.text()

    def test_buttons_enabled_when_configured(self, configured_window: FreePingWindow) -> None:
        assert configured_window.btn_toggle.isEnabled()
        assert configured_window.btn_test.isEnabled()

    def test_buttons_disabled_when_not_configured(self, window: FreePingWindow) -> None:
        assert not window.btn_toggle.isEnabled()
        assert not window.btn_test.isEnabled()

    def test_active_updates_tray(self, configured_window: FreePingWindow) -> None:
        configured_window._tunnel_state = TunnelState.ACTIVE
        configured_window._update_ui_state()
        configured_window._mock_tray.update_state.assert_called_with(TunnelState.ACTIVE)

    def test_error_updates_tray(self, configured_window: FreePingWindow) -> None:
        configured_window._tunnel_state = TunnelState.ERROR
        configured_window._update_ui_state()
        configured_window._mock_tray.update_state.assert_called_with(TunnelState.ERROR)

    def test_inactive_updates_tray(self, configured_window: FreePingWindow) -> None:
        configured_window._tunnel_state = TunnelState.INACTIVE
        configured_window._update_ui_state()
        configured_window._mock_tray.update_state.assert_called_with(TunnelState.INACTIVE)
