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

# Structure for storing line information from the repository
Line = Dict[str, Any]

# Structure for storing topographic place (city) information
TopographicPlace = Dict[str, Any]

# Cache global pour le référentiel des lignes - maintenant un dictionnaire d'instances
_lines_repositories: Dict[str, Dict[str, Line]] = {}
_lines_repository_urls: Dict[str, str] = {}


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
    """Load stops from a NETEX XML file URL using streaming to handle large files."""
    _LOGGER.info(f"Loading stops from NETEX URL: {netex_url}")
    
    # Utiliser un fichier temporaire pour stocker les données
    import tempfile
    import os
    from pathlib import Path
    import re
    from xml.sax import make_parser, handler
    
    stops: List[Stop] = []
    
    try:
        # Créer un fichier temporaire pour stocker le XML
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as temp_file:
            temp_path = temp_file.name
            _LOGGER.info(f"Downloading NETEX file to temporary location: {temp_path}")
            
            # Télécharger le fichier en streaming
            client = get_async_client(hass)
            async with client.stream("GET", netex_url) as response:
                response.raise_for_status()
                
                # Télécharger par morceaux pour économiser la mémoire
                chunk_size = 1024 * 1024  # 1MB
                downloaded_size = 0
                async for chunk in response.aiter_bytes(chunk_size):
                    temp_file.write(chunk)
                    downloaded_size += len(chunk)
                    # Log progression toutes les 10MB
                    if downloaded_size % (10 * chunk_size) < chunk_size:
                        _LOGGER.info(f"Downloaded {downloaded_size / (1024*1024):.2f}MB of NETEX file")
        
        _LOGGER.info(f"Download complete. Processing NETEX file...")
        
        # Classe de gestionnaire SAX pour traiter les arrêts de manière efficace
        class StopHandler(handler.ContentHandler):
            def __init__(self):
                super().__init__()
                self.current_quay = None
                self.current_stop_place = None
                self.current_topographic_place = None
                self.stop_places = {}
                self.topographic_places = {}
                self.stops = []
                self.current_element = None
                self.current_content = ""
                self.in_name = False
                self.in_transport_mode = False
                self.in_other_transport_modes = False
                self.in_site_ref = False
                self.in_topographic_place_ref = False
                self.in_topographic_place = False
                self.in_topographic_place_type = False
            
            def startElement(self, name, attrs):
                self.current_element = name
                
                # Détecter les éléments Quay
                if name == "Quay" or name.endswith(":Quay"):
                    self.current_quay = {
                        "id": attrs.get("id", ""),
                        "name": "",
                        "transportMode": "unknown",
                        "otherTransportModes": [],
                        "normalizedName": "",
                        "normalizedId": "",
                        "parentStopPlaceId": None,
                        "cityName": None
                    }
                
                # Détecter les éléments StopPlace
                elif name == "StopPlace" or name.endswith(":StopPlace"):
                    stop_id = attrs.get("id", "")
                    self.current_stop_place = {
                        "id": stop_id,
                        "otherTransportModes": [],
                        "topographicPlaceRef": None
                    }
                
                # Détecter les éléments TopographicPlace
                elif name == "TopographicPlace" or name.endswith(":TopographicPlace"):
                    place_id = attrs.get("id", "")
                    self.current_topographic_place = {
                        "id": place_id,
                        "name": "",
                        "type": ""
                    }
                    self.in_topographic_place = True
                
                # Détecter les noms
                elif name == "Name" or name.endswith(":Name"):
                    if self.current_quay:
                        self.in_name = True
                    elif self.current_topographic_place and not self.in_name:
                        self.in_name = True
                
                # Détecter les modes de transport
                elif name == "TransportMode" or name.endswith(":TransportMode"):
                    if self.current_quay:
                        self.in_transport_mode = True
                
                # Détecter les autres modes de transport
                elif name == "OtherTransportModes" or name.endswith(":OtherTransportModes"):
                    if self.current_stop_place:
                        self.in_other_transport_modes = True
                
                # Détecter les références à un site
                elif name == "SiteRef" or name.endswith(":SiteRef"):
                    if self.current_quay:
                        self.in_site_ref = True
                        ref = attrs.get("ref", "")
                        if ref:
                            self.current_quay["parentStopPlaceId"] = ref
                
                # Détecter les références à une ville
                elif name == "TopographicPlaceRef" or name.endswith(":TopographicPlaceRef"):
                    if self.current_stop_place:
                        self.in_topographic_place_ref = True
                        ref = attrs.get("ref", "")
                        if ref:
                            self.current_stop_place["topographicPlaceRef"] = ref
                
                # Détecter le type de lieu topographique
                elif name == "TopographicPlaceType" or name.endswith(":TopographicPlaceType"):
                    if self.current_topographic_place:
                        self.in_topographic_place_type = True
            
            def characters(self, content):
                if self.in_name or self.in_transport_mode or self.in_other_transport_modes or self.in_topographic_place_type:
                    self.current_content += content
            
            def endElement(self, name):
                # Terminer le traitement d'un arrêt
                if name == "Quay" or name.endswith(":Quay"):
                    if self.current_quay:
                        # Normaliser le nom et l'ID
                        self.current_quay["normalizedName"] = normalizeString(self.current_quay["name"])
                        self.current_quay["normalizedId"] = normalizeString(self.current_quay["id"])
                        
                        # Chercher les autres modes de transport et la ville dans le StopPlace parent
                        if self.current_quay["parentStopPlaceId"]:
                            parent = self.stop_places.get(self.current_quay["parentStopPlaceId"])
                            if parent:
                                self.current_quay["otherTransportModes"] = parent["otherTransportModes"]
                                
                                # Ajouter la référence à la ville si disponible
                                if parent.get("topographicPlaceRef"):
                                    city = self.topographic_places.get(parent["topographicPlaceRef"])
                                    if city:
                                        self.current_quay["cityName"] = city["name"]
                        
                        # Ajouter l'arrêt à la liste
                        self.stops.append(self.current_quay)
                    self.current_quay = None
                
                # Terminer le traitement d'un lieu d'arrêt
                elif name == "StopPlace" or name.endswith(":StopPlace"):
                    if self.current_stop_place:
                        self.stop_places[self.current_stop_place["id"]] = self.current_stop_place
                    self.current_stop_place = None
                
                # Terminer le traitement d'un lieu topographique
                elif name == "TopographicPlace" or name.endswith(":TopographicPlace"):
                    if self.current_topographic_place:
                        self.topographic_places[self.current_topographic_place["id"]] = self.current_topographic_place
                    self.current_topographic_place = None
                    self.in_topographic_place = False
                
                # Traiter le contenu des éléments
                elif name == "Name" or name.endswith(":Name"):
                    if self.in_name:
                        if self.current_quay:
                            self.current_quay["name"] = self.current_content.strip()
                        elif self.current_topographic_place:
                            self.current_topographic_place["name"] = self.current_content.strip()
                    self.in_name = False
                    self.current_content = ""
                
                elif name == "TransportMode" or name.endswith(":TransportMode"):
                    if self.in_transport_mode and self.current_quay:
                        self.current_quay["transportMode"] = self.current_content.strip().lower()
                    self.in_transport_mode = False
                    self.current_content = ""
                
                elif name == "OtherTransportModes" or name.endswith(":OtherTransportModes"):
                    if self.in_other_transport_modes and self.current_stop_place:
                        modes = self.current_content.strip().split()
                        self.current_stop_place["otherTransportModes"] = [m for m in modes if m]
                    self.in_other_transport_modes = False
                    self.current_content = ""
                
                elif name == "SiteRef" or name.endswith(":SiteRef"):
                    self.in_site_ref = False
                    
                elif name == "TopographicPlaceRef" or name.endswith(":TopographicPlaceRef"):
                    self.in_topographic_place_ref = False
                
                elif name == "TopographicPlaceType" or name.endswith(":TopographicPlaceType"):
                    if self.in_topographic_place_type and self.current_topographic_place:
                        self.current_topographic_place["type"] = self.current_content.strip().lower()
                    self.in_topographic_place_type = False
                    self.current_content = ""
        
        # Fonction pour exécuter le parsing SAX dans un thread séparé
        def parse_netex_file(file_path):
            _LOGGER.info("Starting SAX parsing of NETEX file in executor...")
            parser = make_parser()
            stop_handler = StopHandler()
            parser.setContentHandler(stop_handler)
            parser.parse(file_path)
            return stop_handler.stops
        
        # Exécuter le parsing SAX dans un thread séparé via async_add_executor_job
        stops = await hass.async_add_executor_job(parse_netex_file, temp_path)
        
        _LOGGER.info(f"Successfully loaded {len(stops)} stops using SAX parser.")
        
        # Supprimer le fichier temporaire
        await hass.async_add_executor_job(os.unlink, temp_path)
        
        return stops

    except httpx.HTTPStatusError as e:
        _LOGGER.error(f"HTTP error while fetching NETEX file: {e}")
        return []
    except Exception as e:
        _LOGGER.error(f"Unexpected error loading stops: {e}", exc_info=True)
        return []
    finally:
        # S'assurer que le fichier temporaire est supprimé en cas d'erreur
        try:
            if 'temp_path' in locals():
                if os.path.exists(temp_path):
                    await hass.async_add_executor_job(os.unlink, temp_path)
        except Exception as e:
            _LOGGER.warning(f"Failed to clean up temporary file: {e}")
    
    return []


