"""Application credentials platform for Concept2 Logbook."""

from typing import override

from homeassistant.components.application_credentials import (
    AuthImplementation,
    AuthorizationServer,
    ClientCredential,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

from .const import OAUTH2_AUTHORIZE, OAUTH2_TOKEN, OAUTH_SCOPE


class Concept2OAuth2Implementation(AuthImplementation):
    """OAuth2 implementation that sends the scope on every token request.

    The Concept2 docs say the original scope must be passed when exchanging the
    authorization code and again on every refresh. The stock implementation
    only sends it on the authorize URL.
    """

    @property
    @override
    def extra_authorize_data(self) -> dict:
        """Add the scope to the authorize URL."""
        return {"scope": OAUTH_SCOPE}

    @override
    async def _token_request(self, data: dict) -> dict:
        """Add the scope to every token request."""
        return await super()._token_request({**data, "scope": OAUTH_SCOPE})


async def async_get_auth_implementation(
    hass: HomeAssistant, auth_domain: str, credential: ClientCredential
) -> config_entry_oauth2_flow.AbstractOAuth2Implementation:
    """Return the Concept2 auth implementation."""
    return Concept2OAuth2Implementation(
        hass,
        auth_domain,
        credential,
        AuthorizationServer(authorize_url=OAUTH2_AUTHORIZE, token_url=OAUTH2_TOKEN),
    )


async def async_get_description_placeholders(hass: HomeAssistant) -> dict[str, str]:
    """Return description placeholders for the credentials dialog."""
    return {
        "developer_url": "https://log.concept2.com/developers/keys",
        "redirect_url": "https://my.home-assistant.io/redirect/oauth",
    }
