"""Cenas da central: ativar no Home Assistant dispara a cena (sendScene)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.scene import Scene
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import XPortConfigEntry
from .commands import scene_command
from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: XPortConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub = entry.runtime_data
    async_add_entities(XPortScene(hub, s) for s in hub.index.scenes)


class XPortScene(Scene):
    _attr_should_poll = False

    def __init__(self, hub, scene: dict) -> None:
        self._hub = hub
        self._scene_id = scene["id"]
        self._attr_name = scene.get("name") or f"Cena {scene['id']}"
        self._attr_unique_id = f"{hub.index.serial}_s{scene['id']}"
        self._attr_entity_registry_enabled_default = bool(scene.get("visible", 1))
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, hub.index.serial)})
        hub.unique_ids.add(self._attr_unique_id)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._hub.listen("conn", self._changed))

    @callback
    def _changed(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self._hub.connected

    async def async_activate(self, **kwargs: Any) -> None:
        try:
            await self._hub.send(scene_command(self._scene_id))
        except (ConnectionError, OSError) as err:
            raise HomeAssistantError(f"Central xPortPro sem conexão: {err}") from err
