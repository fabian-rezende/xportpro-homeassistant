"""Configuração: descoberta pelo DHCP (nome xportpro-xxxxxx) ou IP digitado."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from . import NoCatalog, fetch_catalog
from .const import DEFAULT_PORT, DOMAIN


class XPortConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._host: str = ""
        self._name: str = ""

    async def _probe(self, host: str) -> str | None:
        """Lê o catálogo, fixa o serial como id único e devolve o código do erro (ou None)."""
        try:
            index = await fetch_catalog(async_get_clientsession(self.hass), host)
        except NoCatalog:
            return "no_catalog"
        except ConnectionError:
            return "cannot_connect"
        await self.async_set_unique_id(index.serial)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        self._host = host
        self._name = index.project_name or index.serial
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            error = await self._probe(host)
            if error is None:
                return self.async_create_entry(title=self._name, data={CONF_HOST: host, CONF_PORT: user_input[CONF_PORT]})
            errors["base"] = error
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=(user_input or {}).get(CONF_HOST, "")): str,
                vol.Required(CONF_PORT, default=(user_input or {}).get(CONF_PORT, DEFAULT_PORT)): int,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        error = await self._probe(discovery_info.ip)
        if error is not None:
            return self.async_abort(reason=error)
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title=self._name, data={CONF_HOST: self._host, CONF_PORT: DEFAULT_PORT})
        self._set_confirm_only()
        return self.async_show_form(step_id="confirm", description_placeholders={"name": self._name, "host": self._host})
