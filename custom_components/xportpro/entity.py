"""Base das entidades: um dispositivo do catálogo vira um dispositivo do Home Assistant."""
from __future__ import annotations

from typing import Any

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .catalog import Binding, Kind, describe
from .const import DOMAIN, MANUFACTURER
from .hub import XPortHub


def devices_of(hub: XPortHub, *tipos: str) -> list[dict]:
    return [d for d in hub.index.devices if d["_c"].tipo in tipos]


class XPortEntity(Entity):
    """Entidade ligada a um dispositivo do catálogo."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_name = None

    def __init__(self, hub: XPortHub, dev: dict, suffix: str = "") -> None:
        self._hub = hub
        self._dev = dev
        self._kind: Kind = dev["_c"]
        self._b: Binding | None = self._kind.b
        serial = hub.index.serial
        dev_key = f"{serial}_d{dev['id']}"
        self._attr_unique_id = dev_key + suffix
        # o que o instalador escondeu do app entra desativado
        self._attr_entity_registry_enabled_default = bool(dev.get("visible", 1))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dev_key)},
            name=dev.get("name") or f"Dispositivo {dev['id']}",
            manufacturer=MANUFACTURER,
            model=(hub.index.types.get(dev.get("type")) or {}).get("name"),
            suggested_area=hub.index.room_name(dev.get("room")),
            via_device=(DOMAIN, serial),
        )
        hub.unique_ids.add(self._attr_unique_id)
        hub.device_ids.add(dev_key)

    def _listen_keys(self) -> list[str]:
        return [self._b.addr] if self._b else ["conn"]

    async def async_added_to_hass(self) -> None:
        for key in self._listen_keys():
            self.async_on_remove(self._hub.listen(key, self._changed))

    @callback
    def _changed(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self._hub.connected and (self._b is None or self._hub.module_ok(self._b.addr))

    @property
    def _state(self) -> dict[str, Any] | None:
        """Estado do dispositivo pela última linha do módulo (None = ainda sem leitura)."""
        if not self._b:
            return None
        got = self._hub.value(self._b)
        return describe(self._dev, got[0], got[1]) if got else None

    async def _send(self, *lines: str) -> None:
        try:
            await self._hub.send(*lines)
        except (ConnectionError, OSError) as err:
            raise HomeAssistantError(f"Central xPortPro sem conexão: {err}") from err
