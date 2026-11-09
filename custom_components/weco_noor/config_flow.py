"""Config flow per l'integrazione WECO Noor (non ufficiale)."""
from __future__ import annotations

import logging
import secrets
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WecoNoorApiClient, WecoNoorAuthError, WecoNoorApiError
from .const import (
    ALTERNATE_BASE_URL,
    CONF_BASE_URL,
    CONF_DATALOGGER_SN,
    CONF_DEVICE_ALIAS,
    CONF_DEVICE_SN,
    CONF_DEVICE_TYPE,
    CONF_DTC,
    CONF_PLANT_ID,
    CONF_PLANT_NAME,
    DEFAULT_BASE_URL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class WecoNoorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Gestisce login, scelta impianto e scelta dispositivo."""

    VERSION = 1

    def __init__(self) -> None:
        self._client: WecoNoorApiClient | None = None
        self._email: str | None = None
        self._password: str | None = None
        self._base_url: str = DEFAULT_BASE_URL
        self._plants: list[dict[str, Any]] = []
        self._plant_id: str | None = None
        self._plant_name: str | None = None
        self._devices: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._email = user_input[CONF_EMAIL]
            self._password = user_input[CONF_PASSWORD]
            self._base_url = user_input[CONF_BASE_URL]

            session = async_get_clientsession(self.hass)
            mobile_id = f"ha-{secrets.token_hex(6)}"
            self._client = WecoNoorApiClient(
                session, self._base_url, self._email, self._password, mobile_id
            )
            try:
                await self._client.login()
                self._plants = await self._client.list_plants()
            except WecoNoorAuthError:
                errors["base"] = "invalid_auth"
            except (WecoNoorApiError, aiohttp.ClientError):
                errors["base"] = "cannot_connect"
            else:
                if not self._plants:
                    errors["base"] = "no_plants"
                else:
                    return await self.async_step_plant()

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): vol.In(
                    [DEFAULT_BASE_URL, ALTERNATE_BASE_URL]
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_plant(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}
        options = {
            str(p.get("id")): p.get("plantName") or p.get("name") or str(p.get("id"))
            for p in self._plants
        }

        if user_input is not None:
            self._plant_id = user_input[CONF_PLANT_ID]
            self._plant_name = options.get(self._plant_id, self._plant_id)
            try:
                self._devices = await self._client.list_devices(self._plant_id)
            except WecoNoorApiError:
                errors["base"] = "cannot_connect"
            else:
                if not self._devices:
                    errors["base"] = "no_devices"
                else:
                    return await self.async_step_device()

        if len(options) == 1 and not errors:
            # Un solo impianto: lo seleziono senza chiedere.
            self._plant_id = next(iter(options))
            self._plant_name = options[self._plant_id]
            self._devices = await self._client.list_devices(self._plant_id)
            if self._devices:
                return await self.async_step_device()
            errors["base"] = "no_devices"

        schema = vol.Schema({vol.Required(CONF_PLANT_ID): vol.In(options)})
        return self.async_show_form(step_id="plant", data_schema=schema, errors=errors)

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}
        options = {}
        by_key = {}
        for dev in self._devices:
            key = str(dev.get("deviceSn") or dev.get("dataLoggerSn"))
            label = f"{dev.get('alias', key)} (dtc {dev.get('dtc')})"
            options[key] = label
            by_key[key] = dev

        if user_input is not None:
            dev = by_key[user_input[CONF_DEVICE_SN]]
            device_sn = str(dev.get("deviceSn") or dev.get("dataLoggerSn"))
            datalogger_sn = str(dev.get("dataLoggerSn") or device_sn)
            dtc = str(dev.get("dtc"))
            alias = dev.get("alias") or device_sn
            # L'app tratta come colonnina EV i dispositivi senza "children" di
            # tipo inverter noto: qui ci basiamo solo sul dtc 65535, osservato
            # per una Charge Station durante lo sviluppo di questa integrazione.
            device_type = "ev" if dtc == "65535" else "inverter"

            await self.async_set_unique_id(f"{self._plant_id}_{device_sn}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"WECO Noor - {alias}",
                data={
                    CONF_EMAIL: self._email,
                    CONF_PASSWORD: self._password,
                    CONF_BASE_URL: self._base_url,
                    CONF_PLANT_ID: self._plant_id,
                    CONF_PLANT_NAME: self._plant_name,
                    CONF_DEVICE_SN: device_sn,
                    CONF_DATALOGGER_SN: datalogger_sn,
                    CONF_DTC: dtc,
                    CONF_DEVICE_TYPE: device_type,
                    CONF_DEVICE_ALIAS: alias,
                },
            )

        schema = vol.Schema({vol.Required(CONF_DEVICE_SN): vol.In(options)})
        return self.async_show_form(step_id="device", data_schema=schema, errors=errors)
