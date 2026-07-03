from __future__ import annotations

import asyncio
import typing
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from freeping.core.config import AppConfig
from freeping.core.models import OciCredentials
from freeping.provisioning.key_manager import KeyManager

ORACLE_SIGNUP_URL = "https://signup.cloud.oracle.com/"
ORACLE_CONSOLE_URL = "https://cloud.oracle.com/"
ORACLE_API_KEY_GUIDE = "https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm"


class ProvisioningWorker(QThread):
    progress = Signal(str, int)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, credentials: OciCredentials, region: str) -> None:
        super().__init__()
        self.credentials = credentials
        self.region = region
        self._created_instance_id: str | None = None

    def run(self) -> None:
        loop = None
        client = None
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            self.progress.emit("Generando llaves WireGuard...", 10)
            from freeping.provisioning.oci_client import OciClient, WireGuardKeyPair
            server_keys = WireGuardKeyPair.generate()
            client_keys = WireGuardKeyPair.generate()

            self.progress.emit("Conectando con Oracle Cloud...", 20)
            client = OciClient(self.credentials)

            self.progress.emit("Creando VCN y red...", 30)

            self.progress.emit("Creando instancia Ampere A1...", 50)
            from freeping.provisioning.cloud_init import CloudInitGenerator
            cloud_gen = CloudInitGenerator(
                server_private_key=server_keys.private_key,
                server_public_key=server_keys.public_key,
                client_public_key=client_keys.public_key,
            )
            cloud_init_yaml = cloud_gen.render()

            instance = loop.run_until_complete(
                client.create_instance(
                    ssh_public_key="",
                    cloud_init_yaml=cloud_init_yaml,
                    compartment_id=self.credentials.tenancy_ocid,
                )
            )
            self._created_instance_id = instance.id

            self.progress.emit("Esperando que la instancia esté lista...", 70)
            import time
            time.sleep(10)

            instance = loop.run_until_complete(
                client.get_instance(instance.id)
            )

            self.progress.emit("Guardando configuración...", 90)
            result = {
                "instance_id": instance.id,
                "public_ip": instance.public_ip,
                "region": self.region,
                "server_private_key": server_keys.private_key,
                "server_public_key": server_keys.public_key,
                "client_private_key": client_keys.private_key,
                "client_public_key": client_keys.public_key,
            }

            self.progress.emit("¡Completado!", 100)
            self.finished.emit(result)
        except Exception as e:
            self._cleanup_orphan_resources(client, loop)
            self.error.emit(str(e))
        finally:
            if loop:
                loop.close()

    def _cleanup_orphan_resources(self, client: object | None, loop: asyncio.AbstractEventLoop | None) -> None:
        if not self._created_instance_id or not client or not loop:
            return
        try:
            loop.run_until_complete(client.terminate_instance(self._created_instance_id))
        except Exception:
            pass


class SetupWizard(QWizard):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Asistente de Configuración FreePing")
        self.setMinimumSize(680, 580)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)

        self._provisioning_result: dict | None = None

        self.addPage(WelcomePage(self))
        self.addPage(RegionPage(self))
        self.addPage(CredentialsPage(self))
        self.addPage(ReviewPage(self))
        self.addPage(ProgressPage(self))
        self.addPage(CompletePage(self))

    def get_credentials(self) -> OciCredentials:
        return self.page(2).get_credentials()

    def get_region(self) -> str:
        return self.page(1).get_region()


