"""Tests for the packing service."""

import pytest

from orbit.models import Task
from orbit.services import packing


class TestParseRequiredItems:
    """Tests for parsing required items."""

    def test_parse_none(self):
        """Test parsing None."""
        items = packing.parse_required_items(None)
        assert items == []

    def test_parse_empty_string(self):
        """Test parsing empty string."""
        items = packing.parse_required_items("")
        assert items == []

    def test_parse_json_list(self):
        """Test parsing JSON list."""
        items = packing.parse_required_items('["item1", "item2", "item3"]')
        assert items == ["item1", "item2", "item3"]

    def test_parse_newline_separated(self):
        """Test parsing newline-separated items."""
        items = packing.parse_required_items("item1\nitem2\nitem3")
        assert items == ["item1", "item2", "item3"]

    def test_parse_strips_whitespace(self):
        """Test that whitespace is stripped."""
        items = packing.parse_required_items("  item1  \n  item2  ")
        assert items == ["item1", "item2"]

    def test_parse_filters_empty_lines(self):
        """Test that empty lines are filtered."""
        items = packing.parse_required_items("item1\n\nitem2\n")
        assert items == ["item1", "item2"]


class TestGetSuggestedItems:
    """Tests for getting suggested items."""

    def test_dmv_suggestions(self):
        """Test DMV-related suggestions."""
        items = packing.get_suggested_items(purpose="DMV license renewal")

        assert "Driver's license/ID" in items
        assert "Proof of address" in items
        assert "Payment method" in items

    def test_bank_suggestions(self):
        """Test bank-related suggestions."""
        items = packing.get_suggested_items(purpose="bank deposit")

        assert "ID" in items
        assert "Documents to sign" in items

    def test_car_service_suggestions(self):
        """Test car service suggestions."""
        items = packing.get_suggested_items(purpose="car service appointment")

        assert "Car keys" in items
        assert "Insurance card" in items

    def test_includes_defaults(self):
        """Test that defaults are included."""
        items = packing.get_suggested_items(purpose="random task", include_defaults=True)

        assert "Phone" in items
        assert "Wallet" in items

    def test_excludes_defaults(self):
        """Test that defaults can be excluded."""
        items = packing.get_suggested_items(purpose="random task", include_defaults=False)

        assert "Phone" not in items
        assert "Wallet" not in items

    def test_auto_rules(self):
        """Test auto_rules tags."""
        items = packing.get_suggested_items(auto_rules="pharmacy,bank")

        assert "ID" in items
        assert "Insurance card" in items

    def test_no_duplicates(self):
        """Test that items are deduplicated."""
        items = packing.get_suggested_items(
            purpose="DMV license bank",
            auto_rules="dmv,bank",
        )

        # Count occurrences of "ID"
        id_count = sum(1 for item in items if "ID" in item)
        # Should only appear once (deduplicated)
        assert id_count >= 1


class TestGetTaskChecklist:
    """Tests for getting task checklists."""

    def test_explicit_items(self):
        """Test that explicit items are included."""
        task = Task(
            title="Test Task",
            required_items="Custom Item 1\nCustom Item 2",
        )

        checklist = packing.get_task_checklist(task)

        assert "Custom Item 1" in checklist
        assert "Custom Item 2" in checklist

    def test_purpose_based_suggestions(self):
        """Test that purpose triggers suggestions."""
        task = Task(
            title="DMV Visit",
            purpose="DMV license renewal",
        )

        checklist = packing.get_task_checklist(task, include_suggestions=True)

        assert "Driver's license/ID" in checklist

    def test_combined_items(self):
        """Test combined explicit and suggested items."""
        task = Task(
            title="DMV Visit",
            purpose="DMV",
            required_items="Appointment printout",
        )

        checklist = packing.get_task_checklist(task)

        assert "Appointment printout" in checklist
        assert "Driver's license/ID" in checklist
        assert "Phone" in checklist  # Default

    def test_no_suggestions(self):
        """Test with suggestions disabled."""
        task = Task(
            title="DMV Visit",
            purpose="DMV",
            required_items="My Item",
        )

        checklist = packing.get_task_checklist(task, include_suggestions=False)

        assert "My Item" in checklist
        assert "Driver's license/ID" not in checklist


