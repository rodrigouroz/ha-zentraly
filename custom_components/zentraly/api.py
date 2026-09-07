"""Zentraly API Client."""
from __future__ import annotations

import base64
import json
import logging
import secrets
import time
import uuid
from typing import Any

import aiohttp
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .const import (
    API_BASE_URL,
    API_FIREBASE_IV,
    API_FIREBASE_KEY,
    API_LOGIN_ENDPOINT,
    API_APP_ENDPOINT,
    API_IOT_COMMAND_ENDPOINT,
    AUTH_PREFIX_LOGIN,
    AUTH_PREFIX_TOKEN,
    CLIENT_MOBILE_MODEL,
    CLIENT_MOBILE_OS_VERSION,
    CLIENT_MOBILE_TRADE,
    CMD_GET_CONFIG,
    CMD_SET_CONFIG,
    CONFIG_IDS,
    DC_OPER_RUN_IOT,
    TEMP_SCALE,
    ZENTRALY_APP_VERSION,
)

_LOGGER = logging.getLogger(__name__)

# Enough of the server stack trace to name the failing constraint or exception.
_STACK_EXCERPT_LENGTH = 300


def _error_detail(payload: Any) -> str:
    """Summarize an API error without echoing the whole response body.

    Responses carry the session token, the user ID and device serials, and these
    messages end up in the Home Assistant log, which users routinely paste into
    bug reports. Keep the status, the server message and a short stack excerpt.
    """
    if not isinstance(payload, dict):
        return "unexpected response"

    io_data = payload.get("ioData")
    if not isinstance(io_data, dict):
        io_data = {}

    parts = [f"numStatus={payload.get('numStatus')}"]
    if message := io_data.get("ivstrMsg"):
        parts.append(str(message))
    if stack := io_data.get("ivstrStack"):
        parts.append(" ".join(str(stack).split())[:_STACK_EXCERPT_LENGTH])
    return " | ".join(parts)


class ZentralyApiError(Exception):
    """Base exception for Zentraly API errors."""


class ZentralyAuthError(ZentralyApiError):
    """Authentication error."""