async def load_lines_repository(hass, url: str, instance_id: str = "default") -> Dict[str, Line]:
    """Charge le référentiel des lignes à partir d'un fichier XML en utilisant streaming."""
    global _lines_repositories, _lines_repository_urls
    
    # Si le référentiel est déjà chargé avec cette URL pour cette instance, le renvoyer directement
    if instance_id in _lines_repository_urls and url == _lines_repository_urls[instance_id] and instance_id in _lines_repositories:
        _LOGGER.debug(f"Using cached lines repository for instance {instance_id} ({len(_lines_repositories[instance_id])} lines)")
        return _lines_repositories[instance_id]
    
    _LOGGER.info(f"Loading lines repository from URL: {url} for instance {instance_id}")
    
    # Utiliser un fichier temporaire pour stocker les données
    import tempfile
    import os
    from xml.sax import make_parser, handler
    
    try:
        # Créer un fichier temporaire pour stocker le XML
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as temp_file:
            temp_path = temp_file.name
            _LOGGER.info(f"Downloading lines repository file to temporary location: {temp_path}")
            
            # Télécharger le fichier en streaming
            client = get_async_client(hass)
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                
                # Télécharger par morceaux pour économiser la mémoire
                chunk_size = 1024 * 1024  # 1MB
                downloaded_size = 0
                async for chunk in response.aiter_bytes(chunk_size):
                    temp_file.write(chunk)
                    downloaded_size += len(chunk)
                    # Log progression toutes les 10MB
                    if downloaded_size % (10 * chunk_size) < chunk_size:
                        _LOGGER.info(f"Downloaded {downloaded_size / (1024*1024):.2f}MB of lines repository file")
        
        _LOGGER.info(f"Download complete. Processing lines repository file...")
        
        # Classe de gestionnaire SAX pour traiter les lignes de manière efficace
        class LineHandler(handler.ContentHandler):
            def __init__(self):
                super().__init__()
                self.lines = {}
                self.current_line = None
                self.current_element = None
                self.current_content = ""
                self.in_public_code = False
                self.in_transport_mode = False
                self.in_colour = False
                self.in_text_colour = False
                self.has_presentation = False
            
            def startElement(self, name, attrs):
                self.current_element = name
                
                # Détecter les éléments Line
                if name == "Line" or name.endswith(":Line"):
                    line_id = attrs.get("id", "")
                    if line_id:
                        short_id = line_id.split(":")[-1].replace(":LOC", "")
                        self.current_line = {
                            "id": short_id,
                            "full_id": line_id,
                            "public_code": None,
                            "transport_mode": None,
                            "color": None,
                            "text_color": None
                        }
                
                # Détecter les éléments PublicCode
                elif name == "PublicCode" or name.endswith(":PublicCode"):
                    if self.current_line:
                        self.in_public_code = True
                
                # Détecter les éléments TransportMode
                elif name == "TransportMode" or name.endswith(":TransportMode"):
                    if self.current_line:
                        self.in_transport_mode = True
                
                # Détecter les éléments Presentation
                elif name == "Presentation" or name.endswith(":Presentation"):
                    if self.current_line:
                        self.has_presentation = True
                
                # Détecter les éléments Colour
                elif name == "Colour" or name.endswith(":Colour"):
                    if self.current_line and self.has_presentation:
                        self.in_colour = True
                
                # Détecter les éléments TextColour
                elif name == "TextColour" or name.endswith(":TextColour"):
                    if self.current_line and self.has_presentation:
                        self.in_text_colour = True
            
            def characters(self, content):
                if self.in_public_code or self.in_transport_mode or self.in_colour or self.in_text_colour:
                    self.current_content += content
            
            def endElement(self, name):
                # Terminer le traitement d'une ligne
                if name == "Line" or name.endswith(":Line"):
                    if self.current_line:
                        line_id = self.current_line["full_id"]
                        short_id = self.current_line["id"]
                        
                        # Ajouter la ligne au dictionnaire
                        self.lines[short_id] = self.current_line
                        self.lines[line_id] = self.current_line  # Ajouter aussi avec l'ID complet
                    
                    self.current_line = None
                    self.has_presentation = False
                
                # Terminer le traitement de Presentation
                elif name == "Presentation" or name.endswith(":Presentation"):
                    self.has_presentation = False
                
                # Traiter le contenu des éléments
                elif name == "PublicCode" or name.endswith(":PublicCode"):
                    if self.in_public_code and self.current_line:
                        self.current_line["public_code"] = self.current_content.strip()
                    self.in_public_code = False
                    self.current_content = ""
                
                elif name == "TransportMode" or name.endswith(":TransportMode"):
                    if self.in_transport_mode and self.current_line:
                        self.current_line["transport_mode"] = self.current_content.strip().lower()
                    self.in_transport_mode = False
                    self.current_content = ""
                
                elif name == "Colour" or name.endswith(":Colour"):
                    if self.in_colour and self.current_line:
                        color = self.current_content.strip()
                        if color:
                            self.current_line["color"] = f"#{color}"
                    self.in_colour = False
                    self.current_content = ""
                
                elif name == "TextColour" or name.endswith(":TextColour"):
                    if self.in_text_colour and self.current_line:
                        text_color = self.current_content.strip()
                        if text_color:
                            self.current_line["text_color"] = f"#{text_color}"
                    self.in_text_colour = False
                    self.current_content = ""
        
        # Fonction pour exécuter le parsing SAX dans un thread séparé
        def parse_lines_file(file_path):
            _LOGGER.info("Starting SAX parsing of lines repository file in executor...")
            parser = make_parser()
            line_handler = LineHandler()
            parser.setContentHandler(line_handler)
            parser.parse(file_path)
            return line_handler.lines
        
        # Exécuter le parsing SAX dans un thread séparé via async_add_executor_job
        lines = await hass.async_add_executor_job(parse_lines_file, temp_path)
        
        _LOGGER.info(f"Successfully loaded {len(lines)} lines using SAX parser.")
        
        # Supprimer le fichier temporaire
        await hass.async_add_executor_job(os.unlink, temp_path)
        
        # Mettre à jour le cache global pour cette instance
        if instance_id not in _lines_repositories:
            _lines_repositories[instance_id] = {}
        _lines_repositories[instance_id] = lines
        _lines_repository_urls[instance_id] = url
        
        return lines

    except httpx.HTTPStatusError as e:
        _LOGGER.error(f"HTTP error while fetching lines repository for instance {instance_id}: {e}")
        return {}
    except Exception as e:
        _LOGGER.error(f"Unexpected error loading lines repository for instance {instance_id}: {e}", exc_info=True)
        return {}
    finally:
        # S'assurer que le fichier temporaire est supprimé en cas d'erreur
        try:
            if 'temp_path' in locals():
                if os.path.exists(temp_path):
                    await hass.async_add_executor_job(os.unlink, temp_path)
        except Exception as e:
            _LOGGER.warning(f"Failed to clean up temporary file for lines repository: {e}")
    
    return {}


