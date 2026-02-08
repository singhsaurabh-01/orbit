"""Pytest fixtures for Orbit tests."""

import os
import tempfile
from datetime import date, datetime, time
from pathlib import Path

import pytest

# Set up test database before importing orbit modules
_test_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["ORBIT_TEST_DB"] = _test_db_file.name

# Now we can import orbit modules
from orbit import db
from orbit import config
from orbit.models import FixedBlock, Settings, Task


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    """Set up a fresh test database for each test."""
    # Override the database path
    test_db = tmp_path / "test_orbit.db"
    config.DB_PATH = test_db
    config.DATA_DIR = tmp_path

    # Remove any existing db file
    if test_db.exists():
        test_db.unlink()

    # Initialize the database
    db.init_db()

    yield

    # Cleanup
    if test_db.exists():
        test_db.unlink()


@pytest.fixture
def sample_settings():
    """Create sample settings with home location."""
    settings = Settings(
        home_name="Test Home",
        home_address="123 Test St, Austin, TX 78701",
        home_lat=30.2672,
        home_lon=-97.7431,
        default_timezone="America/Chicago",
        default_work_start="09:00",
        default_work_end="17:00",
    )
    db.save_settings(settings)
    return settings


@pytest.fixture
def sample_tasks(sample_settings):
    """Create sample tasks."""
    today = date.today()

    tasks = [
        Task(
            title="Errand 1 - Bank",
            category="errand",
            priority=3,
            duration_minutes=30,
            location_name="Bank",
            address="100 Bank St",
            lat=30.2700,
            lon=-97.7400,
            open_time_local="09:00",
            close_time_local="17:00",
            days_open="Mon,Tue,Wed,Thu,Fri",
        ),
        Task(
            title="Errand 2 - Post Office",
            category="errand",
            priority=2,
            duration_minutes=20,
            location_name="Post Office",
            address="200 Post St",
            lat=30.2750,
            lon=-97.7350,
            open_time_local="08:00",
            close_time_local="17:00",
            days_open="Mon,Tue,Wed,Thu,Fri,Sat",
        ),
        Task(
            title="Errand 3 - Grocery",
            category="shopping",
            priority=2,
            duration_minutes=45,
            location_name="Grocery Store",
            address="300 Grocery Ave",
            lat=30.2600,
            lon=-97.7500,
            open_time_local="07:00",
            close_time_local="22:00",
            days_open="Mon,Tue,Wed,Thu,Fri,Sat,Sun",
        ),
        Task(
            title="Home Task - Deep Work",
            category="deep_work",
            priority=3,
            duration_minutes=60,
        ),
    ]

    for task in tasks:
        db.save_task(task)

    return tasks


@pytest.fixture
def sample_fixed_block():
    """Create a sample fixed block."""
    today = date.today()
    block = FixedBlock(
        date=today,
        start_dt=datetime.combine(today, time(12, 0)),
        end_dt=datetime.combine(today, time(13, 0)),
        title="Lunch Meeting",
    )
    db.save_fixed_block(block)
    return block
