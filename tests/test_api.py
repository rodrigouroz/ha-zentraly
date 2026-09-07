"""Tests for the Zentraly API client."""
from __future__ import annotations

import importlib.util
import base64
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PATH = ROOT / "custom_components" / "zentraly"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


custom_components = types.ModuleType("custom_components")
custom_components.__path__ = [str(ROOT / "custom_components")]
sys.modules.setdefault("custom_components", custom_components)

zentraly_package = types.ModuleType("custom_components.zentraly")
zentraly_package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("custom_components.zentraly", zentraly_package)

aiohttp = types.ModuleType("aiohttp")
aiohttp.ClientSession = object
sys.modules.setdefault("aiohttp", aiohttp)

homeassistant = types.ModuleType("homeassistant")
homeassistant.__path__ = []
sys.modules.setdefault("homeassistant", homeassistant)

homeassistant_const = types.ModuleType("homeassistant.const")
homeassistant_const.Platform = types.SimpleNamespace(CLIMATE="climate")
sys.modules.setdefault("homeassistant.const", homeassistant_const)

_load_module("custom_components.zentraly.const", PACKAGE_PATH / "const.py")
api_module = _load_module("custom_components.zentraly.api", PACKAGE_PATH / "api.py")

ZentralyApi = api_module.ZentralyApi
ZentralyApiError = api_module.ZentralyApiError
const_module = sys.modules["custom_components.zentraly.const"]


class FakeResponse:
    """Minimal aiohttp response context manager."""

    def __init__(self, status: int, data: dict) -> None:
        self.status = status
        self._data = data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def json(self) -> dict:
        return self._data


class FakeSession:
    """Record requests and return queued responses."""

    def __init__(self, *responses: FakeResponse) -> None:
        self.responses = list(responses)
        self.requests: list[dict] = []

    def post(self, url: str, *, headers: dict, json: dict) -> FakeResponse:
        self.requests.append({"url": url, "headers": headers, "json": json})
        return self.responses.pop(0)

    def get(self, url: str, *, headers: dict) -> FakeResponse:
        self.requests.append({"url": url, "headers": headers})
        return self.responses.pop(0)


def decode_firebase_header(header: str) -> dict:
    decryptor = Cipher(
        algorithms.AES(bytes.fromhex(const_module.API_FIREBASE_KEY)),
        modes.CBC(bytes.fromhex(const_module.API_FIREBASE_IV)),
    ).decryptor()
    padded = decryptor.update(base64.b64decode(header)) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    envelope = json.loads(unpadder.update(padded) + unpadder.finalize())
    return json.loads(base64.b64decode(envelope["data"]))


