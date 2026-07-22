"""Sensor platform for Zentraly thermostats — water temps and diagnostics."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DEVICE_TYPE_THERMOSTAT, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class ZentralySensorDescription(SensorEntityDescription):
    """Describes a Zentraly sensor with a value extractor."""

    value_fn: Callable[[dict[str, Any]], Any] = lambda d: None


SENSORS: tuple[ZentralySensorDescription, ...] = (
    ZentralySensorDescription(
        key="heating_water_temp",
        name="Heating water temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: d.get("heating_water_temp"),
    ),
    ZentralySensorDescription(
        key="dhw_temp",
        name="Domestic hot water temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: d.get("dhw_temp"),
    ),
    ZentralySensorDescription(
        key="rssi",
        name="WiFi signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("rssi"),
    ),
    ZentralySensorDescription(
        key="ssid",
        name="WiFi network",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("ssid"),
    ),
    ZentralySensorDescription(
        key="ip_address",
        name="IP address",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: (d.get("dates") or {}).get("ip"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Zentraly sensors."""
    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[SensorEntity] = []
    for device in coordinator.data or []:
        if device.get("device_type") != DEVICE_TYPE_THERMOSTAT:
            continue
        for description in SENSORS:
            entities.append(ZentralySensor(coordinator, device, description))
    async_add_entities(entities)


class ZentralySensor(CoordinatorEntity, SensorEntity):
    """A Zentraly diagnostic / water-temperature sensor."""

    _attr_has_entity_name = True
    entity_description: ZentralySensorDescription

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device: dict[str, Any],
        description: ZentralySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._device_serial = device["serial"]
        self._attr_unique_id = f"zentraly_{device['serial']}_{description.key}"
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
    def native_value(self) -> Any:
        if not (data := self._device_data):
            return None
        return self.entity_description.value_fn(data)

    @property
    def available(self) -> bool:
        if not (data := self._device_data):
            return False
        return data.get("connected", False)
