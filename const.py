"""Constants for the SIRI Next Departures integration."""

DOMAIN = "siri_next_departures"
PLATFORMS = ["sensor"]

# Configuration keys
CONF_NETEX_URL = "netex_url"
CONF_SIRI_ENDPOINT = "siri_endpoint"
CONF_DATASET_ID = "dataset_id"
CONF_STOP_ID = "stop_id"
CONF_STOP_NAME = "stop_name"
CONF_SEARCH_TERM = "search_term"
CONF_MAX_DEPARTURES = "max_departures"
CONF_LINES_REPOSITORY_URL = "lines_repository_url"

# Default values
DEFAULT_NAME = "SIRI Next Departures"
DEFAULT_SCAN_INTERVAL = 60  # seconds
DEFAULT_MAX_DEPARTURES = 5