class WelcomePage(QWizardPage):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("Bienvenido a FreePing")
        self.setSubTitle("Tu VPN personal, gratuita y auto-gestionada para gaming")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel(
            "FreePing crea un servidor WireGuard gratuito en Oracle Cloud Always Free Tier "
            "para reducir tu latencia de juego. No requiere tarjeta de crédito."
        ))

        steps_box = QLabel(
            "<hr>"
            "<b>Qué haremos en 5 minutos:</b><br><br>"
            "1. <b>Crea</b> una cuenta en Oracle Cloud (si no tienes una)<br>"
            "2. <b>Genera</b> una llave API para que FreePing administre tus recursos<br>"
            "3. <b>Despliega</b> una VM gratuita (4 núcleos ARM, 24 GB RAM) con WireGuard preinstalado<br>"
            "4. <b>Conecta</b> tu tráfico de juego a través del túnel cifrado<br><br>"
            f'<a href="{ORACLE_SIGNUP_URL}" style="color: #4CAF50;">'
            "Haz clic aquí para crear tu cuenta gratuita de Oracle Cloud</a>"
            "<hr>"
        )
        steps_box.setOpenExternalLinks(True)
        steps_box.setWordWrap(True)
        layout.addWidget(steps_box)

        prereqs = QLabel(
            "<b>Requisitos:</b><br>"
            "• Cuenta de Oracle Cloud (gratis en cloud.oracle.com)<br>"
            "• Python 3.12 o superior<br>"
            "• Conexión a internet<br><br>"
            "<b>Qué obtienes:</b><br>"
            "• VM.Standard.A1.Flex (4 OCPU, 24 GB RAM) — <b>gratis para siempre</b><br>"
            "• WireGuard VPN con split tunneling (solo tráfico de juego)<br>"
            "• Reconexión automática si la conexión se pierde<br>"
            "• Integración con la bandeja del sistema"
        )
        prereqs.setWordWrap(True)
        prereqs.setStyleSheet("padding: 8px; background: #f0f7f0; border-radius: 4px;")
        layout.addWidget(prereqs)

        layout.addStretch()


class RegionPage(QWizardPage):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("Seleccionar Región")
        self.setSubTitle("Elige la región de Oracle Cloud más cercana a ti.")

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Elige la región geográficamente más cercana a tu ubicación física "
            "para obtener la latencia más baja posible."
        ))

        self.region_combo = QComboBox()
        from freeping.provisioning.oci_client import OCI_REGIONS
        for key, name in sorted(OCI_REGIONS.items()):
            self.region_combo.addItem(f"{name} ({key})", key)
        self.region_combo.setCurrentIndex(
            list(OCI_REGIONS.keys()).index("sa-saopaulo-1")
            if "sa-saopaulo-1" in OCI_REGIONS else 0
        )

        self.region_combo.setToolTip(
            "Elige la región más cercana a ti. "
            "Cada región tiene elegibilidad gratuita. "
            "São Paulo (sa-saopaulo-1) está preseleccionada para Sudamérica."
        )
        layout.addWidget(self.region_combo)

        layout.addStretch()

    def get_region(self) -> str:
        return self.region_combo.currentData()


