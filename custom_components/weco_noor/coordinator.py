"""DataUpdateCoordinator per l'integrazione WECO Noor (non ufficiale)."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import WecoNoorApiClient, WecoNoorApiError, WecoNoorAuthError
from .const import (
    CONF_BASE_URL,
    CONF_DATALOGGER_SN,
    CONF_DEVICE_SN,
    CONF_DEVICE_TYPE,
    CONF_DTC,
    DEFAULT_SCAN_INTERVAL,
    ENERGY_ENDPOINT_V2,
    ENERGY_ENDPOINT_V3,
    ENERGY_ENDPOINT_V3_DTC,
    ENERGY_EVERY_N_CYCLES,
    TELEMETRY_ENDPOINT_BY_DTC,
    TELEMETRY_ENDPOINT_EV,
    TELEMETRY_ENDPOINT_FALLBACK,
)

_LOGGER = logging.getLogger(__name__)


class WecoNoorCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Interroga periodicamente telemetria ed energia dell'impianto."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{entry.title}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.entry = entry
        session = async_get_clientsession(hass)
        mobile_id = f"ha-{secrets.token_hex(6)}"
        self.client = WecoNoorApiClient(
            session,
            entry.data[CONF_BASE_URL],
            entry.data["email"],
            entry.data["password"],
            mobile_id,
        )
        self._cycle = 0

        device_type = entry.data[CONF_DEVICE_TYPE]
        dtc = entry.data[CONF_DTC]
        device_sn = entry.data[CONF_DEVICE_SN]

        if device_type == "ev":
            self._telemetry_path = TELEMETRY_ENDPOINT_EV.format(sn=device_sn)
            self._energy_path: str | None = None  # non noto per le colonnine EV
        else:
            template = TELEMETRY_ENDPOINT_BY_DTC.get(dtc, TELEMETRY_ENDPOINT_FALLBACK)
            self._telemetry_path = template.format(sn=device_sn)
            self._energy_path = (
                ENERGY_ENDPOINT_V3 if dtc in ENERGY_ENDPOINT_V3_DTC else ENERGY_ENDPOINT_V2
            )

    async def _async_update_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        try:
            data["telemetry"] = await self.client.get_telemetry(self._telemetry_path)

            self._cycle += 1
            fetch_energy = self._energy_path is not None and (
                self._cycle % ENERGY_EVERY_N_CYCLES == 0 or not self.data
            )
            if fetch_energy:
                today = datetime.now().strftime("%Y-%m-%d")
                data["energy"] = await self.client.get_energy(
                    self._energy_path, self.entry.data[CONF_DEVICE_SN], "0", today
                )
            elif self.data:
                data["energy"] = self.data.get("energy", {})
            else:
                data["energy"] = {}
        except WecoNoorAuthError as err:
            raise UpdateFailed(f"Autenticazione fallita: {err}") from err
        except WecoNoorApiError as err:
            raise UpdateFailed(f"Errore API WECO Noor: {err}") from err

        return data
