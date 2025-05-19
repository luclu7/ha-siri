"""Sensor platform for SIRI Next Departures."""

import logging
from datetime import timedelta, datetime
import asyncio
from typing import List, Dict, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
import httpx  # For API calls in the coordinator
import xmltodict  # For parsing SIRI XML response

from .const import (
    DOMAIN,
    CONF_SIRI_ENDPOINT,
    CONF_DATASET_ID,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    DEFAULT_SCAN_INTERVAL,
    CONF_MAX_DEPARTURES,
    DEFAULT_MAX_DEPARTURES,
)

# from .utils import get_next_departures # We use the global coordinator now

_LOGGER = logging.getLogger(__name__)

# SCAN_INTERVAL is now effectively managed by the global coordinator based on options
# We keep it here if individual sensors had specific logic, but they don't anymore.
# SCAN_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform from a config entry."""
    _LOGGER.info("Setting up SIRI sensor platform for entry ID: %s", entry.entry_id)

    # Get the global coordinator from hass.data
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    configured_sensors_opts = entry.options.get("sensors", [])
    _LOGGER.info(
        "Found %s configured sensors in options.", len(configured_sensors_opts)
    )
    _LOGGER.debug("Configured_sensors_opts details: %s", configured_sensors_opts)

    sensors_to_add = []
    if configured_sensors_opts:
        for sensor_conf in configured_sensors_opts:
            stop_id = sensor_conf.get(CONF_STOP_ID)
            stop_name = sensor_conf.get(CONF_STOP_NAME, stop_id)
            # max_departures for API call is handled globally by coordinator for now.
            # The per-sensor CONF_MAX_DEPARTURES can be used for display filtering if needed.
            sensor_specific_max_departures = sensor_conf.get(
                CONF_MAX_DEPARTURES, DEFAULT_MAX_DEPARTURES
            )

            if not stop_id:
                _LOGGER.warning(
                    "Sensor configuration found without a stop_id: %s. Skipping.",
                    sensor_conf,
                )
                continue

            _LOGGER.info(
                "Setting up sensor for stop_id: %s, name: %s (display_limit: %s)",
                stop_id,
                stop_name,
                sensor_specific_max_departures,
            )

            sensors_to_add.append(
                SiriNextDepartureSensor(
                    coordinator,
                    entry.entry_id,
                    stop_id,
                    stop_name,
                    sensor_specific_max_departures,
                )
            )
    else:
        _LOGGER.info("No sensors configured in options to add.")

    if sensors_to_add:
        _LOGGER.info("Adding %s sensor(s) to Home Assistant.", len(sensors_to_add))
        async_add_entities(sensors_to_add)
    else:
        _LOGGER.info("No sensors to add to Home Assistant.")

    # The options listener in __init__.py now handles reloading the whole integration
    # So, no need for a separate options_update_listener here in sensor.py
    _LOGGER.info("SIRI Sensor platform setup complete for entry ID: %s", entry.entry_id)


# The SiriDataUpdateCoordinator is now global in __init__.py, remove local one.
# class SiriDataUpdateCoordinator(DataUpdateCoordinator): ...


class SiriNextDepartureSensor(CoordinatorEntity, SensorEntity):
    """Representation of a SIRI Next Departure sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry_id: str,
        stop_id: str,
        stop_name: str,
        display_limit: int,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator)  # Pass the global coordinator
        self._entry_id = entry_id
        self._stop_id = stop_id
        self._stop_name = stop_name
        self._display_limit = display_limit
        self._attr_name = f"Next Departures - {self._stop_name}"
        self._attr_unique_id = f"{entry_id}_{self._stop_id}"
        self._attr_icon = "mdi:bus-clock"

    @property
    def _departures_for_this_stop(self) -> List[Dict[str, Any]]:
        """Helper to get departures for this specific sensor from global coordinator data."""
        if self.coordinator.data and isinstance(self.coordinator.data, dict):
            return self.coordinator.data.get(self._stop_id, [])
        return []

    @property
    def state(self):
        """Return the state of the sensor."""
        departures = self._departures_for_this_stop
        if departures:
            # Apply display limit if needed, though API limit is global
            # For state, we just take the first one available.
            return departures[0].get("expected_departure_time")
        return "No departures"

    @property
    def extra_state_attributes(self):
        """Return other attributes of the sensor."""
        departures = self._departures_for_this_stop

        # Apply the sensor-specific display limit to the departures shown in attributes
        limited_departures = (
            departures[: self._display_limit] if self._display_limit > 0 else departures
        )

        attributes = {
            "stop_id": self._stop_id,
            "stop_name": self._stop_name,
            "configured_display_limit": self._display_limit,
            "departures": limited_departures,
        }
        return attributes

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Check if coordinator has data AND if data for this specific stop_id is present.
        # The coordinator itself might be successful but might not have data for THIS stop if API returned partial/empty for it.
        return (
            super().available
            and self.coordinator.data is not None
            and self._stop_id in self.coordinator.data
        )
