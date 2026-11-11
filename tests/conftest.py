"""Fixtures for Concept2 Logbook tests."""

from __future__ import annotations

import time
from typing import Any

import pytest
from homeassistant.components.application_credentials import (
    ClientCredential,
    async_import_client_credential,
)
from homeassistant.components.recorder import Recorder
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.concept2_logbook.const import DOMAIN

CLIENT_ID = "client-id"
CLIENT_SECRET = "client-secret"
USER = {
    "id": 42,
    "username": "rower42",
    "first_name": "Test",
    "last_name": "Rower",
}


def result(
    rid: int,
    date: str,
    distance: int,
    time_tenths: int,
    rtype: str = "rower",
    **extra: Any,
) -> dict[str, Any]:
    """Build an API result dict."""
    return {
        "id": rid,
        "user_id": USER["id"],
        "date": date,
        "timezone": None,
        "date_utc": None,
        "distance": distance,
        "type": rtype,
        "time": time_tenths,
        "workout_type": "JustRow",
        **extra,
    }


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    recorder_mock: Recorder, enable_custom_integrations: None
) -> None:
    """Enable custom integrations and the recorder (a dependency) in every test.

    recorder_mock has to be requested before anything that sets up hass.
    """


@pytest.fixture
async def setup_credentials(hass: HomeAssistant) -> None:
    """Register application credentials."""
    assert await async_setup_component(hass, "application_credentials", {})
    await async_import_client_credential(
        hass, DOMAIN, ClientCredential(CLIENT_ID, CLIENT_SECRET), DOMAIN
    )


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A configured entry with a valid token."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test Rower",
        unique_id=str(USER["id"]),
        data={
            "auth_implementation": DOMAIN,
            "token": {
                "access_token": "access",
                "refresh_token": "refresh",
                "token_type": "Bearer",
                "expires_in": 3600,
                "expires_at": time.time() + 3600,
            },
        },
    )
