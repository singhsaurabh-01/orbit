"""Routing service - distance and travel time calculations."""

import hashlib
import json
import math
from typing import Optional

import requests

from orbit import db
from orbit.config import (
    CACHE_TTL_DAYS,
    DEFAULT_CITY_SPEED_KMH,
    OSRM_BASE_URL,
    OSRM_TIMEOUT_SECONDS,
)
from orbit.models import RouteResult


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points in kilometers.

    Args:
        lat1, lon1: First point coordinates
        lat2, lon2: Second point coordinates

    Returns:
        Distance in kilometers
    """
    R = 6371  # Earth's radius in kilometers

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def _get_route_cache_key(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Generate a cache key for a route."""
    content = json.dumps([lat1, lon1, lat2, lon2], sort_keys=True)
    hash_val = hashlib.md5(content.encode()).hexdigest()[:16]
    return f"route:{hash_val}"


def get_route_osrm(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
) -> Optional[RouteResult]:
    """
    Get route from OSRM API.

    Args:
        origin_lat, origin_lon: Origin coordinates
        dest_lat, dest_lon: Destination coordinates

    Returns:
        RouteResult if successful, None otherwise
    """
    try:
        # OSRM expects lon,lat order
        url = (
            f"{OSRM_BASE_URL}/route/v1/driving/"
            f"{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
        )
        response = requests.get(
            url,
            params={
                "overview": "simplified",
                "geometries": "polyline",
            },
            timeout=OSRM_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("code") == "Ok" and data.get("routes"):
            route = data["routes"][0]
            distance_km = route["distance"] / 1000  # Convert meters to km
            duration_minutes = route["duration"] / 60  # Convert seconds to minutes

            return RouteResult(
                origin_lat=origin_lat,
                origin_lon=origin_lon,
                dest_lat=dest_lat,
                dest_lon=dest_lon,
                distance_km=round(distance_km, 2),
                duration_minutes=round(duration_minutes, 1),
                geometry=route.get("geometry"),
                source="osrm",
            )
        return None

    except requests.RequestException as e:
        print(f"OSRM routing error: {e}")
        return None


def get_route_fallback(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    avg_speed_kmh: float = DEFAULT_CITY_SPEED_KMH,
) -> RouteResult:
    """
    Calculate route using haversine distance as fallback.

    Assumes straight-line distance with a multiplier for road paths
    and average city driving speed.

    Args:
        origin_lat, origin_lon: Origin coordinates
        dest_lat, dest_lon: Destination coordinates
        avg_speed_kmh: Average driving speed in km/h

    Returns:
        RouteResult with estimated values
    """
    # Haversine gives straight-line distance; multiply by ~1.4 for road paths
    straight_distance = haversine_distance(origin_lat, origin_lon, dest_lat, dest_lon)
    road_distance = straight_distance * 1.4

    # Estimate duration based on average speed
    duration_minutes = (road_distance / avg_speed_kmh) * 60

    return RouteResult(
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        dest_lat=dest_lat,
        dest_lon=dest_lon,
        distance_km=round(road_distance, 2),
        duration_minutes=round(duration_minutes, 1),
        geometry=None,
        source="fallback",
    )


def get_route(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    use_cache: bool = True,
) -> RouteResult:
    """
    Get route between two points.

    Tries OSRM first, falls back to haversine estimation.
    Results are cached.

    Args:
        origin_lat, origin_lon: Origin coordinates
        dest_lat, dest_lon: Destination coordinates
        use_cache: Whether to use/store cache

    Returns:
        RouteResult
    """
    # Check cache
    if use_cache:
        cache_key = _get_route_cache_key(origin_lat, origin_lon, dest_lat, dest_lon)
        cached = db.get_cache(cache_key)
        if cached:
            data = json.loads(cached)
            return RouteResult(**data)

    # Try OSRM
    result = get_route_osrm(origin_lat, origin_lon, dest_lat, dest_lon)

    # Fall back to haversine if OSRM fails
    if result is None:
        result = get_route_fallback(origin_lat, origin_lon, dest_lat, dest_lon)

    # Cache result
    if use_cache:
        db.set_cache(cache_key, result.model_dump_json(), CACHE_TTL_DAYS)

    return result


def build_distance_matrix(
    locations: list[tuple[float, float]],
) -> tuple[list[list[float]], list[list[float]]]:
    """
    Build NxN matrices of distances and travel times between all location pairs.

    Args:
        locations: List of (lat, lon) tuples

    Returns:
        Tuple of (distance_matrix_km, duration_matrix_minutes)
    """
    n = len(locations)
    distances = [[0.0] * n for _ in range(n)]
    durations = [[0.0] * n for _ in range(n)]

    for i in range(n):
        for j in range(n):
            if i != j:
                route = get_route(
                    locations[i][0], locations[i][1],
                    locations[j][0], locations[j][1],
                )
                distances[i][j] = route.distance_km
                durations[i][j] = route.duration_minutes

    return distances, durations


def get_total_route_distance(
    waypoints: list[tuple[float, float]],
) -> tuple[float, float]:
    """
    Calculate total distance and duration for a sequence of waypoints.

    Args:
        waypoints: Ordered list of (lat, lon) tuples

    Returns:
        Tuple of (total_distance_km, total_duration_minutes)
    """
    if len(waypoints) < 2:
        return 0.0, 0.0

    total_distance = 0.0
    total_duration = 0.0

    for i in range(len(waypoints) - 1):
        route = get_route(
            waypoints[i][0], waypoints[i][1],
            waypoints[i + 1][0], waypoints[i + 1][1],
        )
        total_distance += route.distance_km
        total_duration += route.duration_minutes

    return round(total_distance, 2), round(total_duration, 1)


def get_route_geometry(waypoints: list[tuple[float, float]]) -> list[Optional[str]]:
    """
    Get route geometries for a sequence of waypoints.

    Args:
        waypoints: Ordered list of (lat, lon) tuples

    Returns:
        List of encoded polyline strings (or None if unavailable)
    """
    geometries = []
    for i in range(len(waypoints) - 1):
        route = get_route(
            waypoints[i][0], waypoints[i][1],
            waypoints[i + 1][0], waypoints[i + 1][1],
        )
        geometries.append(route.geometry)
    return geometries
