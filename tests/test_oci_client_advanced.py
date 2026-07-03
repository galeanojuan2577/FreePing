from __future__ import annotations

import builtins
import json
import subprocess
from unittest import mock

import httpx
import pytest

from freeping.provisioning.oci_client import (
    AuthError,
    OciClient,
    OciError,
    VPSStatus,
    WireGuardKeyPair,
)


def _mock_response(status_code: int, json_data):
    resp = mock.MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = json.dumps(json_data) if isinstance(json_data, (dict, list)) else str(json_data)
    return resp


class TestOciClientAdvanced:

    @pytest.mark.asyncio
    async def test_create_instance_full_flow(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance = m.return_value.__aenter__.return_value
            instance.get = mock.AsyncMock(side_effect=[
                _mock_response(200, {"data": []}),
                _mock_response(200, {"data": []}),
                _mock_response(200, {"data": [{"id": "rt-1"}]}),
                _mock_response(200, {"data": []}),
                _mock_response(200, {"data": []}),
            ])
            instance.post = mock.AsyncMock(side_effect=[
                _mock_response(200, {"id": "vcn-1"}),
                _mock_response(200, {"id": "subnet-1"}),
                _mock_response(200, {"id": "vcn-1"}),
                _mock_response(200, {"id": "nsg-1"}),
                _mock_response(200, {}),
                _mock_response(200, {"id": "inst-1", "displayName": "test-vps", "lifecycleState": "RUNNING"}),
            ])
            result = await client.create_instance(
                ssh_public_key="ssh-rsa test",
                cloud_init_yaml="#cloud-config",
                compartment_id="comp-1",
                display_name="test-vps",
            )
            assert result.id == "inst-1"
            assert result.display_name == "test-vps"
            assert result.status == VPSStatus.RUNNING
            assert result.region == "sa-saopaulo-1"
            assert instance.get.call_count == 5
            assert instance.post.call_count == 6
            post_calls = instance.post.call_args_list
            assert "/20160918/vcns" in str(post_calls[0])
            assert "/20160918/subnets" in str(post_calls[1])
            assert "/20160918/vcns" in str(post_calls[2])
            assert "/20160918/networkSecurityGroups" in str(post_calls[3])
            assert "securityRules" in str(post_calls[4])
            assert "/20160918/instances" in str(post_calls[5])

    @pytest.mark.asyncio
    async def test_create_instance_with_existing_resources(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance = m.return_value.__aenter__.return_value
            instance.get = mock.AsyncMock(side_effect=[
                _mock_response(200, {"data": [{"id": "vcn-1"}]}),
                _mock_response(200, {"data": [{"id": "subnet-1"}]}),
                _mock_response(200, {"data": [{"id": "vcn-1"}]}),
                _mock_response(200, {"data": [{"id": "nsg-1", "displayName": "FreePing-NSG"}]}),
            ])
            instance.post = mock.AsyncMock(side_effect=[
                _mock_response(200, {"id": "inst-1", "displayName": "test-vps", "lifecycleState": "RUNNING"}),
            ])
            result = await client.create_instance(
                ssh_public_key="ssh-rsa test",
                cloud_init_yaml="#cloud-config",
                compartment_id="comp-1",
                display_name="test-vps",
            )
            assert result.id == "inst-1"
            assert result.status == VPSStatus.RUNNING
            assert instance.post.call_count == 1

    @pytest.mark.asyncio
    async def test_get_instance_running_with_vnic_list(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(side_effect=[
                _mock_response(200, {"id": "inst-1", "lifecycleState": "RUNNING", "compartmentId": "comp-1", "displayName": "test"}),
                _mock_response(200, [{"vnicId": "vnic-1", "displayName": "test-vnic"}]),
                _mock_response(200, {"publicIp": "203.0.113.42"}),
            ])
            result = await client.get_instance("inst-1")
            assert result.id == "inst-1"
            assert result.status == VPSStatus.RUNNING
            assert result.public_ip == "203.0.113.42"
            assert instance_obj.get.call_count == 3

    @pytest.mark.asyncio
    async def test_get_instance_running_with_vnic_data_dict(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(side_effect=[
                _mock_response(200, {"id": "inst-1", "lifecycleState": "RUNNING", "compartmentId": "comp-1", "displayName": "test"}),
                _mock_response(200, {"data": [{"vnicId": "vnic-1"}]}),
                _mock_response(200, {"publicIp": "203.0.113.99"}),
            ])
            result = await client.get_instance("inst-1")
            assert result.public_ip == "203.0.113.99"

    @pytest.mark.asyncio
    async def test_get_instance_running_no_vnic_attachment(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(side_effect=[
                _mock_response(200, {"id": "inst-1", "lifecycleState": "RUNNING", "compartmentId": "comp-1", "displayName": "test"}),
                _mock_response(200, []),
            ])
            result = await client.get_instance("inst-1")
            assert result.status == VPSStatus.RUNNING
            assert result.public_ip == ""

    @pytest.mark.asyncio
    async def test_get_instance_running_vnic_without_id(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(side_effect=[
                _mock_response(200, {"id": "inst-1", "lifecycleState": "RUNNING", "compartmentId": "comp-1", "displayName": "test"}),
                _mock_response(200, [{"vnicId": ""}]),
            ])
            result = await client.get_instance("inst-1")
            assert result.status == VPSStatus.RUNNING
            assert result.public_ip == ""

    @pytest.mark.asyncio
    async def test_get_instance_stopped(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(return_value=_mock_response(200, {
                "id": "inst-1", "lifecycleState": "STOPPED", "displayName": "test",
            }))
            result = await client.get_instance("inst-1")
            assert result.status == VPSStatus.STOPPED
            assert result.public_ip == ""

    @pytest.mark.asyncio
    async def test_get_instance_terminated(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(return_value=_mock_response(200, {
                "id": "inst-1", "lifecycleState": "TERMINATED", "displayName": "test",
            }))
            result = await client.get_instance("inst-1")
            assert result.status == VPSStatus.TERMINATED

    @pytest.mark.asyncio
    async def test_get_instance_terminating(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(return_value=_mock_response(200, {
                "id": "inst-1", "lifecycleState": "TERMINATING", "displayName": "test",
            }))
            result = await client.get_instance("inst-1")
            assert result.status == VPSStatus.TERMINATED

    @pytest.mark.asyncio
    async def test_get_instance_unknown_state(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(return_value=_mock_response(200, {
                "id": "inst-1", "lifecycleState": "STARTING", "displayName": "test",
            }))
            result = await client.get_instance("inst-1")
            assert result.status == VPSStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_get_instance_status_running(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(return_value=_mock_response(200, {
                "id": "inst-1", "lifecycleState": "RUNNING", "compartmentId": "comp-1", "displayName": "test",
            }))
            status = await client.get_instance_status("inst-1")
            assert status == VPSStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_instance(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.post = mock.AsyncMock(return_value=_mock_response(200, {}))
            status = await client.start_instance("inst-1")
            assert status == VPSStatus.RUNNING
            instance_obj.post.assert_called_once()
            assert "actions/start" in str(instance_obj.post.call_args)

    @pytest.mark.asyncio
    async def test_stop_instance(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.post = mock.AsyncMock(return_value=_mock_response(200, {}))
            status = await client.stop_instance("inst-1")
            assert status == VPSStatus.STOPPED
            instance_obj.post.assert_called_once()
            assert "actions/stop" in str(instance_obj.post.call_args)

    @pytest.mark.asyncio
    async def test_terminate_instance(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.post = mock.AsyncMock(return_value=_mock_response(200, {}))
            status = await client.terminate_instance("inst-1")
            assert status == VPSStatus.TERMINATED
            instance_obj.post.assert_called_once()
            assert "actions/terminate" in str(instance_obj.post.call_args)

    @pytest.mark.asyncio
    async def test_get_or_create_subnet_creates(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(side_effect=[
                _mock_response(200, {"data": [{"id": "vcn-1"}]}),
                _mock_response(200, {"data": []}),
                _mock_response(200, {"data": [{"id": "rt-1"}]}),
            ])
            instance_obj.post = mock.AsyncMock(return_value=_mock_response(200, {"id": "subnet-1"}))
            subnet_id = await client._get_or_create_subnet("comp-1")
            assert subnet_id == "subnet-1"
            instance_obj.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_or_create_subnet_exists(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(side_effect=[
                _mock_response(200, {"data": [{"id": "vcn-1"}]}),
                _mock_response(200, {"data": [{"id": "subnet-1"}]}),
            ])
            subnet_id = await client._get_or_create_subnet("comp-1")
            assert subnet_id == "subnet-1"
            assert instance_obj.get.call_count == 2

    @pytest.mark.asyncio
    async def test_get_or_create_subnet_response_as_list(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(side_effect=[
                _mock_response(200, [{"id": "vcn-1"}]),
                _mock_response(200, [{"id": "subnet-1"}]),
            ])
            subnet_id = await client._get_or_create_subnet("comp-1")
            assert subnet_id == "subnet-1"

    @pytest.mark.asyncio
    async def test_get_or_create_vcn_creates(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(return_value=_mock_response(200, {"data": []}))
            instance_obj.post = mock.AsyncMock(return_value=_mock_response(200, {"id": "vcn-1"}))
            vcn_id = await client._get_or_create_vcn("comp-1")
            assert vcn_id == "vcn-1"
            instance_obj.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_or_create_vcn_exists(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(return_value=_mock_response(200, {"data": [{"id": "vcn-1"}]}))
            vcn_id = await client._get_or_create_vcn("comp-1")
            assert vcn_id == "vcn-1"

    @pytest.mark.asyncio
    async def test_get_or_create_vcn_response_as_list(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(return_value=_mock_response(200, [{"id": "vcn-1"}]))
            vcn_id = await client._get_or_create_vcn("comp-1")
            assert vcn_id == "vcn-1"

    @pytest.mark.asyncio
    async def test_get_or_create_nsg_creates_with_rules(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(side_effect=[
                _mock_response(200, {"data": [{"id": "vcn-1"}]}),
                _mock_response(200, {"data": []}),
            ])
            instance_obj.post = mock.AsyncMock(side_effect=[
                _mock_response(200, {"id": "nsg-1"}),
                _mock_response(200, {}),
            ])
            nsg_id = await client._get_or_create_nsg("comp-1")
            assert nsg_id == "nsg-1"
            assert instance_obj.post.call_count == 2
            post_calls = instance_obj.post.call_args_list
            assert "networkSecurityGroups" in str(post_calls[0])
            assert "securityRules" in str(post_calls[1])

    @pytest.mark.asyncio
    async def test_get_or_create_nsg_freeping_exists(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(side_effect=[
                _mock_response(200, {"data": [{"id": "vcn-1"}]}),
                _mock_response(200, {"data": [{"id": "nsg-1", "displayName": "FreePing-NSG"}]}),
            ])
            nsg_id = await client._get_or_create_nsg("comp-1")
            assert nsg_id == "nsg-1"

    @pytest.mark.asyncio
    async def test_get_or_create_nsg_non_freeping_exists_creates(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(side_effect=[
                _mock_response(200, {"data": [{"id": "vcn-1"}]}),
                _mock_response(200, {"data": [
                    {"id": "nsg-other", "displayName": "Other-NSG"},
                ]}),
            ])
            instance_obj.post = mock.AsyncMock(side_effect=[
                _mock_response(200, {"id": "nsg-new"}),
                _mock_response(200, {}),
            ])
            nsg_id = await client._get_or_create_nsg("comp-1")
            assert nsg_id == "nsg-new"

    @pytest.mark.asyncio
    async def test_get_default_route_table_success(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(return_value=_mock_response(200, {
                "data": [{"id": "rt-1"}],
            }))
            rt_id = await client._get_default_route_table("comp-1", "vcn-1")
            assert rt_id == "rt-1"

    @pytest.mark.asyncio
    async def test_get_default_route_table_not_found(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(return_value=_mock_response(200, {
                "data": [],
            }))
            with pytest.raises(OciError, match="No default route table found"):
                await client._get_default_route_table("comp-1", "vcn-1")

    @pytest.mark.asyncio
    async def test_request_put(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.put = mock.AsyncMock(return_value=_mock_response(200, {"status": "updated"}))
            result = await client._request("PUT", "/test", {"key": "value"})
            assert result == {"status": "updated"}

    @pytest.mark.asyncio
    async def test_request_delete(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.delete = mock.AsyncMock(return_value=_mock_response(200, {"status": "deleted"}))
            result = await client._request("DELETE", "/test")
            assert result == {"status": "deleted"}

    @pytest.mark.asyncio
    async def test_request_unsupported_method(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with pytest.raises(OciError, match="Unsupported method: PATCH"):
            await client._request("PATCH", "/test")

    @pytest.mark.asyncio
    async def test_request_timeout(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(side_effect=httpx.TimeoutException("timed out"))
            with pytest.raises(OciError, match="Request timed out"):
                await client._request("GET", "/test")

    @pytest.mark.asyncio
    async def test_request_network_error(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(side_effect=httpx.RequestError("connection failed"))
            with pytest.raises(OciError, match="Network error"):
                await client._request("GET", "/test")

    @pytest.mark.asyncio
    async def test_request_http_error_400(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(return_value=_mock_response(400, {
                "message": "bad request", "code": "400",
            }))
            with pytest.raises(OciError, match="bad request") as exc:
                await client._request("GET", "/test")
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_request_http_error_401(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            instance_obj.get = mock.AsyncMock(return_value=_mock_response(401, {
                "message": "not authorized", "code": "401",
            }))
            with pytest.raises(AuthError):
                await client._request("GET", "/test")

    @pytest.mark.asyncio
    async def test_request_post_with_http_error_non_json(self, rsa_oci_credentials):
        client = OciClient(rsa_oci_credentials)
        with mock.patch("httpx.AsyncClient") as m:
            instance_obj = m.return_value.__aenter__.return_value
            err_resp = mock.MagicMock(spec=httpx.Response)
            err_resp.status_code = 500
            err_resp.text = "Internal Server Error"
            err_resp.json.return_value = "Internal Server Error"
            instance_obj.post = mock.AsyncMock(return_value=err_resp)
            with pytest.raises(OciError) as exc:
                await client._request("POST", "/test", {"key": "val"})
            assert exc.value.status_code == 500


class TestWireGuardKeyPairAdvanced:

    def test_generate_with_wg_tool(self):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                mock.MagicMock(stdout="priv_key_value\n"),
                mock.MagicMock(stdout="pub_key_value\n"),
            ]
            kp = WireGuardKeyPair.generate()
            assert kp.private_key == "priv_key_value"
            assert kp.public_key == "pub_key_value"

    def test_generate_fallback_on_called_process_error(self):
        with mock.patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "wg")):
            kp = WireGuardKeyPair.generate()
            assert len(kp.private_key) > 0
            assert len(kp.public_key) > 0
            assert kp.private_key != kp.public_key

    def test_generate_fallback_on_file_not_found(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            kp = WireGuardKeyPair.generate()
            assert len(kp.private_key) > 0
            assert len(kp.public_key) > 0

    def test_curve25519_public_import_error(self):
        orig_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "cryptography.hazmat.primitives.asymmetric.x25519":
                raise ImportError("No module named x25519")
            return orig_import(name, *args, **kwargs)

        with mock.patch.object(builtins, "__import__", side_effect=mock_import):
            with pytest.raises(RuntimeError, match="Cannot generate WireGuard keys"):
                WireGuardKeyPair._curve25519_public(b"a" * 32)
