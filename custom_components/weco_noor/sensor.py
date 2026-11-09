"""Sensori per l'integrazione WECO Noor (non ufficiale).

Le entita' vengono create dinamicamente leggendo i campi numerici
restituiti dall'API al primo aggiornamento, perche' lo schema esatto
delle risposte (nomi e unita' di misura dei campi) non e' documentato
da WECO ed e' stato solo in parte osservato durante lo sviluppo di
questa integrazione. I nomi dei sensori corrispondono quindi al nome
del campo come restituito dal server.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ALIAS, CONF_DEVICE_SN, DOMAIN, EXCLUDE_KEYS
from .coordinator import WecoNoorCoordinator

# Euristiche sul nome del campo per assegnare un'unita' di misura plausibile.
# Non confermate con la documentazione ufficiale: controllare i valori in
# Impostazioni -> Dispositivi e servizi -> Entita' dopo il primo avvio.
_UNIT_HINTS: list[tuple[str, str | None]] = [
    ("power", "W"),
    ("soc", "%"),
    ("percentage", "%"),
    ("electrical", "kWh"),
    ("energy", "kWh"),
    ("temp", "°C"),
    ("voltage", "V"),
    ("current", "A"),
    ("frequency", "Hz"),
]


def _guess_unit(key: str) -> str | None:
    lowered = key.lower()
    for hint, unit in _UNIT_HINTS:
        if hint in lowered:
            return unit
    return None


def _flatten_numeric(prefix: str, data: Any, out: dict[str, Any]) -> None:
    """Estrae ricorsivamente i campi numerici da un dizionario di risposta."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key in EXCLUDE_KEYS:
                continue
            _flatten_numeric(f"{prefix}.{key}" if prefix else key, value, out)
    elif isinstance(data, (int, float)) and not isinstance(data, bool):
        out[prefix] = data
    elif isinstance(data, bool):
        out[prefix] = "on" if data else "off"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: WecoNoorCoordinator = hass.data[DOMAIN][entry.entry_id]

    flat: dict[str, Any] = {}
    for source in ("telemetry", "energy"):
        _flatten_numeric("", coordinator.data.get(source, {}), flat)
        # usa un dict temporaneo per tenere traccia della provenienza
    entities = []
    seen_keys: set[str] = set()
    for source in ("telemetry", "energy"):
        per_source: dict[str, Any] = {}
        _flatten_numeric("", coordinator.data.get(source, {}), per_source)
        for key in per_source:
            unique = f"{source}:{key}"
            if unique in seen_keys:
                continue
            seen_keys.add(unique)
            entities.append(WecoNoorSensor(coordinator, entry, source, key))

    async_add_entities(entities)


class WecoNoorSensor(CoordinatorEntity[WecoNoorCoordinator], SensorEntity):
    """Un sensore generico per un campo numerico restituito dall'API."""

    def __init__(
        self, coordinator: WecoNoorCoordinator, entry: ConfigEntry, source: str, field: str
    ) -> None:
        super().__init__(coordinator)
        self._source = source
        self._field = field
        self._attr_unique_id = f"{entry.entry_id}_{source}_{field}"
        self._attr_name = f"{entry.data[CONF_DEVICE_ALIAS]} {source} {field}"
        self._attr_native_unit_of_measurement = _guess_unit(field)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_DEVICE_SN])},
            name=entry.data[CONF_DEVICE_ALIAS],
            manufacturer="WECO",
        )

    @property
    def native_value(self) -> Any:
        flat: dict[str, Any] = {}
        _flatten_numeric("", self.coordinator.data.get(self._source, {}), flat)
        return flat.get(self._field)
