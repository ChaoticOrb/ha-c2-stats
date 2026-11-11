"""Setup, sync and statistics tests."""

from __future__ import annotations

import time
from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.recorder import Recorder
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.concept2_logbook.const import (
    API_BASE,
    OAUTH2_TOKEN,
    UPDATE_INTERVAL,
)

from .conftest import USER, result

RESULTS_URL = f"{API_BASE}/users/me/results"


def page(data, current=1, total_pages=1, total=None):
    return {
        "data": data,
        "meta": {
            "pagination": {
                "current_page": current,
                "total_pages": total_pages,
                "total": total if total is not None else len(data) * total_pages,
            }
        },
    }


@pytest.fixture(autouse=True)
async def tz(hass: HomeAssistant) -> None:
    await hass.config.async_set_time_zone("America/New_York")


async def _setup(hass, config_entry):
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.freeze_time("2026-11-11 17:00:00+00:00")
async def test_setup_sensors_and_pagination(
    recorder_mock: Recorder,
    hass: HomeAssistant,
    setup_credentials: None,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.get(f"{API_BASE}/users/me", json={"data": USER})
    aioclient_mock.get(
        RESULTS_URL,
        params={"number": 250, "page": 1},
        json=page(
            [result(1, "2026-11-11 07:00:00", 5000, 12000, stroke_rate=24)], 1, 2
        ),
    )
    aioclient_mock.get(
        RESULTS_URL,
        params={"number": 250, "page": 2},
        json=page(
            [
                result(
                    2, "2026-06-01 07:00:00", 8000, 19200, "skierg", rest_distance=400
                )
            ],
            2,
            2,
        ),
    )
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    assert (
        hass.states.get("sensor.concept2_test_rower_lifetime_distance").state == "13000"
    )
    assert hass.states.get("sensor.concept2_test_rower_week_distance").state == "5000"
    assert (
        hass.states.get("sensor.concept2_test_rower_rowerg_lifetime_distance").state
        == "5000"
    )
    assert (
        hass.states.get("sensor.concept2_test_rower_skierg_season_distance").state
        == "8000"
    )
    workouts = hass.states.get("sensor.concept2_test_rower_workouts")
    assert workouts.state == "2"
    assert workouts.attributes["logbook_reported_count"] == 2
    lifetime = hass.states.get("sensor.concept2_test_rower_lifetime_distance")
    assert lifetime.attributes["rest_distance"] == 400
    assert lifetime.attributes["work_plus_rest_distance"] == 13400
    last = hass.states.get("sensor.concept2_test_rower_last_workout")
    assert last.state == "2026-11-11T12:00:00+00:00"
    assert last.attributes["pace"] == "2:00.0"
    assert (
        hass.states.get("sensor.concept2_test_rower_last_workout_pace").state == "120.0"
    )
    assert (
        hass.states.get("sensor.concept2_test_rower_last_workout_stroke_rate").state
        == "24"
    )

    # Full history lands in long-term statistics.
    await async_wait_recording_done(hass)
    stats = await hass.async_add_executor_job(
        statistics_during_period,
        hass,
        dt_util.utcnow() - timedelta(days=365),
        None,
        {"concept2_logbook:distance_42", "concept2_logbook:skierg_distance_42"},
        "hour",
        None,
        {"sum", "state"},
    )
    assert [r["sum"] for r in stats["concept2_logbook:distance_42"]] == [8000, 13000]
    assert [r["sum"] for r in stats["concept2_logbook:skierg_distance_42"]] == [8000]


async def test_incremental_then_daily_full_sync(
    recorder_mock: Recorder,
    hass: HomeAssistant,
    setup_credentials: None,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-11-11 17:00:00+00:00")
    aioclient_mock.get(f"{API_BASE}/users/me", json={"data": USER})
    aioclient_mock.get(
        RESULTS_URL,
        params={"number": 250, "page": 1},
        json=page([result(1, "2026-11-10 07:00:00", 5000, 12000)]),
    )
    await _setup(hass, config_entry)
    entity = "sensor.concept2_test_rower_lifetime_distance"
    assert hass.states.get(entity).state == "5000"

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        RESULTS_URL,
        params={"number": 250, "page": 1, "updated_after": "2026-11-11 15:00:00"},
        json=page([result(2, "2026-11-11 11:00:00", 2000, 4800)]),
    )
    freezer.tick(UPDATE_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity).state == "7000"
    assert len(aioclient_mock.mock_calls) == 1
    assert "updated_after" in str(aioclient_mock.mock_calls[0][1])

    # A day later the token has expired, gets refreshed, and a full sync runs
    # and drops the deleted result 1.
    aioclient_mock.clear_requests()
    aioclient_mock.post(
        OAUTH2_TOKEN,
        json={
            "access_token": "new",
            "refresh_token": "r2",
            "token_type": "Bearer",
            "expires_in": 3600,
        },
    )
    aioclient_mock.get(f"{API_BASE}/users/me", json={"data": USER})
    aioclient_mock.get(
        RESULTS_URL,
        params={"number": 250, "page": 1},
        json=page([result(2, "2026-11-11 11:00:00", 2000, 4800)]),
    )
    freezer.tick(timedelta(hours=24))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity).state == "2000"


async def test_auth_failure_starts_reauth(
    recorder_mock: Recorder,
    hass: HomeAssistant,
    setup_credentials: None,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.get(f"{API_BASE}/users/me", status=401)
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert flows and flows[0]["context"]["source"] == "reauth"


async def test_refresh_sends_scope(
    recorder_mock: Recorder,
    hass: HomeAssistant,
    setup_credentials: None,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        data={
            **config_entry.data,
            "token": {**config_entry.data["token"], "expires_at": time.time() - 10},
        },
    )
    aioclient_mock.post(
        OAUTH2_TOKEN,
        json={
            "access_token": "new",
            "refresh_token": "new-refresh",
            "token_type": "Bearer",
            "expires_in": 3600,
        },
    )
    aioclient_mock.get(f"{API_BASE}/users/me", json={"data": USER})
    aioclient_mock.get(RESULTS_URL, json=page([]))
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    token_call = next(c for c in aioclient_mock.mock_calls if str(c[1]) == OAUTH2_TOKEN)
    assert token_call[2]["grant_type"] == "refresh_token"
    assert token_call[2]["scope"] == "user:read,results:read"
    assert config_entry.data["token"]["access_token"] == "new"
    # No workouts yet: last workout sensors are unavailable, totals are zero.
    assert (
        hass.states.get("sensor.concept2_test_rower_last_workout").state
        == "unavailable"
    )
    assert hass.states.get("sensor.concept2_test_rower_lifetime_distance").state == "0"


async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    setup_credentials: None,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.get(f"{API_BASE}/users/me", json={"data": USER})
    aioclient_mock.get(
        RESULTS_URL,
        json=page(
            [
                result(1, "2026-11-10 07:00:00", 5000, 12000, rest_distance=150),
                result(2, "2026-11-09 07:00:00", 0, 0),
            ],
            total=3,
        ),
    )
    assert await async_setup_component(hass, "diagnostics", {})
    await _setup(hass, config_entry)
    diag = await get_diagnostics_for_config_entry(hass, hass_client, config_entry)
    assert diag["logbook_reported_count"] == 3
    assert diag["cached_count"] == 2
    assert diag["totals"]["all"] == {
        "work_distance": 5000,
        "rest_distance": 150,
        "workouts": 2,
    }
    assert diag["zero_distance_workouts"] == 1
    assert "token" not in str(diag)
