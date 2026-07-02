from __future__ import annotations

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

    def run(self) -> None:
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            self.progress.emit("Generating WireGuard keys...", 10)
            from freeping.provisioning.oci_client import OciClient, WireGuardKeyPair
            keys = WireGuardKeyPair.generate()

            self.progress.emit("Connecting to Oracle Cloud...", 20)
            client = OciClient(self.credentials)

            self.progress.emit("Creating VCN and network...", 30)

            self.progress.emit("Launching Ampere A1 instance...", 50)
            from freeping.provisioning.cloud_init import CloudInitGenerator
            cloud_gen = CloudInitGenerator(
                server_private_key=keys.private_key,
                server_public_key=keys.public_key,
                client_public_key=keys.public_key,
            )
            cloud_init_yaml = cloud_gen.render()

            instance = loop.run_until_complete(
                client.create_instance(
                    ssh_public_key="",
                    cloud_init_yaml=cloud_init_yaml,
                    compartment_id=self.credentials.tenancy_ocid,
                )
            )

            self.progress.emit("Waiting for instance to be ready...", 70)
            import time
            time.sleep(10)

            instance = loop.run_until_complete(
                client.get_instance(instance.id)
            )

            self.progress.emit("Saving configuration...", 90)
            result = {
                "instance_id": instance.id,
                "public_ip": instance.public_ip,
                "region": self.region,
                "server_private_key": keys.private_key,
                "server_public_key": keys.public_key,
                "client_private_key": keys.private_key,
                "client_public_key": keys.public_key,
            }

            loop.close()
            self.progress.emit("Done!", 100)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class SetupWizard(QWizard):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("FreePing Setup Wizard")
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
        self.setTitle("Welcome to FreePing")
        self.setSubTitle("Your personal, free, self-hosted gaming VPN")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel(
            "FreePing creates a free WireGuard VPN server on Oracle Cloud's Always Free Tier "
            "to reduce your gaming latency. No credit card required."
        ))

        steps_box = QLabel(
            "<hr>"
            "<b>What we'll do in 5 minutes:</b><br><br>"
            "1. <b>Create</b> an Oracle Cloud account (if you don't have one)<br>"
            "2. <b>Generate</b> an API key for FreePing to manage your cloud resources<br>"
            "3. <b>Deploy</b> a free VM (4 ARM cores, 24 GB RAM) with WireGuard pre-installed<br>"
            "4. <b>Connect</b> your gaming traffic through the encrypted tunnel<br><br>"
            f'<a href="{ORACLE_SIGNUP_URL}" style="color: #4CAF50;">'
            "Click here to create your free Oracle Cloud account</a>"
            "<hr>"
        )
        steps_box.setOpenExternalLinks(True)
        steps_box.setWordWrap(True)
        layout.addWidget(steps_box)

        prereqs = QLabel(
            "<b>Requirements:</b><br>"
            "• Oracle Cloud account (free at cloud.oracle.com)<br>"
            "• Python 3.12 or later<br>"
            "• Internet connection<br><br>"
            "<b>What you get:</b><br>"
            "• VM.Standard.A1.Flex (4 OCPU, 24 GB RAM) — <b>free forever</b><br>"
            "• WireGuard VPN with split tunneling (game traffic only)<br>"
            "• Auto-reconnect if connection drops<br>"
            "• System tray integration for quick access"
        )
        prereqs.setWordWrap(True)
        prereqs.setStyleSheet("padding: 8px; background: #f0f7f0; border-radius: 4px;")
        layout.addWidget(prereqs)

        layout.addStretch()


class RegionPage(QWizardPage):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("Select Region")
        self.setSubTitle("Choose the Oracle Cloud region closest to you.")

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Pick the region geographically closest to your physical location "
            "for the lowest possible latency."
        ))

        self.region_combo = QComboBox()
        from freeping.provisioning.oci_client import OCI_REGIONS
        for key, name in sorted(OCI_REGIONS.items()):
            self.region_combo.addItem(name, key)
        self.region_combo.setCurrentIndex(
            list(OCI_REGIONS.keys()).index("sa-saopaulo-1")
            if "sa-saopaulo-1" in OCI_REGIONS else 0
        )
        layout.addWidget(self.region_combo)

        self.region_combo.setToolTip(
            "Choose the region nearest to you. "
            "Each region has free tier eligibility. "
            "São Paulo (sa-saopaulo-1) is pre-selected for South America."
        )

        layout.addStretch()

    def get_region(self) -> str:
        return self.region_combo.currentData()


