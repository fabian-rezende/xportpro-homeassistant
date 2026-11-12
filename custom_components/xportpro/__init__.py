"""Integração Controlart xPortPro: lê o catálogo da central e comanda pela rede local."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later

from .catalog import Index
from .const import DEFAULT_PORT, DOMAIN, MANUFACTURER, RELOAD_DELAY_S
from .hub import XPortHub

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR, Platform.BUTTON, Platform.CLIMATE, Platform.COVER,
    Platform.LIGHT, Platform.MEDIA_PLAYER, Platform.SCENE, Platform.SWITCH,
]

type XPortConfigEntry = ConfigEntry[XPortHub]


class NoCatalog(Exception):
    """A central respondeu, mas está sem o catálogo (slot 3 vazio)."""


async def fetch_json(session: aiohttp.ClientSession, host: str, path: str, tries: int = 3) -> Any:
    """GET http://<central>/<path>. A porta 80 da central pode cortar arquivo grande sob carga: tenta de novo."""
    last: Exception | None = None
    for attempt in range(tries):
        if attempt:
            await asyncio.sleep(1.5)
        try:
            async with session.get(f"http://{host}/{path}", timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 404:
                    raise NoCatalog(path)
                resp.raise_for_status()
                return await resp.json(content_type=None, encoding="utf-8")
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            last = err
    raise ConnectionError(f"{path}: {last}")


async def fetch_catalog(session: aiohttp.ClientSession, host: str) -> Index:
    """O catálogo da casa: o mesmo appdata.json que o app do usuário lê."""
    try:
        data = await fetch_json(session, host, "appdata.json")
    except ConnectionError as err:
        # slot 3 vazio devolve corpo vazio: chega aqui como JSON inválido
        if "Expecting value" in str(err):
            raise NoCatalog("appdata.json") from err
        raise
    if not isinstance(data, dict) or "devices" not in data or not (data.get("project") or {}).get("device_id"):
        raise NoCatalog("appdata.json")
    return Index(data)


async def async_setup_entry(hass: HomeAssistant, entry: XPortConfigEntry) -> bool:
    host = entry.data[CONF_HOST]
    session = async_get_clientsession(hass)
    try:
        index = await fetch_catalog(session, host)
    except (ConnectionError, NoCatalog) as err:
        raise ConfigEntryNotReady(f"catálogo da central {host}: {err}") from err

    fw: str | None = None
    try:
        sync = await fetch_json(session, host, "sync.json", tries=1)
        if isinstance(sync, dict) and sync.get("fw") is not None:
            fw = str(sync["fw"])
    except (ConnectionError, NoCatalog):
        pass  # firmware sem /sync.json: segue sem a versão

    store: dict[str, Any] = hass.data.setdefault(DOMAIN, {}).setdefault(entry.entry_id, {})
    cancel_reload: list[Any] = []

    @callback
    def on_sync_counter(n: int) -> None:
        """O projeto mudou (Sincronizar): relê o catálogo. Uma vez por contador, para não ficar em laço."""
        if store.get("reloaded_for") == n or cancel_reload:
            return

        @callback
        def reload(_now: Any) -> None:
            cancel_reload.clear()
            store["reloaded_for"] = n
            _LOGGER.info("xPortPro %s: projeto alterado (contador %s), relendo o catálogo", host, n)
            hass.config_entries.async_schedule_reload(entry.entry_id)

        cancel_reload.append(async_call_later(hass, RELOAD_DELAY_S, reload))

    hub = XPortHub(host, entry.data.get(CONF_PORT, DEFAULT_PORT), index, on_sync_counter)
    try:
        await hub.start()
    except ConnectionError as err:
        raise ConfigEntryNotReady(str(err)) from err
    entry.runtime_data = hub

    @callback
    def cancel_pending() -> None:
        while cancel_reload:
            cancel_reload.pop()()

    entry.async_on_unload(cancel_pending)

    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, index.serial)},
        manufacturer=MANUFACTURER,
        model="xPortPro",
        name=index.project_name or f"xPortPro {index.serial}",
        serial_number=index.serial,
        sw_version=fw,
        configuration_url=f"http://{host}/",
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _remove_stale(hass, entry, hub)
    return True


def _remove_stale(hass: HomeAssistant, entry: XPortConfigEntry, hub: XPortHub) -> None:
    """Tira do Home Assistant o que saiu do projeto (dispositivo ou cena apagados no xConfig)."""
    ent_reg = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if ent.unique_id not in hub.unique_ids:
            ent_reg.async_remove(ent.entity_id)
    dev_reg = dr.async_get(hass)
    for dev in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if not any(i[0] == DOMAIN and i[1] in hub.device_ids for i in dev.identifiers):
            dev_reg.async_update_device(dev.id, remove_config_entry_id=entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: XPortConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.stop()
    return ok
