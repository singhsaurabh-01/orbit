"""Planner service - optimal daily schedule generation."""

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Optional
from uuid import UUID, uuid4

from orbit import db
from orbit.models import FixedBlock, OverflowTask, Plan, PlanItem, Settings, Task
from orbit.services import routing, tasks as tasks_service


@dataclass
class TimeWindow:
    """A time window for scheduling."""
    start: datetime
    end: datetime

    @property
    def duration_minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60

    def contains(self, dt: datetime) -> bool:
        return self.start <= dt <= self.end

    def overlaps(self, other: "TimeWindow") -> bool:
        return self.start < other.end and other.start < self.end

    def intersection(self, other: "TimeWindow") -> Optional["TimeWindow"]:
        start = max(self.start, other.start)
        end = min(self.end, other.end)
        if start < end:
            return TimeWindow(start=start, end=end)
        return None


@dataclass
class ScheduledItem:
    """An item scheduled in the plan."""
    type: str  # travel, task, fixed, break
    start: datetime
    end: datetime
    title: str
    task: Optional[Task] = None
    from_place: Optional[str] = None
    to_place: Optional[str] = None
    distance_km: Optional[float] = None
    travel_minutes: Optional[int] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


@dataclass
class PlanResult:
    """Result of plan generation."""
    plan: Plan
    items: list[ScheduledItem]
    overflow: list[OverflowTask]
    total_travel_km: float
    total_travel_minutes: float
    # Time window validation
    fits_in_window: bool = True
    schedule_end_time: Optional[datetime] = None
    window_end_time: Optional[datetime] = None
    window_start_time: Optional[datetime] = None
    overtime_minutes: float = 0.0
    buffer_minutes: float = 0.0
    suggestions: list[str] = field(default_factory=list)


def parse_time(time_str: str) -> time:
    """Parse a time string like '09:00' to time object."""
    parts = time_str.split(":")
    return time(hour=int(parts[0]), minute=int(parts[1]))


def combine_date_time(d: date, t: time) -> datetime:
    """Combine date and time into datetime."""
    return datetime(d.year, d.month, d.day, t.hour, t.minute)


def get_task_feasible_window(
    task: Task,
    plan_date: date,
    work_start: time,
    work_end: time,
) -> Optional[TimeWindow]:
    """
    Calculate the feasible time window for a task.

    Intersection of:
    - Working hours
    - Place open/close times
    - Task earliest_start/latest_end constraints

    Args:
        task: The task
        plan_date: Planning date
        work_start: Day start time
        work_end: Day end time

    Returns:
        TimeWindow if feasible, None if no valid window
    """
    # Start with working hours
    window_start = combine_date_time(plan_date, work_start)
    window_end = combine_date_time(plan_date, work_end)

    # Apply place open/close times
    if task.open_time_local:
        open_time = parse_time(task.open_time_local)
        open_dt = combine_date_time(plan_date, open_time)
        window_start = max(window_start, open_dt)

    if task.close_time_local:
        close_time = parse_time(task.close_time_local)
        close_dt = combine_date_time(plan_date, close_time)
        # Need to finish task before closing
        window_end = min(window_end, close_dt)

    # Apply task constraints
    if task.earliest_start:
        window_start = max(window_start, task.earliest_start)

    if task.latest_end:
        window_end = min(window_end, task.latest_end)

    # Check if window is valid and can fit the task
    if window_start >= window_end:
        return None

    duration = (window_end - window_start).total_seconds() / 60
    if duration < task.duration_minutes:
        return None

    return TimeWindow(start=window_start, end=window_end)


def get_free_windows(
    day_start: datetime,
    day_end: datetime,
    fixed_blocks: list[FixedBlock],
) -> list[TimeWindow]:
    """
    Calculate free time windows around fixed blocks.

    Args:
        day_start: Day start time
        day_end: Day end time
        fixed_blocks: List of fixed blocks

    Returns:
        List of free TimeWindows
    """
    if not fixed_blocks:
        return [TimeWindow(start=day_start, end=day_end)]

    # Sort blocks by start time
    blocks = sorted(fixed_blocks, key=lambda b: b.start_dt)

    windows = []
    current_start = day_start

    for block in blocks:
        # Free time before this block
        if current_start < block.start_dt:
            windows.append(TimeWindow(start=current_start, end=block.start_dt))
        current_start = max(current_start, block.end_dt)

    # Free time after all blocks
    if current_start < day_end:
        windows.append(TimeWindow(start=current_start, end=day_end))

    return windows


