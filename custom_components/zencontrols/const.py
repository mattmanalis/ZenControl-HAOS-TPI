"""Constants for the Zen Controls integration."""

DOMAIN = "zencontrols"
PLATFORMS = ["light"]

CONF_HOST = "host"
CONF_PORT = "port"
CONF_SCAN_GROUPS = "scan_groups"
CONF_SCAN_GEARS = "scan_gears"
CONF_TIMEOUT = "timeout"
CONF_RETRIES = "retries"

DEFAULT_PORT = 5108
DEFAULT_TIMEOUT = 1.5
DEFAULT_RETRIES = 1
DEFAULT_SCAN_GROUPS = True
DEFAULT_SCAN_GEARS = True

COORDINATOR_UPDATE_SECONDS = 5
