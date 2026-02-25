"""Light platform for Zen Controls."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.color import color_temperature_mired_to_kelvin

from .api import ZenEntityDescription
from .const import DOMAIN


def _arc_to_ha_brightness(arc_level: int | None) -> int | None:
    if arc_level is None:
        return None
    return round((arc_level / 254) * 255)


def _ha_to_arc_brightness(ha_brightness: int) -> int:
    return max(0, min(254, round((ha_brightness / 255) * 254)))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Zen Controls lights from config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    hub = data["hub"]

    entities: list[ZenControlsLightEntity] = []
    for desc in hub.entities.values():
        entities.append(ZenControlsLightEntity(coordinator, hub, desc, entry))

    async_add_entities(entities)


class ZenControlsLightEntity(CoordinatorEntity, LightEntity):
    """Representation of a Zen control group/device light."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        hub,
        desc: ZenEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._hub = hub
        self._desc = desc
        self._entry = entry

        self._attr_unique_id = f"{entry.entry_id}_{desc.unique_id}"
        self._attr_name = desc.name

        self._supported_modes = self._build_supported_modes(desc)

        min_kelvin, max_kelvin = hub.get_kelvin_limits(desc.unique_id)
        if min_kelvin is not None and max_kelvin is not None:
            self._attr_min_color_temp_kelvin = min_kelvin
            self._attr_max_color_temp_kelvin = max_kelvin

    @staticmethod
    def _build_supported_modes(desc: ZenEntityDescription) -> set[ColorMode]:
        modes: set[ColorMode] = set()
        if desc.supports_rgb:
            modes.add(ColorMode.RGB)
        if desc.supports_color_temp:
            modes.add(ColorMode.COLOR_TEMP)
        if not modes:
            modes.add(ColorMode.BRIGHTNESS)
        return modes

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
    def available(self) -> bool:
        return super().available and self._desc.unique_id in self.coordinator.data

    @property
    def is_on(self) -> bool:
        state = self.coordinator.data.get(self._desc.unique_id)
        return bool(state and state.is_on)

    @property
    def brightness(self) -> int | None:
        state = self.coordinator.data.get(self._desc.unique_id)
        if not state:
            return None
        return _arc_to_ha_brightness(state.brightness)

    @property
    def color_mode(self) -> ColorMode:
        state = self.coordinator.data.get(self._desc.unique_id)
        if state and state.rgb_color and ColorMode.RGB in self._supported_modes:
            return ColorMode.RGB
        if state and state.color_temp_kelvin and ColorMode.COLOR_TEMP in self._supported_modes:
            return ColorMode.COLOR_TEMP
        if ColorMode.BRIGHTNESS in self._supported_modes:
            return ColorMode.BRIGHTNESS
        # If RGB/COLOR_TEMP only and no color state yet, prefer RGB first.
        if ColorMode.RGB in self._supported_modes:
            return ColorMode.RGB
        return ColorMode.COLOR_TEMP

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        return self._supported_modes

    @property
    def color_temp_kelvin(self) -> int | None:
        state = self.coordinator.data.get(self._desc.unique_id)
        return state.color_temp_kelvin if state else None

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        state = self.coordinator.data.get(self._desc.unique_id)
        return state.rgb_color if state else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        uid = self._desc.unique_id

        if ATTR_BRIGHTNESS in kwargs:
            arc = _ha_to_arc_brightness(kwargs[ATTR_BRIGHTNESS])
            await self._hub.async_set_level(uid, arc)

        if ATTR_COLOR_TEMP_KELVIN in kwargs and self._desc.supports_color_temp:
            kelvin = int(kwargs[ATTR_COLOR_TEMP_KELVIN])
            arc = _ha_to_arc_brightness(kwargs.get(ATTR_BRIGHTNESS, 255))
            await self._hub.async_set_color_temp_kelvin(uid, kelvin, arc)
        elif "color_temp" in kwargs and self._desc.supports_color_temp:
            # Backward compatibility with mired-based service calls.
            kelvin = int(color_temperature_mired_to_kelvin(kwargs["color_temp"]))
            arc = _ha_to_arc_brightness(kwargs.get(ATTR_BRIGHTNESS, 255))
            await self._hub.async_set_color_temp_kelvin(uid, kelvin, arc)

        if ATTR_RGB_COLOR in kwargs and self._desc.supports_rgb:
            rgb = kwargs[ATTR_RGB_COLOR]
            arc = _ha_to_arc_brightness(kwargs.get(ATTR_BRIGHTNESS, 255))
            await self._hub.async_set_rgb(uid, (int(rgb[0]), int(rgb[1]), int(rgb[2])), arc)

        if not kwargs:
            # Turn on with a sane default if no explicit level is provided.
            await self._hub.async_set_level(uid, 254)

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._hub.async_turn_off(self._desc.unique_id)
        await self.coordinator.async_request_refresh()
