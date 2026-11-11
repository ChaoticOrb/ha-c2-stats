"""Data update coordinator for Concept2 Logbook."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    OAuth2TokenRequestBaseError,
    OAuth2TokenRequestReauthError,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import Concept2ApiClient, Concept2AuthError, Concept2Error
from .const import (
    DOMAIN,
    FULL_SYNC_INTERVAL,
    INCREMENTAL_OVERLAP,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
)
from .models import Summary, Workout, summarize
from .statistics import import_statistics

_LOGGER = logging.getLogger(__name__)

type Concept2ConfigEntry = ConfigEntry[Concept2Coordinator]


@dataclass(slots=True)
class Concept2Data:
    """Coordinator payload."""

    user: dict[str, Any]
    workouts: list[Workout]
    summary: Summary


class Concept2Coordinator(DataUpdateCoordinator[Concept2Data]):
    """Fetch results, cache them locally, and aggregate.

    The first refresh and one refresh a day pull every result so deletions are
    picked up. Refreshes in between ask only for results updated since the
    last sync.
    """

    config_entry: Concept2ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: Concept2ConfigEntry,
        client: Concept2ApiClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._results: dict[int, dict[str, Any]] = {}
        self._user: dict[str, Any] | None = None
        self._last_sync: datetime | None = None
        self._last_full_sync: datetime | None = None
        self._stat_hours: dict[str, set[datetime]] = {}
        self._stats_hash: str | None = None
        self._loaded = False
        self.reported_total: int | None = None

    async def _async_load(self) -> None:
        stored = await self._store.async_load() or {}
        self._results = {int(r["id"]): r for r in stored.get("results", [])}
        self._user = stored.get("user")
        self._last_sync = dt_util.parse_datetime(stored.get("last_sync") or "")
        self._last_full_sync = dt_util.parse_datetime(
            stored.get("last_full_sync") or ""
        )
        self._stat_hours = {
            k: {datetime.fromisoformat(h) for h in v}
            for k, v in (stored.get("stat_hours") or {}).items()
        }
        self._stats_hash = stored.get("stats_hash")
        self._loaded = True

    def _store_payload(self) -> dict[str, Any]:
        return {
            "user": self._user,
            "results": list(self._results.values()),
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
            "last_full_sync": (
                self._last_full_sync.isoformat() if self._last_full_sync else None
            ),
            "stat_hours": {
                k: sorted(h.isoformat() for h in v) for k, v in self._stat_hours.items()
            },
            "stats_hash": self._stats_hash,
        }

    async def _async_fetch(self, now: datetime) -> None:
        full = (
            not self._results
            or self._last_full_sync is None
            or now - self._last_full_sync >= FULL_SYNC_INTERVAL
        )
        if full or self._user is None:
            self._user = await self.client.async_get_user()
        if full:
            raw = await self.client.async_get_results()
            self._results = {int(r["id"]): r for r in raw}
            self._last_full_sync = now
            self.reported_total = self.client.last_reported_total
            if self.reported_total is not None and self.reported_total != len(
                self._results
            ):
                _LOGGER.warning(
                    "Concept2 reported %s results but %s were fetched",
                    self.reported_total,
                    len(self._results),
                )
        else:
            assert self._last_sync is not None
            since = dt_util.as_utc(self._last_sync - INCREMENTAL_OVERLAP)
            raw = await self.client.async_get_results(
                updated_after=since.strftime("%Y-%m-%d %H:%M:%S")
            )
            for r in raw:
                self._results[int(r["id"])] = r
        self._last_sync = now
        _LOGGER.debug(
            "%s sync fetched %d results, %d cached",
            "Full" if full else "Incremental",
            len(raw),
            len(self._results),
        )

    async def _async_update_data(self) -> Concept2Data:
        if not self._loaded:
            await self._async_load()
        now = dt_util.utcnow()
        try:
            await self._async_fetch(now)
        except (Concept2AuthError, OAuth2TokenRequestReauthError) as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (Concept2Error, OAuth2TokenRequestBaseError) as err:
            if not self._results or self._user is None:
                raise UpdateFailed(str(err)) from err
            # Keep serving the cache; totals still roll over at period ends.
            _LOGGER.warning("Concept2 update failed, using cached results: %s", err)

        assert self._user is not None
        default_tz = dt_util.get_default_time_zone()
        workouts = sorted(
            (Workout.from_api(r, default_tz) for r in self._results.values()),
            key=lambda w: w.start,
        )
        summary = summarize(workouts, dt_util.now())

        digest = hashlib.sha256(
            json.dumps(
                [[w.id, w.start.isoformat(), w.type, w.distance] for w in workouts]
            ).encode()
        ).hexdigest()
        if digest != self._stats_hash:
            self._stat_hours = import_statistics(
                self.hass,
                self._user["id"],
                self.config_entry.title,
                workouts,
                self._stat_hours,
            )
            self._stats_hash = digest

        await self._store.async_save(self._store_payload())
        return Concept2Data(user=self._user, workouts=workouts, summary=summary)