class ZentralyApi:
    """Zentraly API client."""

    def __init__(
        self,
        email: str | None = None,
        password: str | None = None,
        token: str | None = None,
        session: aiohttp.ClientSession | None = None,
        device_guid: str | None = None,
    ) -> None:
        """Initialize the API client."""
        self._email = email
        self._password = password
        self._token = token
        self._session = session
        self._user_id: int | None = None
        self._close_session = False
        self._device_guid = device_guid or str(uuid.uuid4()).upper()
        self._request_counter = 0
        self._command_rid = 0

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._close_session = True
        return self._session

    async def close(self) -> None:
        """Close the session if we created it."""
        if self._close_session and self._session:
            await self._session.close()

    def _generate_firebase_header(self) -> str:
        """Generate Firebase header for API requests."""
        firebase_data = {
            # The app falls back to its device ID when Firebase is unavailable.
            "ivstrUserFBToken": self._device_guid,
            "ivstrUserGuid": self._device_guid,
            "ivstrUserZtVersion": ZENTRALY_APP_VERSION,
            "ivnroUserMobileOS": 1,
            "ivstrUserMobileTrade": CLIENT_MOBILE_TRADE,
            "ivstrUserMobileModel": CLIENT_MOBILE_MODEL,
            "ivstrUserMobileOSVersion": CLIENT_MOBILE_OS_VERSION,
            "ivstrUserLanguage": "es",
            "ivstrUserCountry": "AR",
        }
        encoded_data = base64.b64encode(
            json.dumps(firebase_data, separators=(",", ":")).encode()
        ).decode()

        self._request_counter += 1
        request_data = {
            "contador": self._request_counter,
            "random": secrets.randbelow(100000),
            "data": encoded_data,
            "timestamp": int(time.time() * 1000) + secrets.randbelow(20001) - 10000,
        }

        key = bytes.fromhex(API_FIREBASE_KEY)
        iv = bytes.fromhex(API_FIREBASE_IV)
        padder = padding.PKCS7(algorithms.AES.block_size).padder()
        plaintext = json.dumps(request_data, separators=(",", ":")).encode()
        padded_plaintext = padder.update(plaintext) + padder.finalize()
        encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
        ciphertext = encryptor.update(padded_plaintext) + encryptor.finalize()
        return base64.b64encode(ciphertext).decode()

    def _get_headers(self, auth_type: str = "token") -> dict[str, str]:
        """Get request headers."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "zentralyRN/420",
            "Firebase": self._generate_firebase_header(),
        }

        if auth_type == "login":
            headers["Authorization"] = f"{AUTH_PREFIX_LOGIN}{self._email}:{self._password}"
        elif auth_type == "token" and self._token:
            headers["Authorization"] = f"{AUTH_PREFIX_TOKEN}{self._token}"

        return headers

    def _get_next_command_rid(self) -> int:
        """Return the next device command request ID used by the official app."""
        rid = self._command_rid
        self._command_rid = (rid + 1) % 10000
        return rid

    async def authenticate(self) -> dict[str, Any]:
        """Authenticate and get token."""
        session = await self._get_session()

        async with session.get(
            f"{API_BASE_URL}{API_LOGIN_ENDPOINT}",
            headers=self._get_headers("login"),
        ) as response:
            if response.status != 200:
                raise ZentralyAuthError(f"Authentication failed: {response.status}")

            data = await response.json()

            if data.get("numStatus") != 0:
                raise ZentralyAuthError(f"Authentication failed: {_error_detail(data)}")

            io_data = data.get("ioData", {})
            self._token = io_data.get("ivstrToken")
            self._user_id = io_data.get("ioUser", {}).get("ioDCModel", {}).get("ivlngUser")

            if not self._token:
                raise ZentralyAuthError("No token received")

            return data

    async def get_user_data(self) -> dict[str, Any]:
        """Get all user data including devices."""
        if not self._token:
            await self.authenticate()

        session = await self._get_session()

        payload = {
            "coUbications": [],
            "eDcOper": 1,
            "ioDCModel": {
                "ivlngUser": self._user_id
            }
        }

        async with session.post(
            f"{API_BASE_URL}{API_APP_ENDPOINT}",
            headers=self._get_headers("token"),
            json=payload,
        ) as response:
            if response.status != 200:
                raise ZentralyApiError(f"API error: {response.status}")

            data = await response.json()

            if data.get("numStatus") != 0:
                raise ZentralyApiError(f"API error: {_error_detail(data)}")

            return data

    async def get_devices(self) -> list[dict[str, Any]]:
        """Get list of thermostat devices."""
        data = await self.get_user_data()

        devices = []
        io_data = data.get("ioData", {})
        io_user = io_data.get("ioUser", {})
        ubications = io_user.get("coUbications", [])

        for ubication in ubications:
            ubication_name = ubication.get("ioDCModel", {}).get("ivstrUbicationName", "")
            zones = ubication.get("coZones", [])

            for zone in zones:
                zone_name = zone.get("ioDCModel", {}).get("ivstrZoneName", "")
                zone_devices = zone.get("coDevices", [])

                for device in zone_devices:
                    device_model = device.get("ioDCModel", {})
                    sub_type = device.get("ioSubTypeObj", {}).get("ioDCModel", {})

                    devices.append({
                        "serial": device_model.get("ivstrDeviceSerial"),
                        "iot_hub_device_id": device_model.get(
                            "ivstrParentDeviceSerial"
                        ),
                        "name": device_model.get("ivstrDeviceName"),
                        "mac": device_model.get("ivstrDeviceMac"),
                        "connected": device_model.get("ivblnDeviceConnected", False),
                        "firmware": device_model.get("ivstrDeviceFWVersion"),
                        "device_type": device_model.get("ivnroDeviceType"),
                        "ubication": ubication_name,
                        "zone": zone_name,
                        "user_id": device_model.get("ivlngUser"),
                        "ubication_id": device_model.get("ivnumUbication"),
                        "zone_id": device_model.get("ivnumZone"),
                        "device_id": device_model.get("ivnumDevice"),
                        "endpoint_id": device_model.get("ivnumEndPoint"),
                        # Thermostat specific data
                        "current_temperature": sub_type.get("ivnumDeviceTemperature", 0) / TEMP_SCALE,
                        "target_temperature": sub_type.get("ivnumDeviceTargetTemperature", 0) / TEMP_SCALE,
                        "humidity": sub_type.get("ivnumDeviceHumedity", 0),
                        "mode": sub_type.get("ivnroDeviceMode", 1),
                        "is_on": sub_type.get("ivblnDeviceOn", False),
                        "is_locked": sub_type.get("ivblnDeviceLockMode", False),
                    })

        return devices

    async def send_iot_command(
        self,
        device_serial: str,
        command: str,
        data: dict[str, Any],
        timeout: int = 15000,
    ) -> dict[str, Any]:
        """Send IoT command to device."""
        if not self._token:
            await self.authenticate()

        session = await self._get_session()

        command_payload = {
            "deviceId": device_serial,
            "timeOut": timeout,
            "data": {
                "cmd": command,
                "rid": self._get_next_command_rid(),
                **data,
            }
        }
        payload = {
            "eDcOper": DC_OPER_RUN_IOT,
            "vioBody": command_payload,
        }

        async with session.post(
            f"{API_BASE_URL}{API_IOT_COMMAND_ENDPOINT}",
            headers=self._get_headers("token"),
            json=payload,
        ) as response:
            if response.status != 200:
                raise ZentralyApiError(f"Command failed: {response.status}")

            result = await response.json()

            if result.get("numStatus") != 0:
                raise ZentralyApiError(f"Command failed: {_error_detail(result)}")

            # Parse the inner JSON response
            io_data = result.get("ioData", "{}")
            if isinstance(io_data, str):
                io_data = json.loads(io_data)

            device_status = io_data.get("status") if isinstance(io_data, dict) else None
            if device_status != 200:
                raise ZentralyApiError(
                    f"Command failed: device status {device_status}"
                )

            return io_data

    async def get_device_config(self, device_serial: str) -> dict[str, Any]:
        """Get device configuration."""
        return await self.send_iot_command(
            device_serial,
            CMD_GET_CONFIG,
            {"ids": CONFIG_IDS}
        )

    async def set_target_temperature(self, device_serial: str, temperature: float) -> dict[str, Any]:
        """Set target temperature."""
        temp_value = int(temperature * TEMP_SCALE)
        return await self.send_iot_command(
            device_serial,
            CMD_SET_CONFIG,
            {"ids": [{"targetTemp": temp_value}]}
        )

    async def set_hvac_mode(self, device_serial: str, mode: int) -> dict[str, Any]:
        """Set HVAC mode."""
        return await self.send_iot_command(
            device_serial,
            CMD_SET_CONFIG,
            {"ids": [{"thermostatMode": mode}]}
        )

    async def turn_on(self, device_serial: str) -> dict[str, Any]:
        """Turn thermostat on (heat mode)."""
        return await self.set_hvac_mode(device_serial, 1)

    async def turn_off(self, device_serial: str) -> dict[str, Any]:
        """Turn thermostat off."""
        return await self.set_hvac_mode(device_serial, 4)

    @property
    def token(self) -> str | None:
        """Get current token."""
        return self._token

    @property
    def user_id(self) -> int | None:
        """Get user ID."""
        return self._user_id
