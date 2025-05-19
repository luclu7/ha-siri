"""Config flow for SIRI Next Departures integration."""

import logging
from typing import Any, Dict

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_NETEX_URL,
    CONF_SIRI_ENDPOINT,
    CONF_DATASET_ID,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    CONF_SEARCH_TERM,
    CONF_MAX_DEPARTURES,
    CONF_LINES_REPOSITORY_URL,
    DEFAULT_MAX_DEPARTURES,
)
from .utils import (
    load_stops_from_url,
    normalizeString,
)  # We will implement normalizeString in utils.py

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NETEX_URL): str,
        vol.Required(CONF_SIRI_ENDPOINT): str,
        vol.Required(CONF_DATASET_ID): str,
        vol.Optional(CONF_LINES_REPOSITORY_URL): str,
    }
)


class SiriNextDeparturesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SIRI Next Departures."""

    VERSION = 1

    async def async_step_user(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: Dict[str, str] = {}
        if user_input is not None:
            # Here you would normally validate the input, e.g., try to connect
            # For now, we'll assume the input is valid
            # You could also use self.hass.async_add_executor_job to run blocking validation

            # For a real integration, you'd fetch the NETEX file here to ensure it's valid
            # and perhaps to allow the user to select a "name" for this configuration instance.
            # For now, we'll use the dataset_id or a fixed name.
            title = f"SIRI Departures ({user_input[CONF_DATASET_ID]})"

            return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Get the options flow for this handler."""
        return SiriNextDeparturesOptionsFlowHandler(config_entry)


class SiriNextDeparturesOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle an options flow for SIRI Next Departures sensors."""

    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        super().__init__()
        self.all_stops_data = []
        self._search_term: str | None = None
        self._selected_stop_id: str | None = None
        self._selected_stop_name: str | None = None
        self._max_departures: int = DEFAULT_MAX_DEPARTURES
        # self.options will be initialized in the first step (e.g., async_step_init)

    async def async_step_init(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options: show menu."""
        # Initialize self.options here, where self.config_entry is available
        self.options = dict(self.config_entry.options)

        if user_input is not None:
            # Mise à jour du référentiel des lignes
            if CONF_LINES_REPOSITORY_URL in user_input:
                self.options[CONF_LINES_REPOSITORY_URL] = user_input[CONF_LINES_REPOSITORY_URL]
                
            # Retourner au menu principal ou sauvegarder directement
            if user_input.get("next_step") == "menu":
                return self.async_show_menu(
                    step_id="init",
                    menu_options=["search_stop", "remove_sensor", "update_lines_repository"],
                )
            else:
                return self.async_create_entry(title="", data=self.options)

        # Afficher le menu principal
        return self.async_show_menu(
            step_id="init",
            menu_options=["search_stop", "remove_sensor", "update_lines_repository"],
        )

    async def async_step_update_lines_repository(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        """Étape pour mettre à jour l'URL du référentiel des lignes."""
        errors: Dict[str, str] = {}
        
        if user_input is not None:
            self.options[CONF_LINES_REPOSITORY_URL] = user_input.get(CONF_LINES_REPOSITORY_URL, "")
            
            # Sauvegarder les modifications et recharger l'intégration
            try:
                result = self.async_create_entry(title="", data=self.options)
                _LOGGER.debug("Référentiel des lignes mis à jour.")
                
                # Recharger l'intégration pour appliquer les changements
                if self.hass and self.config_entry:
                    _LOGGER.info(
                        "Reloading config entry %s to apply changes.",
                        self.config_entry.entry_id,
                    )
                    self.hass.async_create_task(
                        self.hass.config_entries.async_reload(
                            self.config_entry.entry_id
                        )
                    )
                return result
            except Exception as e:
                _LOGGER.error(
                    "Error saving options: %s", e, exc_info=True
                )
                errors["base"] = "save_options_failed"
        
        # Préparer les valeurs par défaut
        current_url = self.config_entry.options.get(
            CONF_LINES_REPOSITORY_URL,
            self.config_entry.data.get(CONF_LINES_REPOSITORY_URL, "")
        )
        
        return self.async_show_form(
            step_id="update_lines_repository",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_LINES_REPOSITORY_URL, 
                    default=current_url
                ): str,
            }),
            errors=errors,
            description_placeholders={
                "current_url": current_url or "Non configuré"
            },
        )

    async def _ensure_stops_loaded(self) -> bool:
        """Helper to load stops if not already available."""
        if not self.all_stops_data:
            _LOGGER.info("Attempting to load stops during options flow...")
            # Stops should be in hass.data, loaded by __init__.py
            entry_data = self.hass.data[DOMAIN].get(self.config_entry.entry_id)
            if entry_data:
                self.all_stops_data = entry_data.get("stops", [])

            if not self.all_stops_data:
                _LOGGER.warning(
                    "Stops data not found in hass.data for entry %s. Trying to load from URL.",
                    self.config_entry.entry_id,
                )
                # As a fallback, try to load them directly. This might be slow in UI.
                try:
                    self.all_stops_data = await load_stops_from_url(
                        self.hass, self.config_entry.data[CONF_NETEX_URL]
                    )
                except Exception as e:
                    _LOGGER.error(
                        "Failed to load stops from URL during options flow: %s", e
                    )
                    return False  # Abort or show error if stops can't be loaded

            if not self.all_stops_data:
                _LOGGER.error(
                    "Failed to load stops for entry %s", self.config_entry.entry_id
                )
                return False
        return True

    async def async_step_search_stop(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: User enters search term for a stop."""
        errors: Dict[str, str] = {}

        if not await self._ensure_stops_loaded():
            return self.async_abort(reason="cannot_load_stops_for_search")

        if user_input is not None:
            self._search_term = user_input[CONF_SEARCH_TERM]
            return await self.async_step_select_stop()

        return self.async_show_form(
            step_id="search_stop",
            data_schema=vol.Schema({vol.Required(CONF_SEARCH_TERM): str}),
            errors=errors,
            description_placeholders={"stop_count": len(self.all_stops_data)},
        )

    async def async_step_select_stop(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: User selects a stop from search results."""
        errors: Dict[str, str] = {}

        if not self.all_stops_data:  # Should have been loaded in previous step
            _LOGGER.error("Stops not loaded before select_stop step.")
            return self.async_abort(reason="cannot_load_stops")

        normalized_search = normalizeString(self._search_term or "")

        matching_stops = {
            stop[
                "id"
            ]: f"{stop.get('name', 'Unknown Name')} ({stop.get('id')}) - {stop.get('transportMode','N/A')}"
            + (
                f" (Correspondances: {', '.join(stop.get('otherTransportModes',[]))})"
                if stop.get("otherTransportModes")
                else ""
            )
            + (
                f" ({stop.get('cityName', '')})"
                if stop.get("cityName")
                else ""
            )
            for stop in self.all_stops_data
            if normalized_search in stop.get("normalizedName", "")
            or normalized_search in stop.get("normalizedId", "")
        }

        if not matching_stops:
            errors["base"] = "no_stops_found"
            # Go back to search step by not advancing and showing the form again
            # Or, could return self.async_show_form for search_stop with an error message
            self._search_term = None  # Clear search term to allow new search
            return self.async_show_form(
                step_id="search_stop",  # Show search form again
                data_schema=vol.Schema({vol.Required(CONF_SEARCH_TERM): str}),
                errors=errors,
                description_placeholders={"stop_count": len(self.all_stops_data)},
            )

        if user_input is not None:
            self._selected_stop_id = user_input[CONF_STOP_ID]
            # Find the selected stop's original name for pre-filling
            selected_stop_details = next(
                (s for s in self.all_stops_data if s["id"] == self._selected_stop_id),
                None,
            )
            self._selected_stop_name = (
                selected_stop_details["name"]
                if selected_stop_details
                else self._selected_stop_id
            )
            return await self.async_step_sensor_options()

        return self.async_show_form(
            step_id="select_stop",
            data_schema=vol.Schema(
                {vol.Required(CONF_STOP_ID): vol.In(matching_stops)}
            ),
            errors=errors,
            description_placeholders={"search_term": self._search_term},
        )

    async def async_step_sensor_options(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: User sets sensor name and other options."""
        errors: Dict[str, str] = {}
        _LOGGER.debug(
            "Entering async_step_sensor_options, current options: %s", self.options
        )

        if user_input is not None:
            stop_name = user_input.get(
                CONF_STOP_NAME, self._selected_stop_name
            )  # Use selected name or default
            max_departures = user_input.get(CONF_MAX_DEPARTURES, DEFAULT_MAX_DEPARTURES)

            # Ensure "sensors" key exists and is a list
            if "sensors" not in self.options or not isinstance(
                self.options.get("sensors"), list
            ):
                self.options["sensors"] = []

            sensors = self.options["sensors"]  # Get a direct reference

            if any(
                sensor[CONF_STOP_ID] == self._selected_stop_id for sensor in sensors
            ):
                errors["base"] = "already_configured_stop"
            else:
                new_sensor_config = {
                    CONF_STOP_ID: self._selected_stop_id,
                    CONF_STOP_NAME: stop_name,
                    CONF_MAX_DEPARTURES: max_departures,
                }
                _LOGGER.debug("Adding new sensor config: %s", new_sensor_config)
                sensors.append(new_sensor_config)
                # self.options["sensors"] = sensors # This line is redundant if sensors is a direct reference

                _LOGGER.debug("Options before saving: %s", self.options)
                try:
                    result = self.async_create_entry(title="", data=self.options)
                    _LOGGER.debug("async_create_entry called. Result: %s", result)
                    # After successful save, config_entry.options should be updated
                    # Let's log it to see, though it might not reflect immediately in this instance
                    _LOGGER.debug(
                        "config_entry.options after save attempt: %s",
                        self.config_entry.options,
                    )
                except Exception as e:
                    _LOGGER.error(
                        "Error calling async_create_entry: %s", e, exc_info=True
                    )
                    errors["base"] = "save_options_failed"
                    # Potentially return the form here if saving failed, to not lose context
                    # For now, we'll let it fall through to the form display, but with an error
                    # Or, re-raise or handle as appropriate: return self.async_abort(reason="save_failed")

                if "base" not in errors:  # If no error during save
                    # Clean up instance variables for next run
                    self._search_term = None
                    self._selected_stop_id = None
                    self._selected_stop_name = None

                    # Explicitly trigger a reload of the config entry to apply changes
                    if self.hass and self.config_entry:
                        _LOGGER.info(
                            "Reloading config entry %s to apply changes.",
                            self.config_entry.entry_id,
                        )
                        self.hass.async_create_task(
                            self.hass.config_entries.async_reload(
                                self.config_entry.entry_id
                            )
                        )
                    return result  # Return the result from async_create_entry

        # Pre-fill stop name if available
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_STOP_NAME,
                    default=self._selected_stop_name or self._selected_stop_id,
                ): str,
                vol.Optional(
                    CONF_MAX_DEPARTURES,
                    default=self.options.get(
                        CONF_MAX_DEPARTURES, DEFAULT_MAX_DEPARTURES
                    ),
                ): cv.positive_int,
            }
        )

        return self.async_show_form(
            step_id="sensor_options",
            data_schema=schema,
            errors=errors,
            description_placeholders={"stop_id": self._selected_stop_id},
        )

    async def async_step_remove_sensor(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle removing a sensor."""
        errors: Dict[str, str] = {}
        _LOGGER.debug(
            "Entering async_step_remove_sensor, current options: %s", self.options
        )
        current_sensors = self.options.get("sensors", [])

        if not current_sensors:
            _LOGGER.info("No sensors to remove.")
            return self.async_abort(reason="no_sensors_to_remove")

        # Create a list of choices for the form
        # Format: {stop_id: "Sensor Name (stop_id)"}
        sensor_choices = {
            sensor[
                CONF_STOP_ID
            ]: f"{sensor.get(CONF_STOP_NAME, sensor[CONF_STOP_ID])} ({sensor[CONF_STOP_ID]})"
            for sensor in current_sensors
        }

        if user_input is not None:
            stop_id_to_remove = user_input["sensor_to_remove"]

            _LOGGER.debug(
                "Attempting to remove sensor with stop_id: %s", stop_id_to_remove
            )
            # Filter out the sensor to remove
            updated_sensors = [
                sensor
                for sensor in current_sensors
                if sensor[CONF_STOP_ID] != stop_id_to_remove
            ]

            if len(updated_sensors) == len(current_sensors):
                _LOGGER.warning(
                    "Sensor with stop_id %s not found for removal.", stop_id_to_remove
                )
                errors["base"] = "sensor_not_found_for_removal"
            else:
                self.options["sensors"] = updated_sensors
                _LOGGER.info(
                    f"Sensor with stop_id {stop_id_to_remove} marked for removal."
                )

            _LOGGER.debug("Options before saving removal: %s", self.options)

            if "base" not in errors:
                try:
                    result = self.async_create_entry(title="", data=self.options)
                    _LOGGER.debug(
                        "async_create_entry called for removal. Result: %s", result
                    )
                    _LOGGER.debug(
                        "config_entry.options after removal save attempt: %s",
                        self.config_entry.options,
                    )
                except Exception as e:
                    _LOGGER.error(
                        "Error calling async_create_entry for removal: %s",
                        e,
                        exc_info=True,
                    )
                    errors["base"] = "save_options_failed"

                if "base" not in errors:
                    # Explicitly trigger a reload of the config entry to apply changes
                    if self.hass and self.config_entry:
                        _LOGGER.info(
                            "Reloading config entry %s to apply removal changes.",
                            self.config_entry.entry_id,
                        )
                        self.hass.async_create_task(
                            self.hass.config_entries.async_reload(
                                self.config_entry.entry_id
                            )
                        )
                    return result

        # Schema for the form
        remove_schema = vol.Schema(
            {vol.Required("sensor_to_remove"): vol.In(sensor_choices)}
        )

        return self.async_show_form(
            step_id="remove_sensor",
            data_schema=remove_schema,
            errors=errors,
            description_placeholders={  # For the description in translations if needed
                "sensor_count": len(current_sensors)
            },
        )


# We need to add normalizeString to utils.py or define it here if it's simple enough
# For now, assuming it will be in utils.py, used by a potential search function for stops.
