from __future__ import annotations

import asyncio
import logging
import typing

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
from freeping.core.models import LatencyResult, TunnelState
from freeping.gui.tray_icon import TrayIcon
from freeping.gui.wizard import SetupWizard

if typing.TYPE_CHECKING:
    from freeping.core.tunnel import TunnelManager
    from freeping.core.watchdog import Watchdog

logger = logging.getLogger("freeping.gui")


class FreePingWindow(QMainWindow):
    status_changed = Signal(TunnelState)

    def __init__(self) -> None:
        super().__init__()
        self.config = AppConfig.load()
        self._tunnel_state = TunnelState.INACTIVE
        self._tunnel_manager: TunnelManager | None = None
        self._watchdog: Watchdog | None = None
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._ping_without: float | None = None
        self._ping_with: float | None = None
        self._async_busy = False
        self._current_task: asyncio.Task | None = None

        self._setup_ui()
        self._setup_menu()
        self._setup_tray()
        self._connect_signals()
        self._update_ui_state()
        self._start_event_loop()

        self._first_show = True

    def _setup_ui(self) -> None:
        self.setWindowTitle("FreePing — VPN para Gaming")
        self.setMinimumSize(700, 620)
        self.resize(780, 660)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # --- Estado del Túnel ---
        status_group = QGroupBox("Estado del Túnel")
        status_layout = QGridLayout(status_group)

        self.status_icon = QLabel("○")
        self.status_icon.setStyleSheet("font-size: 28px; color: #888;")
        self.status_icon.setToolTip("● Conectado  ○ Inactivo  ● Error")
        self.status_label = QLabel("Inactivo")
        self.status_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        status_layout.addWidget(self.status_icon, 0, 0)
        status_layout.addWidget(self.status_label, 0, 1)

        self.vps_label = QLabel("VPS: No configurado")
        self.vps_label.setStyleSheet("font-size: 12px; color: #999;")
        self.vps_label.setToolTip("La IP pública de tu VPS en Oracle Cloud")
        status_layout.addWidget(self.vps_label, 1, 0, 1, 2)

        self.transfer_label = QLabel("TX: 0 B  |  RX: 0 B")
        self.transfer_label.setStyleSheet("font-size: 12px; color: #999;")
        self.transfer_label.setToolTip("Datos transferidos a través del túnel")
        status_layout.addWidget(self.transfer_label, 2, 0, 1, 2)

        main_layout.addWidget(status_group)

        # --- Región ---
        region_group = QGroupBox("Región del Servidor")
        region_layout = QVBoxLayout(region_group)

        self.region_combo = QComboBox()
        self.region_combo.setToolTip("Selecciona la región para tu VPS. Cambiar región requiere reconfigurar.")
        self.region_combo.addItem("Seleccionar región...", "")
        from freeping.provisioning.oci_client import OCI_REGIONS
        for key, name in sorted(OCI_REGIONS.items()):
            self.region_combo.addItem(name, key)
        if self.config.vps_region in OCI_REGIONS:
            idx = self.region_combo.findData(self.config.vps_region)
            if idx >= 0:
                self.region_combo.setCurrentIndex(idx)
        region_layout.addWidget(self.region_combo)

        main_layout.addWidget(region_group)

        # --- Comparación de Latencia ---
        dash_group = QGroupBox("Comparación de Latencia")
        dash_group.setToolTip("Compara tu ping con y sin el túnel FreePing")
        dash_layout = QGridLayout(dash_group)
        dash_layout.setSpacing(4)

        dash_layout.addWidget(QLabel("Sin túnel:"), 0, 0)
        self.ping_without = QLabel("--- ms")
        self.ping_without.setStyleSheet("font-size: 14px; font-weight: bold; color: #999;")
        dash_layout.addWidget(self.ping_without, 0, 1)

        dash_layout.addWidget(QLabel("Con túnel:"), 1, 0)
        self.ping_with = QLabel("--- ms")
        self.ping_with.setStyleSheet("font-size: 14px; font-weight: bold; color: #999;")
        dash_layout.addWidget(self.ping_with, 1, 1)

        dash_layout.addWidget(QLabel("Mejora:"), 2, 0)
        self.ping_improvement = QLabel("-- ms (--%)")
        self.ping_improvement.setStyleSheet("font-size: 14px; font-weight: bold; color: #666;")
        dash_layout.addWidget(self.ping_improvement, 2, 1)

        main_layout.addWidget(dash_group)

        # --- Selección de Juego / IPs ---
        game_group = QGroupBox("Selección de Juego / IPs")
        game_group.setToolTip("Selecciona un juego para enrutar su tráfico por el túnel")
        game_layout = QVBoxLayout(game_group)

        self.game_combo = QComboBox()
        self.game_combo.setToolTip("Elige un juego preconfigurado para auto-detectar sus IPs de servidor")
        self.game_combo.addItem("Seleccionar un juego...")
        game_layout.addWidget(self.game_combo)

        self.custom_ip_input = QTextEdit()
        self.custom_ip_input.setPlaceholderText("O ingresa IPs personalizadas (una por línea)...")
        self.custom_ip_input.setMaximumHeight(72)
        self.custom_ip_input.setToolTip("Ingresa manualmente las IPs de los servidores de juego (una por línea)")
        game_layout.addWidget(self.custom_ip_input)

        main_layout.addWidget(game_group)

        # --- Botones de Acción ---
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_toggle = QPushButton("Activar Túnel")
        self.btn_toggle.setMinimumHeight(48)
        self.btn_toggle.setToolTip("Iniciar/detener el túnel WireGuard hacia tu VPS")
        self.btn_toggle.setStyleSheet(
            "QPushButton { font-size: 15px; font-weight: bold; border-radius: 8px; }"
            "QPushButton:enabled { background-color: #4CAF50; color: white; }"
            "QPushButton:disabled { background-color: #ccc; color: #888; }"
        )

        self.btn_test = QPushButton("Probar Ping")
        self.btn_test.setMinimumHeight(48)
        self.btn_test.setToolTip("Compara tu ping con y sin el túnel activo")
        self.btn_test.setStyleSheet(
            "QPushButton { font-size: 14px; border-radius: 8px; }"
            "QPushButton:enabled { background-color: #2196F3; color: white; }"
            "QPushButton:disabled { background-color: #ccc; color: #888; }"
        )

        self.btn_settings = QPushButton("Configuración")
        self.btn_settings.setMinimumHeight(48)
        self.btn_settings.setToolTip("Ajustar preferencias de FreePing")

        btn_layout.addWidget(self.btn_toggle, 2)
        btn_layout.addWidget(self.btn_test, 1)
        btn_layout.addWidget(self.btn_settings, 1)

        main_layout.addLayout(btn_layout)

        # --- Registro de eventos ---
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(100)
        self.log_output.setStyleSheet(
            "font-family: 'Consolas', 'Courier New', monospace;"
            " font-size: 11px; background: #1e1e1e; color: #d4d4d4;"
        )
        self.log_output.setToolTip("Registro de eventos — muestra lo que FreePing está haciendo")
        main_layout.addWidget(self.log_output)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setToolTip("Operación en progreso...")
        main_layout.addWidget(self.progress)

        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self.status_text = QLabel("Listo")
        status_bar.addPermanentWidget(self.status_text)

    def _auto_run_wizard(self) -> None:
        import os
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            self.status_text.setText("No configurado — ejecuta el Asistente desde Archivo")
            self.log("FreePing no está configurado. Ve a Archivo → Ejecutar Asistente para comenzar.")
            return
        reply = QMessageBox.question(
            self, "¡Bienvenido a FreePing!",
            "FreePing no está configurado aún.\n\n"
            "¿Quieres ejecutar el asistente de configuración ahora?\n\n"
            "El asistente te guiará a través de:\n"
            "• Crear una cuenta de Oracle Cloud (gratis)\n"
            "• Generar credenciales API\n"
            "• Desplegar tu VPS WireGuard gratuito\n\n"
            "Tarda unos 5 minutos.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._run_wizard()

    def _setup_menu(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("Archivo")
        self.action_setup = QAction("Ejecutar Asistente de Configuración...", self)
        self.action_setup.setToolTip("Aprovisionar un nuevo VPS en Oracle Cloud")
        file_menu.addAction(self.action_setup)
        file_menu.addSeparator()
        self.action_quit = QAction("Salir", self)
        self.action_quit.setShortcut("Ctrl+Q")
        file_menu.addAction(self.action_quit)

        tunnel_menu = menubar.addMenu("Túnel")
        self.action_toggle = QAction("Activar", self)
        self.action_toggle.setShortcut("Ctrl+T")
        self.action_toggle.setToolTip("Activar/desactivar el túnel")
        tunnel_menu.addAction(self.action_toggle)
        self.action_test = QAction("Probar Ping", self)
        self.action_test.setShortcut("Ctrl+R")
        self.action_test.setToolTip("Ejecutar una prueba de ping comparativa")
        tunnel_menu.addAction(self.action_test)

        help_menu = menubar.addMenu("Ayuda")
        self.action_about = QAction("Acerca de FreePing", self)
        help_menu.addAction(self.action_about)

    def _setup_tray(self) -> None:
        self.tray_icon = TrayIcon(
            self,
            on_toggle=self._toggle_tunnel,
            on_quit=self._force_quit_app,
        )
        self.tray_icon.show()

    def _force_quit_app(self) -> None:
        self._cleanup()
        self.close()

    def _connect_signals(self) -> None:
        self.btn_toggle.clicked.connect(self._toggle_tunnel)
        self.action_toggle.triggered.connect(self._toggle_tunnel)
        self.btn_test.clicked.connect(self._run_test)
        self.action_test.triggered.connect(self._run_test)
        self.btn_settings.clicked.connect(self._open_settings)
        self.action_setup.triggered.connect(self._run_wizard)
        self.action_quit.triggered.connect(self._force_quit_app)
        self.action_about.triggered.connect(self._show_about)
        self.game_combo.currentIndexChanged.connect(self._on_game_changed)

    def _start_event_loop(self) -> None:
        try:
            self._event_loop = asyncio.new_event_loop()
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._process_async_tasks)
            self._timer.start(50)
        except Exception as e:
            logger.warning("Error al iniciar el event loop: %s", e)

    def _process_async_tasks(self) -> None:
        if self._event_loop is None or self._event_loop.is_closed():
            return
        if self._async_busy:
            return
        if not self._event_loop.is_running():
            self._async_busy = True
            try:
                self._event_loop.run_until_complete(asyncio.sleep(0))
            except RuntimeError:
                pass
            finally:
                self._async_busy = False

    def _toggle_tunnel(self) -> None:
        if not self.config.is_configured():
            self.log("VPS no configurado. Ejecuta el Asistente de Configuración primero.")
            reply = QMessageBox.question(
                self, "No Configurado",
                "FreePing no está configurado aún. ¿Ejecutar el asistente ahora?",
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

        conf_path = AppConfig.config_dir() / "tunnel.conf"
        self._tunnel_manager = TunnelManager(self.config.tunnel)

        try:
            self.log("Activando túnel...")
            self.status_text.setText("Activando...")
            await self._tunnel_manager.start(conf_path)
            self._tunnel_state = TunnelState.ACTIVE
            self.log("Túnel activado exitosamente")
            self.status_text.setText("Conectado")
            self._start_watchdog()
            self._auto_run_test()
        except Exception as e:
            self._tunnel_state = TunnelState.ERROR
            self.log(f"Error al activar túnel: {e}")
            self.status_text.setText("Error de activación")
            QMessageBox.critical(self, "Error", f"Error al activar el túnel:\n{e}")

        self._update_ui_state()

    def _start_watchdog(self) -> None:
        if not self.config.auto_reconnect:
            return
        if not self.config.vps_ip:
            return
        from freeping.core.watchdog import Watchdog
        self._watchdog = Watchdog(
            vps_ip=self.config.vps_ip,
            on_state_change=self._on_watchdog_state_change,
            on_reconnect=self._on_watchdog_reconnect,
        )
        self._watchdog.start()
        logger.info("Watchdog iniciado para %s", self.config.vps_ip)

    def _on_watchdog_state_change(self, state: TunnelState) -> None:
        self._tunnel_state = state
        self._update_ui_state()

    def _on_watchdog_reconnect(self) -> None:
        logger.info("Watchdog: reconectando...")
        self._deactivate_tunnel()
        self._activate_tunnel()

    def _auto_run_test(self) -> None:
        game_ips = self._get_selected_ips()
        if not game_ips:
            self.log(
                "Auto-test: Ningún juego seleccionado. "
                "Selecciona un juego y haz clic en 'Probar Ping' para ver la mejora."
            )
            return

        self.log("Probando mejora de ping automáticamente...")
        self._run_test()

    async def _deactivate_tunnel_async(self) -> None:
        if self._watchdog:
            logger.info("Deteniendo watchdog...")
            await self._watchdog.stop()
            self._watchdog = None

        if self._tunnel_manager is None:
            from freeping.core.tunnel import TunnelManager
            self._tunnel_manager = TunnelManager(self.config.tunnel)

        try:
            self.log("Desactivando túnel...")
            self.status_text.setText("Desactivando...")
            await self._tunnel_manager.stop()
            self._tunnel_state = TunnelState.INACTIVE
            self.log("Túnel desactivado")
            self.status_text.setText("Desconectado")
        except Exception as e:
            self.log(f"Error al desactivar túnel: {e}")
            self.status_text.setText("Error de desactivación")

        self._tunnel_manager = None
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
            self.log("Configura tu VPS primero antes de probar.")
            return

        game_ips = self._get_selected_ips()
        if not game_ips:
            self.log("Selecciona un juego o ingresa IPs personalizadas primero.")
            return

        self.log(f"Probando latencia para {len(game_ips)} destino(s)...")
        self.status_text.setText("Probando ping...")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)

        if not self._event_loop or self._event_loop.is_closed():
            self.progress.setVisible(False)
            self.log("Error: event loop no disponible")
            return

        from freeping.core.ping import PingManager

        async def _ping_test() -> LatencyResult:
            pm = PingManager()
            result = await pm.compare(
                self.config.vps_ip, game_ips,
                tunnel_active=self._tunnel_state == TunnelState.ACTIVE,
            )
            return result

        task = self._event_loop.create_task(_ping_test())
        if not self._event_loop.is_running():
            self._event_loop.run_until_complete(asyncio.sleep(0))

        if task.done():
            self._on_ping_test_result(task.result())
        else:
            self._current_task = task

    def _process_async_tasks(self) -> None:
        if self._event_loop is None or self._event_loop.is_closed():
            return
        if self._async_busy:
            return
        if not self._event_loop.is_running():
            self._async_busy = True
            try:
                self._event_loop.run_until_complete(asyncio.sleep(0))
            except RuntimeError:
                pass
            finally:
                self._async_busy = False

        if self._current_task is not None and self._current_task.done():
            try:
                result = self._current_task.result()
                self._on_ping_test_result(result)
            except Exception as e:
                self.progress.setVisible(False)
                self.log(f"Error en prueba de ping: {e}")
                self.status_text.setText("Error en prueba de ping")
            finally:
                self._current_task = None

    def _on_ping_test_result(self, result: LatencyResult) -> None:
        self.progress.setVisible(False)
        self._ping_without = result.without_tunnel_ms
        self._ping_with = result.with_tunnel_ms
        self._update_ping_display()
        if result.without_tunnel_ms is not None:
            self.log(f"Sin túnel: {result.without_tunnel_ms:.0f} ms")
        if result.with_tunnel_ms is not None:
            self.log(f"Con túnel: {result.with_tunnel_ms:.0f} ms")
        if result.improvement_ms is not None and result.improvement_ms > 0:
            self.log(f"Mejora: -{result.improvement_ms:.0f} ms ({result.improvement_pct:.0f}%)")
        self._show_test_result_dialog(result)
        self.status_text.setText("Prueba de ping completada")

    def _show_test_result_dialog(self, result) -> None:
        without = f"{result.without_tunnel_ms:.0f}" if result.without_tunnel_ms is not None else "N/A"
        with_ = f"{result.with_tunnel_ms:.0f}" if result.with_tunnel_ms is not None else "N/A"
        improvement = result.improvement_ms

        lines = [
            "Resultados de la Prueba de Ping",
            "─" * 35,
            f"  Sin túnel:       {without:>6} ms",
            f"  Con túnel:       {with_:>6} ms",
            "─" * 35,
        ]

        if improvement is not None and improvement > 0:
            lines.append(f"  Mejora:          -{improvement:.0f} ms ({result.improvement_pct:.0f}%)  ✓")
        elif improvement is not None:
            lines.append(f"  Diferencia:      {improvement:.0f} ms")
            lines.append("  No se detectó una mejora significativa.")
        else:
            lines.append("  No se pudo medir la mejora.")

        self.log("\n".join(lines))

        if improvement is not None and improvement > 0:
            QMessageBox.information(
                self, "Resultados de Ping",
                f"Sin túnel:  {without} ms\n"
                f"Con túnel:  {with_} ms\n\n"
                f"Mejora:     -{improvement:.0f} ms ({result.improvement_pct:.0f}%)\n\n"
                "¡Tu latencia de juego se ha reducido! 🎮",
            )
        elif improvement is not None:
            QMessageBox.information(
                self, "Resultados de Ping",
                f"Sin túnel:  {without} ms\n"
                f"Con túnel:  {with_} ms\n\n"
                "No se detectó una mejora significativa.\n"
                "Prueba con una región diferente o revisa tu configuración.",
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
                self.ping_improvement.setText(f"+{-diff:.0f} ms (peor)")
                self.ping_improvement.setStyleSheet("font-size: 14px; font-weight: bold; color: #e74c3c;")
            else:
                self.ping_improvement.setText("0 ms (sin cambio)")
                self.ping_improvement.setStyleSheet("font-size: 14px; font-weight: bold; color: #666;")
        else:
            self.ping_improvement.setText("-- ms (--%)")
            self.ping_improvement.setStyleSheet("font-size: 14px; font-weight: bold; color: #666;")

    def _get_selected_ips(self) -> list[str]:
        custom_text = self.custom_ip_input.toPlainText().strip()
        if custom_text:
            return [ip.strip() for ip in custom_text.split("\n") if ip.strip()]

        game_name = self.game_combo.currentText()
        if game_name and game_name != "Seleccionar un juego...":
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
            self.log("¡Configuración completada exitosamente!")

            vps_ip = self.config.vps_ip or "desconocida"
            self.vps_label.setText(f"VPS: {vps_ip}")
            self.vps_label.setStyleSheet("font-size: 12px; color: #4CAF50;")

            # Actualizar región
            if self.config.vps_region:
                idx = self.region_combo.findData(self.config.vps_region)
                if idx >= 0:
                    self.region_combo.setCurrentIndex(idx)

            QMessageBox.information(
                self, "Configuración Completada",
                "¡Tu VPS ha sido aprovisionado!\n\n"
                "Próximos pasos:\n"
                "1. Selecciona un juego del menú desplegable\n"
                "2. Haz clic en 'Activar Túnel'\n"
                "3. FreePing probará tu mejora automáticamente",
            )

    def _open_settings(self) -> None:
        from freeping.gui.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            self.config = AppConfig.load()
            self._update_ui_state()
            self.log("Configuración guardada.")

    def _update_ui_state(self) -> None:
        is_active = self._tunnel_state == TunnelState.ACTIVE

        if is_active:
            self.status_icon.setText("●")
            self.status_icon.setStyleSheet("font-size: 28px; color: #4CAF50;")
            self.status_label.setText("Conectado")
            self.status_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #4CAF50;")
            self.btn_toggle.setText("Desactivar Túnel")
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
            self.btn_toggle.setText("Reintentar")
        else:
            self.status_icon.setText("○")
            self.status_icon.setStyleSheet("font-size: 28px; color: #888;")
            self.status_label.setText("Inactivo")
            self.status_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #888;")
            self.btn_toggle.setText("Activar Túnel")

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
            self, "Acerca de FreePing",
            "<h2>FreePing v0.1.0</h2>"
            "<p>Tu VPN personal, gratuita y auto-gestionada para gaming.</p>"
            "<p>Usa WireGuard sobre Oracle Cloud free tier<br>"
            "para reducir tu latencia de juego.</p>"
            "<hr>"
            "<p>Creado con Python 3.12 + PySide6</p>"
            "<p>100% gratis para siempre.</p>"
        )

    @typing.override
    def showEvent(self, event: object) -> None:
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
                "FreePing sigue ejecutándose en la bandeja del sistema.",
            )
            event.ignore()
        else:
            self._cleanup()
            event.accept()

    def _cleanup(self) -> None:
        if self._watchdog:
            async def stop_watchdog():
                await self._watchdog.stop()
            try:
                asyncio.ensure_future(stop_watchdog())
            except Exception:
                pass
            self._watchdog = None
        self._timer.stop()
        if self._event_loop:
            self._event_loop.stop()
