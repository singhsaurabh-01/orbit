"""Database management for Orbit using SQLite."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from orbit import config
from orbit.models import FixedBlock, Place, Plan, PlanItem, Settings, Task


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize the database schema."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY DEFAULT 1,
                home_name TEXT DEFAULT 'Home',
                home_address TEXT,
                home_lat REAL,
                home_lon REAL,
                default_timezone TEXT DEFAULT 'America/Chicago',
                default_work_start TEXT DEFAULT '09:00',
                default_work_end TEXT DEFAULT '18:00'
            )
        """)

        # Places table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS places (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                address TEXT NOT NULL,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                source TEXT DEFAULT 'manual',
                phone TEXT,
                website TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Tasks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT DEFAULT 'errand',
                notes TEXT,
                priority INTEGER DEFAULT 2,
                status TEXT DEFAULT 'todo',
                duration_minutes INTEGER DEFAULT 30,
                due_date TEXT,
                earliest_start TEXT,
                latest_end TEXT,
                place_id TEXT,
                location_name TEXT,
                address TEXT,
                lat REAL,
                lon REAL,
                open_time_local TEXT,
                close_time_local TEXT,
                days_open TEXT,
                purpose TEXT,
                required_items TEXT,
                auto_item_rules TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (place_id) REFERENCES places(id)
            )
        """)

        # Fixed blocks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fixed_blocks (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                start_dt TEXT NOT NULL,
                end_dt TEXT NOT NULL,
                title TEXT NOT NULL,
                notes TEXT
            )
        """)

        # Plans table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                id TEXT PRIMARY KEY,
                plan_date TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                assumptions_json TEXT
            )
        """)

        # Plan items table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS plan_items (
                id TEXT PRIMARY KEY,
                plan_id TEXT NOT NULL,
                order_index INTEGER NOT NULL,
                start_dt TEXT NOT NULL,
                end_dt TEXT NOT NULL,
                type TEXT NOT NULL,
                task_id TEXT,
                title TEXT NOT NULL,
                from_place TEXT,
                to_place TEXT,
                distance_km REAL,
                travel_minutes INTEGER,
                lat REAL,
                lon REAL,
                FOREIGN KEY (plan_id) REFERENCES plans(id),
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
        """)

        # Cache table for geocoding and routing
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)

        # Insert default settings if not exists
        cursor.execute("SELECT COUNT(*) FROM settings")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO settings (id, home_name, default_timezone, default_work_start, default_work_end)
                VALUES (1, 'Home', 'America/Chicago', '09:00', '18:00')
            """)


# Settings operations
def get_settings() -> Settings:
    """Get the settings."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM settings WHERE id = 1")
        row = cursor.fetchone()
        if row:
            return Settings(
                id=row["id"],
                home_name=row["home_name"],
                home_address=row["home_address"],
                home_lat=row["home_lat"],
                home_lon=row["home_lon"],
                default_timezone=row["default_timezone"],
                default_work_start=row["default_work_start"],
                default_work_end=row["default_work_end"],
            )
        return Settings()


def save_settings(settings: Settings):
    """Save settings."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO settings
            (id, home_name, home_address, home_lat, home_lon, default_timezone, default_work_start, default_work_end)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            1,
            settings.home_name,
            settings.home_address,
            settings.home_lat,
            settings.home_lon,
            settings.default_timezone,
            settings.default_work_start,
            settings.default_work_end,
        ))


# Place operations
def get_places() -> list[Place]:
    """Get all places."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM places ORDER BY name")
        rows = cursor.fetchall()
        return [_row_to_place(row) for row in rows]


def get_place(place_id: UUID) -> Optional[Place]:
    """Get a place by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM places WHERE id = ?", (str(place_id),))
        row = cursor.fetchone()
        return _row_to_place(row) if row else None


def save_place(place: Place):
    """Save a place."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO places
            (id, name, address, lat, lon, source, phone, website, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(place.id),
            place.name,
            place.address,
            place.lat,
            place.lon,
            place.source,
            place.phone,
            place.website,
            place.created_at.isoformat(),
            datetime.now().isoformat(),
        ))