class CredentialsPage(QWizardPage):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("Oracle Cloud API Credentials")
        self.setSubTitle("Grant FreePing permission to create resources in your account.")

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        api_guide = QLabel(
            '<b>Step-by-step guide to get your API credentials:</b><br><br>'
            f'1. Sign in to <a href="{ORACLE_CONSOLE_URL}" style="color: #4CAF50;">cloud.oracle.com</a><br>'
            '2. Click your profile icon (top-right) → <b>My Profile</b><br>'
            '3. Go to <b>API Keys</b> on the left sidebar<br>'
            '4. Click <b>"Add API Key"</b> → select <b>"Generate API Key Pair"</b><br>'
            '5. Download the <b>private key (.pem)</b> file<br>'
            '6. Click <b>"Add"</b> — a configuration preview will appear<br>'
            '7. Copy the values from that preview into the fields below<br><br>'
            f'<a href="{ORACLE_API_KEY_GUIDE}" style="color: #666;">'
            ' Full API Key documentation (opens in browser)</a>'
        )
        api_guide.setOpenExternalLinks(True)
        api_guide.setWordWrap(True)
        api_guide.setStyleSheet("padding: 8px; background: #f5f5ff; border-radius: 4px;")
        layout.addWidget(api_guide)

        btn_layout = QHBoxLayout()
        self.btn_upload = QPushButton("Upload PEM File...")
        self.btn_upload.setToolTip("Load an existing API key file (.pem) you downloaded from Oracle Cloud")
        btn_layout.addWidget(self.btn_upload)
        self.btn_generate = QPushButton("Generate New Key")
        self.btn_generate.setToolTip(
            "Create a new API key pair now (upload the public part to Oracle Cloud)"
        )
        btn_layout.addWidget(self.btn_generate)
        layout.addLayout(btn_layout)

        self.key_display = QTextEdit()
        self.key_display.setPlaceholderText("API key content will appear here...")
        self.key_display.setMaximumHeight(100)
        self.key_display.setToolTip(
            "The private key contents (-----BEGIN PRIVATE KEY----- ... -----END PRIVATE KEY-----)"
        )
        layout.addWidget(self.key_display)

        form = QFormLayout()

        self.user_ocid = QLineEdit()
        self.user_ocid.setPlaceholderText("ocid1.user.oc1..xxxxxxxxxxxx")
        self.user_ocid.setToolTip("Your user's OCID. Found in: Profile → My Profile → OCID (click 'Copy')")
        self.user_ocid.textChanged.connect(self._validate)
        form.addRow(self._field_label("User OCID:"), self.user_ocid)

        self.tenancy_ocid = QLineEdit()
        self.tenancy_ocid.setPlaceholderText("ocid1.tenancy.oc1..xxxxxxxxxxxx")
        self.tenancy_ocid.setToolTip("Your tenancy's OCID. Found in: Profile → Tenancy → OCID")
        self.tenancy_ocid.textChanged.connect(self._validate)
        form.addRow(self._field_label("Tenancy OCID:"), self.tenancy_ocid)

        self.fingerprint = QLineEdit()
        self.fingerprint.setPlaceholderText("12:34:56:78:90:ab:cd:ef:01:23:45:67:89:0a:bc:de:f0:12:34:56")
        self.fingerprint.setToolTip(
            "The fingerprint of your uploaded API key. Found in: Profile → API Keys"
        )
        self.fingerprint.textChanged.connect(self._validate)
        form.addRow(self._field_label("Fingerprint:"), self.fingerprint)

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
            self.validation_label.setText("User OCID should start with 'ocid1.user.'")
            self.validation_label.setStyleSheet("color: #e74c3c;")
        elif self.tenancy_ocid.text().strip() and not tenancy_ok:
            self.validation_label.setText("Tenancy OCID should start with 'ocid1.tenancy.'")
            self.validation_label.setStyleSheet("color: #e74c3c;")
        elif not key_ok and self.key_display.toPlainText().strip():
            self.validation_label.setText("Private key should start with '-----BEGIN PRIVATE KEY-----'")
            self.validation_label.setStyleSheet("color: #e74c3c;")
        else:
            text = "All fields look good!" if self.isComplete() else "Fill in all fields to continue."
            self.validation_label.setText(text)
            color = "#4CAF50" if self.isComplete() else "#666"
            self.validation_label.setStyleSheet(f"color: {color}; font-style: italic;")

        self.completeChanged.emit()

    def _upload_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select API Key", "", "PEM files (*.pem);;All files (*)"
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
                        self, "Manual Entry",
                        "Key loaded. Please enter your OCID and fingerprint manually from the Oracle Cloud console.",
                    )

    def _generate_key(self) -> None:
        from freeping.provisioning.key_manager import KeyManager
        try:
            priv, pub = KeyManager.generate_oci_api_key()
            self.key_display.setPlainText(priv)
            QMessageBox.information(
                self, "Key Generated",
                "New API key generated.\n\n"
                "Next steps:\n"
                "1. Go to cloud.oracle.com → Profile → API Keys\n"
                "2. Click 'Add API Key'\n"
                "3. Choose 'Paste Public Key' and paste this:\n\n"
                f"{pub}\n\n"
                "4. Click 'Add' and copy the User OCID and Fingerprint from the preview.",
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate key: {e}")

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
        self.setTitle("Review Configuration")
        self.setSubTitle("Verify your settings before provisioning.")

        layout = QVBoxLayout(self)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.summary)

        self.keep_conf = QCheckBox("Save configuration for future sessions")
        self.keep_conf.setChecked(True)
        layout.addWidget(self.keep_conf)

        layout.addStretch()

    @typing.override
    def initializePage(self) -> None:
        wizard: SetupWizard = self.wizard()
        creds = wizard.get_credentials()
        region = wizard.get_region()

        self.summary.setText(
            "<b>Region:</b> " + region + "<br>"
            "<b>User OCID:</b> " + creds.user_ocid[:20] + "...<br>"
            "<b>Tenancy OCID:</b> " + creds.tenancy_ocid[:20] + "...<br>"
            "<b>Fingerprint:</b> " + creds.fingerprint[:20] + "...<br><br>"
            "<b>What will be created:</b><br>"
            "• VM.Standard.A1.Flex (4 OCPU, 24 GB RAM)<br>"
            "• WireGuard VPN server (port 51820/UDP)<br>"
            "• Keep-alive service (prevents idle shutdown)<br>"
            "• Firewall rules for gaming traffic only<br><br>"
            "<b>Cost: $0.00/month — Always Free Tier</b><br>"
        )


