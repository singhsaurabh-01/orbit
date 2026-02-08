"""Task management service."""

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from orbit import db
from orbit.models import FixedBlock, Task


def get_all_tasks() -> list[Task]:
    """Get all tasks."""
    return db.get_tasks()


def get_todo_tasks() -> list[Task]:
    """Get all tasks with status 'todo'."""
    return db.get_tasks(status="todo")


def get_tasks_for_date(plan_date: date) -> list[Task]:
    """
    Get tasks that can be scheduled for a specific date.

    Returns tasks that:
    - Have status 'todo'
    - Have no due date OR due date >= plan_date
    - If they have days_open, the day matches

    Args:
        plan_date: Date to get tasks for

    Returns:
        List of eligible tasks
    """
    all_todo = db.get_tasks(status="todo")
    day_name = plan_date.strftime("%a")  # Mon, Tue, etc.

    eligible = []
    for task in all_todo:
        # Check due date
        if task.due_date and task.due_date < plan_date:
            continue

        # Check days_open
        if task.days_open:
            days = [d.strip() for d in task.days_open.split(",")]
            if day_name not in days:
                continue

        eligible.append(task)

    return eligible


def get_task(task_id: UUID) -> Optional[Task]:
    """Get a task by ID."""
    return db.get_task(task_id)


def create_task(
    title: str,
    category: str = "errand",
    notes: Optional[str] = None,
    priority: int = 2,
    duration_minutes: int = 30,
    due_date: Optional[date] = None,
    location_name: Optional[str] = None,
    address: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    open_time_local: Optional[str] = None,
    close_time_local: Optional[str] = None,
    days_open: Optional[str] = None,
    purpose: Optional[str] = None,
    required_items: Optional[str] = None,
    auto_item_rules: Optional[str] = None,
    earliest_start: Optional[datetime] = None,
    latest_end: Optional[datetime] = None,
) -> Task:
    """
    Create a new task.

    Args:
        title: Task title
        category: Task category
        notes: Optional notes
        priority: Priority level (1-4)
        duration_minutes: Expected duration
        due_date: Optional due date
        location_name: Location name
        address: Location address
        lat: Latitude
        lon: Longitude
        open_time_local: Opening time
        close_time_local: Closing time
        days_open: Days location is open
        purpose: Purpose description
        required_items: Items required
        auto_item_rules: Auto-suggestion rules
        earliest_start: Earliest start time
        latest_end: Latest end time

    Returns:
        Created Task
    """
    task = Task(
        title=title,
        category=category,
        notes=notes,
        priority=priority,
        duration_minutes=duration_minutes,
        due_date=due_date,
        location_name=location_name,
        address=address,
        lat=lat,
        lon=lon,
        open_time_local=open_time_local,
        close_time_local=close_time_local,
        days_open=days_open,
        purpose=purpose,
        required_items=required_items,
        auto_item_rules=auto_item_rules,
        earliest_start=earliest_start,
        latest_end=latest_end,
    )
    db.save_task(task)
    return task


def update_task(task: Task) -> Task:
    """Update a task."""
    task.updated_at = datetime.now()
    db.save_task(task)
    return task


def delete_task(task_id: UUID):
    """Delete a task."""
    db.delete_task(task_id)


def mark_task_done(task_id: UUID):
    """Mark a task as done."""
    db.update_task_status(task_id, "done")


def mark_task_in_progress(task_id: UUID):
    """Mark a task as in progress."""
    db.update_task_status(task_id, "in_progress")


def mark_task_todo(task_id: UUID):
    """Mark a task as todo."""
    db.update_task_status(task_id, "todo")


# Fixed block operations

def get_fixed_blocks_for_date(plan_date: date) -> list[FixedBlock]:
    """Get fixed blocks for a specific date."""
    return db.get_fixed_blocks(date_filter=plan_date)


def get_all_fixed_blocks() -> list[FixedBlock]:
    """Get all fixed blocks."""
    return db.get_fixed_blocks()


def create_fixed_block(
    date_val: date,
    start_dt: datetime,
    end_dt: datetime,
    title: str,
    notes: Optional[str] = None,
) -> FixedBlock:
    """Create a fixed block."""
    block = FixedBlock(
        date=date_val,
        start_dt=start_dt,
        end_dt=end_dt,
        title=title,
        notes=notes,
    )
    db.save_fixed_block(block)
    return block


def update_fixed_block(block: FixedBlock) -> FixedBlock:
    """Update a fixed block."""
    db.save_fixed_block(block)
    return block


def delete_fixed_block(block_id: UUID):
    """Delete a fixed block."""
    db.delete_fixed_block(block_id)


def get_location_based_tasks(tasks: list[Task]) -> list[Task]:
    """
    Filter tasks that require travel (have locations).

    Args:
        tasks: List of tasks

    Returns:
        Tasks with locations
    """
    return [t for t in tasks if t.has_location and t.is_location_based]


def get_home_based_tasks(tasks: list[Task]) -> list[Task]:
    """
    Filter tasks that don't require travel.

    Args:
        tasks: List of tasks

    Returns:
        Tasks without locations or non-location categories
    """
    return [t for t in tasks if not t.is_location_based or not t.has_location]
