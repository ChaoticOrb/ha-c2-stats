"""The Concept2 Logbook integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client, config_entry_oauth2_flow
from homeassistant.helpers.storage import Store

from .api import Concept2ApiClient
from .const import DOMAIN, STORAGE_VERSION
from .coordinator import Concept2ConfigEntry, Concept2Coordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: Concept2ConfigEntry) -> bool:
    """Set up Concept2 Logbook from a config entry."""
    implementation = (
        await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, entry
        )
    )
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    async def get_token() -> str:
        await session.async_ensure_token_valid()
        return session.token["access_token"]

    client = Concept2ApiClient(aiohttp_client.async_get_clientsession(hass), get_token)
    coordinator = Concept2Coordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Concept2ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: Concept2ConfigEntry) -> None:
    """Remove the local results cache when the entry is deleted."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
