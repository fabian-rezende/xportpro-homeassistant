"""Sensores: abertura e presença (rádio 433) e sensor ON/OFF."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import XPortConfigEntry
from .entity import XPortEntity, devices_of


async def async_setup_entry(hass: HomeAssistant, entry: XPortConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub = entry.runtime_data
    async_add_entities(XPortSensor(hub, d) for d in devices_of(hub, "sensor") if d["_c"].b is not None)


class XPortSensor(XPortEntity, BinarySensorEntity):
    @property
    def is_on(self) -> bool | None:
        st = self._state
        return None if st is None else st["on"]

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        st = self._state
        cls = st.get("class") if st else None
        return BinarySensorDeviceClass(cls) if cls else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        st = self._state
        return {"bateria_fraca": st["low_battery"]} if st and "low_battery" in st else None
