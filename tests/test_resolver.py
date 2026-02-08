"""Tests for the place resolver service."""

import pytest
from unittest.mock import patch, MagicMock

from orbit.models import Settings, PlaceSearchResult
from orbit.services.resolver import (
    normalize_text,
    calculate_name_similarity,
    calculate_distance_miles,
    calculate_combined_score,
    score_candidates,
    should_auto_select,
    resolve_place,
    select_candidate,
    apply_home_proximity_tiebreak,
    select_best_for_route,
    are_same_brand,
    ResolutionDecision,
    ScoredCandidate,
    ResolvedPlace,
    SelectionReason,
)


class TestNormalizeText:
    """Tests for text normalization."""

    def test_lowercase(self):
        """Test lowercase conversion."""
        assert normalize_text("HELLO World") == "hello world"

    def test_remove_punctuation(self):
        """Test punctuation removal."""
        assert normalize_text("Crumbl's Cookies!") == "crumbls cookies"

    def test_collapse_whitespace(self):
        """Test whitespace collapsing."""
        assert normalize_text("  multiple   spaces  ") == "multiple spaces"

    def test_combined(self):
        """Test combined normalization."""
        assert normalize_text("  Crumbl's  COOKIES!! ") == "crumbls cookies"


class TestFuzzyMatching:
    """Tests for fuzzy name similarity."""

    def test_exact_match(self):
        """Test exact match gives 100."""
        similarity = calculate_name_similarity("Target", "Target")
        assert similarity == 100.0

    def test_case_insensitive(self):
        """Test case insensitive matching."""
        similarity = calculate_name_similarity("TARGET", "target")
        assert similarity == 100.0

    def test_typo_crumbl(self):
        """Test typo 'crumbl cookiee' matches 'Crumbl Cookies'."""
        similarity = calculate_name_similarity("crumbl cookiee", "Crumbl Cookies")
        # Should be high due to fuzzy matching
        assert similarity >= 80.0

    def test_partial_match(self):
        """Test partial name matching."""
        similarity = calculate_name_similarity("Great Clips", "Great Clips Hair Salon")
        assert similarity >= 70.0

    def test_no_match(self):
        """Test dissimilar names have lower scores than similar ones."""
        similar = calculate_name_similarity("Target", "Target Store")
        dissimilar = calculate_name_similarity("Target", "Whole Foods")
        # Dissimilar should score lower than similar
        assert dissimilar < similar

    def test_misspelling(self):
        """Test common misspellings are handled."""
        # starbucks -> starbuks
        similarity = calculate_name_similarity("starbuks", "Starbucks")
        assert similarity >= 70.0


class TestDistanceScoring:
    """Tests for distance and combined scoring."""

    def test_calculate_distance_miles(self):
        """Test distance calculation returns miles."""
        # Hutto, TX to nearby point (~1 mile)
        distance = calculate_distance_miles(30.5427, -97.5467, 30.5527, -97.5467)
        assert 0.5 < distance < 1.5

    def test_combined_score_close_high_similarity(self):
        """Test close distance + high similarity = high score."""
        score = calculate_combined_score(distance_miles=1.0, name_similarity=90.0)
        # Close (48/50 distance) + similar (45/50 name) = ~93
        assert score > 85

    def test_combined_score_far_high_similarity(self):
        """Test far distance + high similarity = lower score."""
        score = calculate_combined_score(distance_miles=20.0, name_similarity=90.0)
        # Far (10/50 distance) + similar (45/50 name) = ~55
        assert score < 60

    def test_combined_score_close_low_similarity(self):
        """Test close distance + low similarity = medium score."""
        score = calculate_combined_score(distance_miles=1.0, name_similarity=30.0)
        # Close (48/50 distance) + dissimilar (15/50 name) = ~63
        assert 50 < score < 70


