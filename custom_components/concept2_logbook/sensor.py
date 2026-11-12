"""Sensors for Concept2 Logbook."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfLength, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MACHINE_TYPES
from .coordinator import Concept2ConfigEntry, Concept2Coordinator, Concept2Data
from .models import (
    ALL,
    PbEvent,
    Period,
    PersonalBest,
    Streaks,
    Totals,
    Workout,
    format_seconds,
)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class TotalsSensorDescription(SensorEntityDescription):
    """A sensor computed from a Totals object."""

    value_fn: Callable[[Totals], StateType]
    reset_fn: Callable[[Period], datetime] | None = None
    all_only: bool = False


@dataclass(frozen=True, kw_only=True)
class LastWorkoutSensorDescription(SensorEntityDescription):
    """A sensor computed from the most recent workout."""

    value_fn: Callable[[Workout], StateType | datetime]


def _distance(
    key: str,
    name: str,
    value_fn: Callable[[Totals], int],
    reset_fn: Callable[[Period], datetime] | None = None,
    enabled: bool = True,
) -> TotalsSensorDescription:
    return TotalsSensorDescription(
        key=key,
        name=name,
        native_unit_of_measurement=UnitOfLength.METERS,
        device_class=SensorDeviceClass.DISTANCE,
        # TOTAL rather than TOTAL_INCREASING so a deleted result reads as a
        # decrease instead of a meter reset.
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=value_fn,
        reset_fn=reset_fn,
        entity_registry_enabled_default=enabled,
    )


TOTALS_SENSORS: tuple[TotalsSensorDescription, ...] = (
    _distance("lifetime_distance", "Lifetime distance", lambda t: t.lifetime_distance),
    _distance(
        "season_distance",
        "Season distance",
        lambda t: t.season_distance,
        lambda p: p.season,
    ),
    _distance(
        "year_distance", "Year distance", lambda t: t.year_distance, lambda p: p.year
    ),
    _distance(
        "month_distance",
        "Month distance",
        lambda t: t.month_distance,
        lambda p: p.month,
    ),
    _distance(
        "week_distance", "Week distance", lambda t: t.week_distance, lambda p: p.week
    ),
    _distance(
        "today_distance",
        "Today distance",
        lambda t: t.today_distance,
        lambda p: p.today,
        enabled=False,
    ),
    TotalsSensorDescription(
        key="workout_count",
        name="Workouts",
        native_unit_of_measurement="workouts",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda t: t.workout_count,
    ),
    TotalsSensorDescription(
        key="week_count",
        name="Workouts this week",
        native_unit_of_measurement="workouts",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda t: t.week_count,
        reset_fn=lambda p: p.week,
        all_only=True,
    ),
    TotalsSensorDescription(
        key="lifetime_time",
        name="Lifetime time",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=1,
        value_fn=lambda t: round(t.lifetime_time, 1),
        all_only=True,
    ),
)


@dataclass(frozen=True, kw_only=True)
class StreakSensorDescription(SensorEntityDescription):
    """A consistency stat across all machines."""

    value_fn: Callable[[Streaks], StateType]


STREAK_SENSORS: tuple[StreakSensorDescription, ...] = (
    StreakSensorDescription(
        key="current_daily_streak",
        name="Daily streak",
        native_unit_of_measurement="days",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fire",
        value_fn=lambda s: s.current_daily,
    ),
    StreakSensorDescription(
        key="longest_daily_streak",
        name="Longest daily streak",
        native_unit_of_measurement="days",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fire",
        value_fn=lambda s: s.longest_daily,
    ),
    StreakSensorDescription(
        key="current_weekly_streak",
        name="Weekly streak",
        native_unit_of_measurement="weeks",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-check",
        value_fn=lambda s: s.current_weekly,
    ),
    StreakSensorDescription(
        key="longest_weekly_streak",
        name="Longest weekly streak",
        native_unit_of_measurement="weeks",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-check",
        value_fn=lambda s: s.longest_weekly,
    ),
    StreakSensorDescription(
        key="days_since_last_workout",
        name="Days since last workout",
        native_unit_of_measurement="days",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-clock",
        value_fn=lambda s: s.days_since_last,
    ),
)

LAST_WORKOUT_SENSORS: tuple[LastWorkoutSensorDescription, ...] = (
    LastWorkoutSensorDescription(
        key="last_workout",
        name="Last workout",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda w: w.start,
    ),
    LastWorkoutSensorDescription(
        key="last_workout_distance",
        name="Last workout distance",
        native_unit_of_measurement=UnitOfLength.METERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda w: w.distance,
    ),
    LastWorkoutSensorDescription(
        key="last_workout_time",
        name="Last workout time",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda w: w.time,
    ),
    LastWorkoutSensorDescription(
        key="last_workout_pace",
        name="Last workout pace",
        native_unit_of_measurement="s/500m",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda w: round(w.pace_500m, 1) if w.pace_500m else None,
    ),
    LastWorkoutSensorDescription(
        key="last_workout_watts",
        name="Last workout average power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda w: w.average_watts,
    ),
    LastWorkoutSensorDescription(
        key="last_workout_stroke_rate",
        name="Last workout stroke rate",
        native_unit_of_measurement="spm",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda w: w.stroke_rate,
    ),
    LastWorkoutSensorDescription(
        key="last_workout_calories",
        name="Last workout calories",
        native_unit_of_measurement="kcal",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda w: w.calories,
    ),
    LastWorkoutSensorDescription(
        key="last_workout_heart_rate",
        name="Last workout average heart rate",
        native_unit_of_measurement="bpm",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda w: w.heart_rate_avg,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Concept2ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors, adding per-machine sensors as new machine types appear."""
    coordinator = entry.runtime_data
    known: set[str] = set()
    known_pbs: set[tuple[str, str]] = set()

    entities: list[SensorEntity] = [
        *(LastWorkoutSensor(coordinator, d) for d in LAST_WORKOUT_SENSORS),
        *(StreakSensor(coordinator, d) for d in STREAK_SENSORS),
    ]

    @callback
    def add_machine_sensors() -> None:
        new: list[SensorEntity] = []
        for machine in [ALL, *coordinator.data.summary.machine_types]:
            if machine in known:
                continue
            known.add(machine)
            new.extend(
                TotalsSensor(coordinator, d, machine)
                for d in TOTALS_SENSORS
                if machine == ALL or not d.all_only
            )
        for key, pb in coordinator.data.summary.pbs.items():
            if key not in known_pbs:
                known_pbs.add(key)
                new.append(PersonalBestSensor(coordinator, key[0], pb.event))
        if new:
            async_add_entities(new)

    async_add_entities(entities)
    add_machine_sensors()
    entry.async_on_unload(coordinator.async_add_listener(add_machine_sensors))


