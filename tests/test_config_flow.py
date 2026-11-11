"""Config flow tests."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_entry_oauth2_flow
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.concept2_logbook.const import (
    API_BASE,
    DOMAIN,
    OAUTH2_AUTHORIZE,
    OAUTH2_TOKEN,
)

from .conftest import CLIENT_ID, USER

REDIRECT = "https://example.com/auth/external/callback"


async def _run_flow(
    hass, hass_client_no_auth, aioclient_mock, source=None, flow_id=None
):
    if flow_id is None:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    else:
        result = await hass.config_entries.flow.async_configure(flow_id, {})
    state = config_entry_oauth2_flow._encode_jwt(
        hass, {"flow_id": result["flow_id"], "redirect_uri": REDIRECT}
    )
    assert result["type"] is FlowResultType.EXTERNAL_STEP
    assert result["url"].startswith(OAUTH2_AUTHORIZE)
    assert f"client_id={CLIENT_ID}" in result["url"]
    assert "scope=user:read,results:read" in result["url"]

    client = await hass_client_no_auth()
    resp = await client.get(f"/auth/external/callback?code=abcd&state={state}")
    assert resp.status == HTTPStatus.OK

    aioclient_mock.post(
        OAUTH2_TOKEN,
        json={
            "access_token": "a",
            "refresh_token": "r",
            "token_type": "Bearer",
            "expires_in": 3600,
        },
    )
    aioclient_mock.get(f"{API_BASE}/users/me", json={"data": USER})
    return await hass.config_entries.flow.async_configure(result["flow_id"])


@pytest.mark.usefixtures("current_request_with_host", "setup_credentials")
async def test_full_flow(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    result = await _run_flow(hass, hass_client_no_auth, aioclient_mock)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test Rower"
    assert result["result"].unique_id == "42"
    token_call = next(c for c in aioclient_mock.mock_calls if str(c[1]) == OAUTH2_TOKEN)
    assert token_call[2]["scope"] == "user:read,results:read"


@pytest.mark.usefixtures("current_request_with_host", "setup_credentials")
async def test_already_configured(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    config_entry.add_to_hass(hass)
    result = await _run_flow(hass, hass_client_no_auth, aioclient_mock)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
