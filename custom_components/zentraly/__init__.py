"""Zentraly Thermostat integration for Home Assistant."""
from __future__ import annotations

import logging
from datetime import time as dt_time, timedelta
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import aiohttp_client, config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ZentralyApi, ZentralyApiError
from .const import (
    ATTR_DAYS,
    ATTR_ENTITY_ID,
    ATTR_SCHEDULE,
    ATTR_START,
    ATTR_TEMPERATURE,
    DEVICE_TYPE_THERMOSTAT,
    DOMAIN,
    PLATFORMS,
    SCAN_INTERVAL_SECONDS,
    SERVICE_SET_SCHEDULE,
    TEMP_SCALE,
    WEEKDAY_BITS,
)

_LOGGER = logging.getLogger(__name__)

SCHEDULE_BLOCK_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DAYS): vol.Any(
            vol.All(cv.ensure_list, [cv.string]),
            vol.All(vol.Coerce(int), vol.Range(min=1, max=127)),
        ),
        vol.Required(ATTR_START): cv.time,
        vol.Required(ATTR_TEMPERATURE): vol.All(
            vol.Coerce(float), vol.Range(min=5, max=30)
        ),
    }
)

SET_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Required(ATTR_SCHEDULE): vol.All(
            cv.ensure_list, [SCHEDULE_BLOCK_SCHEMA], vol.Length(min=1)
        ),
    }
)


def _apply_live_state(device: dict[str, Any], live: dict[str, Any]) -> None:
    """Merge the flattened getConfig payload into the coordinator device dict."""
    device["output"] = live.get("output")
    if live.get("schedules") is not None:
        device["schedules"] = live["schedules"]
    if live.get("tAway") is not None:
        device["away_temperature"] = live["tAway"] / TEMP_SCALE
    if live.get("lock") is not None:
        device["locked"] = bool(live["lock"])
    if live.get("rssi") is not None:
        device["rssi"] = live["rssi"]
    if live.get("ssid") is not None:
        device["ssid"] = live["ssid"]
    if live.get("humidity") is not None:
        device["humidity"] = live["humidity"]
    if live.get("vs") is not None:
        device["firmware_vs"] = live["vs"]

    cale = live.get("tempCale")
    if isinstance(cale, list) and cale:
        device["heating_water_temp"] = cale[0].get("tempTarget", 0) / TEMP_SCALE
    sani = live.get("tempSani")
    if isinstance(sani, list) and sani:
        device["dhw_temp"] = sani[0].get("tempTarget", 0) / TEMP_SCALE


def _days_to_mask(days: Any) -> int:
    """Convert a schedule 'days' value (int mask or weekday names) to a bitmask."""
    if isinstance(days, int):
        return days
    mask = 0
    for raw in days:
        key = str(raw).strip().lower()[:3]
        if key not in WEEKDAY_BITS:
            raise HomeAssistantError(
                f"Unknown weekday '{raw}' (use mon..sun or an integer bitmask)"
            )
        mask |= WEEKDAY_BITS[key]
    if mask == 0:
        raise HomeAssistantError("Schedule block has no days selected")
    return mask


def _block_to_api(block: dict[str, Any]) -> dict[str, int]:
    """Convert a service schedule block into the device's schedule dict."""
    start: dt_time = block[ATTR_START]
    return {
        "days": _days_to_mask(block[ATTR_DAYS]),
        "startTime": start.hour * 60 + start.minute,
        "heatSetPoint": int(round(block[ATTR_TEMPERATURE] * TEMP_SCALE)),
    }


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Zentraly from a config entry."""
    session = aiohttp_client.async_get_clientsession(hass)

    api = ZentralyApi(
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        session=session,
    )

    try:
        await api.authenticate()
    except ZentralyApiError as err:
        _LOGGER.error("Failed to authenticate with Zentraly: %s", err)
        return False

    # Static per-device metadata (firmware, IP, MAC, timezone…) fetched once.
    device_meta: dict[str, dict[str, Any]] = {}

    async def async_update_data():
        """Fetch device data, enriched with live config + relay state."""
        try:
            devices = await api.get_devices()
        except ZentralyApiError as err:
            raise UpdateFailed(f"Error communicating with Zentraly API: {err}") from err

        for device in devices:
            serial = device.get("serial")
            if (
                device.get("device_type") != DEVICE_TYPE_THERMOSTAT
                or not serial
                or not device.get("connected", False)
            ):
                continue

            try:
                live = await api.get_live_state(serial)
                _apply_live_state(device, live)
            except ZentralyApiError as err:
                _LOGGER.debug("Could not read live config for %s: %s", serial, err)
                device["output"] = None

            try:
                device["offset"] = await api.get_offset(serial)
            except ZentralyApiError as err:
                _LOGGER.debug("Could not read offset for %s: %s", serial, err)

            if serial not in device_meta:
                try:
                    device_meta[serial] = await api.get_device_dates(serial)
                except ZentralyApiError as err:
                    _LOGGER.debug("Could not read device dates for %s: %s", serial, err)
                    device_meta[serial] = {}
            device["dates"] = device_meta.get(serial, {})

        return devices

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Zentraly",
        update_method=async_update_data,
        update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _async_register_services(hass)

    return True


def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration-level services (once)."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_SCHEDULE):
        return

    async def _handle_set_schedule(call: ServiceCall) -> None:
        entity_id: str = call.data[ATTR_ENTITY_ID]
        blocks: list[dict[str, Any]] = call.data[ATTR_SCHEDULE]

        registry = er.async_get(hass)
        entry = registry.async_get(entity_id)
        if entry is None or entry.platform != DOMAIN:
            raise HomeAssistantError(f"{entity_id} is not a Zentraly entity")

        serial = entry.unique_id.replace("zentraly_", "", 1).split("_")[0]
        store = hass.data.get(DOMAIN, {}).get(entry.config_entry_id)
        if not store:
            raise HomeAssistantError("Zentraly config entry is not loaded")

        api: ZentralyApi = store["api"]
        coordinator: DataUpdateCoordinator = store["coordinator"]

        schedules = [_block_to_api(b) for b in blocks]
        schedules.sort(key=lambda s: s["startTime"])

        try:
            await api.set_schedule(serial, schedules)
        except ZentralyApiError as err:
            raise HomeAssistantError(f"Zentraly set_schedule failed: {err}") from err

        _LOGGER.info("Zentraly schedule updated for %s: %s", entity_id, schedules)
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN, SERVICE_SET_SCHEDULE, _handle_set_schedule, schema=SET_SCHEDULE_SCHEMA
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SET_SCHEDULE)

    return unload_ok
