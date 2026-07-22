"""Binary sensor platform for Zentraly thermostats.

Exposes the real boiler relay state (``output`` from getConfig) as a
``running`` binary sensor. Unlike ``climate.hvac_action`` (historically a
temperature-vs-setpoint heuristic), this reflects whether the burner is
actually firing, which is the correct signal to integrate for runtime/energy
estimates.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DEVICE_TYPE_THERMOSTAT, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Zentraly binary sensors."""
    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    devices = coordinator.data or []
    entities = [
        ZentralyBoilerBinarySensor(coordinator, device)
        for device in devices
        if device.get("device_type") == DEVICE_TYPE_THERMOSTAT
    ]
    async_add_entities(entities)


class ZentralyBoilerBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Real boiler relay/firing state for a Zentraly thermostat."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device: dict[str, Any],
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._device_serial = device["serial"]
        self._attr_unique_id = f"zentraly_{device['serial']}_firing"
        self._attr_name = "Boiler"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device["serial"])},
        }

    @property
    def _device_data(self) -> dict[str, Any] | None:
        if not self.coordinator.data:
            return None
        for device in self.coordinator.data:
            if device.get("serial") == self._device_serial:
                return device
        return None

    @property
    def is_on(self) -> bool | None:
        """Return True when the burner relay is firing."""
        if not (data := self._device_data):
            return None
        output = data.get("output")
        if output is None:
            return None
        return output >= 1

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not (data := self._device_data):
            return False
        return data.get("connected", False) and data.get("output") is not None
