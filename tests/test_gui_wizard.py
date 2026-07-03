from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytestqt.qtbot import QtBot

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from freeping.core.models import OciCredentials
from freeping.gui.wizard import (
    CompletePage,
    CredentialsPage,
    ProgressPage,
    ProvisioningWorker,
    RegionPage,
    ReviewPage,
    SetupWizard,
    WelcomePage,
)


@pytest.fixture(autouse=True)
def mock_services(mocker):
    import freeping.gui.wizard as wz

    km_cls = mocker.patch("freeping.provisioning.key_manager.KeyManager")
    mocker.patch.object(wz, "KeyManager", km_cls)
    km = km_cls.return_value
    km.validate_oci_private_key.return_value = []
    km.validate_oci_credentials.return_value = []

    cfg_cls = mocker.patch("freeping.gui.wizard.AppConfig")
    cfg = MagicMock()
    cfg_cls.load.return_value = cfg

    mocker.patch("PySide6.QtWidgets.QMessageBox.information")
    mocker.patch("PySide6.QtWidgets.QMessageBox.critical")
    mocker.patch(
        "PySide6.QtWidgets.QFileDialog.getOpenFileName",
        return_value=("", ""),
    )

    return {
        "key_manager_cls": km_cls,
        "key_manager": km,
        "app_config": cfg,
        "app_config_cls": cfg_cls,
    }


@pytest.fixture
def wizard(qtbot: QtBot, mock_services):
    w = SetupWizard()
    qtbot.addWidget(w)
    return w


class TestSetupWizard:
    def test_creates_all_six_pages(self, wizard: SetupWizard):
        for i in range(6):
            assert wizard.page(i) is not None

    def test_page_types(self, wizard: SetupWizard):
        assert isinstance(wizard.page(0), WelcomePage)
        assert isinstance(wizard.page(1), RegionPage)
        assert isinstance(wizard.page(2), CredentialsPage)
        assert isinstance(wizard.page(3), ReviewPage)
        assert isinstance(wizard.page(4), ProgressPage)
        assert isinstance(wizard.page(5), CompletePage)

    def test_window_title(self, wizard: SetupWizard):
        assert "FreePing" in wizard.windowTitle()

    def test_get_credentials_delegates(self, wizard: SetupWizard, sample_credentials: OciCredentials):
        page = wizard.page(2)
        page.user_ocid.setText(sample_credentials.user_ocid)
        page.tenancy_ocid.setText(sample_credentials.tenancy_ocid)
        page.fingerprint.setText(sample_credentials.fingerprint)
        page.key_display.setPlainText(sample_credentials.private_key)
        result = wizard.get_credentials()
        assert isinstance(result, OciCredentials)
        assert result.user_ocid == sample_credentials.user_ocid

    def test_get_region_delegates(self, wizard: SetupWizard):
        page = wizard.page(1)
        page.region_combo.setCurrentIndex(1)
        expected = page.region_combo.currentData()
        assert wizard.get_region() == expected

    def test_initial_provisioning_result_is_none(self, wizard: SetupWizard):
        assert wizard._provisioning_result is None


class TestWelcomePage:
    def test_title(self, wizard: SetupWizard):
        page = wizard.page(0)
        assert "Bienvenido" in page.title()

    def test_has_links(self, wizard: SetupWizard):
        page = wizard.page(0)
        text = page.subTitle()
        assert text is not None


class TestRegionPage:
    def test_combo_has_all_regions(self, wizard: SetupWizard):
        page = wizard.page(1)
        from freeping.provisioning.oci_client import OCI_REGIONS

        assert page.region_combo.count() == len(OCI_REGIONS)

    def test_default_selection_is_valid_region(self, wizard: SetupWizard):
        page = wizard.page(1)
        from freeping.provisioning.oci_client import OCI_REGIONS
        assert page.region_combo.currentData() in OCI_REGIONS

    def test_get_region_returns_current_data(self, wizard: SetupWizard):
        page = wizard.page(1)
        page.region_combo.setCurrentIndex(2)
        assert page.get_region() == page.region_combo.currentData()

    def test_first_region_item_has_name_and_key(self, wizard: SetupWizard):
        page = wizard.page(1)
        name = page.region_combo.itemText(0)
        key = page.region_combo.itemData(0)
        assert name and key
        assert len(key.split("-")) >= 2


