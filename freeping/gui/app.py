from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from freeping.gui.main_window import FreePingWindow


def launch_gui() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("FreePing")
    app.setOrganizationName("FreePing")
    app.setOrganizationDomain("freeping.local")

    font = QFont("Segoe UI", 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)

    stylesheet_path = Path(__file__).parent / "resources" / "styles.qss"
    if stylesheet_path.exists():
        with open(stylesheet_path) as f:
            app.setStyleSheet(f.read())

    window = FreePingWindow()
    window.show()

    exit_code = app.exec()
    sys.exit(exit_code)