class CredentialsPage(QWizardPage):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("Credenciales de API de Oracle Cloud")
        self.setSubTitle("Dale permiso a FreePing para crear recursos en tu cuenta.")

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        api_guide = QLabel(
            '<b>Guía paso a paso para obtener tus credenciales API:</b><br><br>'
            f'1. Inicia sesión en <a href="{ORACLE_CONSOLE_URL}" style="color: #4CAF50;">cloud.oracle.com</a><br>'
            '2. Haz clic en tu icono de perfil (arriba a la derecha) → <b>Mi Perfil</b><br>'
            '3. Ve a <b>Llaves API</b> en la barra lateral izquierda<br>'
            '4. Haz clic en <b>"Agregar Llave API"</b> → selecciona <b>"Generar Par de Llaves"</b><br>'
            '5. Descarga el archivo <b>llave privada (.pem)</b><br>'
            '6. Haz clic en <b>"Agregar"</b> — aparecerá una vista previa<br>'
            '7. Copia los valores de esa vista previa en los campos de abajo<br><br>'
            f'<a href="{ORACLE_API_KEY_GUIDE}" style="color: #666;">'
            ' Documentación completa de Llaves API (se abre en el navegador)</a>'
        )
        api_guide.setOpenExternalLinks(True)
        api_guide.setWordWrap(True)
        api_guide.setStyleSheet("padding: 8px; background: #f5f5ff; border-radius: 4px;")
        layout.addWidget(api_guide)

        btn_layout = QHBoxLayout()
        self.btn_upload = QPushButton("Subir Archivo PEM...")
        self.btn_upload.setToolTip("Cargar un archivo de llave API (.pem) descargado de Oracle Cloud")
        btn_layout.addWidget(self.btn_upload)
        self.btn_generate = QPushButton("Generar Nueva Llave")
        self.btn_generate.setToolTip(
            "Crear un nuevo par de llaves API ahora (sube la parte pública a Oracle Cloud)"
        )
        btn_layout.addWidget(self.btn_generate)
        layout.addLayout(btn_layout)

        self.key_display = QTextEdit()
        self.key_display.setPlaceholderText("El contenido de la llave API aparecerá aquí...")
        self.key_display.setMaximumHeight(100)
        self.key_display.setToolTip(
            "El contenido de la llave privada (-----BEGIN PRIVATE KEY----- ... -----END PRIVATE KEY-----)"
        )
        layout.addWidget(self.key_display)

        form = QFormLayout()

        self.user_ocid = QLineEdit()
        self.user_ocid.setPlaceholderText("ocid1.user.oc1..xxxxxxxxxxxx")
        self.user_ocid.setToolTip("Tu OCID de usuario. En: Perfil → Mi Perfil → OCID (clic en 'Copiar')")
        self.user_ocid.textChanged.connect(self._validate)
        form.addRow(self._field_label("OCID de Usuario:"), self.user_ocid)

        self.tenancy_ocid = QLineEdit()
        self.tenancy_ocid.setPlaceholderText("ocid1.tenancy.oc1..xxxxxxxxxxxx")
        self.tenancy_ocid.setToolTip("El OCID de tu tenencia. En: Perfil → Tenencia → OCID")
        self.tenancy_ocid.textChanged.connect(self._validate)
        form.addRow(self._field_label("OCID de Tenencia:"), self.tenancy_ocid)

        self.fingerprint = QLineEdit()
        self.fingerprint.setPlaceholderText("12:34:56:78:90:ab:cd:ef:01:23:45:67:89:0a:bc:de:f0:12:34:56")
        self.fingerprint.setToolTip(
            "La huella digital de tu llave API. En: Perfil → Llaves API"
        )
        self.fingerprint.textChanged.connect(self._validate)
        form.addRow(self._field_label("Huella Digital:"), self.fingerprint)

        layout.addLayout(form)

        self.validation_label = QLabel()
        self.validation_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.validation_label)

        layout.addStretch()

        self.btn_upload.clicked.connect(self._upload_key)
        self.btn_generate.clicked.connect(self._generate_key)

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-weight: bold;")
        return label

    def _validate(self) -> None:
        ocid_ok = self.user_ocid.text().strip().startswith("ocid1.user.")
        tenancy_ok = self.tenancy_ocid.text().strip().startswith("ocid1.tenancy.")
        key_ok = "BEGIN" in self.key_display.toPlainText().strip()

        if self.user_ocid.text().strip() and not ocid_ok:
            self.validation_label.setText("El OCID de usuario debe comenzar con 'ocid1.user.'")
            self.validation_label.setStyleSheet("color: #e74c3c;")
        elif self.tenancy_ocid.text().strip() and not tenancy_ok:
            self.validation_label.setText("El OCID de tenencia debe comenzar con 'ocid1.tenancy.'")
            self.validation_label.setStyleSheet("color: #e74c3c;")
        elif not key_ok and self.key_display.toPlainText().strip():
            self.validation_label.setText("La llave privada debe comenzar con '-----BEGIN PRIVATE KEY-----'")
            self.validation_label.setStyleSheet("color: #e74c3c;")
        else:
            text = "¡Todos los campos se ven bien!" if self.isComplete() else "Completa todos los campos para continuar."
            self.validation_label.setText(text)
            color = "#4CAF50" if self.isComplete() else "#666"
            self.validation_label.setStyleSheet(f"color: {color}; font-style: italic;")

        self.completeChanged.emit()

    def _upload_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar Llave API", "", "Archivos PEM (*.pem);;Todos los archivos (*)"
        )
        if path:
            content = Path(path).read_text()
            if "ocid" in content:
                from freeping.provisioning.key_manager import KeyManager
                key_content, creds = KeyManager.parse_oci_key_from_file(Path(path))
                self.key_display.setPlainText(key_content)
                self.user_ocid.setText(creds.user_ocid)
                self.tenancy_ocid.setText(creds.tenancy_ocid)
                self.fingerprint.setText(creds.fingerprint)
            else:
                self.key_display.setPlainText(content)
                if not self.fingerprint.text():
                    QMessageBox.information(
                        self, "Entrada Manual",
                        "Llave cargada. Ingresa tu OCID y huella digital manualmente desde la consola de Oracle Cloud.",
                    )

    def _generate_key(self) -> None:
        from freeping.provisioning.key_manager import KeyManager
        try:
            priv, pub = KeyManager.generate_oci_api_key()
            self.key_display.setPlainText(priv)
            QMessageBox.information(
                self, "Llave Generada",
                "Nueva llave API generada.\n\n"
                "Próximos pasos:\n"
                "1. Ve a cloud.oracle.com → Perfil → Llaves API\n"
                "2. Haz clic en 'Agregar Llave API'\n"
                "3. Elige 'Pegar Llave Pública' y pega esto:\n\n"
                f"{pub}\n\n"
                "4. Haz clic en 'Agregar' y copia el OCID de Usuario y la Huella Digital de la vista previa.",
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al generar la llave: {e}")

    def get_credentials(self) -> OciCredentials:
        return OciCredentials(
            user_ocid=self.user_ocid.text().strip(),
            tenancy_ocid=self.tenancy_ocid.text().strip(),
            fingerprint=self.fingerprint.text().strip(),
            private_key=self.key_display.toPlainText().strip(),
            region="",
        )

    @typing.override
    def isComplete(self) -> bool:
        ocid_ok = self.user_ocid.text().strip().startswith("ocid1.user.")
        tenancy_ok = self.tenancy_ocid.text().strip().startswith("ocid1.tenancy.")
        fp_ok = len(self.fingerprint.text().strip()) >= 20
        key_ok = "BEGIN" in self.key_display.toPlainText().strip()
        return ocid_ok and tenancy_ok and fp_ok and key_ok


class ReviewPage(QWizardPage):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("Revisar Configuración")
        self.setSubTitle("Verifica tu configuración antes de aprovisionar.")

        layout = QVBoxLayout(self)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.summary)

        self.keep_conf = QCheckBox("Guardar configuración para futuras sesiones")
        self.keep_conf.setChecked(True)
        layout.addWidget(self.keep_conf)

        layout.addStretch()

    @typing.override
    def initializePage(self) -> None:
        wizard: SetupWizard = self.wizard()
        creds = wizard.get_credentials()
        region = wizard.get_region()

        self.summary.setText(
            "<b>Región:</b> " + region + "<br>"
            "<b>OCID de Usuario:</b> " + creds.user_ocid[:20] + "...<br>"
            "<b>OCID de Tenencia:</b> " + creds.tenancy_ocid[:20] + "...<br>"
            "<b>Huella Digital:</b> " + creds.fingerprint[:20] + "...<br><br>"
            "<b>Qué se creará:</b><br>"
            "• VM.Standard.A1.Flex (4 OCPU, 24 GB RAM)<br>"
            "• Servidor WireGuard (puerto 51820/UDP)<br>"
            "• Servicio keep-alive (evita apagado por inactividad)<br>"
            "• Reglas de firewall solo para tráfico de juego<br><br>"
            "<b>Costo: $0.00/mes — Siempre Gratis</b><br>"
        )


