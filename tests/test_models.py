"""Tests for parsing and aggregation."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from custom_components.concept2_logbook.models import (
    ALL,
    Workout,
    format_seconds,
    season_start,
    summarize,
)

from .conftest import result

TZ = ZoneInfo("America/New_York")


def test_parse_prefers_date_utc() -> None:
    w = Workout.from_api(
        result(1, "2026-11-10 18:00:00", 5000, 12000, date_utc="2026-11-10 23:00:00"),
        TZ,
    )
    assert w.start == datetime(2026, 11, 10, 23, tzinfo=ZoneInfo("UTC"))


def test_parse_uses_result_timezone_then_default() -> None:
    w = Workout.from_api(
        result(1, "2026-11-10 18:00:00", 5000, 12000, timezone="Europe/London"), TZ
    )
    assert w.start.tzinfo == ZoneInfo("Europe/London")
    w = Workout.from_api(result(1, "2026-11-10 18:00:00", 5000, 12000), TZ)
    assert w.start.tzinfo == TZ


def test_pace_and_watts() -> None:
    # 2000m in 8:00.0 is a 2:00.0 split: 2.80 / (120 / 500) ** 3 = 202.5W.
    w = Workout.from_api(result(1, "2026-11-10 18:00:00", 2000, 4800), TZ)
    assert w.pace_500m == 120
    assert w.pace_display == "2:00.0"
    assert w.average_watts == pytest.approx(202.5, abs=0.1)
    bike = Workout.from_api(result(2, "2026-11-10 18:00:00", 2000, 4800, "bike"), TZ)
    assert bike.pace_display == "4:00.0"
    assert bike.average_watts is None


def test_format_seconds() -> None:
    assert format_seconds(125.3) == "2:05.3"
    assert format_seconds(15235.0) == "4:13:55.0"


def test_season_start() -> None:
    assert season_start(datetime(2026, 4, 30).date()).isoformat() == "2025-05-01"
    assert season_start(datetime(2026, 5, 1).date()).isoformat() == "2026-05-01"


def test_summarize_periods() -> None:
    now = datetime(2026, 11, 11, 12, tzinfo=TZ)  # a Wednesday
    raw = [
        result(1, "2026-11-11 07:00:00", 5000, 12000),  # today
        result(2, "2026-11-09 07:00:00", 6000, 14400),  # Monday, this week
        result(3, "2026-11-02 07:00:00", 7000, 16800),  # this month
        result(4, "2026-06-01 07:00:00", 8000, 19200, "skierg"),  # this season
        result(5, "2026-02-01 07:00:00", 9000, 21600),  # this year, last season
        result(6, "2025-12-01 07:00:00", 10000, 24000),  # last year
    ]
    summary = summarize([Workout.from_api(r, TZ) for r in raw], now)
    t = summary.totals[ALL]
    assert t.lifetime_distance == 45000
    assert t.workout_count == 6
    assert t.today_distance == 5000
    assert t.week_distance == 11000
    assert t.month_distance == 18000
    assert t.season_distance == 26000
    assert t.year_distance == 35000
    assert t.last_workout.id == 1
    assert summary.machine_types == ["rower", "skierg"]
    assert summary.totals["skierg"].lifetime_distance == 8000
    assert summary.totals["rower"].season_distance == 18000
