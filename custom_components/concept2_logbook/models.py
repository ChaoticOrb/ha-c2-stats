"""Parsing and aggregation of Concept2 results. No Home Assistant I/O here."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .const import PACE_1000M_TYPES

ALL = "all"


def _parse_local(value: str) -> datetime:
    return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S")


@dataclass(frozen=True, slots=True)
class Workout:
    """One Logbook result, normalised."""

    id: int
    start: datetime  # timezone aware
    type: str
    distance: int  # metres, work distance only
    time: float  # seconds, work time only
    workout_type: str | None = None
    rest_distance: int = 0
    rest_time: float = 0.0
    stroke_rate: int | None = None
    stroke_count: int | None = None
    calories: int | None = None
    drag_factor: int | None = None
    heart_rate_avg: int | None = None
    comments: str | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any], default_tz: tzinfo) -> Workout:
        """Build from an API result dict.

        Prefers date_utc. Falls back to the local date plus the result's own
        timezone, then to Home Assistant's timezone (older and manually entered
        results often have both as null).
        """
        start: datetime
        if raw.get("date_utc"):
            start = _parse_local(raw["date_utc"]).replace(tzinfo=ZoneInfo("UTC"))
        else:
            tz = default_tz
            if raw.get("timezone"):
                try:
                    tz = ZoneInfo(raw["timezone"])
                except (ZoneInfoNotFoundError, ValueError):
                    pass
            start = _parse_local(raw["date"]).replace(tzinfo=tz)
        hr = raw.get("heart_rate") or {}
        hr_avg = hr.get("average") if isinstance(hr, dict) else None
        return cls(
            id=int(raw["id"]),
            start=start,
            type=str(raw.get("type") or "unknown"),
            distance=int(raw.get("distance") or 0),
            time=(raw.get("time") or 0) / 10,
            workout_type=raw.get("workout_type"),
            rest_distance=int(raw.get("rest_distance") or 0),
            rest_time=(raw.get("rest_time") or 0) / 10,
            stroke_rate=raw.get("stroke_rate"),
            stroke_count=raw.get("stroke_count"),
            calories=raw.get("calories_total"),
            drag_factor=raw.get("drag_factor"),
            heart_rate_avg=int(hr_avg) if hr_avg not in (None, "") else None,
            comments=raw.get("comments"),
        )

    @property
    def pace_500m(self) -> float | None:
        """Seconds per 500m over the work portion."""
        if not self.distance or not self.time:
            return None
        return self.time / self.distance * 500

    @property
    def pace_display(self) -> str | None:
        """Pace as M:SS.t, per 1000m for the bike and per 500m otherwise."""
        pace = self.pace_500m
        if pace is None:
            return None
        if self.type in PACE_1000M_TYPES:
            pace *= 2
        return format_seconds(pace)

    @property
    def average_watts(self) -> float | None:
        """Average watts from pace, using Concept2's 2.80 / pace^3 formula.

        Only meaningful for the RowErg and SkiErg family, so other machine
        types return None.
        """
        pace = self.pace_500m
        if (
            pace is None
            or self.type in PACE_1000M_TYPES
            or self.type
            in {
                "water",
                "snow",
                "rollerski",
            }
        ):
            return None
        return round(2.80 / (pace / 500) ** 3, 1)


def format_seconds(seconds: float) -> str:
    """Format seconds as H:MM:SS.t or M:SS.t."""
    tenths = round(seconds * 10)
    hours, rem = divmod(tenths, 36000)
    minutes, rem = divmod(rem, 600)
    secs, tenth = divmod(rem, 10)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}.{tenth}"
    return f"{minutes}:{secs:02d}.{tenth}"


def season_start(day: date) -> date:
    """Concept2 seasons run May 1 to April 30."""
    year = day.year if day.month >= 5 else day.year - 1
    return date(year, 5, 1)


@dataclass(slots=True)
class Totals:
    """Aggregates for one machine type, or for all of them."""

    lifetime_distance: int = 0
    lifetime_rest_distance: int = 0
    lifetime_time: float = 0.0
    workout_count: int = 0
    season_distance: int = 0
    year_distance: int = 0
    month_distance: int = 0
    week_distance: int = 0
    today_distance: int = 0
    last_workout: Workout | None = None


@dataclass(slots=True)
class Period:
    """Local period boundaries used for the resetting totals."""

    today: datetime
    week: datetime
    month: datetime
    year: datetime
    season: datetime

    @classmethod
    def for_now(cls, now: datetime) -> Period:
        """Compute period starts for an aware local datetime."""
        tz = now.tzinfo
        today = datetime(now.year, now.month, now.day, tzinfo=tz)
        season = season_start(now.date())
        return cls(
            today=today,
            week=today - timedelta(days=today.weekday()),
            month=today.replace(day=1),
            year=today.replace(month=1, day=1),
            season=datetime(season.year, season.month, season.day, tzinfo=tz),
        )


@dataclass(slots=True)
class Summary:
    """Everything the sensors need."""

    totals: dict[str, Totals] = field(default_factory=dict)
    periods: Period | None = None

    @property
    def machine_types(self) -> list[str]:
        """Machine types that have at least one result."""
        return sorted(k for k in self.totals if k != ALL)


def summarize(workouts: list[Workout], now: datetime) -> Summary:
    """Aggregate workouts. `now` must be aware and in the local timezone."""
    periods = Period.for_now(now)
    totals: dict[str, Totals] = {ALL: Totals()}
    for w in sorted(workouts, key=lambda w: w.start):
        local = w.start.astimezone(now.tzinfo)
        for key in (ALL, w.type):
            t = totals.setdefault(key, Totals())
            t.lifetime_distance += w.distance
            t.lifetime_rest_distance += w.rest_distance
            t.lifetime_time += w.time
            t.workout_count += 1
            t.last_workout = w
            if local >= periods.season:
                t.season_distance += w.distance
            if local >= periods.year:
                t.year_distance += w.distance
            if local >= periods.month:
                t.month_distance += w.distance
            if local >= periods.week:
                t.week_distance += w.distance
            if local >= periods.today:
                t.today_distance += w.distance
    return Summary(totals=totals, periods=periods)