class TestCredentialsPage:
    def test_default_state_is_incomplete(self, wizard: SetupWizard):
        page = wizard.page(2)
        assert page.isComplete() is False

    def test_validate_shows_error_for_bad_user_ocid(self, wizard: SetupWizard):
        page = wizard.page(2)
        page.user_ocid.setText("invalid")
        page._validate()
        assert "ocid1.user" in page.validation_label.text().lower()

    def test_validate_shows_error_for_bad_tenancy_ocid(self, wizard: SetupWizard):
        page = wizard.page(2)
        page.user_ocid.setText("ocid1.user.oc1..valid")
        page.tenancy_ocid.setText("invalid")
        page._validate()
        assert "ocid1.tenancy" in page.validation_label.text().lower()

    def test_validate_shows_error_for_bad_key(self, wizard: SetupWizard):
        page = wizard.page(2)
        page.user_ocid.setText("ocid1.user.oc1..valid")
        page.tenancy_ocid.setText("ocid1.tenancy.oc1..valid")
        page.key_display.setPlainText("no begin marker")
        page._validate()
        assert "BEGIN" in page.validation_label.text()

    def test_validate_shows_fill_message_when_not_complete(self, wizard: SetupWizard):
        page = wizard.page(2)
        page._validate()
        assert "Completa todos" in page.validation_label.text()

    def test_validate_shows_success_when_complete(self, wizard: SetupWizard, sample_credentials: OciCredentials):
        page = wizard.page(2)
        page.user_ocid.setText(sample_credentials.user_ocid)
        page.tenancy_ocid.setText(sample_credentials.tenancy_ocid)
        page.fingerprint.setText(sample_credentials.fingerprint)
        page.key_display.setPlainText(sample_credentials.private_key)
        page._validate()
        assert "se ven bien" in page.validation_label.text().lower()

    def test_is_complete_true_with_valid_data(self, wizard: SetupWizard, sample_credentials: OciCredentials):
        page = wizard.page(2)
        page.user_ocid.setText(sample_credentials.user_ocid)
        page.tenancy_ocid.setText(sample_credentials.tenancy_ocid)
        page.fingerprint.setText(sample_credentials.fingerprint)
        page.key_display.setPlainText(sample_credentials.private_key)
        assert page.isComplete() is True

    def test_is_complete_false_with_short_fingerprint(self, wizard: SetupWizard):
        page = wizard.page(2)
        page.user_ocid.setText("ocid1.user.oc1..valid")
        page.tenancy_ocid.setText("ocid1.tenancy.oc1..valid")
        page.fingerprint.setText("short")
        page.key_display.setPlainText("-----BEGIN PRIVATE KEY-----\nkey\n-----END PRIVATE KEY-----")
        assert page.isComplete() is False

    def test_is_complete_false_missing_key(self, wizard: SetupWizard, sample_credentials: OciCredentials):
        page = wizard.page(2)
        page.user_ocid.setText(sample_credentials.user_ocid)
        page.tenancy_ocid.setText(sample_credentials.tenancy_ocid)
        page.fingerprint.setText(sample_credentials.fingerprint)
        page.key_display.setPlainText("no key")
        assert page.isComplete() is False

    def test_get_credentials_returns_oci_credentials(self, wizard: SetupWizard, sample_credentials: OciCredentials):
        page = wizard.page(2)
        page.user_ocid.setText(sample_credentials.user_ocid)
        page.tenancy_ocid.setText(sample_credentials.tenancy_ocid)
        page.fingerprint.setText(sample_credentials.fingerprint)
        page.key_display.setPlainText(sample_credentials.private_key)
        creds = page.get_credentials()
        assert creds.user_ocid == sample_credentials.user_ocid
        assert creds.tenancy_ocid == sample_credentials.tenancy_ocid
        assert creds.fingerprint == sample_credentials.fingerprint
        assert creds.private_key == sample_credentials.private_key

    def test_upload_pem_with_ocid_parses_fields(self, wizard: SetupWizard, mock_services, mocker, tmp_path: Path):
        pem_content = (
            "user=ocid1.user.oc1..testuser\n"
            "tenancy=ocid1.tenancy.oc1..testtenancy\n"
            "fingerprint=ab:cd:ef:12:34:56:78:90\n"
            "region=sa-saopaulo-1\n"
        )
        pem_path = tmp_path / "test_key.pem"
        pem_path.write_text(pem_content)

        mocker.patch(
            "PySide6.QtWidgets.QFileDialog.getOpenFileName",
            return_value=(str(pem_path), "PEM files (*.pem)"),
        )

        page = wizard.page(2)
        parsed_creds = OciCredentials(
            user_ocid="ocid1.user.oc1..testuser",
            tenancy_ocid="ocid1.tenancy.oc1..testtenancy",
            fingerprint="ab:cd:ef:12:34:56:78:90",
            region="sa-saopaulo-1",
        )
        page.key_display.setPlainText("")
        page.user_ocid.setText("")
        page.tenancy_ocid.setText("")
        page.fingerprint.setText("")
        mock_services["key_manager_cls"].parse_oci_key_from_file.return_value = (
            "-----BEGIN PRIVATE KEY-----\nPARSED\n-----END PRIVATE KEY-----",
            parsed_creds,
        )

        page.btn_upload.click()

        assert page.key_display.toPlainText() == "-----BEGIN PRIVATE KEY-----\nPARSED\n-----END PRIVATE KEY-----"
        assert page.user_ocid.text() == parsed_creds.user_ocid
        assert page.tenancy_ocid.text() == parsed_creds.tenancy_ocid
        assert page.fingerprint.text() == parsed_creds.fingerprint

    def test_upload_pem_without_ocid_sets_key_content(self, wizard: SetupWizard, mocker, tmp_path: Path):
        pem_content = "-----BEGIN PRIVATE KEY-----\nMOCKKEY\n-----END PRIVATE KEY-----"
        pem_path = tmp_path / "key_only.pem"
        pem_path.write_text(pem_content)

        mocker.patch(
            "PySide6.QtWidgets.QFileDialog.getOpenFileName",
            return_value=(str(pem_path), "PEM files (*.pem)"),
        )

        page = wizard.page(2)
        page.key_display.setPlainText("")
        page.btn_upload.click()

        assert "MOCKKEY" in page.key_display.toPlainText()

    def test_generate_key_success(self, wizard: SetupWizard, mock_services):
        mock_services["key_manager_cls"].generate_oci_api_key.return_value = (
            "-----BEGIN PRIVATE KEY-----\nGENERATED\n-----END PRIVATE KEY-----",
            "pub_key_data",
        )

        page = wizard.page(2)
        page.key_display.setPlainText("")
        page.btn_generate.click()

        assert "GENERATED" in page.key_display.toPlainText()

    def test_generate_key_failure_shows_error(self, wizard: SetupWizard, mock_services, mocker):
        mock_error = mocker.patch("PySide6.QtWidgets.QMessageBox.critical")
        mock_services["key_manager_cls"].generate_oci_api_key.side_effect = Exception("Gen failed")

        page = wizard.page(2)
        page.btn_generate.click()

        mock_error.assert_called_once()
        call_args = mock_error.call_args[0]
        assert "Gen failed" in str(call_args)


