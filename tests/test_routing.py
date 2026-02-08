"""Tests for the routing service."""

import pytest

from orbit.services import routing


class TestHaversineDistance:
    """Tests for haversine distance calculation."""

    def test_same_point(self):
        """Same point should have zero distance."""
        dist = routing.haversine_distance(30.0, -97.0, 30.0, -97.0)
        assert dist == 0.0

    def test_short_distance(self):
        """Test a short distance calculation."""
        # Two points about 1 km apart in Austin
        lat1, lon1 = 30.2672, -97.7431  # Downtown Austin
        lat2, lon2 = 30.2762, -97.7431  # About 1 km north

        dist = routing.haversine_distance(lat1, lon1, lat2, lon2)

        # Should be approximately 1 km
        assert 0.9 < dist < 1.1

    def test_medium_distance(self):
        """Test a medium distance calculation."""
        # Austin to San Antonio (about 120 km)
        austin = (30.2672, -97.7431)
        san_antonio = (29.4241, -98.4936)

        dist = routing.haversine_distance(
            austin[0], austin[1],
            san_antonio[0], san_antonio[1]
        )

        # Should be around 120 km
        assert 110 < dist < 130


class TestFallbackRoute:
    """Tests for fallback routing."""

    def test_fallback_route_short(self):
        """Test fallback route for short distance."""
        result = routing.get_route_fallback(
            30.2672, -97.7431,  # Origin
            30.2762, -97.7431,  # Destination (about 1 km away)
        )

        assert result.source == "fallback"
        assert result.distance_km > 0
        assert result.duration_minutes > 0

    def test_fallback_route_same_point(self):
        """Test fallback route for same point."""
        result = routing.get_route_fallback(
            30.2672, -97.7431,
            30.2672, -97.7431,
        )

        assert result.distance_km == 0.0
        assert result.duration_minutes == 0.0

    def test_fallback_includes_road_factor(self):
        """Test that fallback includes road distance factor."""
        # Straight-line distance for 1 degree latitude is about 111 km
        result = routing.get_route_fallback(
            30.0, -97.0,
            31.0, -97.0,
        )

        # Road distance should be greater than straight-line (factor ~1.4)
        straight_line = routing.haversine_distance(30.0, -97.0, 31.0, -97.0)
        assert result.distance_km > straight_line


class TestRouteResult:
    """Tests for RouteResult model."""

    def test_route_result_creation(self):
        """Test creating a RouteResult."""
        from orbit.models import RouteResult

        result = RouteResult(
            origin_lat=30.0,
            origin_lon=-97.0,
            dest_lat=31.0,
            dest_lon=-98.0,
            distance_km=150.5,
            duration_minutes=120.0,
            source="osrm",
        )

        assert result.distance_km == 150.5
        assert result.duration_minutes == 120.0
        assert result.source == "osrm"


class TestDistanceMatrix:
    """Tests for distance matrix building."""

    def test_matrix_dimensions(self):
        """Test that matrix has correct dimensions."""
        locations = [
            (30.0, -97.0),
            (30.1, -97.1),
            (30.2, -97.2),
        ]

        distances, durations = routing.build_distance_matrix(locations)

        assert len(distances) == 3
        assert len(distances[0]) == 3
        assert len(durations) == 3

    def test_matrix_diagonal_zero(self):
        """Test that diagonal elements are zero."""
        locations = [
            (30.0, -97.0),
            (30.1, -97.1),
        ]

        distances, durations = routing.build_distance_matrix(locations)

        assert distances[0][0] == 0.0
        assert distances[1][1] == 0.0

    def test_matrix_symmetry(self):
        """Test that matrix is approximately symmetric."""
        locations = [
            (30.0, -97.0),
            (30.5, -97.5),
        ]

        distances, _ = routing.build_distance_matrix(locations)

        # A to B should equal B to A for straight-line calculations
        assert abs(distances[0][1] - distances[1][0]) < 1.0  # Within 1 km


class TestTotalRouteDistance:
    """Tests for total route distance calculation."""

    def test_empty_waypoints(self):
        """Test with empty waypoints."""
        dist, dur = routing.get_total_route_distance([])
        assert dist == 0.0
        assert dur == 0.0

    def test_single_waypoint(self):
        """Test with single waypoint."""
        dist, dur = routing.get_total_route_distance([(30.0, -97.0)])
        assert dist == 0.0
        assert dur == 0.0

    def test_two_waypoints(self):
        """Test with two waypoints."""
        waypoints = [
            (30.0, -97.0),
            (30.1, -97.1),
        ]

        dist, dur = routing.get_total_route_distance(waypoints)

        assert dist > 0
        assert dur > 0

    def test_multiple_waypoints(self):
        """Test that multiple waypoints add up correctly."""
        waypoints = [
            (30.0, -97.0),
            (30.05, -97.05),
            (30.1, -97.1),
        ]

        total_dist, total_dur = routing.get_total_route_distance(waypoints)

        # Total should be greater than direct A to C
        direct = routing.get_route(30.0, -97.0, 30.1, -97.1)

        # Via B should be longer or equal to direct
        assert total_dist >= direct.distance_km * 0.9  # Allow some tolerance
