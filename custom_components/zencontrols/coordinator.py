"""Coordinator for Zen Controls state polling."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ZenTPIDeviceHub
from .const import COORDINATOR_UPDATE_SECONDS

_LOGGER = logging.getLogger(__name__)


class ZenControlsCoordinator(DataUpdateCoordinator[dict]):
    """Coordinate periodic polling from Zen controller."""

    def __init__(self, hass: HomeAssistant, hub: ZenTPIDeviceHub) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="zencontrols",
            update_interval=timedelta(seconds=COORDINATOR_UPDATE_SECONDS),
        )
        self.hub = hub

    async def _async_update_data(self) -> dict:
        try:
            return await self.hub.async_refresh_states()
        except Exception as err:
            raise UpdateFailed(str(err)) from err

    async def async_handle_push_update(self) -> None:
        """Apply state update pushed by multicast events."""
        self.async_set_updated_data(dict(self.hub.states))