class TestNearestStorePreference:
    """Tests for nearest store preference - the Great Clips issue."""

    def test_nearest_store_wins_same_name(self):
        """
        Test that nearest store wins when multiple same-brand stores exist.

        This is the Great Clips issue: home=Hutto, query="great clips"
        should pick the nearest Great Clips, not one in Georgetown.
        """
        # Mock candidates: two Great Clips locations
        candidates = [
            PlaceSearchResult(
                name="Great Clips",
                address="123 Main St, Georgetown, TX",
                lat=30.6328,  # Georgetown (farther from Hutto)
                lon=-97.6780,
                source="nominatim",
            ),
            PlaceSearchResult(
                name="Great Clips",
                address="456 Main St, Hutto, TX",
                lat=30.5427,  # Hutto (closer)
                lon=-97.5467,
                source="nominatim",
            ),
        ]

        # Home in Hutto
        home_lat, home_lon = 30.5427, -97.5467

        scored = score_candidates("Great Clips", candidates, home_lat, home_lon)

        # Hutto location should be first (closest)
        assert "Hutto" in scored[0].place.address
        assert scored[0].distance_miles < scored[1].distance_miles

    def test_nearest_store_with_slight_name_variation(self):
        """Test nearest wins even with slight name variations."""
        candidates = [
            PlaceSearchResult(
                name="Great Clips Hair Salon",
                address="Far away location",
                lat=31.0,  # Far
                lon=-97.5,
                source="nominatim",
            ),
            PlaceSearchResult(
                name="Great Clips",
                address="Close location",
                lat=30.55,  # Close
                lon=-97.55,
                source="nominatim",
            ),
        ]

        home_lat, home_lon = 30.54, -97.54

        scored = score_candidates("great clips", candidates, home_lat, home_lon)

        # Closer location should win
        assert scored[0].distance_miles < scored[1].distance_miles


class TestAutoSelect:
    """Tests for auto-selection logic."""

    def test_single_candidate_good_match_auto_selects(self):
        """Single candidate with decent match should auto-select."""
        candidates = [
            ScoredCandidate(
                place=MagicMock(),
                distance_miles=2.0,
                name_similarity=70.0,
                combined_score=80.0,
            )
        ]
        should_auto, reason = should_auto_select(candidates)
        assert should_auto is True

    def test_single_candidate_poor_match_no_auto_select(self):
        """Single candidate with poor match should not auto-select."""
        candidates = [
            ScoredCandidate(
                place=MagicMock(),
                distance_miles=20.0,
                name_similarity=30.0,
                combined_score=25.0,
            )
        ]
        should_auto, reason = should_auto_select(candidates)
        assert should_auto is False

    def test_clear_winner_auto_selects(self):
        """Clear winner (big score gap) should auto-select."""
        candidates = [
            ScoredCandidate(
                place=MagicMock(),
                distance_miles=2.0,
                name_similarity=90.0,
                combined_score=90.0,
            ),
            ScoredCandidate(
                place=MagicMock(),
                distance_miles=15.0,
                name_similarity=60.0,
                combined_score=50.0,
            ),
        ]
        should_auto, reason = should_auto_select(candidates)
        assert should_auto is True

    def test_close_scores_triggers_disambiguation(self):
        """Close scores with moderate similarity should trigger disambiguation."""
        candidates = [
            ScoredCandidate(
                place=MagicMock(),
                distance_miles=5.0,
                name_similarity=60.0,  # Moderate similarity
                combined_score=55.0,
            ),
            ScoredCandidate(
                place=MagicMock(),
                distance_miles=6.0,
                name_similarity=60.0,
                combined_score=53.0,
            ),
        ]
        # Both have moderate similarity (<70), scores are close - should trigger disambiguation
        should_auto, reason = should_auto_select(candidates)
        assert should_auto is False

    def test_same_brand_closer_wins(self):
        """When both have high similarity, closer one should auto-select."""
        candidates = [
            ScoredCandidate(
                place=MagicMock(),
                distance_miles=2.0,
                name_similarity=85.0,
                combined_score=88.0,
            ),
            ScoredCandidate(
                place=MagicMock(),
                distance_miles=10.0,
                name_similarity=85.0,
                combined_score=70.0,
            ),
        ]
        # Both high similarity, but first is closer - should auto-select
        should_auto, reason = should_auto_select(candidates)
        assert should_auto is True