class ProgressPage(QWizardPage):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("Provisioning Your VPS")
        self.setSubTitle("Creating your free cloud VM... This may take 2-3 minutes.")

        layout = QVBoxLayout(self)
        self.status_label = QLabel("Starting...")
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
        self.log_area.append("Done!")
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
        QMessageBox.critical(self, "Provisioning Error", msg)

    @typing.override
    def isComplete(self) -> bool:
        return False


class CompletePage(QWizardPage):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("Setup Complete!")
        self.setSubTitle("Your FreePing VPS is ready to use.")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.summary)

        next_steps = QLabel(
            "<b>Next steps:</b><br>"
            "1. Click <b>Finish</b> to return to the main window<br>"
            "2. Select a game from the dropdown (or enter custom IPs)<br>"
            "3. Click <b>Activate Tunnel</b> — FreePing will test your improvement automatically!<br>"
            "4. Play with reduced latency 🎮<br><br>"
            "<b>Tips:</b><br>"
            "• Keep FreePing running in the system tray while gaming<br>"
            "• Use the 'Test Improvement' button anytime to compare latency<br>"
            "• Run the setup wizard again anytime from File → Run Setup Wizard"
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
            "<b>VPS Public IP:</b> " + ip + "<br>"
            "<b>Status:</b> Running<br>"
            "<b>WireGuard Port:</b> 51820/UDP<br>"
            "<b>Region:</b> " + result.get("region", "N/A") + "<br><br>"
            "<i>Your instance is booting with WireGuard pre-installed. "
            "It may take 60 seconds to finish initial setup.</i>"
        )