def delete_place(place_id: UUID):
    """Delete a place."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM places WHERE id = ?", (str(place_id),))


def _row_to_place(row: sqlite3.Row) -> Place:
    """Convert a database row to a Place object."""
    return Place(
        id=UUID(row["id"]),
        name=row["name"],
        address=row["address"],
        lat=row["lat"],
        lon=row["lon"],
        source=row["source"],
        phone=row["phone"],
        website=row["website"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


# Task operations
def get_tasks(status: Optional[str] = None, due_date: Optional[date] = None) -> list[Task]:
    """Get tasks with optional filters."""
    with get_db() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status)

        if due_date:
            query += " AND (due_date IS NULL OR due_date = ?)"
            params.append(due_date.isoformat())

        query += " ORDER BY priority DESC, due_date ASC NULLS LAST, created_at ASC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [_row_to_task(row) for row in rows]


def get_todo_tasks() -> list[Task]:
    """Get all todo tasks."""
    return get_tasks(status="todo")


def get_task(task_id: UUID) -> Optional[Task]:
    """Get a task by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (str(task_id),))
        row = cursor.fetchone()
        return _row_to_task(row) if row else None


def save_task(task: Task):
    """Save a task."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO tasks
            (id, title, category, notes, priority, status, duration_minutes, due_date,
             earliest_start, latest_end, place_id, location_name, address, lat, lon,
             open_time_local, close_time_local, days_open, purpose, required_items,
             auto_item_rules, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(task.id),
            task.title,
            task.category,
            task.notes,
            task.priority,
            task.status,
            task.duration_minutes,
            task.due_date.isoformat() if task.due_date else None,
            task.earliest_start.isoformat() if task.earliest_start else None,
            task.latest_end.isoformat() if task.latest_end else None,
            str(task.place_id) if task.place_id else None,
            task.location_name,
            task.address,
            task.lat,
            task.lon,
            task.open_time_local,
            task.close_time_local,
            task.days_open,
            task.purpose,
            task.required_items,
            task.auto_item_rules,
            task.created_at.isoformat(),
            datetime.now().isoformat(),
        ))


def delete_task(task_id: UUID):
    """Delete a task."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE id = ?", (str(task_id),))


def update_task_status(task_id: UUID, status: str):
    """Update a task's status."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.now().isoformat(), str(task_id))
        )


def _row_to_task(row: sqlite3.Row) -> Task:
    """Convert a database row to a Task object."""
    return Task(
        id=UUID(row["id"]),
        title=row["title"],
        category=row["category"],
        notes=row["notes"],
        priority=row["priority"],
        status=row["status"],
        duration_minutes=row["duration_minutes"],
        due_date=date.fromisoformat(row["due_date"]) if row["due_date"] else None,
        earliest_start=datetime.fromisoformat(row["earliest_start"]) if row["earliest_start"] else None,
        latest_end=datetime.fromisoformat(row["latest_end"]) if row["latest_end"] else None,
        place_id=UUID(row["place_id"]) if row["place_id"] else None,
        location_name=row["location_name"],
        address=row["address"],
        lat=row["lat"],
        lon=row["lon"],
        open_time_local=row["open_time_local"],
        close_time_local=row["close_time_local"],
        days_open=row["days_open"],
        purpose=row["purpose"],
        required_items=row["required_items"],
        auto_item_rules=row["auto_item_rules"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


# Fixed block operations
def get_fixed_blocks(date_filter: Optional[date] = None) -> list[FixedBlock]:
    """Get fixed blocks with optional date filter."""
    with get_db() as conn:
        cursor = conn.cursor()
        if date_filter:
            cursor.execute(
                "SELECT * FROM fixed_blocks WHERE date = ? ORDER BY start_dt",
                (date_filter.isoformat(),)
            )
        else:
            cursor.execute("SELECT * FROM fixed_blocks ORDER BY date, start_dt")
        rows = cursor.fetchall()
        return [_row_to_fixed_block(row) for row in rows]


def get_fixed_block(block_id: UUID) -> Optional[FixedBlock]:
    """Get a fixed block by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fixed_blocks WHERE id = ?", (str(block_id),))
        row = cursor.fetchone()
        return _row_to_fixed_block(row) if row else None


