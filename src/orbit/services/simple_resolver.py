"""Simplified place resolver - Google Places first, OSM fallback."""

from typing import Optional
from orbit.models import Settings, PlaceSearchResult
from orbit.config import GOOGLE_PLACES_API_KEY

# Try to import services
try:
    from orbit.services.google_places import search_place_with_google
    GOOGLE_AVAILABLE = bool(GOOGLE_PLACES_API_KEY)
except ImportError:
    GOOGLE_AVAILABLE = False
    search_place_with_google = None

try:
    from orbit.services import places
    OSM_AVAILABLE = True
except ImportError:
    OSM_AVAILABLE = False
    places = None


def resolve_place_simple(
    query: str,
    settings: Settings,
    radius_miles: float = 25.0,
) -> Optional[PlaceSearchResult]:
    """
    Simple place resolution: Google Places first, OSM fallback.

    Args:
        query: User's search query (e.g., "Carter's", "Target")
        settings: User settings with home location
        radius_miles: Search radius in miles

    Returns:
        PlaceSearchResult if found, None otherwise
    """
    if not settings.has_home_location:
        return None

    # Try Google Places first (most accurate)
    if GOOGLE_AVAILABLE:
        print(f"[Simple Resolver] Trying Google Places for '{query}'")
        result = search_place_with_google(
            query=query,
            center_lat=settings.home_lat,
            center_lon=settings.home_lon,
            radius_miles=radius_miles,
        )
        if result:
            print(f"[Simple Resolver] ✅ Google Places found: {result.name}")
            return result
        print(f"[Simple Resolver] Google Places found nothing")

    # Fallback to OSM if Google fails
    if OSM_AVAILABLE:
        print(f"[Simple Resolver] Falling back to OSM for '{query}'")

        # Try nearby search
        candidates = places.search_places_nearby(
            query,
            settings.home_lat,
            settings.home_lon,
            radius_km=radius_miles / 0.621371,
            limit=5,
        )

        if candidates:
            # Return first result
            result = candidates[0]
            print(f"[Simple Resolver] ✅ OSM found: {result.name}")
            return result

        # Try geocoding as address
        result = places.geocode_address(query)
        if result:
            print(f"[Simple Resolver] ✅ OSM geocoded: {result.name}")
            return result

        print(f"[Simple Resolver] OSM found nothing")

    print(f"[Simple Resolver] ❌ No results for '{query}'")
    return None
