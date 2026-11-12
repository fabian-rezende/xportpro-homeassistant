"""TV com a memória da central (controle marcado como TV no xConfig): liga e desliga."""
from __future__ import annotations

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass, MediaPlayerEntity, MediaPlayerEntityFeature, MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import XPortConfigEntry
from .commands import button_command
from .entity import XPortEntity, devices_of


async def async_setup_entry(hass: HomeAssistant, entry: XPortConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub = entry.runtime_data
    async_add_entities(XPortTv(hub, d) for d in devices_of(hub, "tv"))


class XPortTv(XPortEntity, MediaPlayerEntity):
    _attr_device_class = MediaPlayerDeviceClass.TV

    def __init__(self, hub, dev) -> None:
        super().__init__(hub, dev)
        feats = MediaPlayerEntityFeature(0)
        if self._kind.tv.get("ligar"):
            feats |= MediaPlayerEntityFeature.TURN_ON
        if self._kind.tv.get("desligar"):
            feats |= MediaPlayerEntityFeature.TURN_OFF
        self._attr_supported_features = feats

    @property
    def state(self) -> MediaPlayerState | None:
        st = self._state
        if st is None:
            return None
        return MediaPlayerState.ON if st["on"] else MediaPlayerState.OFF

    async def async_turn_on(self) -> None:
        await self._send(button_command(self._kind.tv["ligar"], self._dev))

    async def async_turn_off(self) -> None:
        await self._send(button_command(self._kind.tv["desligar"], self._dev))
