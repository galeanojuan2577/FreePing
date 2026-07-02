from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from freeping.core.models import TunnelState


class TrayIcon(QSystemTrayIcon):
    def __init__(
        self,
        parent: object,
        on_toggle: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_toggle = on_toggle
        self._state = TunnelState.INACTIVE

        self.setIcon(self._make_icon("#888888"))
        self.setToolTip("FreePing - Inactive")

        self._setup_menu()

    def _setup_menu(self) -> None:
        menu = QMenu()

        self.action_status = QAction("Inactive")
        self.action_status.setEnabled(False)
        menu.addAction(self.action_status)

        menu.addSeparator()

        self.action_toggle = QAction("Activate")
        self.action_toggle.triggered.connect(self._handle_toggle)
        menu.addAction(self.action_toggle)

        menu.addSeparator()

        self.action_show = QAction("Show Window")
        self.action_show.triggered.connect(self._show_window)
        menu.addAction(self.action_show)

        menu.addSeparator()

        self.action_quit = QAction("Quit")
        self.action_quit.triggered.connect(self._quit)
        menu.addAction(self.action_quit)

        self.setContextMenu(menu)

    def update_state(self, state: TunnelState) -> None:
        self._state = state

        if state == TunnelState.ACTIVE:
            self.setIcon(self._make_icon("#4CAF50"))
            self.setToolTip("FreePing - Connected")
            self.action_status.setText("Connected")
            self.action_toggle.setText("Deactivate")
        elif state == TunnelState.ERROR:
            self.setIcon(self._make_icon("#f44336"))
            self.setToolTip("FreePing - Error")
            self.action_status.setText("Error")
            self.action_toggle.setText("Retry")
        elif state == TunnelState.CONNECTING:
            self.setIcon(self._make_icon("#FFC107"))
            self.setToolTip("FreePing - Connecting...")
            self.action_status.setText("Connecting...")
            self.action_toggle.setText("Cancel")
        else:
            self.setIcon(self._make_icon("#888888"))
            self.setToolTip("FreePing - Inactive")
            self.action_status.setText("Inactive")
            self.action_toggle.setText("Activate")

    def _handle_toggle(self) -> None:
        if self._on_toggle:
            self._on_toggle()

    def _show_window(self) -> None:
        parent = self.parent()
        if parent and hasattr(parent, "show"):
            parent.show()
            parent.raise_()
            parent.activateWindow()

    def _quit(self) -> None:
        parent = self.parent()
        if parent and hasattr(parent, "close"):
            parent.close()

    def _make_icon(self, color_hex: str) -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor(0, 0, 0, 0))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setBrush(QColor(color_hex))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(8, 8, 48, 48)

        painter.setPen(QColor(255, 255, 255))
        font = QFont("Arial", 28, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "F")

        painter.end()
        return QIcon(pixmap)
