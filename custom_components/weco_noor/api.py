"""Client HTTP per l'API cloud (non ufficiale) di WECO Noor.

Ricavato da analisi statica dell'app Android com.weco.noor v1.3.0.
Non esiste un endpoint di refresh o logout noto: quando il token scade
il client rifa' automaticamente il login una volta.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


class WecoNoorAuthError(Exception):
    """Credenziali non valide o 2FA richiesta (non supportata)."""


class WecoNoorApiError(Exception):
    """Errore generico nella chiamata API."""


def _operation_time() -> str:
    """Riproduce il formato data usato dall'app, es. 2026-11-09 14:03:07(UTC+01:00)."""
    now = datetime.now().astimezone()
    offset = now.utcoffset() or timezone.utc.utcoffset(now)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    hh, mm = divmod(total_minutes, 60)
    return now.strftime(f"%Y-%m-%d %H:%M:%S(UTC{sign}{hh:02d}:{mm:02d})")


class WecoNoorApiClient:
    """Wrapper minimale sopra l'API HTTP del cloud WECO Noor."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        email: str,
        password: str,
        mobile_id: str,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._email = email
        self._password = password
        self._mobile_id = mobile_id
        self._token: str | None = None

    def _headers(self) -> dict[str, str]:
        headers = {
            "Logintool": "Phone",
            "System": "HomeAssistant 1.0",
            "Operationtime": _operation_time(),
            "Accept-Language": "en",
        }
        if self._token:
            headers["Authorization"] = self._token
        return headers

    async def login(self) -> None:
        """Esegue il login e salva il token di sessione."""
        form = aiohttp.FormData()
        form.add_field("email", self._email)
        form.add_field("password", self._password)
        form.add_field("phoneOSType", "HomeAssistant")
        form.add_field("system", "HomeAssistant 1.0")
        form.add_field("loginTime", _operation_time())
        form.add_field("mobileId", self._mobile_id)
        form.add_field("encryption", "false")

        url = f"{self._base_url}/api/login"
        async with self._session.post(url, data=form, headers=self._headers()) as resp:
            data = await resp.json(content_type=None)

        if not data.get("success"):
            if data.get("data", {}).get("need2fa"):
                raise WecoNoorAuthError(
                    "L'account richiede l'autenticazione a due fattori (2FA), "
                    "non supportata da questa integrazione."
                )
            raise WecoNoorAuthError(data.get("errMessage") or "Login fallito")

        token = data.get("data", {}).get("token")
        if not token:
            raise WecoNoorAuthError("Login riuscito ma token assente nella risposta")
        self._token = token

    async def _request(self, method: str, path: str, *, retry: bool = True, **kwargs) -> dict[str, Any]:
        if not self._token:
            await self.login()

        url = f"{self._base_url}/{path.lstrip('/')}"
        async with self._session.request(
            method, url, headers=self._headers(), **kwargs
        ) as resp:
            try:
                data = await resp.json(content_type=None)
            except Exception as err:  # risposta non JSON
                raise WecoNoorApiError(f"Risposta non valida da {path}: {err}") from err

        status_code = data.get("statusCode")
        if status_code and str(status_code) != "200":
            # Il token potrebbe essere scaduto: un solo nuovo tentativo dopo login.
            if retry:
                _LOGGER.debug("Possibile token scaduto, nuovo login e ripeto la chiamata")
                self._token = None
                await self.login()
                return await self._request(method, path, retry=False, **kwargs)
            raise WecoNoorApiError(data.get("errMessage") or f"Errore {status_code} su {path}")

        return data

    async def get(self, path: str) -> dict[str, Any]:
        return await self._request("GET", path)

    async def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", path, json=body)

    # --- Chiamate di alto livello --------------------------------------

    async def list_plants(self) -> list[dict[str, Any]]:
        data = await self.post("api/plant/homePlantPage", {"keyWord": "", "pageIndex": 1, "pageSize": 50})
        payload = data.get("data")
        if isinstance(payload, dict):
            return payload.get("list") or payload.get("records") or []
        if isinstance(payload, list):
            return payload
        return []

    async def list_devices(self, plant_id: str) -> list[dict[str, Any]]:
        data = await self.get(f"api/plant/getDeviceList/{plant_id}")
        payload = data.get("data") or {}
        return payload.get("tree") or []

    async def get_telemetry(self, path: str) -> dict[str, Any]:
        data = await self.get(path)
        return data.get("data") or {}

    async def get_energy(self, path: str, device_sn: str, query_type: str, date: str) -> dict[str, Any]:
        data = await self.post(
            path,
            {"serialNumberList": [device_sn], "queryType": query_type, "date": date},
        )
        return data.get("data") or {}