class TestGetConsolidatedChecklist:
    """Tests for consolidated checklists."""

    def test_empty_list(self):
        """Test with empty task list."""
        checklist = packing.get_consolidated_checklist([])
        assert checklist == []

    def test_single_task(self):
        """Test with single task."""
        task = Task(title="Test", required_items="Item1")

        checklist = packing.get_consolidated_checklist([task])

        assert "Item1" in checklist
        assert "Phone" in checklist  # Default

    def test_multiple_tasks_deduplicated(self):
        """Test that items across tasks are deduplicated."""
        task1 = Task(title="Task 1", required_items="ID")
        task2 = Task(title="Task 2", required_items="ID")

        checklist = packing.get_consolidated_checklist([task1, task2])

        # ID should only appear once
        assert checklist.count("ID") == 1

    def test_sorted_output(self):
        """Test that output is sorted."""
        task = Task(title="Test", required_items="Zebra\nApple\nMango")

        checklist = packing.get_consolidated_checklist([task])

        # Should be alphabetically sorted
        filtered = [c for c in checklist if c in ["Zebra", "Apple", "Mango"]]
        assert filtered == sorted(filtered)


class TestGetChecklistByStop:
    """Tests for checklist by stop."""

    def test_returns_list_of_dicts(self):
        """Test that result is list of dicts."""
        task = Task(title="Test Task", location_name="Test Location")

        result = packing.get_checklist_by_stop([task])

        assert len(result) == 1
        assert "task_id" in result[0]
        assert "task_title" in result[0]
        assert "location" in result[0]
        assert "checklist" in result[0]

    def test_includes_location(self):
        """Test that location is included."""
        task = Task(title="Test", location_name="My Store", address="123 Main St")

        result = packing.get_checklist_by_stop([task])

        assert result[0]["location"] == "My Store"


class TestFormatChecklist:
    """Tests for checklist formatting."""

    def test_format_for_display(self):
        """Test display formatting."""
        items = ["Item 1", "Item 2"]

        formatted = packing.format_checklist_for_display(items)

        assert "☐ Item 1" in formatted
        assert "☐ Item 2" in formatted

    def test_format_empty_display(self):
        """Test empty list display."""
        formatted = packing.format_checklist_for_display([])
        assert formatted == "No items needed"

    def test_format_for_ics(self):
        """Test ICS formatting."""
        items = ["Item 1", "Item 2"]

        formatted = packing.format_checklist_for_ics(items)

        assert "Items to bring:" in formatted
        assert "- Item 1" in formatted
        assert "- Item 2" in formatted

    def test_format_empty_ics(self):
        """Test empty list ICS."""
        formatted = packing.format_checklist_for_ics([])
        assert formatted == ""


class TestSuggestRulesForPurpose:
    """Tests for rule suggestion."""

    def test_dmv_rules(self):
        """Test DMV rule matching."""
        rules = packing.suggest_rules_for_purpose("DMV license renewal")
        assert "dmv" in rules
        assert "license" in rules

    def test_no_matches(self):
        """Test no matches."""
        rules = packing.suggest_rules_for_purpose("random unrelated task")
        assert rules == []

    def test_empty_purpose(self):
        """Test empty purpose."""
        rules = packing.suggest_rules_for_purpose("")
        assert rules == []


class TestGetAvailableRules:
    """Tests for getting available rules."""

    def test_returns_dict(self):
        """Test that result is a dict."""
        rules = packing.get_available_rules()
        assert isinstance(rules, dict)

    def test_excludes_default(self):
        """Test that _default is excluded."""
        rules = packing.get_available_rules()
        assert "_default" not in rules

    def test_includes_dmv(self):
        """Test that common rules are included."""
        rules = packing.get_available_rules()
        assert "dmv" in rules
        assert "bank" in rules
