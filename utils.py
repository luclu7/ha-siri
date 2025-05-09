"""Utility functions for the SIRI Next Departures integration."""

import logging
import httpx
import xmltodict
from typing import List, Dict, Any, Optional
from unidecode import unidecode
from homeassistant.helpers.httpx_client import get_async_client

_LOGGER = logging.getLogger(__name__)

NETEX_NAMESPACE = "http://www.netex.org.uk/netex"
SIRI_NAMESPACE = "http://www.siri.org.uk/siri"

# Define a simple Stop type for clarity, similar to your TypeScript Stop interface
# but as a TypedDict for Python type hinting if desired, or just use dicts.
# For now, using Dict[str, Any] for simplicity in the function signature.
Stop = Dict[str, Any]  # Replace with TypedDict if strict typing is preferred later


def normalizeString(input_str: str) -> str:
    """Normalize a string by removing diacritics, converting to lowercase, and removing spaces/hyphens."""
    if not input_str:
        return ""
    # Transliterate (remove diacritics/accents)
    normalized = unidecode(input_str)
    # Convert to lowercase
    normalized = normalized.lower()
    # Replace spaces and hyphens with nothing (remove them)
    normalized = normalized.replace(" ", "").replace("-", "")
    return normalized


async def load_stops_from_url(hass, netex_url: str) -> List[Stop]:
    """Load stops from a NETEX XML file URL."""
    _LOGGER.info(f"Loading stops from NETEX URL: {netex_url}")
    try:
        # Use the Home Assistant provided httpx client
        client = get_async_client(hass)
        response = await client.get(netex_url)
        response.raise_for_status()  # Raise an exception for HTTP errors

        xml_data = response.text
        # Use force_list with namespaced keys
        data = xmltodict.parse(
            xml_data,
            process_namespaces=True,  # Keep this to handle namespaces generally
            namespaces={},  # This tells xmltodict to use full URI if no mapping, or default ns if defined
            force_list=(
                f"{NETEX_NAMESPACE}:Quay",
                f"{NETEX_NAMESPACE}:StopPlace",
                f"{NETEX_NAMESPACE}:KeyValue",
            ),
            # attribute_prefix='@' # This is usually the default, matching your sample
        )

        stops: List[Stop] = []

        try:
            publication_delivery = data.get(f"{NETEX_NAMESPACE}:PublicationDelivery")
            if not publication_delivery:
                _LOGGER.error(
                    f"'{NETEX_NAMESPACE}:PublicationDelivery' not found in NETEX XML."
                )
                return []

            data_objects = publication_delivery.get(f"{NETEX_NAMESPACE}:dataObjects")
            if not data_objects:
                _LOGGER.error(
                    f"'{NETEX_NAMESPACE}:dataObjects' not found in NETEX XML."
                )
                return []

            general_frame = data_objects.get(f"{NETEX_NAMESPACE}:GeneralFrame")
            if not general_frame:
                _LOGGER.error(
                    f"'{NETEX_NAMESPACE}:GeneralFrame' not found in NETEX XML."
                )
                return []

            members = general_frame.get(f"{NETEX_NAMESPACE}:members")
            if not members:
                _LOGGER.error(f"'{NETEX_NAMESPACE}:members' not found in NETEX XML.")
                return []

            quays = members.get(f"{NETEX_NAMESPACE}:Quay", [])
            stop_places = members.get(f"{NETEX_NAMESPACE}:StopPlace", [])

            _LOGGER.info(
                f"Found {len(quays)} quays and {len(stop_places)} stop places in NETEX file."
            )

            for quay in quays:
                quay_id = quay.get("@id")
                quay_name_obj = quay.get(f"{NETEX_NAMESPACE}:Name")
                quay_name = (
                    quay_name_obj
                    if isinstance(quay_name_obj, str)
                    else (
                        quay_name_obj.get("#text", "Unknown Quay")
                        if isinstance(quay_name_obj, dict)
                        else "Unknown Quay"
                    )
                )

                transport_mode = quay.get(f"{NETEX_NAMESPACE}:TransportMode", "unknown")
                site_ref_obj = quay.get(f"{NETEX_NAMESPACE}:SiteRef")
                site_ref = (
                    site_ref_obj.get("@ref") if isinstance(site_ref_obj, dict) else None
                )

                parent_stop_place_details = None
                other_transport_modes = []
                parent_stop_place_id = None

                if site_ref:
                    found_sp = [sp for sp in stop_places if sp.get("@id") == site_ref]
                    if found_sp:
                        parent_stop_place_details = found_sp[0]
                        parent_stop_place_id = parent_stop_place_details.get("@id")
                        modes_obj = parent_stop_place_details.get(
                            f"{NETEX_NAMESPACE}:OtherTransportModes"
                        )
                        if isinstance(modes_obj, str):
                            other_transport_modes = modes_obj.split(" ")
                        elif isinstance(modes_obj, list):
                            other_transport_modes = modes_obj
                        elif isinstance(modes_obj, dict) and "#text" in modes_obj:
                            other_transport_modes = modes_obj["#text"].split(" ")
                        other_transport_modes = [
                            mode.strip()
                            for mode in other_transport_modes
                            if mode.strip()
                        ]

                stop: Stop = {
                    "id": quay_id,
                    "name": quay_name,
                    "transportMode": transport_mode.lower(),
                    "otherTransportModes": other_transport_modes,
                    "normalizedName": normalizeString(quay_name),
                    "normalizedId": normalizeString(quay_id) if quay_id else "",
                    "parentStopPlaceId": parent_stop_place_id,
                }
                stops.append(stop)

        except Exception as e:
            _LOGGER.error(f"Error parsing NETEX structure: {e}", exc_info=True)
            # Log the part of data that caused error if possible, or just re-raise/return empty
            return []

        _LOGGER.info(f"Successfully loaded {len(stops)} stops.")
        return stops

    except httpx.HTTPStatusError as e:
        _LOGGER.error(f"HTTP error while fetching NETEX file: {e}")
        return []
    except xmltodict.expat.ExpatError as e:
        _LOGGER.error(f"Error parsing NETEX XML: {e}")
        return []
    except Exception as e:
        _LOGGER.error(f"Unexpected error loading stops: {e}", exc_info=True)
        return []


