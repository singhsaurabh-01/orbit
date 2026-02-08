"""Data models for Orbit."""

from datetime import date, datetime, time
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Settings(BaseModel):
    """User settings including home location."""

    id: int = 1
    home_name: str = "Home"
    home_address: Optional[str] = None
    home_lat: Optional[float] = None
    home_lon: Optional[float] = None
    default_timezone: str = "America/Chicago"
    default_work_start: str = "09:00"
    default_work_end: str = "18:00"

    @property
    def has_home_location(self) -> bool:
        """Check if home location is set."""
        return self.home_lat is not None and self.home_lon is not None


class Place(BaseModel):
    """A saved place/location."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    address: str
    lat: float
    lon: float
    source: str = "manual"  # manual, nominatim, overpass
    phone: Optional[str] = None
    website: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class Task(BaseModel):
    """A task or errand."""

    id: UUID = Field(default_factory=uuid4)
    title: str
    category: str = "errand"
    notes: Optional[str] = None
    priority: int = 2  # 1-4 (Low to Urgent)
    status: str = "todo"  # todo, in_progress, done
    duration_minutes: int = 30  # Expected time spent

    # Date constraints
    due_date: Optional[date] = None

    # Time constraints for execution
    earliest_start: Optional[datetime] = None
    latest_end: Optional[datetime] = None

    # Location (either linked place or manual)
    place_id: Optional[UUID] = None
    location_name: Optional[str] = None
    address: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None

    # Place working hours constraint
    open_time_local: Optional[str] = None  # e.g., "10:00"
    close_time_local: Optional[str] = None  # e.g., "16:00"
    days_open: Optional[str] = None  # e.g., "Mon,Tue,Wed,Thu,Fri"

    # Packing / requirements
    purpose: Optional[str] = None  # e.g., "DMV license renewal"
    required_items: Optional[str] = None  # JSON list or newline-separated
    auto_item_rules: Optional[str] = None  # Tags to trigger suggestions

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @property
    def has_location(self) -> bool:
        """Check if task has a location."""
        return self.lat is not None and self.lon is not None

    @property
    def is_location_based(self) -> bool:
        """Check if task requires travel."""
        return self.category in ["errand", "appointment", "shopping", "health", "financial"]


class FixedBlock(BaseModel):
    """A fixed time block (meeting, appointment)."""

    id: UUID = Field(default_factory=uuid4)
    date: date
    start_dt: datetime
    end_dt: datetime
    title: str
    notes: Optional[str] = None


class Plan(BaseModel):
    """A generated daily plan."""

    id: UUID = Field(default_factory=uuid4)
    plan_date: date
    generated_at: datetime = Field(default_factory=datetime.now)
    assumptions_json: Optional[str] = None


class PlanItem(BaseModel):
    """An item in a plan (task, travel, or break)."""

    id: UUID = Field(default_factory=uuid4)
    plan_id: UUID
    order_index: int
    start_dt: datetime
    end_dt: datetime
    type: str  # travel, task, break, fixed
    task_id: Optional[UUID] = None
    title: str
    from_place: Optional[str] = None
    to_place: Optional[str] = None
    distance_km: Optional[float] = None
    travel_minutes: Optional[int] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


class PlaceSearchResult(BaseModel):
    """A place search result from geocoding/search."""

    name: str
    address: str
    lat: float
    lon: float
    source: str = "nominatim"
    osm_id: Optional[str] = None
    place_type: Optional[str] = None


class RouteResult(BaseModel):
    """Result from routing calculation."""

    origin_lat: float
    origin_lon: float
    dest_lat: float
    dest_lon: float
    distance_km: float
    duration_minutes: float
    geometry: Optional[str] = None  # Encoded polyline if available
    source: str = "osrm"  # osrm or fallback


class OverflowTask(BaseModel):
    """A task that couldn't be scheduled."""

    task: Task
    reason: str