def get_line_info(line_ref: str, instance_id: str = "default") -> Optional[Line]:
    """Récupère les informations d'une ligne à partir de son identifiant."""
    global _lines_repositories
    
    if instance_id not in _lines_repositories or not _lines_repositories[instance_id]:
        return None
    
    # Essayer d'abord avec l'ID complet
    if line_ref in _lines_repositories[instance_id]:
        return _lines_repositories[instance_id][line_ref]
    
    # Si non trouvé, essayer avec l'ID court (après le dernier ":")
    short_id = line_ref.split(":")[-1].replace(":LOC", "")
    if short_id in _lines_repositories[instance_id]:
        return _lines_repositories[instance_id][short_id]
    
    return None


def enrich_departure_with_line_info(departure: Dict[str, Any], instance_id: str = "default") -> Dict[str, Any]:
    """Enrichit les données de départ avec les informations de ligne."""
    if not departure or instance_id not in _lines_repositories:
        return departure
    
    # Copier le départ pour ne pas modifier l'original
    enriched = dict(departure)
    
    # Récupérer l'identifiant de la ligne
    line_ref = departure.get("line_ref")
    if not line_ref:
        return enriched
    
    # Obtenir les informations de la ligne
    line_info = get_line_info(line_ref, instance_id)
    if not line_info:
        return enriched
    
    # Ajouter les informations de la ligne au départ
    enriched["line_public_code"] = line_info.get("public_code")
    enriched["line_transport_mode"] = line_info.get("transport_mode")
    enriched["line_color"] = line_info.get("color")
    enriched["line_text_color"] = line_info.get("text_color")
    
    return enriched


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
    lines_repository_url: Optional[str] = None,
    instance_id: str = "default",
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

    # Charger le référentiel des lignes si une URL est fournie
    lines_repository = {}
    if lines_repository_url:
        lines_repository = await load_lines_repository(hass, lines_repository_url, instance_id)

    try:
        client = get_async_client(hass)
        response = await client.post(siri_endpoint, data=xml_request, headers=headers)
        _LOGGER.debug(
            f"SIRI API response status: {response.status_code} for {len(stop_ids)} stops."
        )
        response.raise_for_status()

        _LOGGER.debug(f"SIRI API response: {response.text}")

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
            
            # Enrichir avec les informations du référentiel des lignes
            if lines_repository and line_ref:
                line_info = get_line_info(line_ref, instance_id)
                if line_info:
                    departure_data["line_public_code"] = line_info.get("public_code")
                    departure_data["line_transport_mode"] = line_info.get("transport_mode")
                    departure_data["line_color"] = line_info.get("color")
                    departure_data["line_text_color"] = line_info.get("text_color")
            
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