class Concept2Entity(CoordinatorEntity[Concept2Coordinator]):
    """Base entity, one device per Logbook account."""

    _attr_has_entity_name = True
    _attr_attribution = "Data from the Concept2 Logbook"

    def __init__(self, coordinator: Concept2Coordinator, key: str) -> None:
        """Initialize."""
        super().__init__(coordinator)
        user_id = coordinator.data.user["id"]
        self._attr_unique_id = f"{user_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(user_id))},
            name=f"Concept2 {coordinator.config_entry.title}",
            manufacturer="Concept2",
            model="Logbook",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://log.concept2.com/log",
        )

    @property
    def _data(self) -> Concept2Data:
        return self.coordinator.data


class TotalsSensor(Concept2Entity, SensorEntity):
    """Aggregate total for all machines or one machine type."""

    entity_description: TotalsSensorDescription

    def __init__(
        self,
        coordinator: Concept2Coordinator,
        description: TotalsSensorDescription,
        machine: str,
    ) -> None:
        """Initialize."""
        key = description.key if machine == ALL else f"{machine}_{description.key}"
        super().__init__(coordinator, key)
        self.entity_description = description
        self._machine = machine
        if machine != ALL:
            self._attr_name = (
                f"{MACHINE_TYPES.get(machine, machine)} {str(description.name).lower()}"
            )

    @property
    def _totals(self) -> Totals:
        return self._data.summary.totals.get(self._machine) or Totals()

    @property
    def native_value(self) -> StateType:
        """Return the value."""
        return self.entity_description.value_fn(self._totals)

    @property
    def last_reset(self) -> datetime | None:
        """Return the start of the current period for resetting totals."""
        reset_fn = self.entity_description.reset_fn
        periods = self._data.summary.periods
        if reset_fn is None or periods is None:
            return None
        return reset_fn(periods)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Breakdown that helps reconcile totals with the Logbook website."""
        key = self.entity_description.key
        t = self._totals
        if key == "lifetime_distance":
            return {
                "work_distance": t.lifetime_distance - t.lifetime_rest_distance,
                "rest_distance": t.lifetime_rest_distance,
            }
        if key == "workout_count" and self._machine == ALL:
            return {"logbook_reported_count": self.coordinator.reported_total}
        return None


class LastWorkoutSensor(Concept2Entity, SensorEntity):
    """A value from the most recent workout on any machine."""

    entity_description: LastWorkoutSensorDescription

    def __init__(
        self,
        coordinator: Concept2Coordinator,
        description: LastWorkoutSensorDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def _workout(self) -> Workout | None:
        return self._data.summary.totals[ALL].last_workout

    @property
    def available(self) -> bool:
        """Unavailable until there is at least one workout."""
        return super().available and self._workout is not None

    @property
    def native_value(self) -> StateType | datetime:
        """Return the value."""
        workout = self._workout
        return self.entity_description.value_fn(workout) if workout else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Full detail of the last workout on the timestamp sensor only."""
        workout = self._workout
        if self.entity_description.key != "last_workout" or workout is None:
            return None
        return {
            "result_id": workout.id,
            "machine": MACHINE_TYPES.get(workout.type, workout.type),
            "workout_type": workout.workout_type,
            "distance_m": workout.distance,
            "time": format_seconds(workout.time),
            "pace": workout.pace_display,
            "stroke_rate": workout.stroke_rate,
            "calories": workout.calories,
            "drag_factor": workout.drag_factor,
            "heart_rate_avg": workout.heart_rate_avg,
            "rest_distance_m": workout.rest_distance or None,
            "comments": workout.comments,
        }


