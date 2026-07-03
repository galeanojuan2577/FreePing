from __future__ import annotations

import os

import pytest
from pytestqt.qtbot import QtBot

from freeping.core.models import TunnelState

_has_system_tray = os.environ.get("QT_QPA_PLATFORM") != "offscreen"


@pytest.fixture
def window(qtbot: QtBot):
    from freeping.gui.main_window import FreePingWindow

    win = FreePingWindow()
    qtbot.addWidget(win)
    yield win
    win.close()


class TestMainWindowLogic:
    def test_initial_state_label(self, window) -> None:
        assert window._tunnel_state == TunnelState.INACTIVE
        assert "Inactivo" in window.status_label.text()

    def test_toggle_button_text_when_inactive(self, window) -> None:
        assert "Activar" in window.btn_toggle.text()

    def test_toggle_button_disabled_without_config(self, window) -> None:
        if not window.config.is_configured():
            assert not window.btn_toggle.isEnabled()

    def test_status_icon_initially_gray(self, window) -> None:
        assert "888" in window.status_icon.styleSheet() or "○" in window.status_icon.text()

    def test_log_method_appends_message(self, window) -> None:
        initial = window.log_output.toPlainText()
        window.log("Test message")
        assert window.log_output.toPlainText() != initial
        assert "Test message" in window.log_output.toPlainText()

    def test_title_contains_freeping(self, window) -> None:
        assert "FreePing" in window.windowTitle()


@pytest.mark.gui
class TestTrayIcon:
    def test_tray_icon_created(self, window) -> None:
        assert window.tray_icon is not None

    @pytest.mark.skipif(not _has_system_tray, reason="No system tray available")
    def test_tray_state_update_active(self, window) -> None:
        window.tray_icon.update_state(TunnelState.ACTIVE)
        assert "Conectado" in window.tray_icon.action_status.text()

    @pytest.mark.skipif(not _has_system_tray, reason="No system tray available")
    def test_tray_state_update_error(self, window) -> None:
        window.tray_icon.update_state(TunnelState.ERROR)
        assert "Error" in window.tray_icon.action_status.text()

    @pytest.mark.skipif(not _has_system_tray, reason="No system tray available")
    def test_tray_state_update_inactive(self, window) -> None:
        window.tray_icon.update_state(TunnelState.INACTIVE)
        assert "Inactivo" in window.tray_icon.action_status.text()
