"""Config flow for Concept2 Logbook."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, override

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_TOKEN
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client, config_entry_oauth2_flow, selector

from .api import Concept2ApiClient, Concept2AuthError, Concept2Error
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    OAUTH_SCOPE,
)

_LOGGER = logging.getLogger(__name__)


class OAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Handle the Concept2 OAuth2 flow."""

    DOMAIN = DOMAIN
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> Concept2OptionsFlow:
        """Return the options flow."""
        return Concept2OptionsFlow()

    @property
    @override
    def logger(self) -> logging.Logger:
        """Return logger."""
        return _LOGGER

    @property
    @override
    def extra_authorize_data(self) -> dict[str, str]:
        """Request read-only access to the profile and results."""
        return {"scope": OAUTH_SCOPE}

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauth when the refresh token stops working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauth."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_user()

    @override
    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Look up the Logbook user and create or update the entry."""

        async def get_token() -> str:
            return data[CONF_TOKEN]["access_token"]

        client = Concept2ApiClient(
            aiohttp_client.async_get_clientsession(self.hass), get_token
        )
        try:
            user = await client.async_get_user()
        except Concept2AuthError:
            return self.async_abort(reason="invalid_auth")
        except Concept2Error as err:
            _LOGGER.error("Could not read Concept2 profile: %s", err)
            return self.async_abort(reason="cannot_connect")

        await self.async_set_unique_id(str(user["id"]))
        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data=data
            )
        self._abort_if_unique_id_configured()
        name = (
            " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p)
            or user.get("username")
            or "Concept2"
        )
        return self.async_create_entry(title=name, data=data)


class Concept2OptionsFlow(OptionsFlowWithReload):
    """Set how often to check the Logbook."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options form."""
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])}
            )
        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): (
                        selector.NumberSelector(
                            selector.NumberSelectorConfig(
                                min=MIN_SCAN_INTERVAL,
                                max=MAX_SCAN_INTERVAL,
                                step=1,
                                unit_of_measurement="minutes",
                                mode=selector.NumberSelectorMode.BOX,
                            )
                        )
                    )
                }
            ),
        )
