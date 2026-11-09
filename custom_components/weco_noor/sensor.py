"""Sensori per l'integrazione WECO Noor (non ufficiale).

Le entita' vengono create dinamicamente leggendo i campi numerici
restituiti dall'API al primo aggiornamento, perche' lo schema esatto
delle risposte non e' documentato da WECO. Per i nomi di campo visti
nell'app (schermata principale e statistiche energia, per i dispositivi
di tipo inverter/cabinet, famiglia a cui appartiene anche "Senergy",
dtc 109/110/111) viene usata la mappa _EXACT_FIELDS qui sotto, con
nome descrittivo, unita', device_class e state_class gia' corrette per
comparire nella scheda Energia. Per ogni altro campo non riconosciuto
si ricade su un'euristica basata sul nome, meno affidabile.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ALIAS, CONF_DEVICE_SN, DOMAIN, EXCLUDE_KEYS
from .coordinator import WecoNoorCoordinator


@dataclass
class _Classification:
    unit: str | None
    device_class: SensorDeviceClass | None
    state_class: SensorStateClass | None
    friendly_name: str | None = None


# Campi osservati nel codice dell'app per la schermata principale (telemetria
# in tempo reale, funzione interna "xa") e per le statistiche energia
# (funzione interna "Fa"), condivisi dai dispositivi di tipo inverter/cabinet,
# famiglia a cui appartiene anche "Senergy" (dtc 109/110/111, il tuo
# dispositivo). Non e' documentazione ufficiale WECO: se un valore non
# corrisponde a quanto mostra l'app, segnalalo cosi' si corregge la voce.
_EXACT_FIELDS: dict[str, _Classification] = {
    # --- Telemetria in tempo reale ---
    "pvPower": _Classification(UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "Potenza fotovoltaico"),
    "generatorPower": _Classification(UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "Potenza generatore"),
    "gridPower": _Classification(UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "Potenza scambiata con la rete"),
    "batteryPower": _Classification(UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "Potenza batteria"),
    "batPower": _Classification(UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "Potenza batteria"),
    "loadPower": _Classification(UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "Potenza carico"),
    "pvInverterPower": _Classification(UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "Potenza inverter FV aggiuntivo"),
    "externalLoadPower": _Classification(UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "Potenza carico esterno"),
    "evPower": _Classification(UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "Potenza colonnina EV"),
    "batSoc": _Classification(PERCENTAGE, SensorDeviceClass.BATTERY, SensorStateClass.MEASUREMENT, "Stato di carica batteria"),
    "batVoltage": _Classification(UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "Tensione batteria"),
    # --- Energia (totali del periodo selezionato: giorno/mese/anno) ---
    # state_class "total_increasing" perche' sono contatori del periodo che
    # ripartono da zero, non un totale storico mai azzerato.
    "pvElectrical": _Classification(UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, "Produzione fotovoltaica (periodo)"),
    "pvSelfUseTotalEnergy": _Classification(UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, "Autoconsumo fotovoltaico (periodo)"),
    "pvTrade": _Classification(UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, "Fotovoltaico ceduto alla rete (periodo)"),
    "gridTotalEnergy": _Classification(UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, "Energia ceduta alla rete (periodo)"),
    "purchasingTotalEnergy": _Classification(UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, "Energia prelevata dalla rete (periodo)"),
    "batCharge": _Classification(UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, "Energia di carica batteria (periodo)"),
    "batDischarge": _Classification(UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, "Energia di scarica batteria (periodo)"),
    "loadElectrical": _Classification(UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, "Consumo domestico (periodo)"),
    "generatorTotalEnergy": _Classification(UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, "Energia generatore (periodo)"),
    "pvSelfUsePercentage": _Classification(PERCENTAGE, None, SensorStateClass.MEASUREMENT, "Percentuale autoconsumo fotovoltaico"),
    "batSelfUsePercentage": _Classification(PERCENTAGE, None, SensorStateClass.MEASUREMENT, "Percentuale autoconsumo da batteria"),
    "gridSelfUsePercentage": _Classification(PERCENTAGE, None, SensorStateClass.MEASUREMENT, "Percentuale autoconsumo da rete"),
}

# Euristica di riserva per campi non presenti nella mappa esatta sopra.
# Ordine dal piu' specifico al piu' generico: "power" va controllato prima
# di "current", perche' un nome come "currentPower" deve finire in "power".
_HINTS: list[tuple[str, _Classification]] = [
    ("power", _Classification(UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT)),
    ("soc", _Classification(PERCENTAGE, SensorDeviceClass.BATTERY, SensorStateClass.MEASUREMENT)),
    ("percentage", _Classification(PERCENTAGE, None, SensorStateClass.MEASUREMENT)),
    ("voltage", _Classification(UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT)),
    ("frequency", _Classification(UnitOfFrequency.HERTZ, SensorDeviceClass.FREQUENCY, SensorStateClass.MEASUREMENT)),
    ("temp", _Classification(UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT)),
    ("electrical", _Classification(UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING)),
    ("energy", _Classification(UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING)),
    ("trade", _Classification(UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING)),
    ("current", _Classification(UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT)),
]


def _classify(key: str) -> _Classification:
    # Il campo puo' comparire con un prefisso di percorso (es. "foo.pvPower"
    # per strutture annidate): si confronta solo l'ultimo pezzo con la mappa
    # esatta, ma si conserva il percorso completo come nome del campo.
    last = key.rsplit(".", 1)[-1]
    if last in _EXACT_FIELDS:
        return _EXACT_FIELDS[last]

    lowered = last.lower()
    for hint, classification in _HINTS:
        if hint in lowered:
            return classification
    return _Classification(None, None, None)


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

        value = self.native_value
        if isinstance(value, str):
            # Campi booleani (es. "online") convertiti in "on"/"off": niente
            # unita' ne' classe, sono stringhe di stato, non misure.
            classification = _Classification(None, None, None)
        else:
            classification = _classify(field)

        label = classification.friendly_name or field
        self._attr_name = f"{entry.data[CONF_DEVICE_ALIAS]} {label}"
        self._attr_native_unit_of_measurement = classification.unit
        self._attr_device_class = classification.device_class
        self._attr_state_class = classification.state_class
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
