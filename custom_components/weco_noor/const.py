"""Costanti per l'integrazione WECO Noor (non ufficiale)."""
from __future__ import annotations

DOMAIN = "weco_noor"

CONF_BASE_URL = "base_url"
CONF_PLANT_ID = "plant_id"
CONF_PLANT_NAME = "plant_name"
CONF_DEVICE_SN = "device_sn"
CONF_DATALOGGER_SN = "datalogger_sn"
CONF_DTC = "dtc"
CONF_DEVICE_TYPE = "device_type"
CONF_DEVICE_ALIAS = "device_alias"

DEFAULT_BASE_URL = "http://noor.olpess-api.com"
ALTERNATE_BASE_URL = "http://noor.olipowerota.com"

DEFAULT_SCAN_INTERVAL = 60  # secondi, telemetria in tempo reale
ENERGY_EVERY_N_CYCLES = 5   # l'energia viene aggiornata una volta ogni N cicli di telemetria

# Mappatura dtc (codice modello) -> endpoint di telemetria in tempo reale.
# Ricavata dall'analisi statica dell'app ufficiale (versione 1.3.0). Non e'
# un'API documentata da WECO: puo' cambiare senza preavviso.
_DTC_SMART5K0 = {"4096", "4097"}
_DTC_THMAX = {"4101", "4104"}
_DTC_THINV = {"4098", "4099", "4102", "4103"}
_DTC_MICINV = {"4100"}
_DTC_TQINV = {"61181", "105", "106", "107"}
_DTC_SENERGY = {"109", "110", "111", "65532"}
_DTC_STK = {"112", "113", "114"}

TELEMETRY_ENDPOINT_BY_DTC = {
    **{d: "api/home/getSmart5K0Home/{sn}" for d in _DTC_SMART5K0},
    **{d: "api/home/getThMaxHomeV2/{sn}" for d in _DTC_THMAX},
    **{d: "api/home/getThInverterHomeV2/{sn}" for d in _DTC_THINV},
    **{d: "api/home/getMicInvHome/{sn}" for d in _DTC_MICINV},
    **{d: "api/home/getTQInverterHomeV2/{sn}" for d in _DTC_TQINV},
    **{d: "api/home/getSenergyHome/{sn}" for d in _DTC_SENERGY},
    **{d: "api/home/getStkHome/{sn}" for d in _DTC_STK},
}
TELEMETRY_ENDPOINT_FALLBACK = "api/home/getMgrnInverterV2/{sn}"
TELEMETRY_ENDPOINT_EV = "api/home/getChargePoint/{sn}"

# Endpoint energia: V3 per la famiglia ThMax, V2 per tutti gli altri inverter.
# Non verificato con una risposta reale per tutte le famiglie: se la risposta
# e' vuota o in errore, provare a cambiare endpoint in const.py.
ENERGY_ENDPOINT_V3_DTC = _DTC_THMAX
ENERGY_ENDPOINT_V2 = "api/home/getInverterHomeEnergyV2"
ENERGY_ENDPOINT_V3 = "api/home/getInverterHomeEnergyV3"

# Chiavi da non trasformare in sensori numerici (identificativi, non misure).
EXCLUDE_KEYS = {
    "id", "deviceSn", "dataLogSn", "dataLoggerSn", "plantId", "serialNumber",
    "serialNumberList", "sn", "dtc", "statusCode", "success", "errCode",
    "errMessage", "parentId", "type",
}
