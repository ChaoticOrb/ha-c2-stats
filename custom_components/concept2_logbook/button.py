"""Buttons for Concept2 Logbook."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import Concept2ConfigEntry, Concept2Coordinator
from .entity import Concept2Entity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class Concept2ButtonDescription(ButtonEntityDescription):
    """A button that triggers a sync."""

    press_fn: Callable[[Concept2Coordinator], Awaitable[None]]


BUTTONS: tuple[Concept2ButtonDescription, ...] = (
    Concept2ButtonDescription(
        key="sync_now",
        translation_key="sync_now",
        icon="mdi:sync",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c: c.async_refresh(),
    ),
    Concept2ButtonDescription(
        key="full_resync",
        translation_key="full_resync",
        icon="mdi:database-sync",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c: c.async_full_resync(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Concept2ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up buttons."""
    async_add_entities(
        Concept2Button(entry.runtime_data, description) for description in BUTTONS
    )


class Concept2Button(Concept2Entity, ButtonEntity):
    """Trigger a sync with the Logbook."""

    entity_description: Concept2ButtonDescription

    def __init__(
        self, coordinator: Concept2Coordinator, description: Concept2ButtonDescription
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        """Run the sync."""
        await self.entity_description.press_fn(self.coordinator)
