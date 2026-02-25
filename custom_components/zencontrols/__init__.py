"""Zen Controls integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .api import ZenTPIDeviceHub
from .const import (
    CONF_HOST,
    CONF_PORT,
    CONF_RETRIES,
    CONF_SCAN_GEARS,
    CONF_SCAN_GROUPS,
    CONF_TIMEOUT,
    DEFAULT_RETRIES,
    DEFAULT_SCAN_GEARS,
    DEFAULT_SCAN_GROUPS,
    DEFAULT_TIMEOUT,
    DOMAIN,
)
from .coordinator import ZenControlsCoordinator

PLATFORMS: list[Platform] = [Platform.LIGHT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Zen Controls from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]

    scan_groups = entry.options.get(CONF_SCAN_GROUPS, DEFAULT_SCAN_GROUPS)
    scan_gears = entry.options.get(CONF_SCAN_GEARS, DEFAULT_SCAN_GEARS)
    timeout = entry.options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
    retries = entry.options.get(CONF_RETRIES, DEFAULT_RETRIES)

    hub = ZenTPIDeviceHub(
        host=host,
        port=port,
        timeout=timeout,
        retries=retries,
        scan_groups=scan_groups,
        scan_gears=scan_gears,
    )
    await hub.async_initialize()

    coordinator = ZenControlsCoordinator(hass, hub)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "hub": hub,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
