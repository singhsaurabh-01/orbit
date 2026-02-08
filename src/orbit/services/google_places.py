"""Google Places API service for enhanced place resolution."""

from typing import Optional, List
import googlemaps

from orbit.config import GOOGLE_PLACES_API_KEY, ENABLE_GOOGLE_PLACES
from orbit.models import PlaceSearchResult


# Initialize Google Maps client
gmaps_client = googlemaps.Client(key=GOOGLE_PLACES_API_KEY) if GOOGLE_PLACES_API_KEY else None


def search_place_with_google(
    query: str,
    center_lat: float,
    center_lon: float,
    radius_miles: float = 25.0,
) -> Optional[PlaceSearchResult]:
    """
    Search for a place using Google Places Text Search API.

    Args:
        query: Search query (e.g., "Carter's", "Target")
        center_lat: Center latitude for location bias
        center_lon: Center longitude for location bias
        radius_miles: Search radius in miles (for location bias)

    Returns:
        PlaceSearchResult if found, None otherwise
    """
    if not ENABLE_GOOGLE_PLACES or not gmaps_client:
        return None

    try:
        # Convert miles to meters for Google API
        radius_meters = int(radius_miles * 1609.34)

        print(f"[Google Places] Searching for '{query}' near ({center_lat}, {center_lon})")

        # Use Text Search (New) - more flexible and accurate
        # locationbias parameter prioritizes results near the location
        result = gmaps_client.places(
            query=query,
            location=(center_lat, center_lon),
            radius=radius_meters,
            type=None,  # Let Google infer the type
        )

        if not result or 'results' not in result or len(result['results']) == 0:
            print(f"[Google Places] No results found")
            return None

        # Get the top result
        place = result['results'][0]

        # Extract details
        name = place.get('name', query)
        address = place.get('formatted_address', '')
        location = place.get('geometry', {}).get('location', {})
        lat = location.get('lat')
        lon = location.get('lng')
        place_id = place.get('place_id')

        if not lat or not lon:
            print(f"[Google Places] Result missing coordinates")
            return None

        print(f"[Google Places] Found: {name} at {address}")

        # Create PlaceSearchResult
        place_result = PlaceSearchResult(
            name=name,
            address=address,
            lat=lat,
            lon=lon,
            source="google_places",
            osm_id=None,
            place_type=place.get('types', [None])[0] if place.get('types') else None,
        )

        return place_result

    except googlemaps.exceptions.ApiError as e:
        print(f"[Google Places] API error: {e}")
        return None
    except Exception as e:
        print(f"[Google Places] Unexpected error: {e}")
        return None


def get_place_candidates(
    query: str,
    center_lat: float,
    center_lon: float,
    radius_miles: float = 25.0,
    limit: int = 5,
) -> List[PlaceSearchResult]:
    """
    Get multiple place candidates from Google Places.

    Args:
        query: Search query
        center_lat: Center latitude
        center_lon: Center longitude
        radius_miles: Search radius in miles
        limit: Maximum number of results

    Returns:
        List of PlaceSearchResult objects
    """
    if not ENABLE_GOOGLE_PLACES or not gmaps_client:
        return []

    try:
        radius_meters = int(radius_miles * 1609.34)

        result = gmaps_client.places(
            query=query,
            location=(center_lat, center_lon),
            radius=radius_meters,
        )

        if not result or 'results' not in result:
            return []

        candidates = []
        for place in result['results'][:limit]:
            name = place.get('name', query)
            address = place.get('formatted_address', '')
            location = place.get('geometry', {}).get('location', {})
            lat = location.get('lat')
            lon = location.get('lng')

            if lat and lon:
                place_result = PlaceSearchResult(
                    name=name,
                    address=address,
                    lat=lat,
                    lon=lon,
                    source="google_places",
                    osm_id=None,
                    place_type=place.get('types', [None])[0] if place.get('types') else None,
                )
                candidates.append(place_result)

        print(f"[Google Places] Found {len(candidates)} candidates")
        return candidates

    except Exception as e:
        print(f"[Google Places] Error getting candidates: {e}")
        return []


def should_use_google_places(
    query: str,
    osm_results: List[PlaceSearchResult],
) -> bool:
    """
    Determine if we should use Google Places API.

    Use Google Places when:
    - OSM has no results
    - OSM has very few results (<= 2)
    - Query looks like a retail chain or business name
    - OSM result looks suspicious (e.g., street names for business queries)

    Args:
        query: User's search query
        osm_results: Results from OSM

    Returns:
        True if should use Google Places
    """
    # Always use if no OSM results
    if not osm_results or len(osm_results) == 0:
        return True

    # Use if very few results (increased threshold)
    if len(osm_results) <= 2:
        return True

    # Common retail chains (Google Places has better data)
    retail_chains = [
        'target', 'walmart', 'costco', 'cvs', 'walgreens', 'safeway',
        'kroger', 'whole foods', 'trader joe', "carter", 'gap',
        'old navy', 'kohls', 'macy', 'nordstrom', 'best buy',
        'home depot', 'lowes', 'bed bath', 'starbucks', 'mcdonalds',
        'burger king', 'taco bell', 'chipotle', 'panera', 'babies',
        'kids', 'clothing', 'store', 'shop', 'market', 'pharmacy'
    ]

    query_lower = query.lower()
    if any(chain in query_lower for chain in retail_chains):
        print(f"[Google Places] Query '{query}' matches retail pattern - using Google")
        return True

    # Check if OSM results look like street names instead of businesses
    # (e.g., "John Carter Drive" for query "Carter's")
    if osm_results:
        first_result = osm_results[0]
        result_name_lower = first_result.name.lower()

        # If result contains "drive", "street", "road", etc. but query doesn't,
        # it's probably a street name not a business
        street_indicators = ['drive', 'street', 'road', 'avenue', 'lane', 'boulevard', 'way', 'court']
        if any(indicator in result_name_lower for indicator in street_indicators):
            if not any(indicator in query_lower for indicator in street_indicators):
                print(f"[Google Places] OSM result '{first_result.name}' looks like street, query '{query}' looks like business - using Google")
                return True

    return False
