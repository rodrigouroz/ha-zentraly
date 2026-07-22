"""Constants for Zentraly integration."""
from homeassistant.const import Platform

DOMAIN = "zentraly"
PLATFORMS = [
    Platform.CLIMATE,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SENSOR,
]

# API
API_BASE_URL = "https://ztprdrestservicesv2.azurewebsites.net"
API_LOGIN_ENDPOINT = "/Login"
API_APP_ENDPOINT = "/App"
API_IOT_COMMAND_ENDPOINT = "/IOTCommand/Run"

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
CMD_SET_OFFSET_TEMP = "setOffsetTemp"
CMD_GET_DATES_DEVICE = "getDatesDevice"

# Config IDs for getConfig — full set (schedules, away temp, water setpoints…)
CONFIG_IDS = [
    "targetTemp",
    "temperature",
    "thermostatMode",
    "humidity",
    "ssid",
    "rssi",
    "otASF",
    "vs",
    "schedules",
    "tAway",
    "tempCale",
    "tempSani",
    "lock",
    "service",
    "output",
]

# Weekday bitmask for schedules. Catalog coDays numbers Monday=1..Sunday=7,
# so the schedule "days" field is a 7-bit mask with Monday as the lowest bit.
WEEKDAY_BITS = {
    "mon": 1,
    "tue": 2,
    "wed": 4,
    "thu": 8,
    "fri": 16,
    "sat": 32,
    "sun": 64,
}
ALL_DAYS_MASK = 127

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

# Service to set the weekly schedule
SERVICE_SET_SCHEDULE = "set_schedule"
ATTR_ENTITY_ID = "entity_id"
ATTR_SCHEDULE = "schedule"
ATTR_DAYS = "days"
ATTR_START = "start"
ATTR_TEMPERATURE = "temperature"

# Calibration offset / away temperature limits (°C)
OFFSET_MIN = -5.0
OFFSET_MAX = 5.0
OFFSET_STEP = 0.1
AWAY_TEMP_MIN = 5.0
AWAY_TEMP_MAX = 30.0
AWAY_TEMP_STEP = 0.5
