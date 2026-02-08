"""Route optimizer - TSP-style optimization for minimal travel distance."""

from dataclasses import dataclass
from itertools import permutations
from typing import Optional

from orbit.services import routing


@dataclass
class OptimizedRoute:
    """Result of route optimization."""
    stop_order: list[int]  # Indices into original stops list
    total_distance_km: float
    naive_distance_km: float  # Distance if stops visited in original order
    savings_km: float  # How much distance saved
    method: str  # "brute_force", "nearest_neighbor", or "2opt"


def calculate_route_distance(
    start_lat: float,
    start_lon: float,
    stops: list[tuple[float, float]],
    order: list[int],
    return_to_start: bool = True,
) -> float:
    """
    Calculate total route distance for a given stop order.

    Args:
        start_lat: Starting point latitude
        start_lon: Starting point longitude
        stops: List of (lat, lon) tuples for stops
        order: Indices specifying the order to visit stops
        return_to_start: Whether to return to starting point

    Returns:
        Total distance in kilometers
    """
    if not order:
        return 0.0

    total_km = 0.0

    # Distance from start to first stop
    first_stop = stops[order[0]]
    total_km += routing.haversine_distance(
        start_lat, start_lon,
        first_stop[0], first_stop[1]
    )

    # Distance between consecutive stops
    for i in range(len(order) - 1):
        from_stop = stops[order[i]]
        to_stop = stops[order[i + 1]]
        total_km += routing.haversine_distance(
            from_stop[0], from_stop[1],
            to_stop[0], to_stop[1]
        )

    # Distance from last stop back to start
    if return_to_start:
        last_stop = stops[order[-1]]
        total_km += routing.haversine_distance(
            last_stop[0], last_stop[1],
            start_lat, start_lon
        )

    return total_km


def optimize_brute_force(
    start_lat: float,
    start_lon: float,
    stops: list[tuple[float, float]],
    return_to_start: bool = True,
) -> tuple[list[int], float]:
    """
    Find optimal route by trying all permutations.

    Only use for small N (≤ 6) as complexity is O(n!).

    Args:
        start_lat: Starting point latitude
        start_lon: Starting point longitude
        stops: List of (lat, lon) tuples
        return_to_start: Whether to return to start

    Returns:
        (best_order, best_distance) tuple
    """
    n = len(stops)
    if n == 0:
        return [], 0.0
    if n == 1:
        return [0], calculate_route_distance(
            start_lat, start_lon, stops, [0], return_to_start
        )

    best_order = list(range(n))
    best_distance = calculate_route_distance(
        start_lat, start_lon, stops, best_order, return_to_start
    )

    for perm in permutations(range(n)):
        order = list(perm)
        distance = calculate_route_distance(
            start_lat, start_lon, stops, order, return_to_start
        )
        if distance < best_distance:
            best_distance = distance
            best_order = order

    return best_order, best_distance


def optimize_nearest_neighbor(
    start_lat: float,
    start_lon: float,
    stops: list[tuple[float, float]],
    return_to_start: bool = True,
) -> tuple[list[int], float]:
    """
    Greedy nearest neighbor heuristic.

    At each step, visit the nearest unvisited stop.

    Args:
        start_lat: Starting point latitude
        start_lon: Starting point longitude
        stops: List of (lat, lon) tuples
        return_to_start: Whether to return to start

    Returns:
        (order, distance) tuple
    """
    n = len(stops)
    if n == 0:
        return [], 0.0
    if n == 1:
        return [0], calculate_route_distance(
            start_lat, start_lon, stops, [0], return_to_start
        )

    visited = set()
    order = []
    current_lat, current_lon = start_lat, start_lon

    while len(visited) < n:
        # Find nearest unvisited stop
        best_idx = -1
        best_dist = float('inf')

        for i in range(n):
            if i in visited:
                continue
            dist = routing.haversine_distance(
                current_lat, current_lon,
                stops[i][0], stops[i][1]
            )
            if dist < best_dist:
                best_dist = dist
                best_idx = i

        if best_idx >= 0:
            visited.add(best_idx)
            order.append(best_idx)
            current_lat, current_lon = stops[best_idx]

    total_distance = calculate_route_distance(
        start_lat, start_lon, stops, order, return_to_start
    )

    return order, total_distance


