"""Interruptores: relé fora da categoria Iluminação (acionamento, tomada, bomba)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import XPortConfigEntry
from .commands import slider_command, switch_command
from .entity import XPortEntity, devices_of
from .light import is_light


async def async_setup_entry(hass: HomeAssistant, entry: XPortConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub = entry.runtime_data
    async_add_entities(XPortSwitch(hub, d) for d in devices_of(hub, "rele") if not is_light(d))


class XPortSwitch(XPortEntity, SwitchEntity):
    @property
    def is_on(self) -> bool | None:
        st = self._state
        return None if st is None else st["on"]

    async def _set(self, on: bool) -> None:
        k, d = self._kind, self._dev
        if k.sw is not None:
            await self._command({"on": on}, switch_command(k.sw, d, on))
        elif k.sl is not None:
            await self._command({"on": on}, slider_command(k.sl, d, 100 if on else 0))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