def calculate_priority_score(task: Task, plan_date: date) -> float:
    """
    Calculate a priority score for task ordering.

    Higher score = higher priority.

    Args:
        task: The task
        plan_date: Planning date

    Returns:
        Priority score
    """
    score = task.priority * 10

    # Boost for due today
    if task.due_date:
        days_until_due = (task.due_date - plan_date).days
        if days_until_due <= 0:
            score += 100  # Due today or overdue
        elif days_until_due == 1:
            score += 50  # Due tomorrow
        elif days_until_due <= 3:
            score += 20  # Due soon

    return score


def generate_plan(
    plan_date: date,
    settings: Settings,
    return_home: bool = True,
) -> PlanResult:
    """
    Generate an optimal daily plan.

    Uses a greedy insertion heuristic that:
    1. Starts at home
    2. At each step, chooses the next feasible errand that minimizes travel
    3. Respects time constraints and working hours
    4. Optionally returns home at the end

    Args:
        plan_date: Date to plan for
        settings: User settings
        return_home: Whether to return home at end

    Returns:
        PlanResult with plan, items, and overflow
    """
    # Validate home location
    if not settings.has_home_location:
        raise ValueError("Home location not set")

    # Get work hours
    work_start = parse_time(settings.default_work_start)
    work_end = parse_time(settings.default_work_end)
    day_start = combine_date_time(plan_date, work_start)
    day_end = combine_date_time(plan_date, work_end)

    # Get fixed blocks
    fixed_blocks = tasks_service.get_fixed_blocks_for_date(plan_date)

    # Get eligible tasks
    all_tasks = tasks_service.get_tasks_for_date(plan_date)

    # Separate location-based and home tasks
    errand_tasks = tasks_service.get_location_based_tasks(all_tasks)
    home_tasks = tasks_service.get_home_based_tasks(all_tasks)

    # Initialize result lists
    scheduled: list[ScheduledItem] = []
    overflow: list[OverflowTask] = []

    # Add fixed blocks to schedule
    for block in fixed_blocks:
        scheduled.append(ScheduledItem(
            type="fixed",
            start=block.start_dt,
            end=block.end_dt,
            title=block.title,
        ))

    # Current state
    current_time = day_start
    current_lat = settings.home_lat
    current_lon = settings.home_lon
    current_place = settings.home_name

    # Track which tasks are done
    scheduled_task_ids: set[UUID] = set()
    total_travel_km = 0.0
    total_travel_minutes = 0.0

    # Calculate feasible windows for all errands
    errand_windows: dict[UUID, TimeWindow] = {}
    for task in errand_tasks:
        if not task.has_location:
            overflow.append(OverflowTask(task=task, reason="Missing location"))
            continue

        window = get_task_feasible_window(task, plan_date, work_start, work_end)
        if window:
            errand_windows[task.id] = window
        else:
            overflow.append(OverflowTask(task=task, reason="No feasible time window"))

    # Greedy insertion for errands
    while True:
        # Find best next errand
        best_task: Optional[Task] = None
        best_score = float("-inf")
        best_arrival_time: Optional[datetime] = None
        best_travel_time = 0.0
        best_travel_km = 0.0

        for task in errand_tasks:
            if task.id in scheduled_task_ids:
                continue
            if task.id not in errand_windows:
                continue

            window = errand_windows[task.id]

            # Calculate travel time from current location
            route = routing.get_route(
                current_lat, current_lon,
                task.lat, task.lon,
            )
            travel_minutes = route.duration_minutes

            # Calculate arrival time
            arrival_time = current_time + timedelta(minutes=travel_minutes)

            # Check if we can start within the window
            if arrival_time > window.end:
                continue  # Can't make it in time

            # Wait if we arrive early
            actual_start = max(arrival_time, window.start)

            # Check if we can finish within the window and day
            task_end = actual_start + timedelta(minutes=task.duration_minutes)
            if task_end > window.end:
                continue  # Task won't fit
            if task_end > day_end:
                continue  # Past work hours

            # Check for conflicts with fixed blocks
            task_window = TimeWindow(start=actual_start, end=task_end)
            conflict = False
            for block in fixed_blocks:
                block_window = TimeWindow(start=block.start_dt, end=block.end_dt)
                if task_window.overlaps(block_window):
                    conflict = True
                    break

            # Also check against already scheduled items
            for item in scheduled:
                item_window = TimeWindow(start=item.start, end=item.end)
                if task_window.overlaps(item_window):
                    conflict = True
                    break

            if conflict:
                continue

            # Calculate score: minimize travel, prioritize by due date/priority
            priority_score = calculate_priority_score(task, plan_date)
            # Negative travel time so lower travel = higher score
            score = priority_score - travel_minutes * 2

            if score > best_score:
                best_score = score
                best_task = task
                best_arrival_time = arrival_time
                best_travel_time = travel_minutes
                best_travel_km = route.distance_km

        if best_task is None:
            break  # No more feasible errands

        window = errand_windows[best_task.id]
        actual_start = max(best_arrival_time, window.start)

        # Add travel segment
        if best_travel_time > 0:
            travel_item = ScheduledItem(
                type="travel",
                start=current_time,
                end=best_arrival_time,
                title=f"Drive to {best_task.location_name or best_task.address}",
                from_place=current_place,
                to_place=best_task.location_name or best_task.address,
                distance_km=best_travel_km,
                travel_minutes=int(best_travel_time),
            )
            scheduled.append(travel_item)
            total_travel_km += best_travel_km
            total_travel_minutes += best_travel_time

        # Add wait/break if needed
        if actual_start > best_arrival_time:
            wait_minutes = (actual_start - best_arrival_time).total_seconds() / 60
            wait_item = ScheduledItem(
                type="break",
                start=best_arrival_time,
                end=actual_start,
                title=f"Wait for {best_task.location_name or 'location'} to open",
            )
            scheduled.append(wait_item)

        # Add task
        task_end = actual_start + timedelta(minutes=best_task.duration_minutes)
        task_item = ScheduledItem(
            type="task",
            start=actual_start,
            end=task_end,
            title=best_task.title,
            task=best_task,
            lat=best_task.lat,
            lon=best_task.lon,
        )
        scheduled.append(task_item)

        # Update state
        current_time = task_end
        current_lat = best_task.lat
        current_lon = best_task.lon
        current_place = best_task.location_name or best_task.address
        scheduled_task_ids.add(best_task.id)

    # Mark remaining errands as overflow
    for task in errand_tasks:
        if task.id not in scheduled_task_ids and task.id in errand_windows:
            overflow.append(OverflowTask(task=task, reason="Insufficient time in schedule"))

    # Return home if requested
    if return_home and (current_lat != settings.home_lat or current_lon != settings.home_lon):
        if current_time < day_end:
            route = routing.get_route(
                current_lat, current_lon,
                settings.home_lat, settings.home_lon,
            )
            travel_end = current_time + timedelta(minutes=route.duration_minutes)

            travel_item = ScheduledItem(
                type="travel",
                start=current_time,
                end=travel_end,
                title=f"Return to {settings.home_name}",
                from_place=current_place,
                to_place=settings.home_name,
                distance_km=route.distance_km,
                travel_minutes=int(route.duration_minutes),
            )
            scheduled.append(travel_item)
            total_travel_km += route.distance_km
            total_travel_minutes += route.duration_minutes
            current_time = travel_end

    # Schedule home tasks in remaining gaps
    # Find free windows
    scheduled_windows = [TimeWindow(start=s.start, end=s.end) for s in scheduled]
    all_busy = sorted(scheduled_windows, key=lambda w: w.start)

    # Merge overlapping windows
    merged_busy = []
    for w in all_busy:
        if merged_busy and w.start <= merged_busy[-1].end:
            merged_busy[-1] = TimeWindow(
                start=merged_busy[-1].start,
                end=max(merged_busy[-1].end, w.end)
            )
        else:
            merged_busy.append(w)

    # Find gaps
    free_gaps = []
    gap_start = day_start
    for busy in merged_busy:
        if gap_start < busy.start:
            free_gaps.append(TimeWindow(start=gap_start, end=busy.start))
        gap_start = max(gap_start, busy.end)
    if gap_start < day_end:
        free_gaps.append(TimeWindow(start=gap_start, end=day_end))

    # Schedule home tasks (earliest deadline first)
    home_tasks_sorted = sorted(
        home_tasks,
        key=lambda t: (t.due_date or date.max, -t.priority)
    )

    for task in home_tasks_sorted:
        # Find a gap that fits
        for gap in free_gaps:
            if gap.duration_minutes >= task.duration_minutes:
                task_start = gap.start
                task_end = task_start + timedelta(minutes=task.duration_minutes)

                task_item = ScheduledItem(
                    type="task",
                    start=task_start,
                    end=task_end,
                    title=task.title,
                    task=task,
                    lat=settings.home_lat,
                    lon=settings.home_lon,
                )
                scheduled.append(task_item)
                scheduled_task_ids.add(task.id)

                # Update gap
                if task_end < gap.end:
                    gap.start = task_end
                else:
                    free_gaps.remove(gap)
                break
        else:
            # No gap found
            if task.id not in scheduled_task_ids:
                overflow.append(OverflowTask(task=task, reason="No free time slot available"))

    # Sort scheduled items by start time
    scheduled.sort(key=lambda s: s.start)

    # Create plan and plan items
    plan = Plan(
        plan_date=plan_date,
        assumptions_json=json.dumps({
            "work_start": settings.default_work_start,
            "work_end": settings.default_work_end,
            "return_home": return_home,
            "home_address": settings.home_address,
        }),
    )
    db.save_plan(plan)

    # Delete old plan items
    db.delete_plan_items(plan.id)

    # Save plan items
    for idx, item in enumerate(scheduled):
        plan_item = PlanItem(
            plan_id=plan.id,
            order_index=idx,
            start_dt=item.start,
            end_dt=item.end,
            type=item.type,
            task_id=item.task.id if item.task else None,
            title=item.title,
            from_place=item.from_place,
            to_place=item.to_place,
            distance_km=item.distance_km,
            travel_minutes=item.travel_minutes,
            lat=item.lat,
            lon=item.lon,
        )
        db.save_plan_item(plan_item)

    # Calculate time window validation
    schedule_end_time = None
    if scheduled:
        schedule_end_time = max(item.end for item in scheduled)

    # Check if schedule fits in time window
    fits_in_window = True
    overtime_minutes = 0.0
    buffer_minutes = 0.0

    if schedule_end_time:
        if schedule_end_time > day_end:
            fits_in_window = False
            overtime_minutes = (schedule_end_time - day_end).total_seconds() / 60
        else:
            buffer_minutes = (day_end - schedule_end_time).total_seconds() / 60

    # Generate suggestions if plan doesn't fit
    suggestions = []
    if not fits_in_window:
        suggestions = generate_suggestions(
            scheduled, overflow, day_start, day_end, overtime_minutes
        )

    return PlanResult(
        plan=plan,
        items=scheduled,
        overflow=overflow,
        total_travel_km=round(total_travel_km, 2),
        total_travel_minutes=round(total_travel_minutes, 1),
        fits_in_window=fits_in_window,
        schedule_end_time=schedule_end_time,
        window_end_time=day_end,
        window_start_time=day_start,
        overtime_minutes=round(overtime_minutes, 1),
        buffer_minutes=round(buffer_minutes, 1),
        suggestions=suggestions,
    )


