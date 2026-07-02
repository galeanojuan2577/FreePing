from __future__ import annotations

import asyncio
import typing
from typing import Optional

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from freeping.core.config import AppConfig
from freeping.core.models import TunnelState
from freeping.gui.tray_icon import TrayIcon
from freeping.gui.wizard import SetupWizard


class FreePingWindow(QMainWindow):
    status_changed = Signal(TunnelState)

    def __init__(self) -> None:
        super().__init__()
        self.config = AppConfig.load()
        self._tunnel_state = TunnelState.INACTIVE
        self._tunnel_manager: Optional = None
        self._watchdog: Optional = None
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._ping_without: float | None = None
        self._ping_with: float | None = None

        self._setup_ui()
        self._setup_menu()
        self._setup_tray()
        self._connect_signals()
        self._update_ui_state()
        self._start_event_loop()

        self._first_show = True

    def _setup_ui(self) -> None:
        self.setWindowTitle("FreePing v0.1.0 — Gaming VPN")
        self.setMinimumSize(700, 620)
        self.resize(780, 660)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # --- Latency Dashboard Card ---
        dash_group = QGroupBox("Latency Dashboard")
        dash_group.setToolTip("Compare your ping with and without the FreePing tunnel")
        dash_layout = QGridLayout(dash_group)
        dash_layout.setSpacing(4)

        # Without tunnel
        dash_layout.addWidget(QLabel("Without tunnel:"), 0, 0)
        self.ping_without = QLabel("--- ms")
        self.ping_without.setStyleSheet("font-size: 14px; font-weight: bold; color: #999;")
        dash_layout.addWidget(self.ping_without, 0, 1)

        # With tunnel
        dash_layout.addWidget(QLabel("With tunnel:"), 1, 0)
        self.ping_with = QLabel("--- ms")
        self.ping_with.setStyleSheet("font-size: 14px; font-weight: bold; color: #999;")
        dash_layout.addWidget(self.ping_with, 1, 1)

        # Improvement
        dash_layout.addWidget(QLabel("Improvement:"), 2, 0)
        self.ping_improvement = QLabel("-- ms (--%)")
        self.ping_improvement.setStyleSheet("font-size: 14px; font-weight: bold; color: #666;")
        dash_layout.addWidget(self.ping_improvement, 2, 1)

        main_layout.addWidget(dash_group)

        # --- Tunnel Status Card ---
        status_group = QGroupBox("Tunnel Status")
        status_layout = QGridLayout(status_group)

        self.status_icon = QLabel("○")
        self.status_icon.setStyleSheet("font-size: 28px; color: #888;")
        self.status_icon.setToolTip("● Connected  ○ Inactive  ● Error")
        self.status_label = QLabel("Inactive")
        self.status_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        status_layout.addWidget(self.status_icon, 0, 0)
        status_layout.addWidget(self.status_label, 0, 1)

        self.vps_label = QLabel("VPS: Not configured")
        self.vps_label.setStyleSheet("font-size: 12px; color: #999;")
        self.vps_label.setToolTip("The public IP of your Oracle Cloud VPS")
        status_layout.addWidget(self.vps_label, 1, 0, 1, 2)

        self.transfer_label = QLabel("TX: 0 B  |  RX: 0 B")
        self.transfer_label.setStyleSheet("font-size: 12px; color: #999;")
        self.transfer_label.setToolTip("Data transferred through the tunnel")
        status_layout.addWidget(self.transfer_label, 2, 0, 1, 2)

        main_layout.addWidget(status_group)

        # --- Game Selection ---
        game_group = QGroupBox("Game / Target Selection")
        game_group.setToolTip("Select a game to route its traffic through the tunnel")
        game_layout = QVBoxLayout(game_group)

        self.game_combo = QComboBox()
        self.game_combo.setToolTip("Choose a pre-configured game to auto-detect its server IPs")
        self.game_combo.addItem("Select a game...")
        game_layout.addWidget(self.game_combo)

        self.custom_ip_input = QTextEdit()
        self.custom_ip_input.setPlaceholderText("Or enter custom IPs (one per line)...")
        self.custom_ip_input.setMaximumHeight(72)
        self.custom_ip_input.setToolTip("Manually enter game server IP addresses (one per line)")
        game_layout.addWidget(self.custom_ip_input)

        main_layout.addWidget(game_group)

        # --- Action Buttons ---
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_toggle = QPushButton("Activate Tunnel")
        self.btn_toggle.setMinimumHeight(48)
        self.btn_toggle.setToolTip("Start/stop the WireGuard tunnel to your VPS")
        self.btn_toggle.setStyleSheet(
            "QPushButton { font-size: 15px; font-weight: bold; border-radius: 8px; }"
            "QPushButton:enabled { background-color: #4CAF50; color: white; }"
            "QPushButton:disabled { background-color: #ccc; color: #888; }"
        )

        self.btn_test = QPushButton("Test Ping")
        self.btn_test.setMinimumHeight(48)
        self.btn_test.setToolTip("Compare your ping with and without the tunnel active")
        self.btn_test.setStyleSheet(
            "QPushButton { font-size: 14px; border-radius: 8px; }"
            "QPushButton:enabled { background-color: #2196F3; color: white; }"
            "QPushButton:disabled { background-color: #ccc; color: #888; }"
        )

        self.btn_settings = QPushButton("Settings")
        self.btn_settings.setMinimumHeight(48)
        self.btn_settings.setToolTip("Adjust FreePing preferences")

        btn_layout.addWidget(self.btn_toggle, 2)
        btn_layout.addWidget(self.btn_test, 1)
        btn_layout.addWidget(self.btn_settings, 1)

        main_layout.addLayout(btn_layout)

        # --- Log output ---
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(100)
        self.log_output.setStyleSheet(
            "font-family: 'Consolas', 'Courier New', monospace;"
            " font-size: 11px; background: #1e1e1e; color: #d4d4d4;"
        )
        self.log_output.setToolTip("Event log — shows what FreePing is doing")
        main_layout.addWidget(self.log_output)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setToolTip("Operation in progress...")
        main_layout.addWidget(self.progress)

        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self.status_text = QLabel("Ready")
        status_bar.addPermanentWidget(self.status_text)

    def _auto_run_wizard(self) -> None:
        import os
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            self.status_text.setText("Not configured — run Setup Wizard from File menu")
            self.log("FreePing is not configured. Go to File → Run Setup Wizard to get started.")
            return
        reply = QMessageBox.question(
            self, "Welcome to FreePing!",
            "FreePing is not configured yet.\n\n"
            "Would you like to run the setup wizard now?\n\n"
            "The wizard will guide you through:\n"
            "• Creating an Oracle Cloud account (free)\n"
            "• Generating API credentials\n"
            "• Deploying your free WireGuard VPS\n\n"
            "It takes about 5 minutes.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._run_wizard()

    def _setup_menu(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        self.action_setup = QAction("Run Setup Wizard...", self)
        self.action_setup.setToolTip("Provision a new Oracle Cloud VPS")
        file_menu.addAction(self.action_setup)
        file_menu.addSeparator()
        self.action_quit = QAction("Quit", self)
        self.action_quit.setShortcut("Ctrl+Q")
        file_menu.addAction(self.action_quit)

        tunnel_menu = menubar.addMenu("Tunnel")
        self.action_toggle = QAction("Activate", self)
        self.action_toggle.setShortcut("Ctrl+T")
        self.action_toggle.setToolTip("Toggle tunnel on/off")
        tunnel_menu.addAction(self.action_toggle)
        self.action_test = QAction("Test Ping", self)
        self.action_test.setShortcut("Ctrl+R")
        self.action_test.setToolTip("Run a ping comparison test")
        tunnel_menu.addAction(self.action_test)

        help_menu = menubar.addMenu("Help")
        self.action_about = QAction("About FreePing", self)
        help_menu.addAction(self.action_about)

    def _setup_tray(self) -> None:
        self.tray_icon = TrayIcon(self, on_toggle=self._toggle_tunnel)
        self.tray_icon.show()

    def _connect_signals(self) -> None:
        self.btn_toggle.clicked.connect(self._toggle_tunnel)
        self.action_toggle.triggered.connect(self._toggle_tunnel)
        self.btn_test.clicked.connect(self._run_test)
        self.action_test.triggered.connect(self._run_test)
        self.btn_settings.clicked.connect(self._open_settings)
        self.action_setup.triggered.connect(self._run_wizard)
        self.action_quit.triggered.connect(self.close)
        self.action_about.triggered.connect(self._show_about)
        self.game_combo.currentIndexChanged.connect(self._on_game_changed)

    def _start_event_loop(self) -> None:
        try:
            self._event_loop = asyncio.new_event_loop()
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._process_async_tasks)
            self._timer.start(50)
        except Exception:
            pass

    def _process_async_tasks(self) -> None:
        if self._event_loop and self._event_loop.is_running():
            self._event_loop.stop()
            try:
                self._event_loop.run_until_complete(asyncio.sleep(0))
            except RuntimeError:
                pass

    def _toggle_tunnel(self) -> None:
        if not self.config.is_configured():
            self.log("VPS not configured. Run Setup Wizard first.")
            reply = QMessageBox.question(
                self, "Not Configured",
                "FreePing is not configured yet. Run the setup wizard now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._run_wizard()
            return

        if self._tunnel_state == TunnelState.ACTIVE:
            self._deactivate_tunnel()
        else:
            self._activate_tunnel()

    async def _activate_tunnel_async(self) -> None:
        from freeping.core.tunnel import TunnelManager

        conf_path = AppConfig.CONFIG_DIR / "tunnel.conf"
        self._tunnel_manager = TunnelManager(self.config.tunnel)

        try:
            self.log("Activating tunnel...")
            self.status_text.setText("Activating...")
            await self._tunnel_manager.start(conf_path)
            self._tunnel_state = TunnelState.ACTIVE
            self.log("Tunnel activated successfully")
            self.status_text.setText("Connected")
            self._auto_run_test()
        except Exception as e:
            self._tunnel_state = TunnelState.ERROR
            self.log(f"Failed to activate tunnel: {e}")
            self.status_text.setText("Activation failed")
            QMessageBox.critical(self, "Error", f"Failed to activate tunnel:\n{e}")

        self._update_ui_state()

    def _auto_run_test(self) -> None:
        game_ips = self._get_selected_ips()
        if not game_ips:
            self.log("Auto-test: No game selected. Select a game and click 'Test Ping' to see improvement.")
            return

        self.log("Auto-testing ping improvement...")
        self._run_test()

    async def _deactivate_tunnel_async(self) -> None:
        from freeping.core.tunnel import TunnelManager

        self._tunnel_manager = TunnelManager(self.config.tunnel)

        try:
            self.log("Deactivating tunnel...")
            self.status_text.setText("Deactivating...")
            await self._tunnel_manager.stop()
            self._tunnel_state = TunnelState.INACTIVE
            self.log("Tunnel deactivated")
            self.status_text.setText("Disconnected")
        except Exception as e:
            self.log(f"Error deactivating tunnel: {e}")
            self.status_text.setText("Deactivation error")

        self._ping_without = None
        self._ping_with = None
        self._update_ping_display()
        self._update_ui_state()

    def _activate_tunnel(self) -> None:
        if self._event_loop:
            self._event_loop.run_until_complete(self._activate_tunnel_async())

    def _deactivate_tunnel(self) -> None:
        if self._event_loop:
            self._event_loop.run_until_complete(self._deactivate_tunnel_async())

    def _run_test(self) -> None:
        if not self.config.is_configured():
            self.log("Configure your VPS first before testing.")
            return

        game_ips = self._get_selected_ips()
        if not game_ips:
            self.log("Select a game or enter custom IPs first.")
            return

        self.log(f"Testing latency for {len(game_ips)} target(s)...")
        self.status_text.setText("Testing ping...")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)

        if self._event_loop:
            async def test():
                from freeping.core.ping import PingManager
                pm = PingManager()
                result = await pm.compare(
                    self.config.vps_ip, game_ips,
                    tunnel_active=self._tunnel_state == TunnelState.ACTIVE,
                )
                return result

            result = self._event_loop.run_until_complete(test())

            self.progress.setVisible(False)

            self._ping_without = result.without_tunnel_ms
            self._ping_with = result.with_tunnel_ms
            self._update_ping_display()

            if result.without_tunnel_ms is not None:
                self.log(f"Without tunnel: {result.without_tunnel_ms:.0f} ms")
            if result.with_tunnel_ms is not None:
                self.log(f"With tunnel: {result.with_tunnel_ms:.0f} ms")
            if result.improvement_ms is not None and result.improvement_ms > 0:
                self.log(f"Improvement: -{result.improvement_ms:.0f} ms ({result.improvement_pct:.0f}%)")

            self._show_test_result_dialog(result)
            self.status_text.setText("Ping test complete")

    def _show_test_result_dialog(self, result) -> None:
        without = f"{result.without_tunnel_ms:.0f}" if result.without_tunnel_ms is not None else "N/A"
        with_ = f"{result.with_tunnel_ms:.0f}" if result.with_tunnel_ms is not None else "N/A"
        improvement = result.improvement_ms

        lines = [
            "Ping Comparison Results",
            "─" * 35,
            f"  Without tunnel:  {without:>6} ms",
            f"  With tunnel:     {with_:>6} ms",
            "─" * 35,
        ]

        if improvement is not None and improvement > 0:
            lines.append(f"  Improvement:     -{improvement:.0f} ms ({result.improvement_pct:.0f}%)  ✓")
        elif improvement is not None:
            lines.append(f"  Difference:      {improvement:.0f} ms")
            lines.append("  No significant improvement detected.")
        else:
            lines.append("  Could not measure improvement.")

        self.log("\n".join(lines))

        if improvement is not None and improvement > 0:
            QMessageBox.information(
                self, "Ping Test Results",
                f"Without tunnel:  {without} ms\n"
                f"With tunnel:     {with_} ms\n\n"
                f"Improvement:     -{improvement:.0f} ms ({result.improvement_pct:.0f}%)\n\n"
                "Your gaming latency is reduced! 🎮",
            )
        elif improvement is not None:
            QMessageBox.information(
                self, "Ping Test Results",
                f"Without tunnel:  {without} ms\n"
                f"With tunnel:     {with_} ms\n\n"
                "No significant improvement detected.\n"
                "Try a different VPS region or check your configuration.",
            )

    def _update_ping_display(self) -> None:
        if self._ping_without is not None:
            self.ping_without.setText(f"{self._ping_without:.0f} ms")
            self.ping_without.setStyleSheet("font-size: 14px; font-weight: bold; color: #e74c3c;")
        else:
            self.ping_without.setText("--- ms")
            self.ping_without.setStyleSheet("font-size: 14px; font-weight: bold; color: #999;")

        if self._ping_with is not None:
            self.ping_with.setText(f"{self._ping_with:.0f} ms")
            self.ping_with.setStyleSheet("font-size: 14px; font-weight: bold; color: #4CAF50;")
        else:
            self.ping_with.setText("--- ms")
            self.ping_with.setStyleSheet("font-size: 14px; font-weight: bold; color: #999;")

        if self._ping_without is not None and self._ping_with is not None:
            diff = self._ping_without - self._ping_with
            if diff > 0:
                pct = (diff / self._ping_without) * 100
                self.ping_improvement.setText(f"-{diff:.0f} ms ({pct:.0f}%)")
                self.ping_improvement.setStyleSheet("font-size: 14px; font-weight: bold; color: #4CAF50;")
            elif diff < 0:
                self.ping_improvement.setText(f"+{-diff:.0f} ms (worse)")
                self.ping_improvement.setStyleSheet("font-size: 14px; font-weight: bold; color: #e74c3c;")
            else:
                self.ping_improvement.setText("0 ms (no change)")
                self.ping_improvement.setStyleSheet("font-size: 14px; font-weight: bold; color: #666;")
        else:
            self.ping_improvement.setText("-- ms (--%)")
            self.ping_improvement.setStyleSheet("font-size: 14px; font-weight: bold; color: #666;")

    def _get_selected_ips(self) -> list[str]:
        custom_text = self.custom_ip_input.toPlainText().strip()
        if custom_text:
            return [ip.strip() for ip in custom_text.split("\n") if ip.strip()]

        game_name = self.game_combo.currentText()
        if game_name and game_name != "Select a game...":
            from freeping.data.games_list import load_games
            games = load_games()
            game = games.find_game(game_name)
            if game:
                return game.ip_ranges

        return []

    def _on_game_changed(self, index: int) -> None:
        if index > 0:
            self.custom_ip_input.clear()

    def _run_wizard(self) -> None:
        wizard = SetupWizard(self)
        if wizard.exec() == SetupWizard.DialogCode.Accepted:
            self.config = AppConfig.load()
            self._update_ui_state()
            self.log("Setup completed successfully!")

            vps_ip = self.config.vps_ip or "unknown"
            self.vps_label.setText(f"VPS: {vps_ip}")
            self.vps_label.setStyleSheet("font-size: 12px; color: #4CAF50;")

            QMessageBox.information(
                self, "Setup Complete",
                "Your VPS has been provisioned!\n\n"
                "Next steps:\n"
                "1. Select a game from the dropdown\n"
                "2. Click 'Activate Tunnel'\n"
                "3. FreePing will test your improvement automatically",
            )

    def _open_settings(self) -> None:
        from freeping.gui.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            self.config = AppConfig.load()
            self._update_ui_state()
            self.log("Settings saved.")

    def _update_ui_state(self) -> None:
        is_active = self._tunnel_state == TunnelState.ACTIVE

        if is_active:
            self.status_icon.setText("●")
            self.status_icon.setStyleSheet("font-size: 28px; color: #4CAF50;")
            self.status_label.setText("Connected")
            self.status_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #4CAF50;")
            self.btn_toggle.setText("Deactivate Tunnel")
            self.btn_toggle.setStyleSheet(
                "QPushButton {"
                "  font-size: 15px; font-weight: bold; border-radius: 8px;"
                "  background-color: #f44336; color: white;"
                "}"
            )
        elif self._tunnel_state == TunnelState.ERROR:
            self.status_icon.setText("●")
            self.status_icon.setStyleSheet("font-size: 28px; color: #f44336;")
            self.status_label.setText("Error")
            self.status_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #f44336;")
            self.btn_toggle.setText("Retry")
        else:
            self.status_icon.setText("○")
            self.status_icon.setStyleSheet("font-size: 28px; color: #888;")
            self.status_label.setText("Inactive")
            self.status_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #888;")
            self.btn_toggle.setText("Activate Tunnel")

        is_configured = self.config.is_configured()
        self.btn_toggle.setEnabled(is_configured)
        self.btn_test.setEnabled(is_configured)

        if is_configured and self.config.vps_ip:
            self.vps_label.setText(f"VPS: {self.config.vps_ip}")
            color = "#4CAF50" if is_active else "#666"
            self.vps_label.setStyleSheet(f"font-size: 12px; color: {color};")

        self.tray_icon.update_state(self._tunnel_state)

    def log(self, message: str) -> None:
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_output.append(f"[{ts}] {message}")
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _show_about(self) -> None:
        QMessageBox.about(
            self, "About FreePing",
            "<h2>FreePing v0.1.0</h2>"
            "<p>Your personal, free, self-hosted gaming VPN.</p>"
            "<p>Uses WireGuard over Oracle Cloud free tier<br>"
            "to reduce gaming latency.</p>"
            "<hr>"
            "<p>Built with Python 3.12 + PySide6</p>"
            "<p>100% free forever.</p>"
            "<p>Created by Diego Galeano</p>"
        )

    @typing.override
    @typing.override
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._first_show and not self.config.is_configured():
            self._first_show = False
            from PySide6.QtCore import QTimer as SingleTimer
            SingleTimer.singleShot(500, self._auto_run_wizard)

    @typing.override
    def closeEvent(self, event) -> None:
        if self.config.minimize_to_tray and self.tray_icon.isVisible():
            self.hide()
            self.tray_icon.showMessage(
                "FreePing",
                "FreePing is still running in the system tray.",
            )
            event.ignore()
        else:
            self._timer.stop()
            if self._event_loop:
                self._event_loop.stop()
            event.accept()
