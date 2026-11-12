"""Base das entidades: um dispositivo do catálogo vira um dispositivo do Home Assistant.

O comportamento segue o app do usuário (userapp/src/motor.js):

  - módulo que não responde NÃO bloqueia o controle: a entidade só fica indisponível quando
    a conexão com a central cai;
  - ao comandar, vale o estado pedido por 4 s; sem confirmação do módulo, volta ao último
    estado conhecido;
  - sem nenhuma leitura, o estado fica desconhecido durante a janela de leitura e depois
    vale o padrão: apagado (luz, interruptor, sensor) ou aberta (cortina com posição).
"""
from __future__ import annotations

import time
from typing import Any

from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_call_later

from .catalog import Binding, Kind, describe
from .const import DOMAIN, MANUFACTURER
from .hub import XPortHub

# sem confirmação do módulo nesse tempo, volta ao último estado conhecido (WAIT_MS do app)
OPTIMISTIC_S = 4.0
# o Home Assistant novo liga o dispositivo ao pai por via_device_id; o antigo, por via_device
_VIA_BY_ID = "via_device_id" in DeviceInfo.__annotations__


def devices_of(hub: XPortHub, *tipos: str) -> list[dict]:
    return [d for d in hub.index.devices if d["_c"].tipo in tipos]


def default_state(kind: Kind) -> dict[str, Any] | None:
    """Estado de quem nunca respondeu, como no app. None = desconhecido."""
    if kind.b is None or kind.b.rf or kind.b.tv:
        return None  # cortina RF e TV: a central só informa quando sabe
    if kind.tipo == "cortina":
        return {"position": 0}
    if kind.tipo == "dimmer":
        return {"on": False, "level": 0}
    if kind.tipo == "rgbw":
        return {"on": False, "brightness": 0, "rgb": None}
    if kind.tipo == "sensor":
        return {"on": False, "class": None, "low_battery": False}
    return {"on": False}


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
        self._optimistic: tuple[dict[str, Any], float] | None = None
        self._optimistic_timer: CALLBACK_TYPE | None = None
        serial = hub.index.serial
        dev_key = f"{serial}_d{dev['id']}"
        self._attr_unique_id = dev_key + suffix
        # o que o instalador escondeu do app entra desativado
        self._attr_entity_registry_enabled_default = bool(dev.get("visible", 1))
        info = DeviceInfo(
            identifiers={(DOMAIN, dev_key)},
            name=dev.get("name") or f"Dispositivo {dev['id']}",
            manufacturer=MANUFACTURER,
            model=(hub.index.types.get(dev.get("type")) or {}).get("name"),
            suggested_area=hub.index.room_name(dev.get("room")),
        )
        if _VIA_BY_ID:
            if hub.device_entry_id:
                info["via_device_id"] = hub.device_entry_id
        else:
            info["via_device"] = (DOMAIN, serial)  # type: ignore[typeddict-unknown-key]
        self._attr_device_info = info
        hub.unique_ids.add(self._attr_unique_id)
        hub.device_ids.add(dev_key)

    def _listen_keys(self) -> list[str]:
        return [self._b.addr] if self._b else ["conn"]

    async def async_added_to_hass(self) -> None:
        for key in self._listen_keys():
            self.async_on_remove(self._hub.listen(key, self._changed))
        self.async_on_remove(self._drop_optimistic)

    @callback
    def _changed(self) -> None:
        """Chegou estado do módulo (ou a conexão mudou): o estado pedido deixa de valer."""
        self._drop_optimistic()
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        # módulo que não responde não bloqueia: o comando sempre pode ser tentado
        return self._hub.connected

    @property
    def _state(self) -> dict[str, Any] | None:
        """Estado do dispositivo (None = desconhecido)."""
        if self._optimistic is not None:
            if time.monotonic() < self._optimistic[1]:
                return self._optimistic[0]
            self._optimistic = None
        if not self._b:
            return None
        got = self._hub.value(self._b)
        if got:
            return describe(self._dev, got[0], got[1])
        return default_state(self._kind) if self._hub.settled else None

    @callback
    def _drop_optimistic(self) -> None:
        self._optimistic = None
        if self._optimistic_timer is not None:
            self._optimistic_timer()
            self._optimistic_timer = None

    async def _send(self, *lines: str) -> None:
        try:
            await self._hub.send(*lines)
        except (ConnectionError, OSError) as err:
            raise HomeAssistantError(f"Central xPortPro sem conexão: {err}") from err

    async def _command(self, state: dict[str, Any], *lines: str) -> None:
        """Envia e mostra o estado pedido até o módulo confirmar (ou por 4 s)."""
        await self._send(*lines)
        self._drop_optimistic()
        self._optimistic = (state, time.monotonic() + OPTIMISTIC_S)

        @callback
        def expired(_now: Any) -> None:
            self._optimistic_timer = None
            self._optimistic = None
            self.async_write_ha_state()

        self._optimistic_timer = async_call_later(self.hass, OPTIMISTIC_S, expired)
        self.async_write_ha_state()