class PersonalBestSensor(Concept2Entity, SensorEntity):
    """Best result for a standard event on one machine.

    Distance events report the best time in seconds. Time events report the
    best distance in metres. Only pieces set up as that exact distance or time
    count.
    """

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:trophy"

    def __init__(
        self, coordinator: Concept2Coordinator, machine: str, event: PbEvent
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, f"{machine}_pb_{event.key}")
        self._key = (machine, event.key)
        self._event = event
        self._attr_name = f"{MACHINE_TYPES.get(machine, machine)} {event.label} PB"
        if event.kind == "distance":
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.SECONDS
            self._attr_suggested_display_precision = 1
        else:
            self._attr_device_class = SensorDeviceClass.DISTANCE
            self._attr_native_unit_of_measurement = UnitOfLength.METERS
            self._attr_suggested_display_precision = 0

    @property
    def _pb(self) -> PersonalBest | None:
        return self._data.summary.pbs.get(self._key)

    @property
    def available(self) -> bool:
        """Unavailable if the qualifying results were deleted."""
        return super().available and self._pb is not None

    def _value(self, w: Workout) -> float:
        return w.time if self._event.kind == "distance" else w.distance

    @property
    def native_value(self) -> StateType:
        """Return the all-time best."""
        pb = self._pb
        return self._value(pb.best) if pb else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Formatted result, date and the current season's best."""
        pb = self._pb
        if pb is None:
            return None
        attrs: dict[str, Any] = {
            "time": format_seconds(pb.best.time),
            "distance_m": pb.best.distance,
            "pace": pb.best.pace_display,
            "date": pb.best.start.isoformat(),
            "result_id": pb.best.id,
        }
        season = pb.season_best
        attrs["season_best_time"] = format_seconds(season.time) if season else None
        attrs["season_best_distance_m"] = season.distance if season else None
        attrs["season_best_date"] = season.start.isoformat() if season else None
        return attrs


class StreakSensor(Concept2Entity, SensorEntity):
    """A streak or consistency value across all machines."""

    entity_description: StreakSensorDescription

    def __init__(
        self, coordinator: Concept2Coordinator, description: StreakSensorDescription
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        """Return the value."""
        return self.entity_description.value_fn(self._data.summary.streaks)