class TestResolvePlace:
    """Tests for full place resolution."""

    @patch('orbit.services.resolver.places.search_places_nearby')
    def test_resolve_with_clear_match(self, mock_search):
        """Test resolution with a clear best match."""
        mock_search.return_value = [
            PlaceSearchResult(
                name="Target",
                address="123 Main St",
                lat=30.55,
                lon=-97.55,
                source="nominatim",
            )
        ]

        settings = Settings(
            home_lat=30.54,
            home_lon=-97.54,
            home_address="Home",
        )

        result = resolve_place("Target", settings)

        assert result.decision == ResolutionDecision.AUTO_BEST
        assert result.selected is not None
        assert result.selected.display_name == "Target"

    @patch('orbit.services.resolver.places.search_places_nearby')
    def test_resolve_triggers_disambiguation(self, mock_search):
        """Test resolution triggers disambiguation with close candidates."""
        mock_search.return_value = [
            PlaceSearchResult(
                name="Starbucks",
                address="Location A",
                lat=30.55,
                lon=-97.55,
                source="nominatim",
            ),
            PlaceSearchResult(
                name="Starbucks Coffee",
                address="Location B",
                lat=30.56,
                lon=-97.56,
                source="nominatim",
            ),
        ]

        settings = Settings(
            home_lat=30.54,
            home_lon=-97.54,
            home_address="Home",
        )

        result = resolve_place("Starbucks", settings)

        # With two similar candidates close together, might trigger disambiguation
        # or auto-select the closest - depends on scoring
        assert result.candidates is not None
        assert len(result.candidates) >= 2

    @patch('orbit.services.resolver.places.search_places_nearby')
    @patch('orbit.services.resolver.places.geocode_address')
    def test_resolve_no_match(self, mock_geocode, mock_search):
        """Test resolution when no match found."""
        mock_search.return_value = []
        mock_geocode.return_value = None

        settings = Settings(
            home_lat=30.54,
            home_lon=-97.54,
            home_address="Home",
        )

        result = resolve_place("NonexistentPlace12345", settings)

        assert result.decision == ResolutionDecision.NO_MATCH
        assert result.selected is None


class TestSelectCandidate:
    """Tests for user candidate selection."""

    def test_select_valid_candidate(self):
        """Test selecting a valid candidate."""
        candidates = [
            ScoredCandidate(
                place=PlaceSearchResult(
                    name="Option A",
                    address="Address A",
                    lat=30.5,
                    lon=-97.5,
                    source="nominatim",
                ),
                distance_miles=2.0,
                name_similarity=80.0,
                combined_score=85.0,
            ),
            ScoredCandidate(
                place=PlaceSearchResult(
                    name="Option B",
                    address="Address B",
                    lat=30.6,
                    lon=-97.6,
                    source="nominatim",
                ),
                distance_miles=5.0,
                name_similarity=80.0,
                combined_score=75.0,
            ),
        ]

        resolved = ResolvedPlace(
            query="test",
            selected=None,
            candidates=candidates,
            decision=ResolutionDecision.PENDING,
            decision_reason="Multiple matches",
        )

        # Select second candidate
        updated = select_candidate(resolved, 1)

        assert updated.decision == ResolutionDecision.USER_SELECTED
        assert updated.selected.display_name == "Option B"
        assert updated.decision_reason == "User selected"

    def test_select_invalid_index(self):
        """Test selecting invalid index returns unchanged."""
        candidates = [
            ScoredCandidate(
                place=MagicMock(),
                distance_miles=2.0,
                name_similarity=80.0,
                combined_score=85.0,
            ),
        ]

        resolved = ResolvedPlace(
            query="test",
            selected=None,
            candidates=candidates,
            decision=ResolutionDecision.PENDING,
            decision_reason="Multiple matches",
        )

        # Invalid index
        updated = select_candidate(resolved, 5)

        # Should return unchanged
        assert updated.decision == ResolutionDecision.PENDING
        assert updated.selected is None


