"""Packing service - items to carry suggestions and checklists."""

import json
from typing import Optional

from orbit.config import PACKING_RULES
from orbit.models import Task


def parse_required_items(required_items: Optional[str]) -> list[str]:
    """
    Parse required items from string (JSON list or newline-separated).

    Args:
        required_items: String containing items

    Returns:
        List of item strings
    """
    if not required_items:
        return []

    # Try JSON first
    try:
        items = json.loads(required_items)
        if isinstance(items, list):
            return [str(item).strip() for item in items if item]
    except (json.JSONDecodeError, TypeError):
        pass

    # Fall back to newline-separated
    items = required_items.strip().split("\n")
    return [item.strip() for item in items if item.strip()]


def get_suggested_items(
    purpose: Optional[str] = None,
    auto_rules: Optional[str] = None,
    include_defaults: bool = True,
) -> list[str]:
    """
    Get suggested items based on purpose and auto-rules.

    Args:
        purpose: Task purpose description
        auto_rules: Comma-separated rule tags
        include_defaults: Whether to include default essentials

    Returns:
        List of suggested items
    """
    suggestions = set()

    # Match purpose against rules
    if purpose:
        purpose_lower = purpose.lower()
        for keyword, items in PACKING_RULES.items():
            if keyword != "_default" and keyword in purpose_lower:
                suggestions.update(items)

    # Match auto_rules tags
    if auto_rules:
        tags = [tag.strip().lower() for tag in auto_rules.split(",")]
        for tag in tags:
            if tag in PACKING_RULES:
                suggestions.update(PACKING_RULES[tag])

    # Add default essentials
    if include_defaults:
        suggestions.update(PACKING_RULES.get("_default", []))

    return sorted(suggestions)


def get_task_checklist(task: Task, include_suggestions: bool = True) -> list[str]:
    """
    Get complete checklist for a task.

    Combines explicit required items with rule-based suggestions.

    Args:
        task: Task to generate checklist for
        include_suggestions: Whether to include rule-based suggestions

    Returns:
        Deduplicated list of items
    """
    items = set()

    # Add explicit required items
    explicit_items = parse_required_items(task.required_items)
    items.update(explicit_items)

    # Add suggestions if enabled
    if include_suggestions:
        suggested = get_suggested_items(
            purpose=task.purpose,
            auto_rules=task.auto_item_rules,
            include_defaults=True,
        )
        items.update(suggested)

    return sorted(items)


def get_consolidated_checklist(tasks: list[Task]) -> list[str]:
    """
    Get consolidated checklist for multiple tasks.

    Deduplicates items across all tasks.

    Args:
        tasks: List of tasks

    Returns:
        Deduplicated sorted list of all items
    """
    all_items = set()

    for task in tasks:
        task_items = get_task_checklist(task, include_suggestions=True)
        all_items.update(task_items)

    return sorted(all_items)


def get_checklist_by_stop(tasks: list[Task]) -> list[dict]:
    """
    Get checklists organized by stop/task.

    Args:
        tasks: List of tasks

    Returns:
        List of dicts with task info and checklist
    """
    result = []
    for task in tasks:
        checklist = get_task_checklist(task, include_suggestions=True)
        result.append({
            "task_id": str(task.id),
            "task_title": task.title,
            "location": task.location_name or task.address or "No location",
            "checklist": checklist,
        })
    return result


def format_checklist_for_display(items: list[str]) -> str:
    """
    Format checklist items for display.

    Args:
        items: List of item strings

    Returns:
        Formatted string with checkboxes
    """
    if not items:
        return "No items needed"

    lines = [f"☐ {item}" for item in items]
    return "\n".join(lines)


def format_checklist_for_ics(items: list[str]) -> str:
    """
    Format checklist items for ICS event description.

    Args:
        items: List of item strings

    Returns:
        Formatted string for calendar
    """
    if not items:
        return ""

    header = "Items to bring:\n"
    lines = [f"- {item}" for item in items]
    return header + "\n".join(lines)


def suggest_rules_for_purpose(purpose: str) -> list[str]:
    """
    Suggest which rule keywords match a purpose.

    Args:
        purpose: Task purpose description

    Returns:
        List of matching rule keywords
    """
    if not purpose:
        return []

    purpose_lower = purpose.lower()
    matches = []

    for keyword in PACKING_RULES:
        if keyword != "_default" and keyword in purpose_lower:
            matches.append(keyword)

    return matches


def get_available_rules() -> dict[str, list[str]]:
    """
    Get all available packing rules.

    Returns:
        Dict mapping rule keywords to item lists
    """
    return {k: v for k, v in PACKING_RULES.items() if k != "_default"}
