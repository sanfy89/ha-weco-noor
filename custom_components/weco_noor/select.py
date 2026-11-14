"""Entita' select per cambiare la modalita' di lavoro della batteria (WORK_MODE).

Usa l'endpoint di scrittura scoperto da analisi statica dell'app
(api/setting/common/battery/setting), non documentato da WECO: puo'
cambiare senza preavviso, e a differenza delle entita' sensore QUESTA
MODIFICA DAVVERO IL FUNZIONAMENTO DELL'INVERTER. Verificare il
comportamento a mano (es. da Postman) prima di affidarsi ad automazioni
che la usino.
"""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import WecoNoorApiError
from .const import CONF_DEVICE_ALIAS, CONF_DEVICE_SN, DOMAIN
from .coordinator import WecoNoorCoordinator

_LOGGER = logging.getLogger(__name__)

# Stesse quattro modalita' viste nel codice dell'app (mappa workMode).
# Tenute tutte e quattro, anche se all'uso interessano solo "Modalita'
# automatica" e "Peak Shaving", perche' il dispositivo potrebbe trovarsi
# in uno degli altri due stati (es. Battery Priority) e un'entita' select
# mostra male uno stato che non compare tra le opzioni.
# Confermati da analisi statica specifica per la famiglia Senergy (dtc
# 109/110/111): "Time of Use" NON fa parte di WORK_MODE per questa famiglia,
# e' una chiave separata (TIME_OF_USE) non ancora implementata qui.
_OPTION_TO_CODE = {
    "Modalita' automatica": "0",
    "Peak Shaving": "2",
    "Battery Priority": "3",
}
_CODE_TO_OPTION = {v: k for k, v in _OPTION_TO_CODE.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: WecoNoorCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([WecoNoorWorkModeSelect(coordinator, entry)])


class WecoNoorWorkModeSelect(CoordinatorEntity[WecoNoorCoordinator], SelectEntity):
    """Cambia WORK_MODE tramite l'API cloud (non Bluetooth)."""

    _attr_options = list(_OPTION_TO_CODE.keys())

    def __init__(self, coordinator: WecoNoorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_work_mode_select"
        self._attr_name = f"{entry.data[CONF_DEVICE_ALIAS]} Modalita' di lavoro (imposta)"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_DEVICE_SN])},
            name=entry.data[CONF_DEVICE_ALIAS],
            manufacturer="WECO",
        )

    @property
    def current_option(self) -> str | None:
        telemetry = self.coordinator.data.get("telemetry", {})
        raw = telemetry.get("workMode")
        if raw is None:
            return None
        return _CODE_TO_OPTION.get(str(raw))

    async def async_select_option(self, option: str) -> None:
        _LOGGER.warning("WECO select: async_select_option chiamato con option=%s", option)
        new_code = _OPTION_TO_CODE[option]
        telemetry = self.coordinator.data.get("telemetry", {})
        current_raw = str(telemetry.get("workMode", ""))

        try:
            await self.coordinator.client.set_setting(
                device_sn=self._entry.data[CONF_DEVICE_SN],
                key="WORK_MODE",
                value=new_code,
                original_value=current_raw,
                show_name="Work Mode",
            )
        except WecoNoorApiError as err:
            _LOGGER.error("Impossibile impostare WORK_MODE: %s", err)
            raise

        # Il dato vero arrivera' al prossimo polling, ma aggiorniamo subito
        # l'interfaccia per non lasciarla sul valore vecchio nel frattempo.
        self.coordinator.data.setdefault("telemetry", {})["workMode"] = new_code
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
