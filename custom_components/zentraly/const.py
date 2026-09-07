"""Constants for Zentraly integration."""
from homeassistant.const import Platform

DOMAIN = "zentraly"
PLATFORMS = [Platform.CLIMATE]

# API
API_BASE_URL = "https://ztprdrestservicesv2.azurewebsites.net"
API_LOGIN_ENDPOINT = "/Login"
API_APP_ENDPOINT = "/App"
API_IOT_COMMAND_ENDPOINT = "/app/Action"
API_FIREBASE_KEY = "f06d3a055c7066de31d6d1ae583d7bd18d99840bc74d14aaed63860054004f15"
API_FIREBASE_IV = "eeed3a055c7066de31d6d1ae27017bd1"
ZENTRALY_APP_VERSION = "7.1.6"

# Client metadata reported in the encrypted Firebase header.
# The backend refuses to store a push-token row whose client identifies itself as
# Home Assistant: the login fails on a CHECK constraint named
# CK_UserFBTokens_strUserFBToken_NoHaIn. Reporting ordinary mobile client
# metadata is what the previous "HomeAssistant"/"Integration" values replaced.
CLIENT_MOBILE_TRADE = "samsung"
CLIENT_MOBILE_MODEL = "SM-A515F"
CLIENT_MOBILE_OS_VERSION = "13"

# API operations
DC_OPER_RUN_IOT = 28

# Auth prefixes
AUTH_PREFIX_LOGIN = "ztv2Auth"
AUTH_PREFIX_TOKEN = "ztv2Token"

# Device types
DEVICE_TYPE_THERMOSTAT = 2

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
CONF_DEVICE_GUID = "device_guid"
