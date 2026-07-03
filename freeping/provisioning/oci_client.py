from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from freeping.core.models import OciCredentials, VPSStatus


class OciError(Exception):
    def __init__(self, message: str, status_code: int = 0, code: str = "") -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(message)


class AuthError(OciError):
    pass


@dataclass
class OciInstance:
    id: str
    display_name: str
    status: VPSStatus
    public_ip: str = ""
    region: str = ""
    shape: str = "VM.Standard.A1.Flex"


OCI_REGIONS: dict[str, str] = {
    "us-ashburn-1": "Ashburn (US East)",
    "us-phoenix-1": "Phoenix (US West)",
    "eu-frankfurt-1": "Frankfurt (EU)",
    "eu-london-1": "London (EU)",
    "eu-paris-1": "Paris (EU)",
    "eu-amsterdam-1": "Amsterdam (EU)",
    "sa-bogota-1": "Bogotá (Colombia)",
    "sa-saopaulo-1": "São Paulo (South America)",
    "ap-mumbai-1": "Mumbai (Asia)",
    "ap-singapore-1": "Singapore (Asia)",
    "ap-tokyo-1": "Tokyo (Asia)",
    "ap-sydney-1": "Sydney (Asia Pacific)",
}


class OciClient:
    def __init__(self, credentials: OciCredentials, wireguard_port: int = 51820) -> None:
        self.creds = credentials
        self._wg_port = wireguard_port
        self._base_url = f"https://iaas.{credentials.region}.oraclecloud.com"

    def list_regions(self) -> list[dict]:
        return [
            {"key": k, "name": v}
            for k, v in sorted(OCI_REGIONS.items())
        ]

    async def create_instance(
        self,
        ssh_public_key: str,
        cloud_init_yaml: str,
        compartment_id: str,
        display_name: str = "FreePing-VPS",
    ) -> OciInstance:
        subnet_id = await self._get_or_create_subnet(compartment_id)
        nsg_id = await self._get_or_create_nsg(compartment_id)

        body = {
            "compartmentId": compartment_id,
            "displayName": display_name,
            "shape": "VM.Standard.A1.Flex",
            "shapeConfig": {
                "ocpus": 1,
                "memoryInGBs": 6,
            },
            "sourceDetails": {
                "sourceType": "image",
                "imageId": self._get_ubuntu_image_id(),
                "bootVolumeSizeInGBs": 50,
            },
            "metadata": {
                "ssh_authorized_keys": ssh_public_key,
                "user_data": base64.b64encode(
                    cloud_init_yaml.encode()
                ).decode(),
            },
            "createVnicDetails": {
                "subnetId": subnet_id,
                "nsgIds": [nsg_id],
                "assignPublicIp": True,
            },
        }

        data = await self._request("POST", "/20160918/instances", body)

        instance_id = data.get("id", "")
        return OciInstance(
            id=instance_id,
            display_name=data.get("displayName", display_name),
            status=VPSStatus.RUNNING if data.get("lifecycleState") == "RUNNING" else VPSStatus.UNKNOWN,
            region=self.creds.region,
        )

    async def get_instance(self, instance_id: str) -> OciInstance:
        data = await self._request("GET", f"/20160918/instances/{instance_id}")
        state = self._map_state(data.get("lifecycleState", ""))

        instance = OciInstance(
            id=instance_id,
            display_name=data.get("displayName", ""),
            status=state,
            region=self.creds.region,
        )

        if state == VPSStatus.RUNNING:
            vnics = await self._request(
                "GET",
                f"/20160918/vnicAttachments?instanceId={instance_id}&compartmentId={data.get('compartmentId', '')}",
            )
            attachments = vnics if isinstance(vnics, list) else vnics.get("data", [])
            if attachments:
                vnic_id = attachments[0].get("vnicId", "")
                if vnic_id:
                    vnic = await self._request("GET", f"/20160918/vnics/{vnic_id}")
                    instance.public_ip = vnic.get("publicIp", "")

        return instance

    async def get_instance_status(self, instance_id: str) -> VPSStatus:
        instance = await self.get_instance(instance_id)
        return instance.status

    async def start_instance(self, instance_id: str) -> VPSStatus:
        await self._request("POST", f"/20160918/instances/{instance_id}/actions/start")
        return VPSStatus.RUNNING

    async def stop_instance(self, instance_id: str) -> VPSStatus:
        await self._request("POST", f"/20160918/instances/{instance_id}/actions/stop")
        return VPSStatus.STOPPED

    async def terminate_instance(self, instance_id: str) -> VPSStatus:
        await self._request("POST", f"/20160918/instances/{instance_id}/actions/terminate")
        return VPSStatus.TERMINATED

    async def _get_or_create_subnet(self, compartment_id: str) -> str:
        vcn_id = await self._get_or_create_vcn(compartment_id)
        subnets = await self._request(
            "GET",
            f"/20160918/subnets?compartmentId={compartment_id}&vcnId={vcn_id}",
        )
        subnet_list = subnets if isinstance(subnets, list) else subnets.get("data", [])
        if subnet_list:
            return subnet_list[0]["id"]

        body = {
            "compartmentId": compartment_id,
            "vcnId": vcn_id,
            "displayName": "FreePing-Subnet",
            "cidrBlock": "10.0.1.0/24",
            "routeTableId": (await self._get_default_route_table(compartment_id, vcn_id)),
            "securityListIds": [],
        }
        data = await self._request("POST", "/20160918/subnets", body)
        return data["id"]

    async def _get_or_create_vcn(self, compartment_id: str) -> str:
        vcns = await self._request(
            "GET",
            f"/20160918/vcns?compartmentId={compartment_id}",
        )
        vcn_list = vcns if isinstance(vcns, list) else vcns.get("data", [])
        if vcn_list:
            return vcn_list[0]["id"]

        body = {
            "compartmentId": compartment_id,
            "displayName": "FreePing-VCN",
            "cidrBlock": "10.0.0.0/16",
            "dnsLabel": "freeping",
        }
        data = await self._request("POST", "/20160918/vcns", body)
        return data["id"]

    async def _get_or_create_nsg(self, compartment_id: str) -> str:
        vcn_id = await self._get_or_create_vcn(compartment_id)

        nsgs = await self._request(
            "GET",
            f"/20160918/networkSecurityGroups?compartmentId={compartment_id}&vcnId={vcn_id}",
        )
        nsg_list = nsgs if isinstance(nsgs, list) else nsgs.get("data", [])
        for nsg in nsg_list:
            if "FreePing" in nsg.get("displayName", ""):
                return nsg["id"]

        body = {
            "compartmentId": compartment_id,
            "vcnId": vcn_id,
            "displayName": "FreePing-NSG",
        }
        data = await self._request("POST", "/20160918/networkSecurityGroups", body)
        nsg_id = data["id"]

        wg_rule = {
            "networkSecurityGroupId": nsg_id,
            "securityRules": [
                {
                    "description": "WireGuard UDP",
                    "direction": "INGRESS",
                    "protocol": "17",
                    "isStateless": False,
                    "source": "0.0.0.0/0",
                    "sourceType": "CIDR_BLOCK",
                    "tcpOptions": None,
                    "udpOptions": {
                        "destinationPortRange": {"min": self._wg_port, "max": self._wg_port}
                    },
                },
                {
                    "description": "ICMP Ping",
                    "direction": "INGRESS",
                    "protocol": "1",
                    "isStateless": False,
                    "source": "0.0.0.0/0",
                    "sourceType": "CIDR_BLOCK",
                },
                {
                    "description": "SSH",
                    "direction": "INGRESS",
                    "protocol": "6",
                    "isStateless": False,
                    "source": "0.0.0.0/0",
                    "sourceType": "CIDR_BLOCK",
                    "tcpOptions": {
                        "destinationPortRange": {"min": 22, "max": 22}
                    },
                },
                {
                    "description": "Egress all",
                    "direction": "EGRESS",
                    "protocol": "all",
                    "isStateless": False,
                    "destination": "0.0.0.0/0",
                    "destinationType": "CIDR_BLOCK",
                },
            ],
        }
        await self._request(
            "POST",
            f"/20160918/networkSecurityGroups/{nsg_id}/securityRules",
            wg_rule,
        )
        return nsg_id

    async def _get_default_route_table(self, compartment_id: str, vcn_id: str) -> str:
        rt = await self._request(
            "GET",
            f"/20160918/routeTables?compartmentId={compartment_id}&vcnId={vcn_id}",
        )
        rt_list = rt if isinstance(rt, list) else rt.get("data", [])
        if rt_list:
            return rt_list[0]["id"]
        raise OciError("No default route table found")

    def _get_ubuntu_image_id(self) -> str:
        images = {
            "us-ashburn-1": "ocid1.image.oc1.iad.aaaaaaaaigqvtzzzhjq6otqvso3bzwmc5dwr7kz3krrgtj2sqnolsa5g4rwq",
            "us-phoenix-1": "ocid1.image.oc1.phx.aaaaaaaavjndib52k65rpshkotxwjxv5tvc5qa4k36dwiajugta65xv6raaq",
            "eu-frankfurt-1": (
                "ocid1.image.oc1.eu-frankfurt-1."
                "aaaaaaaayl6kny3zvygccnogogfm544dd3qvikkj6enbz4eup7byfvdw2a5a"
            ),
            "eu-london-1": (
                "ocid1.image.oc1.uk-london-1."
                "aaaaaaaaznecwbrmjyjdqk4xdyyppyygnmmbsnb25q44dzrwo6d2szhsv6da"
            ),
            "eu-paris-1": (
                "ocid1.image.oc1.eu-paris-1."
                "aaaaaaaaophdxcybvl2h6am42jtstxiqllolgwsmxzxxbujhdydrki2aowpq"
            ),
            "eu-amsterdam-1": (
                "ocid1.image.oc1.eu-amsterdam-1."
                "aaaaaaaak36bjmrftqb5fqdnkiv36vfjhmcjmfibd3ywtfvfjtndbu6zepta"
            ),
            "sa-bogota-1": "ocid1.image.oc1.sa-bogota-1.aaaaaaaa4gmr625mzitc2swhwairdqfl642pjf4trvcatgci3isevpsob45q",
            "sa-saopaulo-1": (
                "ocid1.image.oc1.sa-saopaulo-1."
                "aaaaaaaa6dm52etzxfkbo2bhm3puuc54yrk5yctvvzyakcxbtix4n23247yq"
            ),
            "ap-mumbai-1": "ocid1.image.oc1.ap-mumbai-1.aaaaaaaaccdubkruxb4xljfqnahwx6dy2kgi7tc4mqpzp24t3tqoo3svqlva",
            "ap-singapore-1": (
                "ocid1.image.oc1.ap-singapore-1."
                "aaaaaaaa6rpevbhllh3j6bx64bzxsiwhzjfzqjrojqomrmrfgaqbzzifmcnq"
            ),
            "ap-tokyo-1": "ocid1.image.oc1.ap-tokyo-1.aaaaaaaavy5wfuezcfzuuiryv26zepg375cfekt7znt3u77qcycs7yvyrxra",
            "ap-sydney-1": "ocid1.image.oc1.ap-sydney-1.aaaaaaaaque5khwgpvd467sootlw5q4evgcbu4i7xy7zk762ir5ihd7776kq",
        }
        return images.get(
            self.creds.region,
            "ocid1.image.oc1..aaaaaaaa",
        )

    @staticmethod
    def _map_state(state: str) -> VPSStatus:
        mapping = {
            "RUNNING": VPSStatus.RUNNING,
            "STOPPED": VPSStatus.STOPPED,
            "TERMINATED": VPSStatus.TERMINATED,
            "TERMINATING": VPSStatus.TERMINATED,
        }
        return mapping.get(state, VPSStatus.UNKNOWN)

    async def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
    ) -> dict | list:
        url = f"{self._base_url}{path}"
        headers = self._sign_request(method, path, body)

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                if method == "GET":
                    resp = await client.get(url, headers=headers)
                elif method == "POST":
                    resp = await client.post(url, headers=headers, json=body or {})
                elif method == "PUT":
                    resp = await client.put(url, headers=headers, json=body or {})
                elif method == "DELETE":
                    resp = await client.delete(url, headers=headers)
                else:
                    raise OciError(f"Unsupported method: {method}")

                if resp.status_code >= 400:
                    self._handle_error(resp.status_code, resp.text)

                return resp.json()
            except httpx.TimeoutException:
                raise OciError("Request timed out", status_code=0)
            except httpx.RequestError as e:
                raise OciError(f"Network error: {e}", status_code=0)

    def _sign_request(self, method: str, path: str, body: dict | None = None) -> dict[str, str]:
        now = datetime.now(UTC)
        header_date = now.strftime("%a, %d %b %Y %H:%M:%S UTC")

        content_type = "application/json"
        body_hash = hashlib.sha256(
            json.dumps(body or {}).encode()
        ).hexdigest() if method in ("POST", "PUT") else hashlib.sha256(b"").hexdigest()

        headers = {
            "host": f"iaas.{self.creds.region}.oraclecloud.com",
            "date": header_date,
            "(request-target)": f"{method.lower()} {path}",
            "content-type": content_type if method in ("POST", "PUT") else "",
            "x-content-sha256": body_hash,
        }

        signing_string = "\n".join([
            f"{key}: {value}" for key, value in headers.items() if value
        ])
        signature = self._sign(signing_string)

        headers_signed = " ".join(
            key for key, value in headers.items() if value
        )
        auth_header = (
            f'Signature version="1",'
            f'keyId="{self.creds.tenancy_ocid}/{self.creds.user_ocid}/{self.creds.fingerprint}",'
            f'algorithm="rsa-sha256",'
            f'headers="{headers_signed}",'
            f'signature="{signature}"'
        )

        result = {
            "Content-Type": "application/json",
            "Date": header_date,
            "Authorization": auth_header,
            "x-content-sha256": body_hash,
        }
        return result

    def _sign(self, data: str) -> str:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        try:
            key = serialization.load_pem_private_key(
                self.creds.private_key.encode(),
                password=None,
            )
            signature = key.sign(
                data.encode(),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return base64.b64encode(signature).decode()
        except Exception as e:
            raise AuthError(f"Failed to sign request: {e}")

    @staticmethod
    def _handle_error(status: int, text: str) -> None:
        try:
            data = json.loads(text)
            message = data.get("message", text)
            code = data.get("code", "")
        except json.JSONDecodeError:
            message = text
            code = ""

        if status in (401, 403):
            raise AuthError(message, status, code)
        raise OciError(message, status, code)


@dataclass
class WireGuardKeyPair:
    private_key: str
    public_key: str

    @classmethod
    def generate(cls) -> WireGuardKeyPair:
        import subprocess

        try:
            priv = subprocess.run(
                ["wg", "genkey"], capture_output=True, text=True, check=True
            ).stdout.strip()
            pub = subprocess.run(
                ["wg", "pubkey"], input=priv, capture_output=True, text=True, check=True
            ).stdout.strip()
            return cls(private_key=priv, public_key=pub)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return cls._generate_python_fallback()

    @classmethod
    def _generate_python_fallback(cls) -> WireGuardKeyPair:
        import os

        priv_bytes = os.urandom(32)
        priv = base64.b64encode(priv_bytes).decode()
        pub_bytes = cls._curve25519_public(priv_bytes)
        pub = base64.b64encode(pub_bytes).decode()
        return cls(private_key=priv, public_key=pub)

    @staticmethod
    def _curve25519_public(private: bytes) -> bytes:
        try:
            from cryptography.hazmat.primitives.asymmetric.x25519 import (
                X25519PrivateKey,
            )
            key = X25519PrivateKey.from_private_bytes(private)
            return key.public_key().public_bytes_raw()
        except ImportError:
            raise RuntimeError(
                "Cannot generate WireGuard keys. Install wireguard-tools "
                "or cryptography>=41.0"
            )