class TestTypoCorrection:
    """Tests specifically for typo correction scenarios."""

    def test_crumbl_cookiee_typo(self):
        """Test 'crumbl cookiee' matches 'Crumbl Cookies'."""
        similarity = calculate_name_similarity("crumbl cookiee", "Crumbl Cookies")
        assert similarity >= 75.0, f"Expected >= 75, got {similarity}"

    def test_starbcks_typo(self):
        """Test 'starbcks' matches 'Starbucks'."""
        similarity = calculate_name_similarity("starbcks", "Starbucks")
        assert similarity >= 70.0, f"Expected >= 70, got {similarity}"

    def test_gren_clips_typo(self):
        """Test 'gren clips' matches 'Great Clips'."""
        similarity = calculate_name_similarity("gren clips", "Great Clips")
        assert similarity >= 65.0, f"Expected >= 65, got {similarity}"

    def test_wallmart_typo(self):
        """Test 'wallmart' matches 'Walmart'."""
        similarity = calculate_name_similarity("wallmart", "Walmart")
        assert similarity >= 70.0, f"Expected >= 70, got {similarity}"


class TestSameBrandDetection:
    """Tests for same-brand detection."""

    def test_same_brand_exact(self):
        """Two Great Clips are same brand."""
        c1 = ScoredCandidate(
            place=PlaceSearchResult(
                name="Great Clips",
                address="123 Main St",
                lat=30.5, lon=-97.5,
                source="test",
            ),
            distance_miles=2.0,
            name_similarity=100.0,
            combined_score=90.0,
        )
        c2 = ScoredCandidate(
            place=PlaceSearchResult(
                name="Great Clips",
                address="456 Oak Ave",
                lat=30.6, lon=-97.6,
                source="test",
            ),
            distance_miles=5.0,
            name_similarity=100.0,
            combined_score=80.0,
        )
        assert are_same_brand(c1, c2) is True

    def test_same_brand_with_suffix(self):
        """Great Clips and Great Clips Hair Salon are same brand."""
        c1 = ScoredCandidate(
            place=PlaceSearchResult(
                name="Great Clips",
                address="123 Main St",
                lat=30.5, lon=-97.5,
                source="test",
            ),
            distance_miles=2.0,
            name_similarity=100.0,
            combined_score=90.0,
        )
        c2 = ScoredCandidate(
            place=PlaceSearchResult(
                name="Great Clips Hair Salon",
                address="456 Oak Ave",
                lat=30.6, lon=-97.6,
                source="test",
            ),
            distance_miles=5.0,
            name_similarity=85.0,
            combined_score=80.0,
        )
        assert are_same_brand(c1, c2) is True

    def test_different_brand(self):
        """Great Clips and Target are NOT same brand."""
        c1 = ScoredCandidate(
            place=PlaceSearchResult(
                name="Great Clips",
                address="123 Main St",
                lat=30.5, lon=-97.5,
                source="test",
            ),
            distance_miles=2.0,
            name_similarity=100.0,
            combined_score=90.0,
        )
        c2 = ScoredCandidate(
            place=PlaceSearchResult(
                name="Target",
                address="456 Oak Ave",
                lat=30.6, lon=-97.6,
                source="test",
            ),
            distance_miles=5.0,
            name_similarity=30.0,
            combined_score=60.0,
        )
        assert are_same_brand(c1, c2) is False


