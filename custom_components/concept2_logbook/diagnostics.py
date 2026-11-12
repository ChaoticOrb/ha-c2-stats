"""Diagnostics for Concept2 Logbook."""

from __future__ import annotations

from collections import Counter
from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import Concept2ConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: Concept2ConfigEntry
) -> dict[str, Any]:
    """Return totals and sync state. No tokens, names or comments."""
    coordinator = entry.runtime_data
    data = coordinator.data
    workouts = data.workouts
    return {
        "logbook_reported_count": coordinator.reported_total,
        "cached_count": len(workouts),
        "first_workout": workouts[0].start.isoformat() if workouts else None,
        "last_workout": workouts[-1].start.isoformat() if workouts else None,
        "count_by_machine": dict(Counter(w.type for w in workouts)),
        "count_by_workout_type": dict(Counter(w.workout_type for w in workouts)),
        "totals": {
            machine: {
                "total_distance": t.lifetime_distance,
                "rest_distance": t.lifetime_rest_distance,
                "workouts": t.workout_count,
            }
            for machine, t in data.summary.totals.items()
        },
        "zero_distance_workouts": sum(1 for w in workouts if not w.distance),
        "last_update_success": coordinator.last_update_success,
    }
