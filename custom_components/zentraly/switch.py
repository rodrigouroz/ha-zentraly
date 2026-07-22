"""Switch platform for Zentraly thermostats — child lock."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .api import ZentralyApi
from .const import DEVICE_TYPE_THERMOSTAT, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Zentraly switches."""
    api: ZentralyApi = hass.data[DOMAIN][entry.entry_id]["api"]
    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    devices = coordinator.data or []
    entities = [
        ZentralyLockSwitch(coordinator, api, device)
        for device in devices
        if device.get("device_type") == DEVICE_TYPE_THERMOSTAT
    ]
    async_add_entities(entities)


class ZentralyLockSwitch(CoordinatorEntity, SwitchEntity):
    """Child lock for a Zentraly thermostat."""

    _attr_has_entity_name = True
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:lock"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        api: ZentralyApi,
        device: dict[str, Any],
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._api = api
        self._device_serial = device["serial"]
        self._attr_unique_id = f"zentraly_{device['serial']}_lock"
        self._attr_name = "Child lock"
        self._attr_device_info = {"identifiers": {(DOMAIN, device["serial"])}}

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
        """Return True when the child lock is engaged."""
        if not (data := self._device_data):
            return None
        return data.get("locked")

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not (data := self._device_data):
            return False
        return data.get("connected", False) and data.get("locked") is not None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Engage the child lock."""
        await self._api.set_lock(self._device_serial, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Release the child lock."""
        await self._api.set_lock(self._device_serial, False)
        await self.coordinator.async_request_refresh()