class TestReviewPage:
    def test_initialize_shows_region_and_credentials(self, wizard: SetupWizard, sample_credentials: OciCredentials):
        cred_page = wizard.page(2)
        cred_page.user_ocid.setText(sample_credentials.user_ocid)
        cred_page.tenancy_ocid.setText(sample_credentials.tenancy_ocid)
        cred_page.fingerprint.setText(sample_credentials.fingerprint)
        cred_page.key_display.setPlainText(sample_credentials.private_key)

        review = wizard.page(3)
        review.initializePage()

        assert sample_credentials.user_ocid[:20] in review.summary.text()
        assert sample_credentials.fingerprint[:20] in review.summary.text()

    def test_keep_conf_checked_by_default(self, wizard: SetupWizard):
        review = wizard.page(3)
        assert review.keep_conf.isChecked() is True


class TestProgressPage:
    def test_is_complete_returns_false(self, wizard: SetupWizard):
        page = wizard.page(4)
        assert page.isComplete() is False

    def test_start_provisioning_with_valid_data(
        self, wizard: SetupWizard, sample_credentials: OciCredentials, mock_services, mocker,
    ):
        mocker.patch.object(ProvisioningWorker, "start")

        page = wizard.page(4)
        page._start_provisioning(sample_credentials, "sa-saopaulo-1")

        mock_services["key_manager"].validate_oci_private_key.assert_called_once_with(sample_credentials.private_key)
        mock_services["key_manager"].validate_oci_credentials.assert_called_once()
        mock_services["key_manager"].save_oci_private_key.assert_called_once_with(sample_credentials.private_key)
        assert page._worker is not None

    def test_start_provisioning_invalid_key_shows_error(
        self, wizard: SetupWizard, sample_credentials: OciCredentials, mock_services,
    ):
        mock_services["key_manager"].validate_oci_private_key.return_value = ["Invalid key format"]

        page = wizard.page(4)
        page._start_provisioning(sample_credentials, "sa-saopaulo-1")

        assert "Invalid key format" in page.log_area.toPlainText()

    def test_start_provisioning_invalid_creds_shows_error(
        self, wizard: SetupWizard, sample_credentials: OciCredentials, mock_services,
    ):
        mock_services["key_manager"].validate_oci_private_key.return_value = []
        mock_services["key_manager"].validate_oci_credentials.return_value = ["Missing fingerprint"]

        page = wizard.page(4)
        page._start_provisioning(sample_credentials, "sa-saopaulo-1")

        assert "Missing fingerprint" in page.log_area.toPlainText()

    def test_on_progress_updates_ui(self, wizard: SetupWizard):
        page = wizard.page(4)
        page._on_progress("Connecting...", 42)

        assert page.status_label.text() == "Connecting..."
        assert page.progress_bar.value() == 42
        assert "[42%] Connecting..." in page.log_area.toPlainText()

    def test_on_finished_saves_config_and_navigates(self, wizard: SetupWizard, mock_services, mocker):
        mock_next = mocker.patch.object(wizard, "next")
        mock_config = mock_services["app_config"]
        result = {
            "public_ip": "203.0.113.10",
            "instance_id": "ocid1.instance..test",
            "region": "sa-saopaulo-1",
            "server_private_key": "spriv",
            "server_public_key": "spub",
            "client_private_key": "cpriv",
            "client_public_key": "cpub",
        }

        page = wizard.page(4)
        page._on_finished(result)

        assert mock_config.vps_ip == "203.0.113.10"
        assert mock_config.vps_id == "ocid1.instance..test"
        assert mock_config.vps_region == "sa-saopaulo-1"
        assert wizard._provisioning_result == result
        mock_config.save.assert_called_once()
        mock_config.save_tunnel_conf.assert_called_once()
        mock_next.assert_called_once()

    def test_on_error_shows_message(self, wizard: SetupWizard, mocker):
        mock_critical = mocker.patch("PySide6.QtWidgets.QMessageBox.critical")

        page = wizard.page(4)
        page._on_error("Connection timeout")

        assert "Connection timeout" in page.log_area.toPlainText()
        mock_critical.assert_called_once()

    def test_initialize_page_triggers_provisioning(
        self, wizard: SetupWizard, sample_credentials: OciCredentials, mock_services, mocker,
    ):
        mocker.patch.object(ProvisioningWorker, "start")

        cred_page = wizard.page(2)
        cred_page.user_ocid.setText(sample_credentials.user_ocid)
        cred_page.tenancy_ocid.setText(sample_credentials.tenancy_ocid)
        cred_page.fingerprint.setText(sample_credentials.fingerprint)
        cred_page.key_display.setPlainText(sample_credentials.private_key)

        page = wizard.page(4)
        page.initializePage()

        assert page._worker is not None
        assert page.log_area.toPlainText() == ""


