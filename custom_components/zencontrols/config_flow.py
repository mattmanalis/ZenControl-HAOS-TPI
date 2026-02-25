"""Config flow for Zen Controls integration."""

from __future__ import annotations

import socket
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .api import ZenTPIClient
from .const import (
    CONF_HOST,
    CONF_PORT,
    CONF_RETRIES,
    CONF_SCAN_GEARS,
    CONF_SCAN_GROUPS,
    CONF_TIMEOUT,
    DEFAULT_PORT,
    DEFAULT_RETRIES,
    DEFAULT_SCAN_GEARS,
    DEFAULT_SCAN_GROUPS,
    DEFAULT_TIMEOUT,
    DOMAIN,
)


class ZenControlsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Zen Controls."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            if await self._can_connect(host, port):
                return self.async_create_entry(
                    title=f"Zen Controls ({host})",
                    data={CONF_HOST: host, CONF_PORT: port},
                    options={
                        CONF_SCAN_GROUPS: DEFAULT_SCAN_GROUPS,
                        CONF_SCAN_GEARS: DEFAULT_SCAN_GEARS,
                        CONF_TIMEOUT: DEFAULT_TIMEOUT,
                        CONF_RETRIES: DEFAULT_RETRIES,
                    },
                )

            errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return options flow handler."""
        return ZenControlsOptionsFlow(config_entry)

    async def _can_connect(self, host: str, port: int) -> bool:
        """Validate connectivity using a quick TPI command."""
        try:
            socket.gethostbyname(host)
            client = ZenTPIClient(host=host, port=port, timeout=1.5, retries=0)
            rtype, _payload = await client.request_basic(command=0x24)
            return rtype in (0xA0, 0xA1, 0xA2)
        except Exception:
            return False


class ZenControlsOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Zen Controls."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_GROUPS,
                    default=options.get(CONF_SCAN_GROUPS, DEFAULT_SCAN_GROUPS),
                ): bool,
                vol.Required(
                    CONF_SCAN_GEARS,
                    default=options.get(CONF_SCAN_GEARS, DEFAULT_SCAN_GEARS),
                ): bool,
                vol.Required(
                    CONF_TIMEOUT,
                    default=options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
                ): vol.Coerce(float),
                vol.Required(
                    CONF_RETRIES,
                    default=options.get(CONF_RETRIES, DEFAULT_RETRIES),
                ): vol.Coerce(int),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
