"""Simplified place resolver - Google Places API only."""

from typing import Optional, List
from dataclasses import dataclass
from enum import Enum
from orbit.models import Settings, PlaceSearchResult
from orbit.config import GOOGLE_PLACES_API_KEY
from orbit.services import routing

# Try to import googlemaps
try:
    import googlemaps
    GOOGLEMAPS_AVAILABLE = True
except ImportError:
    print("[WARNING] googlemaps package not installed - place resolution will not work")
    googlemaps = None
    GOOGLEMAPS_AVAILABLE = False

# Initialize Google Maps client
gmaps = None
if GOOGLEMAPS_AVAILABLE and GOOGLE_PLACES_API_KEY:
    gmaps = googlemaps.Client(key=GOOGLE_PLACES_API_KEY)


# Copy minimal classes from resolver for compatibility
class ResolutionDecision(Enum):
    AUTO_BEST = "auto_best"
    USER_SELECTED = "user_selected"
    NO_MATCH = "no_match"
    PENDING = "pending"


class SelectionReason(Enum):
    BEST_OVERALL_SCORE = "best_overall_score"
    ONLY_MATCH = "only_match"
    USER_SELECTED = "user_selected"


@dataclass
class ScoredCandidate:
    place: PlaceSearchResult
    distance_miles: float
    name_similarity: float = 100.0
    combined_score: float = 100.0
    selection_reason: Optional[SelectionReason] = None

    @property
    def display_name(self) -> str:
        return self.place.name

    @property
    def display_address(self) -> str:
        addr = self.place.address
        if len(addr) > 60:
            return addr[:57] + "..."
        return addr

    @property
    def full_address(self) -> str:
        return self.place.address

    def get_reason_text(self) -> str:
        if self.selection_reason == SelectionReason.ONLY_MATCH:
            return "Only match found"
        elif self.selection_reason == SelectionReason.USER_SELECTED:
            return "User selected"
        return "Best match"


@dataclass
class ResolvedPlace:
    query: str
    selected: Optional[ScoredCandidate]
    candidates: List[ScoredCandidate]
    decision: ResolutionDecision
    decision_reason: str

    @property
    def needs_disambiguation(self) -> bool:
        return self.decision == ResolutionDecision.PENDING

    @property
    def is_resolved(self) -> bool:
        return self.decision in (ResolutionDecision.AUTO_BEST, ResolutionDecision.USER_SELECTED)


def km_to_miles(km: float) -> float:
    """Convert kilometers to miles."""
    return km * 0.621371


