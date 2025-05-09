"""The SIRI Next Departures integration."""

import asyncio
import logging
from datetime import timedelta
from typing import Optional, Dict, List, Any

import httpx
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_NETEX_URL,
    CONF_SIRI_ENDPOINT,
    CONF_DATASET_ID,
    CONF_STOP_ID,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_MAX_DEPARTURES,
)
from .utils import load_stops_from_url, get_departures_for_stops  # Renamed function

_LOGGER = logging.getLogger(__name__)


# Define a central coordinator class
class SiriGlobalDataUpdateCoordinator(DataUpdateCoordinator):
    """Global DataUpdateCoordinator for SIRI departures."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self.siri_endpoint = entry.data[CONF_SIRI_ENDPOINT]
        self.dataset_id = entry.data[CONF_DATASET_ID]

        # Determine a single limit to pass to the API for all stops.
        # This could be the default, or a max of configured sensor limits if desired.
        # For simplicity, using default for now. The actual per-sensor limit can be enforced by the sensor itself if needed.
        self.api_limit_per_stop = DEFAULT_MAX_DEPARTURES

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({entry.title})",
            update_interval=timedelta(
                seconds=entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
            ),
        )

    async def _async_update_data(self) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        """Fetch data for all configured stops."""
        configured_sensors = self.entry.options.get("sensors", [])
        stop_ids_to_fetch = [
            sensor_conf[CONF_STOP_ID]
            for sensor_conf in configured_sensors
            if sensor_conf.get(CONF_STOP_ID)
        ]

        if not stop_ids_to_fetch:
            _LOGGER.info("No stop_ids configured for fetching.")
            return {}

        try:
            departures_by_stop = await get_departures_for_stops(
                self.hass,
                self.siri_endpoint,
                self.dataset_id,
                stop_ids_to_fetch,
                limit_per_stop=self.api_limit_per_stop,
            )
            if departures_by_stop is None:  # API error
                raise UpdateFailed(
                    "Failed to fetch departures from SIRI API (returned None)"
                )
            return departures_by_stop
        except httpx.HTTPStatusError as err:
            raise UpdateFailed(f"Error communicating with SIRI API: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error fetching SIRI data: %s", err, exc_info=True)
            raise UpdateFailed(f"Unexpected error fetching data: {err}") from err


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SIRI Next Departures from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    netex_url = entry.data[CONF_NETEX_URL]
    # Stops are loaded once and stored. If NETEX changes, integration needs reload.
    stops_data = await load_stops_from_url(hass, netex_url)
    if not stops_data:
        _LOGGER.error(
            "Failed to load stops from NETEX URL: %s. Integration will not be set up.",
            netex_url,
        )
        # Optionally, raise ConfigEntryNotReady if stops are essential for any operation.
        # For now, we allow setup, but sensors might not find their stops in config flow if this fails.
        # Or, better, prevent setup if stops cannot be loaded as config flow relies on it.
        return False  # Prevents setup if stops can't be loaded

    # Create and store the global coordinator
    coordinator = SiriGlobalDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()  # Initial refresh

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "stops": stops_data,  # Store loaded stops for config_flow to use
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(options_update_listener_global))

    return True


async def options_update_listener_global(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    _LOGGER.debug("SIRI integration options updated for %s, reloading.", entry.entry_id)
    # Reload the integration to apply new options (e.g., new sensors, scan_interval)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
