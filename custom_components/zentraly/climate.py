"""Climate platform for Zentraly thermostats."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_EMAIL,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .api import ZentralyApi
from .const import (
    DEVICE_TYPES_THERMOSTAT,
    DOMAIN,
    HVAC_MODE_MAP,
    HVAC_MODE_REVERSE,
    SCAN_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Zentraly climate entities."""
    api: ZentralyApi = hass.data[DOMAIN][entry.entry_id]["api"]
    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    devices = coordinator.data or []

    entities = [
        ZentralyThermostat(coordinator, api, device)
        for device in devices
        if device.get("device_type") in DEVICE_TYPES_THERMOSTAT
    ]

    async_add_entities(entities)


class ZentralyThermostat(CoordinatorEntity, ClimateEntity):
    """Zentraly thermostat entity."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_min_temp = 5
    _attr_max_temp = 30
    _attr_target_temperature_step = 0.5

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        api: ZentralyApi,
        device: dict[str, Any],
    ) -> None:
        """Initialize the thermostat."""
        super().__init__(coordinator)
        self._api = api
        self._device_serial = device["serial"]
        self._attr_unique_id = f"zentraly_{device['serial']}"
        self._attr_name = device.get("name", "Thermostat")

        # Device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device["serial"])},
            "name": device.get("name", "Zentraly Thermostat"),
            "manufacturer": "Zentraly (FV Group)",
            "model": "WiFi Thermostat",
            "sw_version": device.get("firmware"),
        }

    @property
    def _device_data(self) -> dict[str, Any] | None:
        """Get current device data from coordinator."""
        if not self.coordinator.data:
            return None
        for device in self.coordinator.data:
            if device.get("serial") == self._device_serial:
                return device
        return None

    @property
    def current_temperature(self) -> float | None:
        """Return current temperature."""
        if data := self._device_data:
            return data.get("current_temperature")
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature."""
        if data := self._device_data:
            return data.get("target_temperature")
        return None

    @property
    def current_humidity(self) -> int | None:
        """Return current humidity."""
        if data := self._device_data:
            return data.get("humidity")
        return None

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        if data := self._device_data:
            mode = data.get("mode", 1)
            mode_str = HVAC_MODE_MAP.get(mode, "heat")
            if mode_str == "heat":
                return HVACMode.HEAT
            elif mode_str == "off":
                return HVACMode.OFF
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return current HVAC action."""
        if data := self._device_data:
            if not data.get("is_on", False):
                return HVACAction.OFF

            current = data.get("current_temperature", 0)
            target = data.get("target_temperature", 0)

            if current < target:
                return HVACAction.HEATING
            else:
                return HVACAction.IDLE
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if data := self._device_data:
            return data.get("connected", False)
        return False

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        await self._api.set_target_temperature(self._device_serial, temperature)
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        if hvac_mode == HVACMode.HEAT:
            await self._api.turn_on(self._device_serial)
        elif hvac_mode == HVACMode.OFF:
            await self._api.turn_off(self._device_serial)

        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn the thermostat on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Turn the thermostat off."""
        await self.async_set_hvac_mode(HVACMode.OFF)