def generate_suggestions(
    scheduled: list[ScheduledItem],
    overflow: list[OverflowTask],
    window_start: datetime,
    window_end: datetime,
    overtime_mins: float
) -> list[str]:
    """
    Generate actionable suggestions when plan doesn't fit in time window.

    Returns list of suggestion strings ordered by impact.
    """
    suggestions = []

    # Suggestion 1: Leave earlier
    if overtime_mins <= 60:
        leave_earlier = math.ceil(overtime_mins / 15) * 15  # Round to 15 min
        suggestions.append(
            f"Leave {leave_earlier} minutes earlier "
            f"(at {(window_start - timedelta(minutes=leave_earlier)).strftime('%-I:%M %p')})"
        )

    # Suggestion 2: Extend return time
    if overtime_mins <= 60:
        extend_return = math.ceil(overtime_mins / 15) * 15
        suggestions.append(
            f"Extend return-by time by {extend_return} minutes "
            f"(to {(window_end + timedelta(minutes=extend_return)).strftime('%-I:%M %p')})"
        )

    # Suggestion 3: Drop lowest priority task
    scheduled_tasks = [
        item for item in scheduled
        if item.type == "task" and item.task is not None
    ]

    if scheduled_tasks:
        # Calculate time savings for each task
        task_savings = []
        for item in scheduled_tasks:
            # Time saved = task duration + associated travel
            time_saved = item.task.duration_minutes

            # Find adjacent travel segments
            item_idx = scheduled.index(item)
            if item_idx > 0 and scheduled[item_idx - 1].type == "travel":
                time_saved += scheduled[item_idx - 1].travel_minutes or 0
            if item_idx < len(scheduled) - 1 and scheduled[item_idx + 1].type == "travel":
                time_saved += scheduled[item_idx + 1].travel_minutes or 0

            task_savings.append((item.task, time_saved))

        # Sort by priority (ascending), then by time saved (descending)
        task_savings.sort(key=lambda x: (x[0].priority, -x[1]))

        # Suggest dropping tasks that would close the gap
        for task, time_saved in task_savings:
            if time_saved >= overtime_mins * 0.7:  # Task saves ≥70% of deficit
                suggestions.append(
                    f"Drop '{task.title}' (priority {task.priority}, "
                    f"saves ~{int(time_saved)} min)"
                )

    # Suggestion 4: Reduce task durations
    long_tasks = [
        item for item in scheduled_tasks
        if item.task.duration_minutes > 30
    ]

    if long_tasks:
        suggestions.append(
            f"Reduce duration of long tasks "
            f"({', '.join([t.task.title for t in long_tasks[:3]])})"
        )

    # Suggestion 5: Pick closer locations
    long_travels = [
        (scheduled[i-1], scheduled[i])
        for i in range(1, len(scheduled))
        if scheduled[i].type == "task"
        and scheduled[i-1].type == "travel"
        and (scheduled[i-1].travel_minutes or 0) > 15
    ]

    if long_travels:
        for travel, task in long_travels[:2]:  # Top 2
            suggestions.append(
                f"Choose closer location for '{task.title}' "
                f"(current: {int(travel.travel_minutes)} min travel)"
            )

    # Limit to top 5 suggestions
    return suggestions[:5]


def get_scheduled_tasks(plan_result: PlanResult) -> list[Task]:
    """Get list of tasks that were scheduled."""
    return [item.task for item in plan_result.items if item.task is not None]


def get_route_waypoints(
    plan_result: PlanResult,
    settings: Settings,
) -> list[tuple[float, float, str]]:
    """
    Get waypoints for the route.

    Args:
        plan_result: Generated plan result
        settings: User settings

    Returns:
        List of (lat, lon, name) tuples
    """
    waypoints = [(settings.home_lat, settings.home_lon, settings.home_name)]

    for item in plan_result.items:
        if item.type == "task" and item.lat and item.lon:
            name = item.task.location_name if item.task else item.title
            waypoints.append((item.lat, item.lon, name))

    # Check if ends at home
    if len(waypoints) > 1:
        last = waypoints[-1]
        if last[0] != settings.home_lat or last[1] != settings.home_lon:
            # Add return to home if there's a return travel segment
            for item in plan_result.items:
                if item.type == "travel" and item.to_place == settings.home_name:
                    waypoints.append((settings.home_lat, settings.home_lon, settings.home_name))
                    break

    return waypoints
