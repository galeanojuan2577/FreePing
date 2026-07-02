from __future__ import annotations

import stat
from pathlib import Path

from freeping.core.models import OciCredentials


class KeyManager:
    def __init__(self, config_dir: Path = Path.home() / ".config" / "freeping") -> None:
        self.config_dir = config_dir
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def save_oci_private_key(self, key_content: str, filename: str = "oci_api_key.pem") -> Path:
        key_path = self.config_dir / filename
        key_path.write_text(key_content)
        key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        return key_path

    def load_oci_private_key(self, filename: str = "oci_api_key.pem") -> str:
        key_path = self.config_dir / filename
        if not key_path.exists():
            raise FileNotFoundError(f"OCI private key not found: {key_path}")
        if key_path.stat().st_mode & 0o077:
            key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        return key_path.read_text()

    def delete_oci_private_key(self, filename: str = "oci_api_key.pem") -> None:
        key_path = self.config_dir / filename
        if key_path.exists():
            key_path.unlink()

    def has_oci_key(self, filename: str = "oci_api_key.pem") -> bool:
        return (self.config_dir / filename).exists()

    @staticmethod
    def validate_oci_private_key(key_content: str) -> list[str]:
        errors: list[str] = []
        if "BEGIN PRIVATE KEY" not in key_content:
            errors.append("Missing 'BEGIN PRIVATE KEY' header")
        if "END PRIVATE KEY" not in key_content:
            errors.append("Missing 'END PRIVATE KEY' footer")
        if len(key_content) < 200:
            errors.append("Key content too short (may be truncated)")
        lines = key_content.strip().split("\n")
        if len(lines) < 3:
            errors.append("Key has too few lines")
        if not key_content.strip().endswith("-----END PRIVATE KEY-----"):
            errors.append("Key must end with END PRIVATE KEY marker")
        return errors

    @staticmethod
    def validate_oci_credentials(creds: OciCredentials) -> list[str]:
        errors: list[str] = []
        if not creds.user_ocid.startswith("ocid1.user.oc1.."):
            errors.append("User OCID must start with 'ocid1.user.oc1..'")
        if not creds.tenancy_ocid.startswith("ocid1.tenancy.oc1.."):
            errors.append("Tenancy OCID must start with 'ocid1.tenancy.oc1..'")
        if not creds.fingerprint:
            errors.append("Fingerprint is required")
        if ":" not in creds.fingerprint:
            errors.append("Fingerprint should be colon-separated hex (e.g. 12:34:56:...)")
        if not creds.region:
            errors.append("Region is required")
        return errors

    @staticmethod
    def parse_oci_key_from_file(file_path: Path) -> tuple[str, OciCredentials]:
        content = file_path.read_text()
        creds = OciCredentials()

        lines = content.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("user="):
                creds.user_ocid = line.split("=", 1)[1].strip()
            elif line.startswith("tenancy="):
                creds.tenancy_ocid = line.split("=", 1)[1].strip()
            elif line.startswith("fingerprint="):
                creds.fingerprint = line.split("=", 1)[1].strip()
            elif line.startswith("region="):
                creds.region = line.split("=", 1)[1].strip()
            elif line.startswith("key_file="):
                key_path_str = line.split("=", 1)[1].strip()
                key_path = file_path.parent / key_path_str
                if key_path.exists():
                    content = key_path.read_text()

        return content, creds

    @staticmethod
    def generate_oci_api_key() -> tuple[str, str]:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=4096,
        )

        private_pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        public_pem = key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

        return private_pem, public_pem
