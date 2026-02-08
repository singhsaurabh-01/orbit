"""Tests for the places service."""

import pytest

from orbit.services import places


class TestDetectInputType:
    """Tests for input type detection."""

    def test_detect_address_with_street_number(self):
        """Detect address with street number."""
        assert places.detect_input_type("123 Main Street") == "address"
        assert places.detect_input_type("456 Oak Ave, Austin TX") == "address"

    def test_detect_address_with_keywords(self):
        """Detect address with street keywords."""
        assert places.detect_input_type("Main Street") == "address"
        assert places.detect_input_type("Oak Avenue") == "address"
        assert places.detect_input_type("Highway 71") == "address"

    def test_detect_address_with_zip(self):
        """Detect address with zip code."""
        assert places.detect_input_type("Austin 78701") == "address"

    def test_detect_place_name(self):
        """Detect place names."""
        assert places.detect_input_type("Starbucks") == "name"
        assert places.detect_input_type("HEB Grocery") == "name"
        assert places.detect_input_type("DMV") == "name"
        assert places.detect_input_type("Chase Bank") == "name"


class TestHaversineDistance:
    """Tests for haversine distance calculation."""

    def test_same_point_zero_distance(self):
        """Same point should have zero distance."""
        from orbit.services.routing import haversine_distance

        dist = haversine_distance(30.0, -97.0, 30.0, -97.0)
        assert dist == 0.0

    def test_known_distance(self):
        """Test with known approximate distance."""
        from orbit.services.routing import haversine_distance

        # Austin to Dallas is approximately 300 km
        austin_lat, austin_lon = 30.2672, -97.7431
        dallas_lat, dallas_lon = 32.7767, -96.7970

        dist = haversine_distance(austin_lat, austin_lon, dallas_lat, dallas_lon)

        # Should be around 290-310 km
        assert 280 < dist < 320


class TestGeocode:
    """Tests for geocoding (these may be skipped if network unavailable)."""

    @pytest.mark.skip(reason="Requires network access and may hit rate limits")
    def test_geocode_known_address(self):
        """Test geocoding a known address."""
        result = places.geocode_address("1600 Pennsylvania Avenue NW, Washington, DC")
        assert result is not None
        assert abs(result.lat - 38.8977) < 0.01  # White House latitude
        assert abs(result.lon - (-77.0365)) < 0.01


class TestPlaceSearchResult:
    """Tests for PlaceSearchResult model."""

    def test_create_place_search_result(self):
        """Test creating a PlaceSearchResult."""
        from orbit.models import PlaceSearchResult

        result = PlaceSearchResult(
            name="Test Place",
            address="123 Test St",
            lat=30.0,
            lon=-97.0,
            source="nominatim",
        )

        assert result.name == "Test Place"
        assert result.lat == 30.0
        assert result.lon == -97.0
