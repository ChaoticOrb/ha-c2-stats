"""Base entity for Concept2 Logbook."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import Concept2Coordinator, Concept2Data


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
