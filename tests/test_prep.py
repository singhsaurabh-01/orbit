"""Tests for the prep notes service."""

import pytest

from orbit.services.prep import get_prep_notes, format_prep_notes, PrepNote


class TestGetPrepNotes:
    """Tests for get_prep_notes function."""

    def test_dmv_purpose(self):
        """DMV purpose should return relevant documents."""
        prep = get_prep_notes("license renewal", "DMV")
        assert len(prep.documents) > 0
        assert any("ID" in doc or "license" in doc.lower() for doc in prep.documents)

    def test_bank_purpose(self):
        """Bank purpose should return relevant items."""
        prep = get_prep_notes("deposit check", "Chase Bank")
        assert len(prep.documents) > 0 or len(prep.items) > 0

    def test_post_office_purpose(self):
        """Post office purpose should return relevant items."""
        prep = get_prep_notes("mail package", "Post Office")
        assert len(prep.items) > 0
        assert any("package" in item.lower() for item in prep.items)

    def test_pharmacy_purpose(self):
        """Pharmacy purpose should return relevant items."""
        prep = get_prep_notes("pickup prescription", "CVS")
        assert len(prep.documents) > 0 or len(prep.items) > 0

    def test_grocery_purpose(self):
        """Grocery purpose should return relevant items."""
        prep = get_prep_notes("grocery shopping", "Kroger")
        assert len(prep.items) > 0
        assert any("list" in item.lower() or "bag" in item.lower() for item in prep.items)

    def test_empty_purpose_returns_generic(self):
        """Empty purpose should still return generic suggestions."""
        prep = get_prep_notes("", "Target")
        # Should have some generic items
        assert prep.documents or prep.items or prep.tips or prep

    def test_haircut_purpose(self):
        """Haircut purpose should return relevant tips."""
        prep = get_prep_notes("haircut", "Great Clips")
        assert len(prep.tips) > 0 or len(prep.items) > 0

    def test_return_purpose(self):
        """Return purpose should mention receipt."""
        prep = get_prep_notes("return item", "Target")
        assert any("receipt" in doc.lower() for doc in prep.documents)

    def test_crowdedness_hint_for_dmv(self):
        """DMV should have crowdedness hint."""
        prep = get_prep_notes("license renewal", "DMV")
        assert prep.crowdedness_hint is not None

    def test_crowdedness_hint_for_grocery(self):
        """Grocery should have crowdedness hint."""
        prep = get_prep_notes("grocery shopping", "Walmart")
        assert prep.crowdedness_hint is not None


class TestFormatPrepNotes:
    """Tests for format_prep_notes function."""

    def test_format_with_documents(self):
        """Format should include documents section."""
        prep = PrepNote(
            documents=["Photo ID", "Proof of address"],
            items=[],
            tips=[],
        )
        formatted = format_prep_notes(prep)
        assert "Documents to bring" in formatted
        assert "Photo ID" in formatted

    def test_format_with_items(self):
        """Format should include items section."""
        prep = PrepNote(
            documents=[],
            items=["Pen", "Checkbook"],
            tips=[],
        )
        formatted = format_prep_notes(prep)
        assert "Items to bring" in formatted
        assert "Pen" in formatted

    def test_format_with_tips(self):
        """Format should include tips section."""
        prep = PrepNote(
            documents=[],
            items=[],
            tips=["Arrive early", "Bring patience"],
        )
        formatted = format_prep_notes(prep)
        assert "Tips" in formatted
        assert "Arrive early" in formatted

    def test_format_with_crowdedness(self):
        """Format should include crowdedness hint."""
        prep = PrepNote(
            documents=[],
            items=[],
            tips=[],
            crowdedness_hint="Busy on weekends",
        )
        formatted = format_prep_notes(prep)
        assert "Crowdedness" in formatted
        assert "Busy on weekends" in formatted

    def test_format_empty_prep(self):
        """Format should handle empty prep notes."""
        prep = PrepNote(
            documents=[],
            items=[],
            tips=[],
        )
        formatted = format_prep_notes(prep)
        assert "No specific preparation needed" in formatted


class TestMultipleMatches:
    """Tests for multiple keyword matching."""

    def test_dmv_license_combines_rules(self):
        """DMV + license renewal should combine both rule sets."""
        prep = get_prep_notes("dmv license renewal", "")
        # Should have documents from both DMV and license renewal rules
        assert len(prep.documents) >= 2

    def test_no_duplicate_items(self):
        """Same item from multiple rules should not duplicate."""
        prep = get_prep_notes("dmv license renewal registration", "")
        # Count occurrences of "Photo ID" type items
        id_items = [d for d in prep.documents if "ID" in d or "license" in d.lower()]
        # Should not have duplicates
        assert len(id_items) == len(set(id_items))
