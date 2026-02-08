"""Tests for Google Maps URL generation."""

import pytest
from urllib.parse import urlparse, parse_qs

# Import from app module
import sys
sys.path.insert(0, "src")
from orbit.app import build_google_maps_url


class TestGoogleMapsUrl:
    """Tests for Google Maps URL builder."""

    def test_single_stop(self):
        """Test URL with single stop."""
        url = build_google_maps_url(
            origin_lat=30.5,
            origin_lon=-97.5,
            waypoints=[(30.6, -97.6)],
            return_home=True,
        )

        assert url is not None
        assert "google.com/maps/dir" in url

        # Parse URL
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert params["api"] == ["1"]
        assert params["origin"] == ["30.5,-97.5"]
        assert params["destination"] == ["30.5,-97.5"]  # Returns home
        assert params["travelmode"] == ["driving"]
        # Single stop becomes waypoint when returning home
        assert "waypoints" in params
        assert params["waypoints"] == ["30.6,-97.6"]

    def test_multiple_stops(self):
        """Test URL with multiple stops."""
        url = build_google_maps_url(
            origin_lat=30.5,
            origin_lon=-97.5,
            waypoints=[
                (30.6, -97.6),
                (30.7, -97.7),
                (30.8, -97.8),
            ],
            return_home=True,
        )

        assert url is not None

        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert params["origin"] == ["30.5,-97.5"]
        assert params["destination"] == ["30.5,-97.5"]
        # All stops as waypoints
        assert params["waypoints"] == ["30.6,-97.6|30.7,-97.7|30.8,-97.8"]

    def test_return_home_enabled(self):
        """Test that return_home=True sets destination to origin."""
        url = build_google_maps_url(
            origin_lat=30.5,
            origin_lon=-97.5,
            waypoints=[(30.6, -97.6), (30.7, -97.7)],
            return_home=True,
        )

        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        # Destination should be same as origin
        assert params["destination"] == ["30.5,-97.5"]
        assert params["origin"] == ["30.5,-97.5"]

    def test_return_home_disabled(self):
        """Test that return_home=False uses last stop as destination."""
        url = build_google_maps_url(
            origin_lat=30.5,
            origin_lon=-97.5,
            waypoints=[(30.6, -97.6), (30.7, -97.7)],
            return_home=False,
        )

        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        # Last waypoint becomes destination
        assert params["destination"] == ["30.7,-97.7"]
        assert params["origin"] == ["30.5,-97.5"]
        # Only first waypoint remains as intermediate
        assert params["waypoints"] == ["30.6,-97.6"]

    def test_explicit_destination(self):
        """Test with explicit destination coordinates."""
        url = build_google_maps_url(
            origin_lat=30.5,
            origin_lon=-97.5,
            waypoints=[(30.6, -97.6)],
            destination_lat=31.0,
            destination_lon=-98.0,
            return_home=True,  # Should be ignored when explicit dest provided
        )

        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        # Explicit destination overrides return_home
        assert params["destination"] == ["31.0,-98.0"]

    def test_no_waypoints_returns_none(self):
        """Test that empty waypoints returns None."""
        url = build_google_maps_url(
            origin_lat=30.5,
            origin_lon=-97.5,
            waypoints=[],
            return_home=True,
        )

        assert url is None

    def test_invalid_waypoints_filtered(self):
        """Test that invalid waypoints are filtered out."""
        url = build_google_maps_url(
            origin_lat=30.5,
            origin_lon=-97.5,
            waypoints=[
                (None, -97.6),  # Invalid
                (30.7, None),   # Invalid
                (30.8, -97.8),  # Valid
            ],
            return_home=True,
        )

        assert url is not None

        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        # Only valid waypoint included
        assert params["waypoints"] == ["30.8,-97.8"]

    def test_all_invalid_waypoints_returns_none(self):
        """Test that all invalid waypoints returns None."""
        url = build_google_maps_url(
            origin_lat=30.5,
            origin_lon=-97.5,
            waypoints=[
                (None, -97.6),
                (30.7, None),
            ],
            return_home=True,
        )

        assert url is None

    def test_url_is_properly_encoded(self):
        """Test that URL parameters are properly encoded."""
        url = build_google_maps_url(
            origin_lat=30.5,
            origin_lon=-97.5,
            waypoints=[(30.6, -97.6), (30.7, -97.7)],
            return_home=True,
        )

        # Pipe separator should be encoded
        assert "%7C" in url or "|" in url  # urlencode may or may not encode pipe
        # Should be a valid URL
        parsed = urlparse(url)
        assert parsed.scheme == "https"
        assert parsed.netloc == "www.google.com"

    def test_travelmode_is_driving(self):
        """Test that travelmode is always driving."""
        url = build_google_maps_url(
            origin_lat=30.5,
            origin_lon=-97.5,
            waypoints=[(30.6, -97.6)],
            return_home=True,
        )

        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert params["travelmode"] == ["driving"]


class TestUrlIntegration:
    """Integration tests for URL generation with realistic data."""

    def test_realistic_route(self):
        """Test with realistic Hutto, TX coordinates."""
        # Simulating: Home -> Target -> Starbucks -> Home
        url = build_google_maps_url(
            origin_lat=30.5427,   # Hutto, TX
            origin_lon=-97.5467,
            waypoints=[
                (30.5127, -97.6780),  # Target in Round Rock
                (30.5327, -97.5567),  # Starbucks nearby
            ],
            return_home=True,
        )

        assert url is not None
        assert "google.com/maps/dir" in url

        # URL should work (contains all parts)
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert "origin" in params
        assert "destination" in params
        assert "waypoints" in params
        assert "travelmode" in params
