"""Place resolver service - fuzzy matching, scoring, and disambiguation."""

import re
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from rapidfuzz import fuzz, process

from orbit.models import Settings, PlaceSearchResult
from orbit.services import places, routing
from orbit.config import OSM_SEARCH_RADIUS_MILES, OSM_EXPANDED_RADIUS_MILES

# Import LLM and web search services (optional)
try:
    from orbit.services.gemini_resolver import (
        validate_and_rank_candidates,
        extract_location_context,
        should_use_web_search,
    )
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    from orbit.services.google_places import (
        search_place_with_google,
        should_use_google_places,
    )
    GOOGLE_PLACES_AVAILABLE = True
except ImportError:
    GOOGLE_PLACES_AVAILABLE = False

try:
    from orbit.services.tavily_search import search_place_with_tavily
    TAVILY_AVAILABLE = True
except ImportError:
    TAVILY_AVAILABLE = False


class ResolutionDecision(Enum):
    """How a place was resolved."""
    AUTO_BEST = "auto_best"          # Clear best match, auto-selected
    USER_SELECTED = "user_selected"  # User chose from candidates
    NO_MATCH = "no_match"            # Could not find any match
    PENDING = "pending"              # Awaiting user selection


class SelectionReason(Enum):
    """Why a candidate was selected."""
    CLOSEST_TO_HOME = "closest_to_home"
    BEST_OVERALL_SCORE = "best_overall_score"
    CLEAR_WINNER = "clear_winner"
    ONLY_MATCH = "only_match"
    USER_SELECTED = "user_selected"
    BEST_FOR_ROUTE = "best_for_route"  # Minimizes total route distance


@dataclass
class ScoredCandidate:
    """A place candidate with scoring information."""
    place: PlaceSearchResult
    distance_miles: float
    name_similarity: float  # 0-100
    combined_score: float   # Higher is better
    selection_reason: Optional[SelectionReason] = None

    @property
    def display_name(self) -> str:
        """Get display name."""
        return self.place.name

    @property
    def display_address(self) -> str:
        """Get shortened address for display."""
        addr = self.place.address
        # Truncate long addresses
        if len(addr) > 60:
            return addr[:57] + "..."
        return addr

    @property
    def full_address(self) -> str:
        """Get full address."""
        return self.place.address

    def get_reason_text(self) -> str:
        """Get human-readable selection reason."""
        if self.selection_reason == SelectionReason.CLOSEST_TO_HOME:
            return "Closest to home"
        elif self.selection_reason == SelectionReason.BEST_OVERALL_SCORE:
            return "Best overall match"
        elif self.selection_reason == SelectionReason.CLEAR_WINNER:
            return "Clear best match"
        elif self.selection_reason == SelectionReason.ONLY_MATCH:
            return "Only match found"
        elif self.selection_reason == SelectionReason.USER_SELECTED:
            return "User selected"
        elif self.selection_reason == SelectionReason.BEST_FOR_ROUTE:
            return "Best for route (min total distance)"
        return "Auto-selected"


@dataclass
class ResolvedPlace:
    """Result of place resolution."""
    query: str                           # Original user input
    selected: Optional[ScoredCandidate]  # The selected candidate
    candidates: list[ScoredCandidate]    # All candidates found
    decision: ResolutionDecision         # How it was resolved
    decision_reason: str                 # Human-readable explanation

    @property
    def needs_disambiguation(self) -> bool:
        """Check if user needs to choose between candidates."""
        return self.decision == ResolutionDecision.PENDING

    @property
    def is_resolved(self) -> bool:
        """Check if place is fully resolved."""
        return self.decision in (ResolutionDecision.AUTO_BEST, ResolutionDecision.USER_SELECTED)