class ZentralyApiTests(unittest.IsolatedAsyncioTestCase):
    """Verify the reverse-engineered API contract."""

    def test_firebase_header_matches_current_encrypted_contract(self) -> None:
        api = ZentralyApi()
        api._device_guid = "TEST-GUID"

        with (
            patch.object(api_module.time, "time", return_value=1_750_000_000.0),
            patch.object(api_module.secrets, "randbelow", side_effect=[12345, 6790]),
        ):
            header = api._generate_firebase_header()

        decryptor = Cipher(
            algorithms.AES(bytes.fromhex(const_module.API_FIREBASE_KEY)),
            modes.CBC(bytes.fromhex(const_module.API_FIREBASE_IV)),
        ).decryptor()
        padded_plaintext = decryptor.update(base64.b64decode(header)) + decryptor.finalize()
        unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
        plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
        encrypted_envelope = json.loads(plaintext)
        firebase_data = json.loads(base64.b64decode(encrypted_envelope["data"]))

        self.assertEqual(1, encrypted_envelope["contador"])
        self.assertEqual(12345, encrypted_envelope["random"])
        self.assertEqual(1_749_999_996_790, encrypted_envelope["timestamp"])
        self.assertEqual("TEST-GUID", firebase_data["ivstrUserGuid"])
        self.assertEqual("TEST-GUID", firebase_data["ivstrUserFBToken"])
        self.assertEqual("7.1.6", firebase_data["ivstrUserZtVersion"])
        self.assertEqual("AR", firebase_data["ivstrUserCountry"])

    async def test_login_reuses_installation_identity_after_client_recreation(self) -> None:
        device_guid = "B32032E5-03E4-42C8-9ED4-062D81357C53"
        for _ in range(2):
            session = FakeSession(FakeResponse(200, {
                "numStatus": 0,
                "ioData": {"ivstrToken": "test-session-token", "ioUser": {"ioDCModel": {"ivlngUser": 1}}},
            }))
            api = ZentralyApi(
                email="test@example.invalid", password="test-password",
                session=session, device_guid=device_guid,
            )
            await api.authenticate()
            request = session.requests[0]
            self.assertEqual("https://ztprdrestservicesv2.azurewebsites.net/Login", request["url"])
            fields = decode_firebase_header(request["headers"]["Firebase"])
            self.assertEqual(device_guid, fields["ivstrUserGuid"])
            self.assertEqual(device_guid, fields["ivstrUserFBToken"])
            self.assertEqual(
                const_module.CLIENT_MOBILE_TRADE, fields["ivstrUserMobileTrade"]
            )
            self.assertEqual(
                const_module.CLIENT_MOBILE_MODEL, fields["ivstrUserMobileModel"]
            )

    def test_error_detail_keeps_diagnosis_and_drops_the_session_token(self) -> None:
        detail = api_module._error_detail({
            "numStatus": 1,
            "ioData": {
                "ivstrToken": "session-token-that-must-not-leak",
                "ivstrMsg": "Error en autentificacion de usuario.",
                "ivstrStack": "SqlException: conflicted with the CHECK constraint\r\n"
                              "\"CK_UserFBTokens_strUserFBToken_NoHaIn\".",
            },
        })

        self.assertIn("numStatus=1", detail)
        self.assertIn("Error en autentificacion de usuario.", detail)
        self.assertIn("CK_UserFBTokens_strUserFBToken_NoHaIn", detail)
        self.assertNotIn("session-token-that-must-not-leak", detail)

    def test_error_detail_handles_a_non_dict_payload(self) -> None:
        self.assertEqual("unexpected response", api_module._error_detail("boom"))

    def test_firebase_counter_increments_per_request(self) -> None:
        api = ZentralyApi()

        with patch.object(api_module.secrets, "randbelow", return_value=0):
            first_header = api._generate_firebase_header()
            second_header = api._generate_firebase_header()

        self.assertNotEqual(first_header, second_header)
        self.assertEqual(2, api._request_counter)

    async def test_send_iot_command_uses_app_action_envelope(self) -> None:
        session = FakeSession(
            FakeResponse(200, {"numStatus": 0, "ioData": '{"status":200}'})
        )
        api = ZentralyApi(token="test-token", session=session)

        result = await api.send_iot_command(
            "serial-123",
            "setConfig",
            {"ids": [{"targetTemp": 2150}]},
        )

        self.assertEqual({"status": 200}, result)
        self.assertEqual(1, len(session.requests))
        request = session.requests[0]
        self.assertEqual(
            "https://ztprdrestservicesv2.azurewebsites.net/app/Action",
            request["url"],
        )
        self.assertEqual(
            {
                "eDcOper": 28,
                "vioBody": {
                    "deviceId": "serial-123",
                    "timeOut": 15000,
                    "data": {
                        "cmd": "setConfig",
                        "rid": 0,
                        "ids": [{"targetTemp": 2150}],
                    },
                },
            },
            request["json"],
        )

    async def test_send_iot_command_reports_http_errors(self) -> None:
        session = FakeSession(FakeResponse(405, {}))
        api = ZentralyApi(token="test-token", session=session)

        with self.assertRaisesRegex(ZentralyApiError, "Command failed: 405"):
            await api.send_iot_command("serial-123", "getConfig", {"ids": []})

    async def test_send_iot_command_reports_device_errors(self) -> None:
        session = FakeSession(
            FakeResponse(200, {"numStatus": 0, "ioData": '{"status":404}'})
        )
        api = ZentralyApi(token="test-token", session=session)

        with self.assertRaisesRegex(ZentralyApiError, "device status 404"):
            await api.send_iot_command("serial-123", "getConfig", {"ids": []})

    async def test_send_iot_command_increments_device_request_id(self) -> None:
        session = FakeSession(
            FakeResponse(200, {"numStatus": 0, "ioData": '{"status":200}'}),
            FakeResponse(200, {"numStatus": 0, "ioData": '{"status":200}'}),
        )
        api = ZentralyApi(token="test-token", session=session)

        await api.send_iot_command("serial-123", "getConfig", {"ids": []})
        await api.send_iot_command("serial-123", "getConfig", {"ids": []})

        self.assertEqual(
            [0, 1],
            [request["json"]["vioBody"]["data"]["rid"] for request in session.requests],
        )

    async def test_get_devices_exposes_parent_iot_hub_device_id(self) -> None:
        session = FakeSession(
            FakeResponse(
                200,
                {
                    "numStatus": 0,
                    "ioData": {
                        "ioUser": {
                            "coUbications": [
                                {
                                    "ioDCModel": {"ivstrUbicationName": "Casa"},
                                    "coZones": [
                                        {
                                            "ioDCModel": {"ivstrZoneName": "PA"},
                                            "coDevices": [
                                                {
                                                    "ioDCModel": {
                                                        "ivstrDeviceSerial": "thermostat-123",
                                                        "ivstrParentDeviceSerial": "iot-hub-456",
                                                    },
                                                    "ioSubTypeObj": {"ioDCModel": {}},
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ]
                        }
                    },
                },
            )
        )
        api = ZentralyApi(token="test-token", session=session)
        api._user_id = 42

        devices = await api.get_devices()

        self.assertEqual("thermostat-123", devices[0]["serial"])
        self.assertEqual("iot-hub-456", devices[0]["iot_hub_device_id"])

    async def test_user_data_keeps_existing_app_contract(self) -> None:
        session = FakeSession(FakeResponse(200, {"numStatus": 0, "ioData": {}}))
        api = ZentralyApi(token="test-token", session=session)
        api._user_id = 42

        await api.get_user_data()

        request = session.requests[0]
        self.assertEqual(
            "https://ztprdrestservicesv2.azurewebsites.net/App",
            request["url"],
        )
        self.assertEqual(
            {
                "coUbications": [],
                "eDcOper": 1,
                "ioDCModel": {"ivlngUser": 42},
            },
            request["json"],
        )


if __name__ == "__main__":
    unittest.main()