class TestCompletePage:
    def test_initialize_shows_ip_from_result(self, wizard: SetupWizard):
        wizard._provisioning_result = {
            "public_ip": "10.0.0.42",
            "region": "us-ashburn-1",
        }

        page = wizard.page(5)
        page.initializePage()

        assert "10.0.0.42" in page.summary.text()
        assert "us-ashburn-1" in page.summary.text()

    def test_initialize_shows_na_when_no_result(self, wizard: SetupWizard):
        wizard._provisioning_result = None

        page = wizard.page(5)
        page.initializePage()

        assert "N/A" in page.summary.text()

    def test_next_steps_are_displayed(self, wizard: SetupWizard):
        page = wizard.page(5)
        assert "Completada" in page.title()


class TestProvisioningWorker:
    def test_run_success_emits_finished(self, qtbot: QtBot, mocker):
        mock_wg = mocker.patch("freeping.provisioning.oci_client.WireGuardKeyPair")
        mock_wg.generate.return_value = MagicMock(private_key="priv123", public_key="pub456")

        mock_oci_cls = mocker.patch("freeping.provisioning.oci_client.OciClient")
        mock_client = mock_oci_cls.return_value
        mock_instance = MagicMock(id="inst-001", public_ip="203.0.113.99")
        mock_client.create_instance.return_value = mock_instance
        mock_client.get_instance.return_value = mock_instance

        mock_cloud = mocker.patch("freeping.provisioning.cloud_init.CloudInitGenerator")
        mock_cloud.return_value.render.return_value = "#cloud-config"

        mocker.patch("time.sleep")
        mocker.patch("asyncio.set_event_loop")
        mocker.patch("asyncio.new_event_loop")
        mock_loop = asyncio.new_event_loop.return_value
        mock_loop.run_until_complete.side_effect = lambda coro: coro

        creds = OciCredentials(
            user_ocid="ocid1.user.oc1..w",
            tenancy_ocid="ocid1.tenancy.oc1..w",
            fingerprint="ab:cd:ef:12:34:56:78:90",
            private_key="-----BEGIN PRIVATE KEY-----\nW\n-----END PRIVATE KEY-----",
            region="sa-saopaulo-1",
        )

        worker = ProvisioningWorker(creds, "sa-saopaulo-1")

        with qtbot.wait_signal(worker.finished, timeout=3000) as blocker:
            worker.run()

        result = blocker.args[0]
        assert result["instance_id"] == "inst-001"
        assert result["public_ip"] == "203.0.113.99"
        assert result["region"] == "sa-saopaulo-1"
        assert result["server_private_key"] == "priv123"
        assert result["server_public_key"] == "pub456"

    def test_run_error_emits_error(self, qtbot: QtBot, mocker):
        mock_wg = mocker.patch("freeping.provisioning.oci_client.WireGuardKeyPair")
        mock_wg.generate.side_effect = Exception("Failed to generate keys")

        mocker.patch("time.sleep")
        mocker.patch("asyncio.set_event_loop")
        mocker.patch("asyncio.new_event_loop")
        mock_loop = asyncio.new_event_loop.return_value
        mock_loop.run_until_complete.side_effect = lambda coro: coro

        creds = OciCredentials(
            user_ocid="ocid1.user.oc1..e",
            tenancy_ocid="ocid1.tenancy.oc1..e",
            fingerprint="12:34:56:78:90:ab:cd:ef",
            private_key="-----BEGIN PRIVATE KEY-----\nE\n-----END PRIVATE KEY-----",
            region="eu-frankfurt-1",
        )

        worker = ProvisioningWorker(creds, "eu-frankfurt-1")

        with qtbot.wait_signal(worker.error, timeout=3000) as blocker:
            worker.run()

        assert "Failed to generate keys" in blocker.args[0]
