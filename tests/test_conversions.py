"""Tests for unit conversions."""

import pytest


class TestKmToMiles:
    """Tests for km to miles conversion."""

    def test_km_to_miles_zero(self):
        """Test zero conversion."""
        from orbit.app import km_to_miles

        assert km_to_miles(0) == 0.0

    def test_km_to_miles_one_km(self):
        """Test 1 km = 0.621371 miles."""
        from orbit.app import km_to_miles

        result = km_to_miles(1)
        assert abs(result - 0.621371) < 0.0001

    def test_km_to_miles_known_value(self):
        """Test known conversion: 10 km ≈ 6.21 miles."""
        from orbit.app import km_to_miles

        result = km_to_miles(10)
        assert abs(result - 6.21371) < 0.001

    def test_km_to_miles_marathon(self):
        """Test marathon distance: 42.195 km ≈ 26.2 miles."""
        from orbit.app import km_to_miles

        result = km_to_miles(42.195)
        assert abs(result - 26.2188) < 0.01

    def test_km_to_miles_round_trip(self):
        """Test consistency: converting and back should be close."""
        from orbit.app import km_to_miles

        km = 100
        miles = km_to_miles(km)
        # Convert back: miles / 0.621371 = km
        km_back = miles / 0.621371
        assert abs(km_back - km) < 0.0001