# Define a type for individual departure for clarity
Departure = Dict[str, Any]


def _generate_siri_xml_for_stops(stop_ids: List[str], limit_per_stop: int) -> str:
    """Generate SIRI XML with a separate StopMonitoringRequest for each stop ID."""
    stop_monitoring_requests_xml = "".join(
        [
            f"""<StopMonitoringRequest version="2.0">
            <MonitoringRef>{stop_id}</MonitoringRef>
            <MaximumStopVisits>{limit_per_stop}</MaximumStopVisits>
        </StopMonitoringRequest>"""
            for stop_id in stop_ids
        ]
    )

    return f"""<?xml version="1.0" encoding="utf-8"?>
<Siri xmlns="{SIRI_NAMESPACE}" xmlns:ns2="http://www.ifopt.org.uk/acsb" xmlns:ns3="http://www.ifopt.org.uk/ifopt" xmlns:ns4="http://datex2.eu/schema/2_0RC1/2_0" version="2.0">
    <ServiceRequest>
        <RequestorRef>home_assistant</RequestorRef>
        {stop_monitoring_requests_xml}
    </ServiceRequest>
</Siri>"""


async def get_departures_for_stops(
    hass,
    siri_endpoint: str,
    dataset_id: str,
    stop_ids: List[str],
    limit_per_stop: int = 5,
) -> Optional[Dict[str, List[Departure]]]:
    """Fetch next departures from SIRI endpoint for a list of stop_ids."""
    if not stop_ids:
        _LOGGER.debug("No stop_ids provided to get_departures_for_stops.")
        return {}

    _LOGGER.debug(
        f"Fetching next departures for {len(stop_ids)} stops from {siri_endpoint} with limit {limit_per_stop} per stop"
    )
    xml_request = _generate_siri_xml_for_stops(stop_ids, limit_per_stop)
    headers = {
        "Content-Type": "application/xml",
        "datasetId": dataset_id,
    }

    _LOGGER.debug(f"XML REQUEST: {xml_request}")

    try:
        client = get_async_client(hass)
        response = await client.post(siri_endpoint, data=xml_request, headers=headers)
        _LOGGER.debug(
            f"SIRI API response status: {response.status_code} for {len(stop_ids)} stops."
        )
        response.raise_for_status()

        parsed_xml = xmltodict.parse(
            response.text,
            process_namespaces=True,
            namespaces={},
            force_list=(f"{SIRI_NAMESPACE}:MonitoredStopVisit",),
        )

        siri_data = parsed_xml.get(f"{SIRI_NAMESPACE}:Siri")
        if not siri_data:
            _LOGGER.warning("No '{SIRI_NAMESPACE}:Siri' element in SIRI response.")
            return None  # Indicate error

        service_delivery = siri_data.get(f"{SIRI_NAMESPACE}:ServiceDelivery")
        if not service_delivery:
            _LOGGER.warning("No '{SIRI_NAMESPACE}:ServiceDelivery' in SIRI response.")
            return None  # Indicate error

        if isinstance(service_delivery, list):
            service_delivery = service_delivery[0]

        stop_monitoring_delivery = service_delivery.get(
            f"{SIRI_NAMESPACE}:StopMonitoringDelivery"
        )
        if not stop_monitoring_delivery:
            _LOGGER.info(
                "No '{SIRI_NAMESPACE}:StopMonitoringDelivery' in SIRI response."
            )
            return {}  # No actual departure data, but not an error in itself

        if isinstance(stop_monitoring_delivery, list):
            stop_monitoring_delivery = stop_monitoring_delivery[0]

        monitored_stop_visits = stop_monitoring_delivery.get(
            f"{SIRI_NAMESPACE}:MonitoredStopVisit", []
        )

        # Prepare a dictionary to hold departures grouped by stop_id
        all_departures: Dict[str, List[Departure]] = {
            stop_id: [] for stop_id in stop_ids
        }

        for visit in monitored_stop_visits:
            monitoring_ref_obj = visit.get(f"{SIRI_NAMESPACE}:MonitoringRef")
            current_stop_id = (
                monitoring_ref_obj.get("#text")
                if isinstance(monitoring_ref_obj, dict)
                else monitoring_ref_obj
            )

            if not current_stop_id or current_stop_id not in all_departures:
                _LOGGER.warning(
                    f"Visit found for unexpected or missing MonitoringRef: {current_stop_id}. Visit data: {visit}"
                )
                continue  # Skip if MonitoringRef doesn't match one of our requested stop_ids

            # Limit client-side per stop if server returns more than requested for a specific stop (though MaximumStopVisits should handle this)
            if (
                len(all_departures[current_stop_id]) >= limit_per_stop
                and limit_per_stop > 0
            ):
                continue

            journey = visit.get(f"{SIRI_NAMESPACE}:MonitoredVehicleJourney")
            if not journey:
                continue

            line_ref_obj = journey.get(f"{SIRI_NAMESPACE}:LineRef")
            line_ref = (
                line_ref_obj.get("#text")
                if isinstance(line_ref_obj, dict)
                else line_ref_obj
            )

            destination_name_obj = journey.get(f"{SIRI_NAMESPACE}:DestinationName")
            destination_name = (
                destination_name_obj.get("#text")
                if isinstance(destination_name_obj, dict)
                else destination_name_obj
            )

            monitored_call = journey.get(f"{SIRI_NAMESPACE}:MonitoredCall")
            if not monitored_call:
                continue

            if isinstance(monitored_call, list):
                monitored_call = monitored_call[0]

            expected_departure_time_obj = monitored_call.get(
                f"{SIRI_NAMESPACE}:ExpectedDepartureTime"
            )
            expected_departure_time = (
                expected_departure_time_obj.get("#text")
                if isinstance(expected_departure_time_obj, dict)
                else expected_departure_time_obj
            )

            aimed_departure_time_obj = monitored_call.get(
                f"{SIRI_NAMESPACE}:AimedDepartureTime"
            )
            aimed_departure_time = (
                aimed_departure_time_obj.get("#text")
                if isinstance(aimed_departure_time_obj, dict)
                else aimed_departure_time_obj
            )

            vehicle_at_stop_obj = monitored_call.get(f"{SIRI_NAMESPACE}:VehicleAtStop")
            vehicle_at_stop_text = (
                vehicle_at_stop_obj.get("#text")
                if isinstance(vehicle_at_stop_obj, dict)
                else vehicle_at_stop_obj
            )
            vehicle_at_stop = (
                vehicle_at_stop_text == "true"
                if isinstance(vehicle_at_stop_text, str)
                else None
            )

            published_line_name_obj = journey.get(f"{SIRI_NAMESPACE}:PublishedLineName")
            published_line_name = (
                published_line_name_obj.get("#text")
                if isinstance(published_line_name_obj, dict)
                else published_line_name_obj
            )

            vehicle_mode_obj = journey.get(f"{SIRI_NAMESPACE}:VehicleMode")
            vehicle_mode = (
                vehicle_mode_obj.get("#text")
                if isinstance(vehicle_mode_obj, dict)
                else vehicle_mode_obj
            )

            departure_data = {
                "line_ref": line_ref,
                "published_line_name": published_line_name,
                "destination_name": destination_name,
                "expected_departure_time": expected_departure_time,
                "aimed_departure_time": aimed_departure_time,
                "vehicle_mode": vehicle_mode,
                "vehicle_at_stop": vehicle_at_stop,
            }
            all_departures[current_stop_id].append(departure_data)

        _LOGGER.debug(
            f"Processed departures for {len(stop_ids)} stops. Result keys: {list(all_departures.keys())}"
        )
        return all_departures

    except httpx.HTTPStatusError as e:
        _LOGGER.error(
            f"HTTP error fetching SIRI data for stops: {e.response.status_code} - {e.response.text}"
        )
        return None
    except xmltodict.expat.ExpatError as e:
        _LOGGER.error(f"XML parsing error for SIRI response (multiple stops): {e}")
        return None
    except Exception as e:
        _LOGGER.error(
            f"Unexpected error fetching departures for multiple stops: {e}",
            exc_info=True,
        )
        return None
