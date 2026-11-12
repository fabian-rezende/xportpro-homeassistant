"""Ar-condicionado no Modo smart.

O estado é o último comando que a central mandou: o controle remoto do próprio ar não
aparece aqui. Mudar temperatura, modo ou velocidade liga o ar, como no app.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import XPortConfigEntry
from .ac import AcError, AcState, clamp, command, default_state, has_discrete_on
from .entity import XPortEntity, devices_of

MODES = {"cool": HVACMode.COOL, "heat": HVACMode.HEAT, "dry": HVACMode.DRY, "fan": HVACMode.FAN_ONLY, "auto": HVACMode.AUTO}


async def async_setup_entry(hass: HomeAssistant, entry: XPortConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub = entry.runtime_data
    async_add_entities(XPortClimate(hub, d) for d in devices_of(hub, "ar"))


class XPortClimate(XPortEntity, ClimateEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1
    _attr_assumed_state = True

    def __init__(self, hub, dev) -> None:
        super().__init__(hub, dev)
        ac = dev["ac"]
        self._modes: list[str] = ac.get("modes") or []
        self._fans: list[str] = ac.get("fans") or []
        self._attr_min_temp = 16 if ac.get("tmin") is None else ac["tmin"]
        self._attr_max_temp = 30 if ac.get("tmax") is None else ac["tmax"]
        self._attr_hvac_modes = [HVACMode.OFF] + [MODES[m] for m in self._modes if m in MODES]
        self._attr_fan_modes = self._fans
        feats = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        if self._fans:
            feats |= ClimateEntityFeature.FAN_MODE
        self._attr_supported_features = feats

    def _listen_keys(self) -> list[str]:
        return [f"ac:{self._dev['id']}"]

    @property
    def _st(self) -> AcState:
        return clamp(self._dev, self._hub.ac_state(self._dev["id"]) or default_state(self._dev))

    @property
    def hvac_mode(self) -> HVACMode:
        st = self._st
        if not st.power or st.mode >= len(self._modes):
            return HVACMode.OFF
        return MODES.get(self._modes[st.mode], HVACMode.AUTO)

    @property
    def target_temperature(self) -> float:
        return self._st.temp

    @property
    def fan_mode(self) -> str | None:
        st = self._st
        return self._fans[st.fan] if st.fan < len(self._fans) else None

    async def _apply(self, **changes: Any) -> None:
        """Ajuste (liga o ar). No ON discreto, com o ar desligado, liga antes com o comando próprio."""
        d, st = self._dev, self._st
        try:
            if not st.power and has_discrete_on(d):
                await self._send(command(d, replace(st, power=1), turn_on_only=True))
                if not changes:
                    return
                await asyncio.sleep(1.5)
            await self._send(command(d, replace(st, power=1, **changes)))
        except AcError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_turn_on(self) -> None:
        await self._apply()

    async def async_turn_off(self) -> None:
        try:
            await self._send(command(self._dev, replace(self._st, power=0)))
        except AcError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            return
        key = next(k for k, v in MODES.items() if v == hvac_mode)
        await self._apply(mode=self._modes.index(key))

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self._apply(fan=self._fans.index(fan_mode))

    async def async_set_temperature(self, **kwargs: Any) -> None:
        changes: dict[str, Any] = {}
        if (t := kwargs.get(ATTR_TEMPERATURE)) is not None:
            changes["temp"] = round(t)
        if (m := kwargs.get("hvac_mode")) is not None and m != HVACMode.OFF:
            changes["mode"] = self._modes.index(next(k for k, v in MODES.items() if v == m))
        await self._apply(**changes)