def save_fixed_block(block: FixedBlock):
    """Save a fixed block."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO fixed_blocks
            (id, date, start_dt, end_dt, title, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            str(block.id),
            block.date.isoformat(),
            block.start_dt.isoformat(),
            block.end_dt.isoformat(),
            block.title,
            block.notes,
        ))


def delete_fixed_block(block_id: UUID):
    """Delete a fixed block."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM fixed_blocks WHERE id = ?", (str(block_id),))


def _row_to_fixed_block(row: sqlite3.Row) -> FixedBlock:
    """Convert a database row to a FixedBlock object."""
    return FixedBlock(
        id=UUID(row["id"]),
        date=date.fromisoformat(row["date"]),
        start_dt=datetime.fromisoformat(row["start_dt"]),
        end_dt=datetime.fromisoformat(row["end_dt"]),
        title=row["title"],
        notes=row["notes"],
    )


# Plan operations
def get_plan(plan_date: date) -> Optional[Plan]:
    """Get a plan for a specific date."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM plans WHERE plan_date = ? ORDER BY generated_at DESC LIMIT 1",
            (plan_date.isoformat(),)
        )
        row = cursor.fetchone()
        return _row_to_plan(row) if row else None


def save_plan(plan: Plan):
    """Save a plan."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO plans
            (id, plan_date, generated_at, assumptions_json)
            VALUES (?, ?, ?, ?)
        """, (
            str(plan.id),
            plan.plan_date.isoformat(),
            plan.generated_at.isoformat(),
            plan.assumptions_json,
        ))


def get_plan_items(plan_id: UUID) -> list[PlanItem]:
    """Get all items for a plan."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM plan_items WHERE plan_id = ? ORDER BY order_index",
            (str(plan_id),)
        )
        rows = cursor.fetchall()
        return [_row_to_plan_item(row) for row in rows]


def save_plan_item(item: PlanItem):
    """Save a plan item."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO plan_items
            (id, plan_id, order_index, start_dt, end_dt, type, task_id, title,
             from_place, to_place, distance_km, travel_minutes, lat, lon)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(item.id),
            str(item.plan_id),
            item.order_index,
            item.start_dt.isoformat(),
            item.end_dt.isoformat(),
            item.type,
            str(item.task_id) if item.task_id else None,
            item.title,
            item.from_place,
            item.to_place,
            item.distance_km,
            item.travel_minutes,
            item.lat,
            item.lon,
        ))


def delete_plan_items(plan_id: UUID):
    """Delete all items for a plan."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM plan_items WHERE plan_id = ?", (str(plan_id),))


def _row_to_plan(row: sqlite3.Row) -> Plan:
    """Convert a database row to a Plan object."""
    return Plan(
        id=UUID(row["id"]),
        plan_date=date.fromisoformat(row["plan_date"]),
        generated_at=datetime.fromisoformat(row["generated_at"]),
        assumptions_json=row["assumptions_json"],
    )


def _row_to_plan_item(row: sqlite3.Row) -> PlanItem:
    """Convert a database row to a PlanItem object."""
    return PlanItem(
        id=UUID(row["id"]),
        plan_id=UUID(row["plan_id"]),
        order_index=row["order_index"],
        start_dt=datetime.fromisoformat(row["start_dt"]),
        end_dt=datetime.fromisoformat(row["end_dt"]),
        type=row["type"],
        task_id=UUID(row["task_id"]) if row["task_id"] else None,
        title=row["title"],
        from_place=row["from_place"],
        to_place=row["to_place"],
        distance_km=row["distance_km"],
        travel_minutes=row["travel_minutes"],
        lat=row["lat"],
        lon=row["lon"],
    )


# Cache operations
def get_cache(key: str) -> Optional[str]:
    """Get a cached value if not expired."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT value FROM cache WHERE key = ? AND expires_at > ?",
            (key, datetime.now().isoformat())
        )
        row = cursor.fetchone()
        return row["value"] if row else None


def set_cache(key: str, value: str, ttl_days: int = 7):
    """Set a cached value with expiration."""
    from datetime import timedelta
    expires_at = datetime.now() + timedelta(days=ttl_days)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO cache (key, value, created_at, expires_at)
            VALUES (?, ?, ?, ?)
        """, (key, value, datetime.now().isoformat(), expires_at.isoformat()))


def clear_expired_cache():
    """Clear expired cache entries."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cache WHERE expires_at < ?", (datetime.now().isoformat(),))