def optimize_2opt(
    start_lat: float,
    start_lon: float,
    stops: list[tuple[float, float]],
    initial_order: list[int],
    return_to_start: bool = True,
    max_iterations: int = 1000,
) -> tuple[list[int], float]:
    """
    2-opt improvement on an initial route.

    Repeatedly reverses segments to reduce total distance.

    Args:
        start_lat: Starting point latitude
        start_lon: Starting point longitude
        stops: List of (lat, lon) tuples
        initial_order: Starting order to improve
        return_to_start: Whether to return to start
        max_iterations: Max improvement iterations

    Returns:
        (improved_order, distance) tuple
    """
    n = len(stops)
    if n <= 2:
        return initial_order, calculate_route_distance(
            start_lat, start_lon, stops, initial_order, return_to_start
        )

    order = list(initial_order)
    best_distance = calculate_route_distance(
        start_lat, start_lon, stops, order, return_to_start
    )

    improved = True
    iterations = 0

    while improved and iterations < max_iterations:
        improved = False
        iterations += 1

        for i in range(n - 1):
            for j in range(i + 2, n):
                # Create new order by reversing segment [i+1, j]
                new_order = order[:i + 1] + order[i + 1:j + 1][::-1] + order[j + 1:]

                new_distance = calculate_route_distance(
                    start_lat, start_lon, stops, new_order, return_to_start
                )

                if new_distance < best_distance - 0.001:  # Small epsilon for floating point
                    order = new_order
                    best_distance = new_distance
                    improved = True
                    break

            if improved:
                break

    return order, best_distance


def optimize_route(
    start_lat: float,
    start_lon: float,
    stops: list[tuple[float, float]],
    return_to_start: bool = True,
) -> OptimizedRoute:
    """
    Find optimal route order to minimize total travel distance.

    Uses brute-force for N ≤ 6, nearest neighbor + 2-opt for larger N.

    Args:
        start_lat: Starting point latitude
        start_lon: Starting point longitude
        stops: List of (lat, lon) tuples for stops to visit
        return_to_start: Whether to return to starting point at end

    Returns:
        OptimizedRoute with optimal order and distance info
    """
    n = len(stops)

    if n == 0:
        return OptimizedRoute(
            stop_order=[],
            total_distance_km=0.0,
            naive_distance_km=0.0,
            savings_km=0.0,
            method="none",
        )

    # Calculate naive distance (original order)
    naive_order = list(range(n))
    naive_distance = calculate_route_distance(
        start_lat, start_lon, stops, naive_order, return_to_start
    )

    if n == 1:
        return OptimizedRoute(
            stop_order=[0],
            total_distance_km=naive_distance,
            naive_distance_km=naive_distance,
            savings_km=0.0,
            method="single_stop",
        )

    # Choose optimization method based on number of stops
    if n <= 6:
        # Brute force for small N (6! = 720 permutations is fast)
        best_order, best_distance = optimize_brute_force(
            start_lat, start_lon, stops, return_to_start
        )
        method = "brute_force"
    else:
        # Nearest neighbor + 2-opt for larger N
        nn_order, nn_distance = optimize_nearest_neighbor(
            start_lat, start_lon, stops, return_to_start
        )
        best_order, best_distance = optimize_2opt(
            start_lat, start_lon, stops, nn_order, return_to_start
        )
        method = "nearest_neighbor_2opt"

    savings = naive_distance - best_distance

    return OptimizedRoute(
        stop_order=best_order,
        total_distance_km=round(best_distance, 2),
        naive_distance_km=round(naive_distance, 2),
        savings_km=round(max(0, savings), 2),
        method=method,
    )


def reorder_items(items: list, order: list[int]) -> list:
    """
    Reorder a list of items according to the given order.

    Args:
        items: Original list of items
        order: New order as list of indices

    Returns:
        Reordered list
    """
    if not order or len(order) != len(items):
        return items
    return [items[i] for i in order]