class ProgressPage(QWizardPage):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("Aprovisionando tu VPS")
        self.setSubTitle("Creando tu VM gratuita en la nube... Esto puede tomar 2-3 minutos.")

        layout = QVBoxLayout(self)
        self.status_label = QLabel("Iniciando...")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(200)
        self.log_area.setStyleSheet("font-family: monospace; font-size: 11px; background: #1e1e1e; color: #d4d4d4;")
        layout.addWidget(self.log_area)

        self._worker: ProvisioningWorker | None = None

    @typing.override
    def initializePage(self) -> None:
        wizard: SetupWizard = self.wizard()
        creds = wizard.get_credentials()
        region = wizard.get_region()

        self.log_area.clear()
        self._start_provisioning(creds, region)

    def _start_provisioning(self, creds: OciCredentials, region: str) -> None:
        creds.region = region

        km = KeyManager()
        key_errors = km.validate_oci_private_key(creds.private_key)
        if key_errors:
            self._on_error("; ".join(key_errors))
            return

        cred_errors = km.validate_oci_credentials(creds)
        if cred_errors:
            self._on_error("; ".join(cred_errors))
            return

        km.save_oci_private_key(creds.private_key)
        config = AppConfig.load()
        config.oci_credentials = creds
        config.save_credentials()
        config.save()

        self._worker = ProvisioningWorker(creds, region)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, msg: str, pct: int) -> None:
        self.status_label.setText(msg)
        self.progress_bar.setValue(pct)
        self.log_area.append(f"[{pct}%] {msg}")

    def _on_finished(self, result: dict) -> None:
        self.log_area.append("¡Completado!")
        config = AppConfig.load()
        config.vps_ip = result.get("public_ip", "")
        config.vps_id = result.get("instance_id", "")
        config.vps_region = result.get("region", "")

        config.tunnel.private_key = result.get("server_private_key", "")
        config.tunnel.public_key = result.get("server_public_key", "")
        config.tunnel.client_private_key = result.get("client_private_key", "")
        config.tunnel.vps_ip = result.get("public_ip", "")
        config.save()
        config.save_tunnel_conf()

        wizard: SetupWizard = self.wizard()
        wizard._provisioning_result = result
        wizard.next()

    def _on_error(self, msg: str) -> None:
        self.log_area.append(f"ERROR: {msg}")
        QMessageBox.critical(self, "Error de Aprovisionamiento", msg)

    @typing.override
    def isComplete(self) -> bool:
        return False


