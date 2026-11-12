"""Botões de controle (IR, RF, serial): cada botão do dispositivo no app vira um botão aqui.

Ficam de fora os botões que já são ação de outra entidade: os da cortina (abrir, parar,
fechar), o liga/desliga da TV e as combinações do ar smart (ac:...).
"""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import XPortConfigEntry
from .commands import button_command
from .entity import XPortEntity


def free_buttons(d: dict) -> list[dict]:
    k = d["_c"]
    used = {id(c) for c in k.cortina.values()} | {id(c) for c in k.tv.values() if c}
    return [
        c for c in k.botoes
        if id(c) not in used and not str(c.get("alias") or "").startswith(("ac:", "blind:"))
    ]


async def async_setup_entry(hass: HomeAssistant, entry: XPortConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub = entry.runtime_data
    async_add_entities(XPortButton(hub, d, c) for d in hub.index.devices for c in free_buttons(d))


class XPortButton(XPortEntity, ButtonEntity):
    def __init__(self, hub, dev, cmd) -> None:
        super().__init__(hub, dev, f"_c{cmd['id']}")
        self._cmd = cmd
        self._b = None  # botão não depende do estado do módulo
        self._attr_name = str(cmd.get("text") or cmd.get("alias") or f"Comando {cmd['id']}").strip()

    async def async_press(self) -> None:
        await self._send(button_command(self._cmd, self._dev))
