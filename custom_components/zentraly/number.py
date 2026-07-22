"""Number platform for Zentraly thermostats — calibration offset and away temp."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .api import ZentralyApi
from .const import (
    AWAY_TEMP_MAX,
    AWAY_TEMP_MIN,
    AWAY_TEMP_STEP,
    DEVICE_TYPE_THERMOSTAT,
    DOMAIN,
    OFFSET_MAX,
    OFFSET_MIN,
    OFFSET_STEP,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Zentraly numbers."""
    api: ZentralyApi = hass.data[DOMAIN][entry.entry_id]["api"]
    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[NumberEntity] = []
    for device in coordinator.data or []:
        if device.get("device_type") != DEVICE_TYPE_THERMOSTAT:
            continue
        entities.append(ZentralyOffsetNumber(coordinator, api, device))
        entities.append(ZentralyAwayTempNumber(coordinator, api, device))
    async_add_entities(entities)


class _ZentralyNumberBase(CoordinatorEntity, NumberEntity):
    """Common plumbing for Zentraly number entities."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX
    _data_key: str = ""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        api: ZentralyApi,
        device: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._api = api
        self._device_serial = device["serial"]
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
    def native_value(self) -> float | None:
        if not (data := self._device_data):
            return None
        return data.get(self._data_key)

    @property
    def available(self) -> bool:
        if not (data := self._device_data):
            return False
        return data.get("connected", False) and data.get(self._data_key) is not None


class ZentralyOffsetNumber(_ZentralyNumberBase):
    """Temperature calibration offset."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:thermometer-plus"
    _attr_native_min_value = OFFSET_MIN
    _attr_native_max_value = OFFSET_MAX
    _attr_native_step = OFFSET_STEP
    _data_key = "offset"

    def __init__(self, coordinator, api, device) -> None:
        super().__init__(coordinator, api, device)
        self._attr_unique_id = f"zentraly_{device['serial']}_offset"
        self._attr_name = "Temperature calibration"

    async def async_set_native_value(self, value: float) -> None:
        await self._api.set_offset(self._device_serial, value)
        await self.coordinator.async_request_refresh()


class ZentralyAwayTempNumber(_ZentralyNumberBase):
    """Away temperature (tAway)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:home-export-outline"
    _attr_native_min_value = AWAY_TEMP_MIN
    _attr_native_max_value = AWAY_TEMP_MAX
    _attr_native_step = AWAY_TEMP_STEP
    _data_key = "away_temperature"

    def __init__(self, coordinator, api, device) -> None:
        super().__init__(coordinator, api, device)
        self._attr_unique_id = f"zentraly_{device['serial']}_away_temp"
        self._attr_name = "Away temperature"

    async def async_set_native_value(self, value: float) -> None:
        await self._api.set_away_temperature(self._device_serial, value)
        await self.coordinator.async_request_refresh()
