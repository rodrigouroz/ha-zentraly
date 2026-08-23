"""Constants for Zentraly integration."""
from homeassistant.const import Platform

DOMAIN = "zentraly"
PLATFORMS = [Platform.CLIMATE]

# API
API_BASE_URL = "https://ztprdrestservicesv2.azurewebsites.net"
API_LOGIN_ENDPOINT = "/Login"
API_APP_ENDPOINT = "/App"
API_IOT_COMMAND_ENDPOINT = "/IOTCommand/Run"

# Auth prefixes
AUTH_PREFIX_LOGIN = "ztv2Auth"
AUTH_PREFIX_TOKEN = "ztv2Token"

# Device types confirmed to expose the thermostat data model
DEVICE_TYPES_THERMOSTAT = {2, 6}

# Temperature conversion (API uses centidegrees)
TEMP_SCALE = 100

# Commands
CMD_GET_CONFIG = "getConfig"
CMD_SET_CONFIG = "setConfig"
CMD_GET_OFFSET_TEMP = "getOffsetTemp"

# Config IDs for getConfig
CONFIG_IDS = [
    "targetTemp",
    "temperature",
    "thermostatMode",
    "humidity",
    "ssid",
    "rssi",
    "output",
    "lock",
    "service"
]

# Thermostat modes (from API)
# Mode 1 = Heat, Mode 4 = Off (based on captured traffic)
HVAC_MODE_MAP = {
    1: "heat",
    2: "cool",  # Assuming
    3: "auto",  # Assuming
    4: "off"
}

HVAC_MODE_REVERSE = {v: k for k, v in HVAC_MODE_MAP.items()}

# Update interval
SCAN_INTERVAL_SECONDS = 60

# Conf keys
CONF_USER_ID = "user_id"
CONF_TOKEN = "token"