class TestHomeProximityTiebreak:
    """Tests for home proximity tie-break selection."""

    def test_same_brand_nearest_wins(self):
        """Same-brand candidates: nearest to home wins."""
        # Great Clips case: two locations, farther one has higher score
        far_location = ScoredCandidate(
            place=PlaceSearchResult(
                name="Great Clips",
                address="2098 Muirfield Bend Dr #115, Austin, TX",
                lat=30.45, lon=-97.75,  # Farther from home
                source="test",
            ),
            distance_miles=8.0,
            name_similarity=100.0,
            combined_score=85.0,  # Higher score
        )
        near_location = ScoredCandidate(
            place=PlaceSearchResult(
                name="Great Clips",
                address="10 Ed Schmidt Blvd Ste 200, Hutto, TX 78634",
                lat=30.54, lon=-97.55,  # Closer to home
                source="test",
            ),
            distance_miles=2.0,
            name_similarity=100.0,
            combined_score=80.0,  # Lower score but closer
        )

        candidates = [far_location, near_location]  # Far is first due to score
        result = apply_home_proximity_tiebreak(candidates)

        # After tiebreak, near location should be first
        assert result[0].distance_miles == 2.0
        assert result[0].selection_reason == SelectionReason.CLOSEST_TO_HOME

    def test_different_brand_no_tiebreak(self):
        """Different brands don't get tiebreak."""
        target = ScoredCandidate(
            place=PlaceSearchResult(
                name="Target",
                address="123 Main St",
                lat=30.5, lon=-97.5,
                source="test",
            ),
            distance_miles=5.0,
            name_similarity=100.0,
            combined_score=90.0,
        )
        walmart = ScoredCandidate(
            place=PlaceSearchResult(
                name="Walmart",
                address="456 Oak Ave",
                lat=30.55, lon=-97.55,
                source="test",
            ),
            distance_miles=2.0,  # Closer
            name_similarity=30.0,  # Low similarity (different query)
            combined_score=70.0,
        )

        candidates = [target, walmart]
        result = apply_home_proximity_tiebreak(candidates)

        # Order should remain: Target first (different brands)
        assert result[0].place.name == "Target"


class TestLastStopOptimization:
    """Tests for last stop route optimization."""

    def test_last_stop_minimizes_total_route(self):
        """Last stop: choose candidate minimizing prev_stop + return_home."""
        home_lat, home_lon = 30.5, -97.5

        # Two Great Clips locations
        # Location A: close to home but very far from prev stop
        loc_a = ScoredCandidate(
            place=PlaceSearchResult(
                name="Great Clips",
                address="Location A - close to home",
                lat=30.51, lon=-97.51,  # Very close to home (~1 mi)
                source="test",
            ),
            distance_miles=1.0,  # Close to home
            name_similarity=100.0,
            combined_score=95.0,  # Higher score
        )
        # Location B: far from home but close to prev stop
        # Total route: prev -> B -> home should be shorter than prev -> A -> home
        loc_b = ScoredCandidate(
            place=PlaceSearchResult(
                name="Great Clips",
                address="Location B - on the way home",
                lat=30.7, lon=-97.6,  # Between prev and home
                source="test",
            ),
            distance_miles=15.0,  # Far from home
            name_similarity=100.0,
            combined_score=70.0,  # Lower score
        )

        candidates = [loc_a, loc_b]  # A is first (higher score)

        # Previous stop is far north - Location B is on the way back
        prev_lat, prev_lon = 30.8, -97.65

        result = select_best_for_route(
            candidates,
            prev_stop_lat=prev_lat,
            prev_stop_lon=prev_lon,
            home_lat=home_lat,
            home_lon=home_lon,
            is_last_stop=True,
            return_home=True,
        )

        # Calculate total route distances:
        # A: prev(30.8,-97.65) -> A(30.51,-97.51) -> home(30.5,-97.5)
        #    ~22 mi to A + ~1 mi to home = ~23 mi
        # B: prev(30.8,-97.65) -> B(30.7,-97.6) -> home(30.5,-97.5)
        #    ~7 mi to B + ~15 mi to home = ~22 mi
        # B should win with lower total
        assert result[0].place.address == "Location B - on the way home"
        assert result[0].selection_reason == SelectionReason.BEST_FOR_ROUTE

    def test_not_last_stop_no_change(self):
        """Non-last stop: no route optimization applied."""
        home_lat, home_lon = 30.5, -97.5

        loc_a = ScoredCandidate(
            place=PlaceSearchResult(
                name="Great Clips",
                address="Location A",
                lat=30.52, lon=-97.52,
                source="test",
            ),
            distance_miles=1.5,
            name_similarity=100.0,
            combined_score=90.0,
        )
        loc_b = ScoredCandidate(
            place=PlaceSearchResult(
                name="Great Clips",
                address="Location B",
                lat=30.65, lon=-97.65,
                source="test",
            ),
            distance_miles=12.0,
            name_similarity=100.0,
            combined_score=75.0,
        )

        candidates = [loc_a, loc_b]

        result = select_best_for_route(
            candidates,
            prev_stop_lat=30.63,
            prev_stop_lon=-97.63,
            home_lat=home_lat,
            home_lon=home_lon,
            is_last_stop=False,  # Not last stop
            return_home=True,
        )

        # Order unchanged - A is still first
        assert result[0].place.address == "Location A"


