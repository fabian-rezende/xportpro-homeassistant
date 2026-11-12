"""Cortinas e persianas.

Na central, posição 0 = ABERTA e 100 = FECHADA. No Home Assistant é o contrário
(100 = aberta), então a posição é invertida nos dois sentidos.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.cover import ATTR_POSITION, CoverDeviceClass, CoverEntity, CoverEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import XPortConfigEntry
from .commands import button_command, slider_command
from .entity import XPortEntity, devices_of


async def async_setup_entry(hass: HomeAssistant, entry: XPortConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub = entry.runtime_data
    async_add_entities(XPortCover(hub, d) for d in devices_of(hub, "cortina"))


class XPortCover(XPortEntity, CoverEntity):
    _attr_device_class = CoverDeviceClass.CURTAIN

    def __init__(self, hub, dev) -> None:
        super().__init__(hub, dev)
        k = self._kind
        feats = CoverEntityFeature(0)
        if k.sl is not None or "abrir" in k.cortina:
            feats |= CoverEntityFeature.OPEN
        if k.sl is not None or "fechar" in k.cortina:
            feats |= CoverEntityFeature.CLOSE
        if "parar" in k.cortina:
            feats |= CoverEntityFeature.STOP
        if k.sl is not None:
            feats |= CoverEntityFeature.SET_POSITION
        self._attr_supported_features = feats
        # cortina só de botões: a central não sabe onde ela está
        self._attr_assumed_state = self._b is None

    @property
    def current_cover_position(self) -> int | None:
        st = self._state
        return None if st is None else 100 - st["position"]

    @property
    def is_closed(self) -> bool | None:
        st = self._state
        return None if st is None else st["position"] >= 100

    async def _move(self, papel: str, closed_pct: int) -> None:
        k, d = self._kind, self._dev
        if papel in k.cortina:
            await self._send(button_command(k.cortina[papel], d))
        elif k.sl is not None:
            await self._send(slider_command(k.sl, d, closed_pct))

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._move("abrir", 0)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._move("fechar", 100)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._send(button_command(self._kind.cortina["parar"], self._dev))

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        await self._send(slider_command(self._kind.sl, self._dev, 100 - kwargs[ATTR_POSITION]))
