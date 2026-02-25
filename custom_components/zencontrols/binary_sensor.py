"""Binary sensor platform for Zen Controls occupancy/PIR states."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Zen Controls occupancy binary sensors from config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    hub = data["hub"]

    entities: list[ZenControlsGroupOccupancyBinarySensor] = []
    for desc in hub.entities.values():
        if desc.endpoint.kind != "group":
            continue
        group_number = desc.endpoint.address - 64
        entities.append(
            ZenControlsGroupOccupancyBinarySensor(
                coordinator=coordinator,
                hub=hub,
                entry=entry,
                group_number=group_number,
                group_name=desc.name,
            )
        )

    async_add_entities(entities)


class ZenControlsGroupOccupancyBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Represents a Zen group occupancy/PIR state."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(
        self,
        coordinator,
        hub,
        entry: ConfigEntry,
        group_number: int,
        group_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._entry = entry
        self._group_number = group_number

        self._attr_unique_id = f"{entry.entry_id}_group_{group_number}_occupancy"
        self._attr_name = f"{group_name} Occupancy"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._hub.controller_label or "Zen Controls Controller",
            manufacturer="Zen Controls",
            model="TPI Advanced",
            sw_version=self._hub.controller_version,
        )

    @property
    def is_on(self) -> bool:
        return bool(self._hub.group_occupancy.get(self._group_number, False))

    @property
    def available(self) -> bool:
        return super().available and self._group_number in self._hub.group_occupancy
