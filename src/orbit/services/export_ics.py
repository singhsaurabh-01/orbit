"""ICS export service for calendar events."""

from datetime import datetime
from typing import Optional

from icalendar import Calendar, Event

from orbit.models import Settings
from orbit.services.packing import format_checklist_for_ics, get_task_checklist
from orbit.services.planner import PlanResult, ScheduledItem


def create_event_from_item(
    item: ScheduledItem,
    include_checklist: bool = True,
    timezone: str = "America/Chicago",
) -> Event:
    """
    Create an iCalendar event from a scheduled item.

    Args:
        item: ScheduledItem to convert
        include_checklist: Whether to include packing checklist
        timezone: Timezone for the event

    Returns:
        iCalendar Event object
    """
    event = Event()
    event.add("summary", item.title)
    event.add("dtstart", item.start)
    event.add("dtend", item.end)

    # Build description
    description_parts = []

    if item.type == "task" and item.task:
        if item.task.notes:
            description_parts.append(item.task.notes)

        if item.task.purpose:
            description_parts.append(f"Purpose: {item.task.purpose}")

        if include_checklist:
            checklist = get_task_checklist(item.task)
            if checklist:
                checklist_text = format_checklist_for_ics(checklist)
                description_parts.append(checklist_text)

    elif item.type == "travel":
        description_parts.append(f"From: {item.from_place}")
        description_parts.append(f"To: {item.to_place}")
        if item.distance_km:
            description_parts.append(f"Distance: {item.distance_km:.1f} km")
        if item.travel_minutes:
            description_parts.append(f"Duration: {item.travel_minutes} min")

    if description_parts:
        event.add("description", "\n\n".join(description_parts))

    # Add location if available
    if item.type == "task" and item.task:
        location = item.task.address or item.task.location_name
        if location:
            event.add("location", location)
    elif item.type == "travel" and item.to_place:
        event.add("location", item.to_place)

    # Add coordinates if available
    if item.lat and item.lon:
        event.add("geo", (item.lat, item.lon))

    return event


def export_plan_to_ics(
    plan_result: PlanResult,
    settings: Settings,
    include_travel: bool = False,
    include_checklist: bool = True,
) -> str:
    """
    Export a plan to ICS format.

    Args:
        plan_result: Generated plan result
        settings: User settings
        include_travel: Whether to include travel segments as events
        include_checklist: Whether to include packing checklists

    Returns:
        ICS file content as string
    """
    cal = Calendar()
    cal.add("prodid", "-//Orbit Day Planner//orbit.local//")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", f"Orbit Plan - {plan_result.plan.plan_date}")

    for item in plan_result.items:
        # Skip travel segments if not requested
        if item.type == "travel" and not include_travel:
            continue

        # Skip breaks
        if item.type == "break":
            continue

        event = create_event_from_item(
            item,
            include_checklist=include_checklist,
            timezone=settings.default_timezone,
        )
        cal.add_component(event)

    return cal.to_ical().decode("utf-8")


def export_to_file(
    plan_result: PlanResult,
    settings: Settings,
    filepath: str,
    include_travel: bool = False,
    include_checklist: bool = True,
):
    """
    Export a plan to an ICS file.

    Args:
        plan_result: Generated plan result
        settings: User settings
        filepath: Output file path
        include_travel: Whether to include travel segments
        include_checklist: Whether to include packing checklists
    """
    ics_content = export_plan_to_ics(
        plan_result,
        settings,
        include_travel=include_travel,
        include_checklist=include_checklist,
    )

    with open(filepath, "w") as f:
        f.write(ics_content)


def get_ics_filename(plan_date) -> str:
    """
    Generate a filename for the ICS export.

    Args:
        plan_date: Date of the plan

    Returns:
        Filename string
    """
    return f"orbit_plan_{plan_date.isoformat()}.ics"
