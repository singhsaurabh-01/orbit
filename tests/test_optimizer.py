"""Tests for route optimizer."""

import pytest
import sys
sys.path.insert(0, "src")

from orbit.services.optimizer import (
    optimize_route,
    optimize_brute_force,
    optimize_nearest_neighbor,
    optimize_2opt,
    calculate_route_distance,
    reorder_items,
    OptimizedRoute,
)


class TestCalculateRouteDistance:
    """Tests for route distance calculation."""

    def test_empty_stops(self):
        """Empty stops should return 0."""
        dist = calculate_route_distance(30.5, -97.5, [], [], return_to_start=True)
        assert dist == 0.0

    def test_single_stop(self):
        """Single stop distance calculation."""
        stops = [(30.6, -97.6)]
        dist = calculate_route_distance(
            30.5, -97.5, stops, [0], return_to_start=True
        )
        # Should be: start -> stop -> start (round trip)
        assert dist > 0

    def test_return_to_start_increases_distance(self):
        """Return to start should add more distance."""
        stops = [(30.6, -97.6)]
        with_return = calculate_route_distance(
            30.5, -97.5, stops, [0], return_to_start=True
        )
        without_return = calculate_route_distance(
            30.5, -97.5, stops, [0], return_to_start=False
        )
        assert with_return > without_return


class TestBruteForceOptimization:
    """Tests for brute-force TSP optimization."""

    def test_single_stop(self):
        """Single stop should return [0]."""
        order, dist = optimize_brute_force(30.5, -97.5, [(30.6, -97.6)])
        assert order == [0]
        assert dist > 0

    def test_two_stops_optimal_order(self):
        """Two stops should find optimal order."""
        # Start at (30.5, -97.5)
        # Stop A at (30.6, -97.5) - north
        # Stop B at (30.7, -97.5) - farther north
        # Optimal should visit A then B (or B then A if returning)
        stops = [(30.6, -97.5), (30.7, -97.5)]
        order, dist = optimize_brute_force(30.5, -97.5, stops, return_to_start=True)
        assert len(order) == 2
        assert set(order) == {0, 1}

    def test_finds_better_than_naive(self):
        """Should find route better or equal to naive order."""
        # Triangle: start at origin, stops at different distances
        stops = [
            (30.8, -97.5),  # Far
            (30.55, -97.5),  # Near
            (30.7, -97.5),  # Medium
        ]
        order, best_dist = optimize_brute_force(30.5, -97.5, stops, return_to_start=True)

        # Calculate naive distance (0, 1, 2)
        naive_dist = calculate_route_distance(30.5, -97.5, stops, [0, 1, 2], return_to_start=True)

        # Optimized should be <= naive
        assert best_dist <= naive_dist


class TestNearestNeighborOptimization:
    """Tests for nearest neighbor heuristic."""

    def test_single_stop(self):
        """Single stop should return [0]."""
        order, dist = optimize_nearest_neighbor(30.5, -97.5, [(30.6, -97.6)])
        assert order == [0]

    def test_visits_all_stops(self):
        """Should visit all stops exactly once."""
        stops = [(30.6, -97.5), (30.7, -97.6), (30.55, -97.55)]
        order, dist = optimize_nearest_neighbor(30.5, -97.5, stops)
        assert len(order) == 3
        assert set(order) == {0, 1, 2}

    def test_picks_nearest_first(self):
        """First stop should be the nearest to start."""
        stops = [
            (30.8, -97.5),   # Far (index 0)
            (30.51, -97.5),  # Very near (index 1)
            (30.6, -97.5),   # Medium (index 2)
        ]
        order, dist = optimize_nearest_neighbor(30.5, -97.5, stops)
        # First visited should be index 1 (nearest)
        assert order[0] == 1


class TestTwoOptOptimization:
    """Tests for 2-opt improvement."""

    def test_improves_or_maintains(self):
        """2-opt should improve or maintain distance."""
        stops = [
            (30.8, -97.5),
            (30.55, -97.5),
            (30.7, -97.5),
            (30.6, -97.6),
        ]
        initial_order = [0, 1, 2, 3]  # Arbitrary order
        initial_dist = calculate_route_distance(30.5, -97.5, stops, initial_order, True)

        improved_order, improved_dist = optimize_2opt(
            30.5, -97.5, stops, initial_order, return_to_start=True
        )

        assert improved_dist <= initial_dist
        assert len(improved_order) == 4
        assert set(improved_order) == {0, 1, 2, 3}


