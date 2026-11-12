"""Luzes: relé de iluminação, dimmer e RGBW."""
from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS, ATTR_EFFECT, ATTR_RGB_COLOR, ColorMode, LightEntity, LightEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import XPortConfigEntry
from .commands import EFFECTS, rgb_command, slider_command, switch_command
from .entity import XPortEntity, devices_of


def is_light(d: dict) -> bool:
    """Relé só é luz na categoria Iluminação; fora dela vira interruptor (switch.py)."""
    k = d["_c"]
    return k.tipo in ("dimmer", "rgbw") or (k.tipo == "rele" and d["cat"] == 1)


async def async_setup_entry(hass: HomeAssistant, entry: XPortConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub = entry.runtime_data
    async_add_entities(XPortLight(hub, d) for d in devices_of(hub, "rele", "dimmer", "rgbw") if is_light(d))


class XPortLight(XPortEntity, LightEntity):
    def __init__(self, hub, dev) -> None:
        super().__init__(hub, dev)
        k = self._kind
        self._is_rgb = k.tipo == "rgbw" and k.rgb is not None
        if self._is_rgb:
            mode = ColorMode.RGB
            self._attr_supported_features = LightEntityFeature.EFFECT
            self._attr_effect_list = EFFECTS
        elif k.sl is not None and k.tipo in ("dimmer", "rgbw"):
            mode = ColorMode.BRIGHTNESS
        else:
            mode = ColorMode.ONOFF
        self._attr_color_mode = mode
        self._attr_supported_color_modes = {mode}

    @property
    def is_on(self) -> bool | None:
        st = self._state
        return None if st is None else st["on"]

    @property
    def brightness(self) -> int | None:
        st = self._state
        if st is None:
            return None
        if "brightness" in st:
            return st["brightness"]
        if self._attr_color_mode == ColorMode.ONOFF:
            return None
        return round(st["level"] * 255 / 100) if "level" in st else None

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        st = self._state
        return st.get("rgb") if st and self._is_rgb else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        k, d = self._kind, self._dev
        bright = kwargs.get(ATTR_BRIGHTNESS)
        # 1..255 -> 3..100: abaixo de 3 % a central entende como desligar
        pct = None if bright is None else max(3, round(bright * 100 / 255))
        if self._is_rgb:
            lines = []
            if ATTR_RGB_COLOR in kwargs:
                r, g, b = kwargs[ATTR_RGB_COLOR]
                lines.append(rgb_command(k.rgb, d, (r << 16) | (g << 8) | b, 0))
            if ATTR_EFFECT in kwargs and kwargs[ATTR_EFFECT] in EFFECTS:
                lines.append(rgb_command(k.rgb, d, EFFECTS.index(kwargs[ATTR_EFFECT]) + 1, 2))
            cur = self._state or {}
            want = {"on": True, "brightness": cur.get("brightness") or 255, "rgb": kwargs.get(ATTR_RGB_COLOR, cur.get("rgb"))}
            if pct is not None or not lines or not self.is_on:
                gain = 100 if pct is None else pct
                lines.append(rgb_command(k.rgb, d, gain, 1))
                want["brightness"] = round(gain * 255 / 100)
            await self._command(want, *lines)
        elif pct is not None and k.sl is not None:
            await self._command({"on": True, "level": pct}, slider_command(k.sl, d, pct))
        elif k.sw is not None:
            await self._command({"on": True, "level": 100}, switch_command(k.sw, d, True))
        elif k.sl is not None:
            await self._command({"on": True, "level": 100}, slider_command(k.sl, d, 100))

    async def async_turn_off(self, **kwargs: Any) -> None:
        k, d = self._kind, self._dev
        off = {"on": False, "level": 0}
        if self._is_rgb:
            await self._command({"on": False, "brightness": 0, "rgb": (self._state or {}).get("rgb")}, rgb_command(k.rgb, d, 0, 1))
        elif k.sw is not None:
            await self._command(off, switch_command(k.sw, d, False))
        elif k.sl is not None:
            await self._command(off, slider_command(k.sl, d, 0))