def resolve_place(
    query: str,
    settings: Settings,
    radius_miles: float = 25.0,
    **kwargs  # Accept and ignore other parameters for compatibility
) -> ResolvedPlace:
    """
    Simple place resolution using only Google Places API.

    No OSM, no LLM, no Tavily - just Google Places.
    Simple, fast, and accurate.

    Args:
        query: User's search query (e.g., "Carter's", "Target")
        settings: User settings with home location
        radius_miles: Search radius in miles

    Returns:
        ResolvedPlace object with resolution status
    """
    if not settings.has_home_location:
        print(f"[Resolver] No home location set")
        return ResolvedPlace(
            query=query,
            selected=None,
            candidates=[],
            decision=ResolutionDecision.NO_MATCH,
            decision_reason="Home location not set",
        )

    if not gmaps:
        print(f"[Resolver] Google Places API key not configured")
        return ResolvedPlace(
            query=query,
            selected=None,
            candidates=[],
            decision=ResolutionDecision.NO_MATCH,
            decision_reason="Google Places API not configured",
        )

    try:
        # Convert miles to meters
        radius_meters = int(radius_miles * 1609.34)

        print(f"[Resolver] Searching Google Places for '{query}' near home")

        # Use Google Places Text Search
        result = gmaps.places(
            query=query,
            location=(settings.home_lat, settings.home_lon),
            radius=radius_meters,
        )

        if not result or 'results' not in result or len(result['results']) == 0:
            print(f"[Resolver] No results found for '{query}'")
            return ResolvedPlace(
                query=query,
                selected=None,
                candidates=[],
                decision=ResolutionDecision.NO_MATCH,
                decision_reason=f"No places found for '{query}'",
            )

        # Convert all results to candidates with distance calculation
        candidates = []
        for place in result['results']:  # Get all results first
            name = place.get('name', query)
            address = place.get('formatted_address', '')
            location = place.get('geometry', {}).get('location', {})
            lat = location.get('lat')
            lon = location.get('lng')

            if lat and lon:
                # Calculate distance from home
                distance_km = routing.haversine_distance(
                    settings.home_lat, settings.home_lon,
                    lat, lon
                )
                distance_miles = km_to_miles(distance_km)

                # Only include results within reasonable distance (50 miles max)
                if distance_miles > 50:
                    print(f"[Resolver] Skipping {name} - too far ({distance_miles:.1f} mi)")
                    continue

                place_result = PlaceSearchResult(
                    name=name,
                    address=address,
                    lat=lat,
                    lon=lon,
                    source="google_places",
                    osm_id=None,
                    place_type=place.get('types', [None])[0] if place.get('types') else None,
                )

                candidate = ScoredCandidate(
                    place=place_result,
                    distance_miles=round(distance_miles, 1),
                    name_similarity=100.0,
                    combined_score=100.0 - distance_miles,  # Score inversely proportional to distance
                    selection_reason=SelectionReason.BEST_OVERALL_SCORE,
                )
                candidates.append(candidate)

        # Sort by distance (closest first)
        candidates.sort(key=lambda c: c.distance_miles)

        # Limit to top 5 closest
        candidates = candidates[:5]

        if not candidates:
            print(f"[Resolver] No valid candidates within 50 miles")
            return ResolvedPlace(
                query=query,
                selected=None,
                candidates=[],
                decision=ResolutionDecision.NO_MATCH,
                decision_reason="No places found within 50 miles",
            )

        # Always auto-select the closest location for optimal route planning
        # In the future, this can be enhanced to consider the full day's route
        # and select locations that minimize total travel time/distance
        top = candidates[0]

        if len(candidates) == 1:
            top.selection_reason = SelectionReason.ONLY_MATCH
            reason = "Only match found"
        else:
            top.selection_reason = SelectionReason.BEST_OVERALL_SCORE
            reason = "Closest location"

        print(f"[Resolver] ✅ Auto-selected: {top.display_name} ({top.distance_miles} mi) - {reason}")
        print(f"   Other options: {', '.join([f'{c.display_name} ({c.distance_miles} mi)' for c in candidates[1:3]])}" if len(candidates) > 1 else "")

        return ResolvedPlace(
            query=query,
            selected=top,
            candidates=candidates,
            decision=ResolutionDecision.AUTO_BEST,
            decision_reason=f"{top.distance_miles} mi - {reason}",
        )

    except Exception as e:
        print(f"[Resolver] Error: {e}")
        import traceback
        traceback.print_exc()
        return ResolvedPlace(
            query=query,
            selected=None,
            candidates=[],
            decision=ResolutionDecision.NO_MATCH,
            decision_reason=f"Error: {str(e)}",
        )


def select_candidate(
    resolved: ResolvedPlace,
    candidate_index: int,
) -> ResolvedPlace:
    """
    Update a ResolvedPlace with user's selection.

    Args:
        resolved: Original ResolvedPlace
        candidate_index: Index of selected candidate

    Returns:
        Updated ResolvedPlace with user selection
    """
    if candidate_index < 0 or candidate_index >= len(resolved.candidates):
        return resolved

    selected = resolved.candidates[candidate_index]
    selected.selection_reason = SelectionReason.USER_SELECTED

    return ResolvedPlace(
        query=resolved.query,
        selected=selected,
        candidates=resolved.candidates,
        decision=ResolutionDecision.USER_SELECTED,
        decision_reason="User selected",
    )


def get_multiple_candidates(
    query: str,
    settings: Settings,
    radius_miles: float = 25.0,
    limit: int = 5,
) -> List[PlaceSearchResult]:
    """
    Get multiple place candidates for user selection.

    Args:
        query: User's search query
        settings: User settings with home location
        radius_miles: Search radius in miles
        limit: Maximum number of results

    Returns:
        List of PlaceSearchResult objects
    """
    if not settings.has_home_location or not gmaps:
        return []

    try:
        radius_meters = int(radius_miles * 1609.34)

        result = gmaps.places(
            query=query,
            location=(settings.home_lat, settings.home_lon),
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
                candidates.append(PlaceSearchResult(
                    name=name,
                    address=address,
                    lat=lat,
                    lon=lon,
                    source="google_places",
                    osm_id=None,
                    place_type=place.get('types', [None])[0] if place.get('types') else None,
                ))

        print(f"[Resolver] Found {len(candidates)} candidates")
        return candidates

    except Exception as e:
        print(f"[Resolver] Error getting candidates: {e}")
        return []