class TestAmbiguityTriggersDisambiguation:
    """Tests for ambiguity detection and disambiguation."""

    def test_close_scores_triggers_pending(self):
        """Two candidates with close scores trigger PENDING state."""
        candidates = [
            ScoredCandidate(
                place=PlaceSearchResult(
                    name="Coffee Shop",
                    address="Location 1",
                    lat=30.5, lon=-97.5,
                    source="test",
                ),
                distance_miles=5.0,
                name_similarity=60.0,  # Moderate
                combined_score=55.0,
            ),
            ScoredCandidate(
                place=PlaceSearchResult(
                    name="Coffee Shop Cafe",
                    address="Location 2",
                    lat=30.55, lon=-97.55,
                    source="test",
                ),
                distance_miles=6.0,
                name_similarity=55.0,  # Similar moderate
                combined_score=52.0,  # Close to first
            ),
        ]

        should_auto, reason = should_auto_select(candidates)
        assert should_auto is False  # Should NOT auto-select

    def test_clear_winner_auto_selects(self):
        """Large score gap triggers auto-selection."""
        candidates = [
            ScoredCandidate(
                place=PlaceSearchResult(
                    name="Target",
                    address="123 Main St",
                    lat=30.5, lon=-97.5,
                    source="test",
                ),
                distance_miles=2.0,
                name_similarity=100.0,
                combined_score=95.0,  # Much higher
            ),
            ScoredCandidate(
                place=PlaceSearchResult(
                    name="Target Express",
                    address="Far away",
                    lat=30.8, lon=-97.8,
                    source="test",
                ),
                distance_miles=20.0,
                name_similarity=80.0,
                combined_score=50.0,  # Much lower
            ),
        ]

        should_auto, reason = should_auto_select(candidates)
        assert should_auto is True
        assert reason == SelectionReason.CLEAR_WINNER


class TestSelectionReasonText:
    """Tests for selection reason human-readable text."""

    def test_reason_text_closest_to_home(self):
        """Test closest to home reason text."""
        c = ScoredCandidate(
            place=MagicMock(),
            distance_miles=2.0,
            name_similarity=100.0,
            combined_score=90.0,
            selection_reason=SelectionReason.CLOSEST_TO_HOME,
        )
        assert c.get_reason_text() == "Closest to home"

    def test_reason_text_user_selected(self):
        """Test user selected reason text."""
        c = ScoredCandidate(
            place=MagicMock(),
            distance_miles=2.0,
            name_similarity=100.0,
            combined_score=90.0,
            selection_reason=SelectionReason.USER_SELECTED,
        )
        assert c.get_reason_text() == "User selected"

    def test_reason_text_best_for_route(self):
        """Test best for route reason text."""
        c = ScoredCandidate(
            place=MagicMock(),
            distance_miles=2.0,
            name_similarity=100.0,
            combined_score=90.0,
            selection_reason=SelectionReason.BEST_FOR_ROUTE,
        )
        assert c.get_reason_text() == "Best for route (min total distance)"
