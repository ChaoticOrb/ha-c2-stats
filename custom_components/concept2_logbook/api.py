"""Minimal async client for the Concept2 Logbook API."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Any

import aiohttp

from .const import ACCEPT_HEADER, API_BASE, PAGE_SIZE


class Concept2Error(Exception):
    """Base error for the Concept2 API."""


class Concept2AuthError(Concept2Error):
    """Authentication was rejected."""


class Concept2ApiClient:
    """Talk to the Logbook API with a token supplied on demand."""

    def __init__(
        self,
        websession: aiohttp.ClientSession,
        get_token: Callable[[], Awaitable[str]],
        base_url: str = API_BASE,
    ) -> None:
        """Initialize the client."""
        self._session = websession
        self._get_token = get_token
        self._base = base_url.rstrip("/")

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        token = await self._get_token()
        headers = {"Accept": ACCEPT_HEADER, "Authorization": f"Bearer {token}"}
        try:
            async with self._session.get(
                f"{self._base}{path}",
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
                    raise Concept2AuthError(f"HTTP {resp.status} from {path}")
                if resp.status >= 400:
                    body = await resp.text()
                    raise Concept2Error(f"HTTP {resp.status} from {path}: {body[:200]}")
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise Concept2Error(f"Error talking to Concept2: {err}") from err

    async def async_get_user(self) -> dict[str, Any]:
        """Return the authenticated user's profile."""
        data = await self._get("/users/me")
        return data["data"]

    async def async_get_results(
        self, updated_after: str | None = None
    ) -> list[dict[str, Any]]:
        """Return every result for the user, following pagination.

        updated_after is a GMT timestamp string, "YYYY-MM-DD HH:MM:SS".
        """
        params: dict[str, Any] = {"number": PAGE_SIZE, "page": 1}
        if updated_after:
            params["updated_after"] = updated_after
        results: list[dict[str, Any]] = []
        while True:
            data = await self._get("/users/me/results", params)
            results.extend(data.get("data") or [])
            pagination = (data.get("meta") or {}).get("pagination") or {}
            total_pages = pagination.get("total_pages") or 1
            if params["page"] >= total_pages:
                return results
            params["page"] += 1
