"""Places service - geocoding, search, and place management."""

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Optional

import requests

from orbit import db
from orbit.config import (
    CACHE_TTL_DAYS,
    DEFAULT_SEARCH_RADIUS_KM,
    NOMINATIM_BASE_URL,
    NOMINATIM_RATE_LIMIT_SECONDS,
    NOMINATIM_USER_AGENT,
)
from orbit.models import Place, PlaceSearchResult, Settings

# Track last request time for rate limiting
_last_request_time: float = 0


def _rate_limit():
    """Enforce rate limiting for Nominatim API."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < NOMINATIM_RATE_LIMIT_SECONDS:
        time.sleep(NOMINATIM_RATE_LIMIT_SECONDS - elapsed)
    _last_request_time = time.time()


def _get_cache_key(prefix: str, *args) -> str:
    """Generate a cache key from prefix and arguments."""
    content = json.dumps(args, sort_keys=True)
    hash_val = hashlib.md5(content.encode()).hexdigest()[:16]
    return f"{prefix}:{hash_val}"


@dataclass
class GeocodedAddress:
    """Result of address geocoding with precision info."""
    name: str
    address: str
    lat: float
    lon: float
    precision: str  # "exact", "street", "city", "region"
    osm_id: Optional[str] = None
    place_type: Optional[str] = None
    importance: float = 0.0  # Nominatim importance/rank

    def is_approximate(self) -> bool:
        """Check if this is an approximate (non-exact) location."""
        return self.precision in ("street", "city", "region")

    def to_place_search_result(self) -> "PlaceSearchResult":
        """Convert to PlaceSearchResult."""
        return PlaceSearchResult(
            name=self.name,
            address=self.address,
            lat=self.lat,
            lon=self.lon,
            source="nominatim",
            osm_id=self.osm_id,
            place_type=self.place_type,
        )


def _get_precision_from_type(osm_type: str, address_type: str) -> str:
    """Determine precision level from OSM type and address type."""
    exact_types = {"house", "building", "apartments", "residential", "commercial"}
    street_types = {"road", "street", "way", "path", "highway"}
    city_types = {"city", "town", "village", "suburb", "neighbourhood", "hamlet"}

    type_lower = (osm_type or "").lower()
    addr_lower = (address_type or "").lower()

    if type_lower in exact_types or addr_lower in exact_types:
        return "exact"
    elif type_lower in street_types or addr_lower in street_types:
        return "street"
    elif type_lower in city_types or addr_lower in city_types:
        return "city"
    return "region"


def geocode_address_multi(
    address: str,
    limit: int = 5,
    bias_lat: Optional[float] = None,
    bias_lon: Optional[float] = None,
) -> list[GeocodedAddress]:
    """
    Geocode an address with multiple results for user selection.

    Args:
        address: Address string to geocode
        limit: Maximum results to return
        bias_lat: Optional latitude to bias results toward
        bias_lon: Optional longitude to bias results toward

    Returns:
        List of GeocodedAddress options, sorted by relevance
    """
    cache_key = _get_cache_key("geocode_multi", address, limit, bias_lat, bias_lon)
    cached = db.get_cache(cache_key)
    if cached:
        data = json.loads(cached)
        return [GeocodedAddress(**item) for item in data] if data else []

    _rate_limit()

    try:
        params = {
            "q": address,
            "format": "json",
            "limit": limit,
            "addressdetails": 1,
        }

        # Add viewbox bias if coordinates provided
        if bias_lat is not None and bias_lon is not None:
            # Create a ~50km viewbox around the bias point
            delta = 0.5  # ~50km
            params["viewbox"] = f"{bias_lon - delta},{bias_lat + delta},{bias_lon + delta},{bias_lat - delta}"
            params["bounded"] = 0  # Prefer but don't require results in viewbox

        response = requests.get(
            f"{NOMINATIM_BASE_URL}/search",
            params=params,
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
        results = response.json()

        geocoded = []
        for result in results:
            osm_type = result.get("type", "")
            addr_type = result.get("addresstype", "")
            precision = _get_precision_from_type(osm_type, addr_type)

            geocoded.append(GeocodedAddress(
                name=result.get("display_name", address).split(",")[0],
                address=result.get("display_name", address),
                lat=float(result["lat"]),
                lon=float(result["lon"]),
                precision=precision,
                osm_id=str(result.get("osm_id")),
                place_type=osm_type,
                importance=float(result.get("importance", 0)),
            ))

        # Sort by importance (higher first), then by precision
        precision_order = {"exact": 0, "street": 1, "city": 2, "region": 3}
        geocoded.sort(key=lambda x: (precision_order.get(x.precision, 4), -x.importance))

        # If bias point provided, also factor in distance
        if bias_lat is not None and bias_lon is not None and geocoded:
            from orbit.services import routing
            for g in geocoded:
                g._distance = routing.haversine_distance(bias_lat, bias_lon, g.lat, g.lon)
            # Re-sort: precision first, then distance for same precision
            geocoded.sort(key=lambda x: (precision_order.get(x.precision, 4), getattr(x, '_distance', 999)))

        # Cache results
        cache_data = [
            {
                "name": g.name,
                "address": g.address,
                "lat": g.lat,
                "lon": g.lon,
                "precision": g.precision,
                "osm_id": g.osm_id,
                "place_type": g.place_type,
                "importance": g.importance,
            }
            for g in geocoded
        ]
        db.set_cache(cache_key, json.dumps(cache_data), CACHE_TTL_DAYS)

        return geocoded

    except requests.RequestException as e:
        print(f"Geocoding error: {e}")
        return []


def geocode_address(address: str) -> Optional[PlaceSearchResult]:
    """
    Geocode an address to coordinates using Nominatim.

    Args:
        address: Full address string to geocode

    Returns:
        PlaceSearchResult if found, None otherwise
    """
    cache_key = _get_cache_key("geocode", address)
    cached = db.get_cache(cache_key)
    if cached:
        data = json.loads(cached)
        return PlaceSearchResult(**data) if data else None

    _rate_limit()

    try:
        response = requests.get(
            f"{NOMINATIM_BASE_URL}/search",
            params={
                "q": address,
                "format": "json",
                "limit": 1,
                "addressdetails": 1,
            },
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
        results = response.json()

        if results:
            result = results[0]
            place_result = PlaceSearchResult(
                name=result.get("display_name", address).split(",")[0],
                address=result.get("display_name", address),
                lat=float(result["lat"]),
                lon=float(result["lon"]),
                source="nominatim",
                osm_id=str(result.get("osm_id")),
                place_type=result.get("type"),
            )
            db.set_cache(cache_key, place_result.model_dump_json(), CACHE_TTL_DAYS)
            return place_result
        else:
            db.set_cache(cache_key, "null", CACHE_TTL_DAYS)
            return None

    except requests.RequestException as e:
        print(f"Geocoding error: {e}")
        return None


def search_places_nearby(
    query: str,
    center_lat: float,
    center_lon: float,
    radius_km: float = DEFAULT_SEARCH_RADIUS_KM,
    limit: int = 10,
) -> list[PlaceSearchResult]:
    """
    Search for places near a location using Nominatim.

    Args:
        query: Search query (place name)
        center_lat: Center latitude for search
        center_lon: Center longitude for search
        radius_km: Search radius in kilometers
        limit: Maximum number of results

    Returns:
        List of PlaceSearchResult
    """
    cache_key = _get_cache_key("search", query, center_lat, center_lon, radius_km, limit)
    cached = db.get_cache(cache_key)
    if cached:
        data = json.loads(cached)
        return [PlaceSearchResult(**item) for item in data]

    _rate_limit()

    # Calculate bounding box
    lat_delta = radius_km / 111.0  # Approximate km per degree latitude
    lon_delta = radius_km / (111.0 * abs(center_lat) * 0.0174533) if center_lat != 0 else radius_km / 111.0

    viewbox = f"{center_lon - lon_delta},{center_lat + lat_delta},{center_lon + lon_delta},{center_lat - lat_delta}"

    try:
        response = requests.get(
            f"{NOMINATIM_BASE_URL}/search",
            params={
                "q": query,
                "format": "json",
                "limit": limit,
                "addressdetails": 1,
                "viewbox": viewbox,
                "bounded": 1,
            },
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
        results = response.json()

        place_results = []
        for result in results:
            place_result = PlaceSearchResult(
                name=result.get("display_name", query).split(",")[0],
                address=result.get("display_name", ""),
                lat=float(result["lat"]),
                lon=float(result["lon"]),
                source="nominatim",
                osm_id=str(result.get("osm_id")),
                place_type=result.get("type"),
            )
            place_results.append(place_result)

        # Cache the results
        cache_data = [p.model_dump() for p in place_results]
        db.set_cache(cache_key, json.dumps(cache_data), CACHE_TTL_DAYS)

        return place_results

    except requests.RequestException as e:
        print(f"Place search error: {e}")
        return []


def search_places_near_home(
    query: str,
    radius_km: float = DEFAULT_SEARCH_RADIUS_KM,
    limit: int = 10,
) -> list[PlaceSearchResult]:
    """
    Search for places near the user's home location.

    Args:
        query: Search query (place name)
        radius_km: Search radius in kilometers
        limit: Maximum number of results

    Returns:
        List of PlaceSearchResult

    Raises:
        ValueError: If home location is not set
    """
    settings = db.get_settings()
    if not settings.has_home_location:
        raise ValueError("Home location not set. Please set your home address first.")

    return search_places_nearby(
        query=query,
        center_lat=settings.home_lat,
        center_lon=settings.home_lon,
        radius_km=radius_km,
        limit=limit,
    )


def reverse_geocode(lat: float, lon: float) -> Optional[str]:
    """
    Get address from coordinates using reverse geocoding.

    Args:
        lat: Latitude
        lon: Longitude

    Returns:
        Address string if found, None otherwise
    """
    cache_key = _get_cache_key("reverse", lat, lon)
    cached = db.get_cache(cache_key)
    if cached:
        return cached if cached != "null" else None

    _rate_limit()

    try:
        response = requests.get(
            f"{NOMINATIM_BASE_URL}/reverse",
            params={
                "lat": lat,
                "lon": lon,
                "format": "json",
            },
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
        result = response.json()

        address = result.get("display_name")
        db.set_cache(cache_key, address if address else "null", CACHE_TTL_DAYS)
        return address

    except requests.RequestException as e:
        print(f"Reverse geocoding error: {e}")
        return None


def save_place_from_search_result(result: PlaceSearchResult, name: Optional[str] = None) -> Place:
    """
    Save a place from a search result.

    Args:
        result: PlaceSearchResult to save
        name: Optional custom name (defaults to result name)

    Returns:
        Saved Place object
    """
    place = Place(
        name=name or result.name,
        address=result.address,
        lat=result.lat,
        lon=result.lon,
        source=result.source,
    )
    db.save_place(place)
    return place


def get_or_create_place(
    name: str,
    address: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> Optional[Place]:
    """
    Get an existing place or create a new one.

    If lat/lon are provided, use those directly.
    If only address is provided, geocode it.

    Args:
        name: Place name
        address: Optional address
        lat: Optional latitude
        lon: Optional longitude

    Returns:
        Place object if successful, None otherwise
    """
    # If coordinates are provided, use them
    if lat is not None and lon is not None:
        place = Place(
            name=name,
            address=address or f"{lat}, {lon}",
            lat=lat,
            lon=lon,
            source="manual",
        )
        db.save_place(place)
        return place

    # If address is provided, geocode it
    if address:
        result = geocode_address(address)
        if result:
            place = Place(
                name=name,
                address=result.address,
                lat=result.lat,
                lon=result.lon,
                source="nominatim",
            )
            db.save_place(place)
            return place

    return None


def detect_input_type(text: str) -> str:
    """
    Detect if input is likely an address or a place name.

    Args:
        text: User input text

    Returns:
        'address' if likely a full address, 'name' if likely a place name
    """
    # Split into words for word-boundary matching
    words = text.lower().split()

    # Street type abbreviations (must be whole words)
    street_types = {
        "street", "st", "st.", "avenue", "ave", "ave.", "road", "rd", "rd.",
        "drive", "dr", "dr.", "lane", "ln", "ln.", "boulevard", "blvd", "blvd.",
        "way", "court", "ct", "ct.", "highway", "hwy", "hwy.", "parkway", "pkwy"
    }

    # Indicators of a full address
    address_indicators = [
        # Contains numbers that look like street addresses (first word is a number)
        any(c.isdigit() for c in text.split()[0]) if text.split() else False,
        # Contains common address words as whole words
        any(word in street_types for word in words),
        # Contains zip code pattern
        any(len(word) == 5 and word.isdigit() for word in text.split()),
        # Contains state abbreviation
        any(word.upper() in [
            "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
            "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
            "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
            "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
            "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"
        ] for word in text.split()),
    ]

    if any(address_indicators):
        return "address"
    return "name"


def smart_search(
    query: str,
    radius_km: float = DEFAULT_SEARCH_RADIUS_KM,
    limit: int = 10,
) -> list[PlaceSearchResult]:
    """
    Smart place search that detects input type and searches accordingly.

    Args:
        query: User input (address or place name)
        radius_km: Search radius for name searches
        limit: Maximum results

    Returns:
        List of PlaceSearchResult
    """
    input_type = detect_input_type(query)

    if input_type == "address":
        # Geocode the address
        result = geocode_address(query)
        return [result] if result else []
    else:
        # Search nearby home
        try:
            return search_places_near_home(query, radius_km, limit)
        except ValueError:
            # Home not set, try geocoding instead
            result = geocode_address(query)
            return [result] if result else []
