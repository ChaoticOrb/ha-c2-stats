"""Import the full Logbook history into long-term statistics.

Sensors only start recording history from the day the integration is set up.
External statistics let the statistics-graph card show every workout back to
the first one, bucketed by day, week or month.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.util.unit_conversion import DistanceConverter

from .const import DOMAIN, MACHINE_TYPES
from .models import ALL, Workout


def statistic_id(user_id: int | str, machine: str) -> str:
    """Return the external statistic id for a user and machine type."""
    suffix = "distance" if machine == ALL else f"{machine}_distance"
    return f"{DOMAIN}:{suffix}_{user_id}"


def _hour(dt: datetime) -> datetime:
    return dt.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def build_statistics(
    workouts: list[Workout],
    machine: str,
    previous_hours: set[datetime],
) -> tuple[list[StatisticData], set[datetime]]:
    """Return hourly rows for one machine type plus the set of hours used.

    Hours that held data on a previous import but no longer do (a deleted or
    re-dated result) get a zero row carrying the running sum, so the stored
    cumulative sum never goes stale.
    """
    buckets: dict[datetime, int] = defaultdict(int)
    for w in workouts:
        if machine == ALL or w.type == machine:
            buckets[_hour(w.start)] += w.distance
    hours = set(buckets)
    rows: list[StatisticData] = []
    running = 0
    for hour in sorted(hours | previous_hours):
        change = buckets.get(hour, 0)
        running += change
        rows.append(StatisticData(start=hour, state=change, sum=running))
    return rows, hours


def import_statistics(
    hass: HomeAssistant,
    user_id: int | str,
    name: str,
    workouts: list[Workout],
    previous: dict[str, set[datetime]],
) -> dict[str, set[datetime]]:
    """Push statistics for all machines and each machine type present.

    `previous` and the return value map machine type to the hours that held
    data, so the next import can detect removed buckets.
    """
    machines = {ALL, *(w.type for w in workouts), *previous}
    used: dict[str, set[datetime]] = {}
    for machine in sorted(machines):
        stat_id = statistic_id(user_id, machine)
        rows, hours = build_statistics(workouts, machine, previous.get(machine, set()))
        if hours:
            used[machine] = hours
        if not rows:
            continue
        label = (
            "all machines" if machine == ALL else MACHINE_TYPES.get(machine, machine)
        )
        metadata = StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name=f"{name} distance ({label})",
            source=DOMAIN,
            statistic_id=stat_id,
            unit_class=DistanceConverter.UNIT_CLASS,
            unit_of_measurement=UnitOfLength.METERS,
        )
        async_add_external_statistics(hass, metadata, rows)
    return used