class TestOptimizeRoute:
    """Tests for main optimize_route function."""

    def test_empty_stops(self):
        """Empty stops should return empty result."""
        result = optimize_route(30.5, -97.5, [])
        assert result.stop_order == []
        assert result.total_distance_km == 0.0
        assert result.method == "none"

    def test_single_stop(self):
        """Single stop optimization."""
        result = optimize_route(30.5, -97.5, [(30.6, -97.6)])
        assert result.stop_order == [0]
        assert result.total_distance_km > 0
        assert result.method == "single_stop"

    def test_small_n_uses_brute_force(self):
        """N <= 6 should use brute force."""
        stops = [(30.5 + i * 0.1, -97.5) for i in range(5)]
        result = optimize_route(30.5, -97.5, stops)
        assert result.method == "brute_force"
        assert len(result.stop_order) == 5

    def test_large_n_uses_nearest_neighbor_2opt(self):
        """N > 6 should use nearest neighbor + 2-opt."""
        stops = [(30.5 + i * 0.05, -97.5 + (i % 2) * 0.05) for i in range(8)]
        result = optimize_route(30.5, -97.5, stops)
        assert result.method == "nearest_neighbor_2opt"
        assert len(result.stop_order) == 8

    def test_savings_calculated(self):
        """Should calculate savings vs naive order."""
        # Deliberately suboptimal naive order
        stops = [
            (30.8, -97.5),   # Far
            (30.51, -97.5),  # Near
            (30.7, -97.5),   # Medium
        ]
        result = optimize_route(30.5, -97.5, stops, return_to_start=True)

        # Naive would go: start -> far -> near -> medium -> start
        # Optimal should be better
        assert result.naive_distance_km >= result.total_distance_km
        assert result.savings_km >= 0


class TestStartingPointOverrideRoute:
    """Tests for starting point affecting route optimization."""

    def test_different_start_different_route(self):
        """Different starting point should give different optimal route."""
        stops = [
            (30.6, -97.6),  # Stop A
            (30.8, -97.8),  # Stop B (far)
        ]

        # Start from position 1
        result1 = optimize_route(30.5, -97.5, stops, return_to_start=True)

        # Start from position near stop B
        result2 = optimize_route(30.75, -97.75, stops, return_to_start=True)

        # Both should have valid orders
        assert len(result1.stop_order) == 2
        assert len(result2.stop_order) == 2

        # Total distances should be different
        assert result1.total_distance_km != result2.total_distance_km


class TestNearbyStopsOptimization:
    """Tests for nearby stops being grouped together."""

    def test_home_depot_great_clips_near_each_other(self):
        """
        Regression test: Home Depot and Great Clips near each other
        should be visited consecutively.
        """
        # Home in Hutto
        home_lat, home_lon = 30.5427, -97.5467

        stops = [
            (30.51, -97.68),   # Target (Round Rock - west)
            (30.63, -97.68),   # Home Depot (Georgetown - northwest)
            (30.64, -97.67),   # Great Clips (Georgetown - near Home Depot)
            (30.56, -97.55),   # CVS (nearby Hutto)
        ]

        result = optimize_route(home_lat, home_lon, stops, return_to_start=True)

        # Find positions of Home Depot (1) and Great Clips (2) in the order
        hd_pos = result.stop_order.index(1)
        gc_pos = result.stop_order.index(2)

        # They should be adjacent in the optimized route
        assert abs(hd_pos - gc_pos) == 1, (
            f"Home Depot and Great Clips should be adjacent. "
            f"Order: {result.stop_order}, HD pos: {hd_pos}, GC pos: {gc_pos}"
        )


class TestReorderItems:
    """Tests for reorder_items helper."""

    def test_reorder_basic(self):
        """Basic reordering test."""
        items = ["A", "B", "C", "D"]
        order = [2, 0, 3, 1]
        result = reorder_items(items, order)
        assert result == ["C", "A", "D", "B"]

    def test_reorder_empty(self):
        """Empty order returns original."""
        items = ["A", "B"]
        result = reorder_items(items, [])
        assert result == items

    def test_reorder_mismatched_length(self):
        """Mismatched length returns original."""
        items = ["A", "B", "C"]
        result = reorder_items(items, [0, 1])
        assert result == items