class CompletePage(QWizardPage):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("¡Configuración Completada!")
        self.setSubTitle("Tu VPS de FreePing está listo para usar.")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.summary)

        next_steps = QLabel(
            "<b>Próximos pasos:</b><br>"
            "1. Haz clic en <b>Finalizar</b> para volver a la ventana principal<br>"
            "2. Selecciona un juego del menú desplegable (o ingresa IPs personalizadas)<br>"
            "3. Haz clic en <b>Activar Túnel</b> — FreePing probará tu mejora automáticamente<br>"
            "4. ¡Juega con latencia reducida! 🎮<br><br>"
            "<b>Consejos:</b><br>"
            "• Mantén FreePing ejecutándose en la bandeja del sistema mientras juegas<br>"
            "• Usa el botón 'Probar Mejora' en cualquier momento para comparar latencia<br>"
            "• Ejecuta el asistente de nuevo desde Archivo → Ejecutar Asistente de Configuración"
        )
        next_steps.setWordWrap(True)
        next_steps.setStyleSheet("padding: 8px; background: #f0f7f0; border-radius: 4px;")
        layout.addWidget(next_steps)

        layout.addStretch()

    @typing.override
    def initializePage(self) -> None:
        wizard: SetupWizard = self.wizard()
        result = wizard._provisioning_result or {}
        ip = result.get("public_ip", "N/A")
        self.summary.setText(
            "<b>IP Pública del VPS:</b> " + ip + "<br>"
            "<b>Estado:</b> Ejecutándose<br>"
            "<b>Puerto WireGuard:</b> 51820/UDP<br>"
            "<b>Región:</b> " + result.get("region", "N/A") + "<br><br>"
            "<i>Tu instancia está iniciando con WireGuard preinstalado. "
            "Puede tomar hasta 60 segundos completar la configuración inicial.</i>"
        )