def normalize_text(text: str) -> str:
    """
    Normalize text for fuzzy matching.

    - Lowercase
    - Strip punctuation
    - Collapse whitespace
    """
    text = text.lower()
    # Remove punctuation except spaces
    text = re.sub(r'[^\w\s]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def calculate_name_similarity(query: str, candidate_name: str) -> float:
    """
    Calculate fuzzy similarity between query and candidate name.

    Uses multiple fuzzy matching strategies and returns best score (0-100).
    """
    query_norm = normalize_text(query)
    name_norm = normalize_text(candidate_name)

    if not query_norm or not name_norm:
        return 0.0

    # Try multiple fuzzy strategies
    scores = [
        fuzz.ratio(query_norm, name_norm),           # Full string match
        fuzz.partial_ratio(query_norm, name_norm),   # Partial/substring match
        fuzz.token_sort_ratio(query_norm, name_norm), # Token order independent
        fuzz.token_set_ratio(query_norm, name_norm),  # Token set comparison
    ]

    return max(scores)


def km_to_miles(km: float) -> float:
    """Convert kilometers to miles."""
    return km * 0.621371


def calculate_distance_miles(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> float:
    """Calculate distance in miles between two coordinates."""
    km = routing.haversine_distance(lat1, lon1, lat2, lon2)
    return km_to_miles(km)


def calculate_combined_score(
    distance_miles: float,
    name_similarity: float,
    max_distance: float = 25.0,
) -> float:
    """
    Calculate combined score for ranking candidates.

    Higher score = better candidate.

    Scoring:
    - Distance: 0-50 points (closer = higher)
    - Name similarity: 0-50 points (more similar = higher)
    """
    # Distance score: 50 points at 0 miles, 0 points at max_distance
    if distance_miles >= max_distance:
        distance_score = 0
    else:
        distance_score = 50 * (1 - distance_miles / max_distance)

    # Name similarity score: direct mapping (0-100 -> 0-50)
    name_score = name_similarity / 2

    return distance_score + name_score


def are_same_brand(candidate1: ScoredCandidate, candidate2: ScoredCandidate, threshold: float = 70.0) -> bool:
    """
    Check if two candidates are the same brand/chain.

    Args:
        candidate1: First candidate
        candidate2: Second candidate
        threshold: Name similarity threshold to consider same brand

    Returns:
        True if candidates appear to be same brand
    """
    name1 = normalize_text(candidate1.place.name)
    name2 = normalize_text(candidate2.place.name)

    # Direct similarity between candidate names
    similarity = calculate_name_similarity(name1, name2)
    return similarity >= threshold


def score_candidates(
    query: str,
    candidates: list[PlaceSearchResult],
    home_lat: float,
    home_lon: float,
) -> list[ScoredCandidate]:
    """
    Score and rank candidates by distance and name similarity.

    Returns candidates sorted by combined score (best first).
    """
    scored = []

    for candidate in candidates:
        # Calculate distance from home
        distance = calculate_distance_miles(
            home_lat, home_lon,
            candidate.lat, candidate.lon,
        )

        # Calculate name similarity
        similarity = calculate_name_similarity(query, candidate.name)

        # Calculate combined score
        combined = calculate_combined_score(distance, similarity)

        scored.append(ScoredCandidate(
            place=candidate,
            distance_miles=round(distance, 1),
            name_similarity=round(similarity, 1),
            combined_score=round(combined, 1),
        ))

    # Sort by combined score (highest first)
    scored.sort(key=lambda x: x.combined_score, reverse=True)

    return scored


def apply_home_proximity_tiebreak(
    candidates: list[ScoredCandidate],
    similarity_threshold: float = 70.0,
) -> list[ScoredCandidate]:
    """
    Apply home proximity tie-break for same-brand candidates.

    When multiple candidates have similar high name similarity (same brand),
    sort by distance to home (closest first).

    Args:
        candidates: Scored candidates
        similarity_threshold: Threshold for "same brand" name similarity

    Returns:
        Reordered candidates with home proximity tie-break applied
    """
    if len(candidates) <= 1:
        return candidates

    # Find candidates that are "same brand" as the top one
    top = candidates[0]
    same_brand_candidates = [top]
    other_candidates = []

    for c in candidates[1:]:
        if (c.name_similarity >= similarity_threshold and
            top.name_similarity >= similarity_threshold and
            are_same_brand(top, c)):
            same_brand_candidates.append(c)
        else:
            other_candidates.append(c)

    # Sort same-brand candidates by distance (closest first)
    same_brand_candidates.sort(key=lambda x: x.distance_miles)

    # Mark the closest same-brand as "closest to home"
    if len(same_brand_candidates) > 1:
        same_brand_candidates[0].selection_reason = SelectionReason.CLOSEST_TO_HOME

    return same_brand_candidates + other_candidates


def select_best_for_route(
    candidates: list[ScoredCandidate],
    prev_stop_lat: Optional[float],
    prev_stop_lon: Optional[float],
    home_lat: float,
    home_lon: float,
    is_last_stop: bool = False,
    return_home: bool = True,
) -> list[ScoredCandidate]:
    """
    Select best candidate considering route optimization.

    For last stop when returning home, prefer candidate that minimizes
    (distance from previous stop + distance to home).

    Args:
        candidates: Scored candidates
        prev_stop_lat: Previous stop latitude (None if first stop)
        prev_stop_lon: Previous stop longitude (None if first stop)
        home_lat: Home latitude
        home_lon: Home longitude
        is_last_stop: Whether this is the last stop
        return_home: Whether returning home after last stop

    Returns:
        Reordered candidates with route-optimized selection
    """
    if not candidates or len(candidates) <= 1:
        return candidates

    # Only apply route optimization for last stop when returning home
    if not (is_last_stop and return_home and prev_stop_lat and prev_stop_lon):
        return candidates

    # Calculate total added distance for each candidate
    # (distance from prev stop + distance to home)
    candidate_route_scores = []
    for c in candidates:
        dist_from_prev = calculate_distance_miles(
            prev_stop_lat, prev_stop_lon,
            c.place.lat, c.place.lon
        )
        dist_to_home = calculate_distance_miles(
            c.place.lat, c.place.lon,
            home_lat, home_lon
        )
        total_added = dist_from_prev + dist_to_home
        candidate_route_scores.append((c, total_added))

    # Find candidates with high name similarity (same brand)
    top = candidates[0]
    same_brand = [
        (c, score) for c, score in candidate_route_scores
        if c.name_similarity >= 70.0 and are_same_brand(top, c)
    ]

    if len(same_brand) > 1:
        # Sort same-brand by total added distance
        same_brand.sort(key=lambda x: x[1])
        best_for_route = same_brand[0][0]

        # If best for route is different from closest to home, mark it
        closest_to_home = min(candidates, key=lambda x: x.distance_miles)
        if best_for_route != closest_to_home:
            best_for_route.selection_reason = SelectionReason.BEST_FOR_ROUTE

        # Reorder: best for route first, then others
        reordered = [best_for_route]
        for c, _ in candidate_route_scores:
            if c != best_for_route:
                reordered.append(c)
        return reordered

    return candidates


def should_auto_select(candidates: list[ScoredCandidate]) -> tuple[bool, SelectionReason]:
    """
    Determine if we should auto-select the top candidate.

    Returns:
        (should_auto_select, reason) tuple
    """
    if len(candidates) == 0:
        return False, SelectionReason.ONLY_MATCH

    if len(candidates) == 1:
        # Single candidate with decent match
        if candidates[0].name_similarity >= 50:
            return True, SelectionReason.ONLY_MATCH
        return False, SelectionReason.ONLY_MATCH

    top = candidates[0]
    second = candidates[1]

    # If top is much better than second, auto-select
    score_gap = top.combined_score - second.combined_score
    if score_gap >= 15:
        return True, SelectionReason.CLEAR_WINNER

    # If top has very high similarity and is close, auto-select
    if top.name_similarity >= 80 and top.distance_miles <= 10:
        return True, SelectionReason.BEST_OVERALL_SCORE

    # If top is same brand/name but closer, auto-select (home proximity)
    if (top.name_similarity >= 70 and
        second.name_similarity >= 70 and
        are_same_brand(top, second) and
        top.distance_miles < second.distance_miles):
        return True, SelectionReason.CLOSEST_TO_HOME

    return False, SelectionReason.BEST_OVERALL_SCORE


def filter_osm_results(
    candidates: list[PlaceSearchResult],
    home_lat: float,
    home_lon: float,
    max_distance_miles: float = 25.0,
) -> list[PlaceSearchResult]:
    """
    Filter out obviously wrong OSM results.

    Removes:
    - Results outside the USA (if home is in USA)
    - Results beyond max_distance_miles
    - Results with very low quality indicators

    Args:
        candidates: List of PlaceSearchResult from OSM
        home_lat: User's home latitude
        home_lon: User's home longitude
        max_distance_miles: Maximum distance threshold

    Returns:
        Filtered list of candidates
    """
    if not candidates:
        return []

    filtered = []

    for candidate in candidates:
        # Calculate distance
        distance_km = routing.haversine_distance(
            home_lat, home_lon,
            candidate.lat, candidate.lon
        )
        distance_miles = km_to_miles(distance_km)

        # Filter by distance
        if distance_miles > max_distance_miles:
            continue

        # Filter by country (US only if home is in US)
        # Check if address contains "United States" or US state abbreviations
        address_lower = candidate.address.lower()

        # If it explicitly mentions other countries, skip
        other_countries = ["ireland", "united kingdom", "canada", "mexico", "australia"]
        if any(country in address_lower for country in other_countries):
            # Skip unless home is in that country
            if not any(country in candidate.address.lower() for country in other_countries):
                continue

        filtered.append(candidate)

    return filtered


def resolve_place(
    query: str,
    settings: Settings,
    search_radius_miles: float = OSM_SEARCH_RADIUS_MILES,
    expand_radius_miles: float = OSM_EXPANDED_RADIUS_MILES,
    limit: int = 10,
    prev_stop_lat: Optional[float] = None,
    prev_stop_lon: Optional[float] = None,
    is_last_stop: bool = False,
    return_home: bool = True,
) -> ResolvedPlace:
    """
    Resolve a place query to coordinates using multi-tier strategy:
    Tier 1: OSM search with filtering
    Tier 2: Google Places API (if OSM fails or for retail chains)
    Tier 3: Gemini LLM validation (if available)
    Tier 4: Tavily web search fallback (if available)

    Args:
        query: User's place query (possibly misspelled)
        settings: User settings with home location
        search_radius_miles: Initial search radius
        expand_radius_miles: Expanded radius if no results
        limit: Max candidates to return
        prev_stop_lat: Previous stop latitude (for route optimization)
        prev_stop_lon: Previous stop longitude (for route optimization)
        is_last_stop: Whether this is the last stop
        return_home: Whether returning home after errands

    Returns:
        ResolvedPlace with candidates and resolution status
    """
    if not settings.has_home_location:
        return ResolvedPlace(
            query=query,
            selected=None,
            candidates=[],
            decision=ResolutionDecision.NO_MATCH,
            decision_reason="Home location not set",
        )

    # Extract user's location context for LLM
    user_city, user_state = "", ""
    if GEMINI_AVAILABLE:
        try:
            user_city, user_state = extract_location_context(settings.home_address)
        except Exception:
            user_city, user_state = "", ""

    # === TIER 1: OSM Search with Smart Filtering ===
    normalized_query = normalize_text(query)

    print(f"[TIER 1] Searching OSM for: '{query}'")

    # Search with initial radius
    candidates = places.search_places_nearby(
        query,
        settings.home_lat,
        settings.home_lon,
        radius_km=search_radius_miles / 0.621371,  # Convert to km
        limit=limit,
    )

    print(f"[TIER 1] OSM found {len(candidates)} candidates")

    # If no results, try expanded radius (but smaller than before - 25mi max)
    if not candidates:
        candidates = places.search_places_nearby(
            query,
            settings.home_lat,
            settings.home_lon,
            radius_km=expand_radius_miles / 0.621371,
            limit=limit,
        )

    # If still no results, try geocoding as an address
    if not candidates:
        result = places.geocode_address(query)
        if result:
            candidates = [result]

    # Filter out obviously wrong results (international, too far, etc.)
    candidates = filter_osm_results(
        candidates,
        settings.home_lat,
        settings.home_lon,
        max_distance_miles=expand_radius_miles,
    )

    # === TIER 2: Google Places API ===
    # Use Google Places if OSM results are poor or query looks like a retail chain
    if GOOGLE_PLACES_AVAILABLE and should_use_google_places(query, candidates):
        print(f"[TIER 2] Using Google Places API")
        google_result = search_place_with_google(
            query=query,
            center_lat=settings.home_lat,
            center_lon=settings.home_lon,
            radius_miles=expand_radius_miles,
        )

        if google_result:
            # Add Google result to top of candidates
            candidates.insert(0, google_result)
            print(f"[TIER 2] Google Places found: {google_result.name}")
        else:
            print(f"[TIER 2] Google Places found nothing")
    else:
        print(f"[TIER 2] Skipped Google Places - OSM results look good or API not available")

    # === TIER 3: Gemini LLM Validation ===
    llm_validation = None
    if GEMINI_AVAILABLE and candidates and user_city and user_state:
        print(f"[TIER 2] Calling Gemini for validation (city: {user_city}, state: {user_state})")
        llm_validation = validate_and_rank_candidates(
            query=query,
            candidates=candidates,
            user_city=user_city,
            user_state=user_state,
            max_distance_miles=expand_radius_miles,
        )

        print(f"[TIER 2] Gemini validation: {llm_validation}")

        # If LLM picked a specific candidate, reorder to put it first
        if llm_validation and llm_validation.get("best_index") is not None:
            best_idx = llm_validation["best_index"]
            if 0 <= best_idx < len(candidates):
                best_candidate = candidates.pop(best_idx)
                candidates.insert(0, best_candidate)
                print(f"[TIER 2] Reordered candidates, best at index 0")
    else:
        print(f"[TIER 2] Skipped - GEMINI_AVAILABLE:{GEMINI_AVAILABLE}, candidates:{len(candidates) if candidates else 0}, city:{user_city}, state:{user_state}")

    # === TIER 4: Tavily Web Search Fallback ===
    if GEMINI_AVAILABLE and TAVILY_AVAILABLE and should_use_web_search(query, candidates, llm_validation):
        print(f"[TIER 4] Triggering Tavily web search")
        if user_city and user_state:
            tavily_result = search_place_with_tavily(query, user_city, user_state)
            if tavily_result:
                # Add Tavily result to top of candidates
                candidates.insert(0, tavily_result)
                print(f"[TIER 4] Tavily found: {tavily_result.name}")
            else:
                print(f"[TIER 4] Tavily returned no results")
    else:
        print(f"[TIER 4] Skipped - should_use_web_search returned False or services unavailable")

    # If no candidates after all tiers, return NO_MATCH
    if not candidates:
        return ResolvedPlace(
            query=query,
            selected=None,
            candidates=[],
            decision=ResolutionDecision.NO_MATCH,
            decision_reason=f"No places found for '{query}'",
        )

    # Score and rank candidates
    scored = score_candidates(
        query,
        candidates,
        settings.home_lat,
        settings.home_lon,
    )

    # Apply home proximity tie-break for same-brand candidates
    scored = apply_home_proximity_tiebreak(scored)

    # Apply route optimization if this is last stop
    if is_last_stop and return_home:
        scored = select_best_for_route(
            scored,
            prev_stop_lat,
            prev_stop_lon,
            settings.home_lat,
            settings.home_lon,
            is_last_stop=True,
            return_home=True,
        )

    # Filter to top candidates (limit)
    scored = scored[:limit]

    # Decide if we can auto-select
    should_auto, reason = should_auto_select(scored)

    # If LLM gave us high confidence, be more aggressive about auto-selecting
    if llm_validation and llm_validation.get("confidence") == "high" and scored:
        should_auto = True
        reason = SelectionReason.BEST_OVERALL_SCORE

    if should_auto:
        top = scored[0]
        if not top.selection_reason:
            top.selection_reason = reason

        reason_text = top.get_reason_text()
        # Include LLM reasoning if available
        if llm_validation and llm_validation.get("reasoning"):
            reason_text += f" - {llm_validation['reasoning']}"

        return ResolvedPlace(
            query=query,
            selected=top,
            candidates=scored,
            decision=ResolutionDecision.AUTO_BEST,
            decision_reason=f"{top.distance_miles} mi ({reason_text})",
        )
    else:
        # Multiple plausible candidates - need user selection
        return ResolvedPlace(
            query=query,
            selected=None,
            candidates=scored,
            decision=ResolutionDecision.PENDING,
            decision_reason="Multiple matches found - please select",
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


def resolve_multiple(
    queries: list[str],
    settings: Settings,
) -> list[ResolvedPlace]:
    """
    Resolve multiple place queries.

    Args:
        queries: List of place queries
        settings: User settings

    Returns:
        List of ResolvedPlace objects
    """
    return [resolve_place(q, settings) for q in queries if q.strip()]


def any_needs_disambiguation(resolved_list: list[ResolvedPlace]) -> bool:
    """Check if any resolved places need user disambiguation."""
    return any(r.needs_disambiguation for r in resolved_list)


def all_resolved(resolved_list: list[ResolvedPlace]) -> bool:
    """Check if all places are fully resolved."""
    return all(r.is_resolved for r in resolved_list)
