#!/usr/bin/env python3
"""Seed the Orbit database with demo data."""

import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from orbit import db
from orbit.models import FixedBlock, Settings, Task


def main():
    """Seed demo data."""
    print("Seeding demo data...")

    # Initialize database first
    db.init_db()

    # Set up home location (Austin, TX downtown as example)
    settings = Settings(
        home_name="Home",
        home_address="100 Congress Ave, Austin, TX 78701",
        home_lat=30.2672,
        home_lon=-97.7431,
        default_timezone="America/Chicago",
        default_work_start="08:00",
        default_work_end="18:00",
    )
    db.save_settings(settings)
    print("  ✓ Home location set (Austin, TX)")

    # Create demo tasks
    today = date.today()
    tomorrow = today + timedelta(days=1)

    tasks = [
        Task(
            title="DMV License Renewal",
            category="errand",
            priority=4,
            duration_minutes=90,
            due_date=tomorrow,
            location_name="Texas DPS - Austin North",
            address="6121 N Lamar Blvd, Austin, TX 78752",
            lat=30.3363,
            lon=-97.7134,
            open_time_local="08:00",
            close_time_local="17:00",
            days_open="Mon,Tue,Wed,Thu,Fri",
            purpose="DMV license renewal",
            required_items="Current license\nProof of insurance\nPayment method",
        ),
        Task(
            title="Grocery Shopping",
            category="shopping",
            priority=2,
            duration_minutes=45,
            location_name="H-E-B Mueller",
            address="1801 E 51st St, Austin, TX 78723",
            lat=30.2992,
            lon=-97.7014,
            open_time_local="06:00",
            close_time_local="23:00",
            days_open="Mon,Tue,Wed,Thu,Fri,Sat,Sun",
            purpose="grocery",
            required_items="Shopping list\nReusable bags",
        ),
        Task(
            title="Car Service Appointment",
            category="errand",
            priority=3,
            duration_minutes=120,
            due_date=today,
            location_name="Austin Auto Service",
            address="5555 N Lamar Blvd, Austin, TX 78751",
            lat=30.3233,
            lon=-97.7234,
            open_time_local="07:30",
            close_time_local="18:00",
            days_open="Mon,Tue,Wed,Thu,Fri,Sat",
            purpose="car service oil change",
            required_items="Car keys\nService coupon",
        ),
        Task(
            title="Post Office - Mail Package",
            category="errand",
            priority=2,
            duration_minutes=20,
            location_name="USPS Downtown Austin",
            address="510 Guadalupe St, Austin, TX 78701",
            lat=30.2691,
            lon=-97.7442,
            open_time_local="08:30",
            close_time_local="17:00",
            days_open="Mon,Tue,Wed,Thu,Fri",
            purpose="post office",
            required_items="Package to mail\nRecipient address",
        ),
        Task(
            title="Bank - Deposit Check",
            category="financial",
            priority=3,
            duration_minutes=15,
            due_date=today,
            location_name="Chase Bank Downtown",
            address="221 W 6th St, Austin, TX 78701",
            lat=30.2677,
            lon=-97.7453,
            open_time_local="09:00",
            close_time_local="17:00",
            days_open="Mon,Tue,Wed,Thu,Fri",
            purpose="bank deposit",
            required_items="Check to deposit\nID\nAccount number",
        ),
        Task(
            title="Pharmacy - Pick Up Prescription",
            category="health",
            priority=4,
            duration_minutes=15,
            location_name="CVS Pharmacy",
            address="1701 Lavaca St, Austin, TX 78701",
            lat=30.2752,
            lon=-97.7465,
            open_time_local="08:00",
            close_time_local="21:00",
            days_open="Mon,Tue,Wed,Thu,Fri,Sat,Sun",
            purpose="pharmacy prescription",
            required_items="Prescription number\nID\nInsurance card",
        ),
        Task(
            title="Deep Work - Project Planning",
            category="deep_work",
            priority=3,
            duration_minutes=120,
            notes="Review Q1 project roadmap and update timeline",
        ),
        Task(
            title="Call Mom",
            category="personal",
            priority=2,
            duration_minutes=30,
            notes="Weekly check-in call",
        ),
    ]

    for task in tasks:
        db.save_task(task)
    print(f"  ✓ Created {len(tasks)} demo tasks")

    # Create a fixed block (meeting)
    meeting_date = today
    meeting = FixedBlock(
        date=meeting_date,
        start_dt=datetime.combine(meeting_date, time(10, 0)),
        end_dt=datetime.combine(meeting_date, time(11, 0)),
        title="Team Standup",
        notes="Daily team sync meeting",
    )
    db.save_fixed_block(meeting)
    print("  ✓ Created 1 fixed block (meeting)")

    print("\nDemo data seeded successfully!")
    print("\nYou can now run the app with:")
    print("  uv run streamlit run src/orbit/app.py")


if __name__ == "__main__":
    main()
