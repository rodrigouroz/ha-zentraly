"""Zentraly API Client."""
from __future__ import annotations

import base64
import json
import logging
import uuid
from typing import Any

import aiohttp

from .const import (
    API_BASE_URL,
    API_LOGIN_ENDPOINT,
    API_APP_ENDPOINT,
    API_IOT_COMMAND_ENDPOINT,
    AUTH_PREFIX_LOGIN,
    AUTH_PREFIX_TOKEN,
    CMD_GET_CONFIG,
    CMD_SET_CONFIG,
    CONFIG_IDS,
    TEMP_SCALE,
)

_LOGGER = logging.getLogger(__name__)


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
    ) -> None:
        """Initialize the API client."""
        self._email = email
        self._password = password
        self._token = token
        self._session = session
        self._user_id: int | None = None
        self._close_session = False
        self._device_guid = str(uuid.uuid4()).upper()

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
            "ivstrUserFBToken": "ha_integration_dummy_token",
            "ivstrUserGuid": self._device_guid,
            "ivstrUserZtVersion": "7.0.3",
            "ivnroUserMobileOS": 3,  # 3 for "other" / integration
            "ivstrUserMobileTrade": "HomeAssistant",
            "ivstrUserMobileModel": "Integration",
            "ivstrUserMobileOSVersion": "1.0",
            "ivstrUserLanguage": "es"
        }
        return base64.b64encode(json.dumps(firebase_data).encode()).decode()

    def _get_headers(self, auth_type: str = "token") -> dict[str, str]:
        """Get request headers."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "zentralyRN/420",
            "firebase": self._generate_firebase_header(),
        }

        if auth_type == "login":
            headers["Authorization"] = f"{AUTH_PREFIX_LOGIN}{self._email}:{self._password}"
        elif auth_type == "token" and self._token:
            headers["Authorization"] = f"{AUTH_PREFIX_TOKEN}{self._token}"

        return headers

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
                raise ZentralyAuthError(f"Authentication failed: {data}")

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
                raise ZentralyApiError(f"API error: {data}")

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

        payload = {
            "deviceId": device_serial,
            "timeOut": timeout,
            "data": {
                "cmd": command,
                "rid": 0,
                **data,
            }
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
                raise ZentralyApiError(f"Command failed: {result}")

            # Parse the inner JSON response
            io_data = result.get("ioData", "{}")
            if isinstance(io_data, str):
                io_data = json.loads(io_data)

            return io_data

    async def get_device_config(self, device_serial: str) -> dict[str, Any]:
        """Get device configuration."""
        return await self.send_iot_command(
            device_serial,
            CMD_GET_CONFIG,
            {"ids": CONFIG_IDS}
        )

    async def get_live_state(self, device_serial: str) -> dict[str, Any]:
        """Return the live device config flattened to a single dict.

        ``getConfig`` returns ``ioData.ids`` as a list of single-key dicts,
        e.g. ``[{"targetTemp": 1801}, {"output": 0}, ...]``. ``output`` is the
        real relay/burner state (0 = idle, >=1 = firing) read directly from the
        device, rather than inferred from temperature vs. setpoint.
        """
        raw = await self.get_device_config(device_serial)
        flat: dict[str, Any] = {}
        ids = raw.get("ids", []) if isinstance(raw, dict) else []
        for item in ids:
            if isinstance(item, dict):
                flat.update(item)
        return flat

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
