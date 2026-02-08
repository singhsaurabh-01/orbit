#!/usr/bin/env python3
"""Initialize the Orbit database."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from orbit import db
from orbit.config import DB_PATH


def main():
    """Initialize the database."""
    print(f"Initializing database at: {DB_PATH}")

    # Ensure data directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Initialize schema
    db.init_db()

    print("Database initialized successfully!")
    print("\nTables created:")
    print("  - settings")
    print("  - places")
    print("  - tasks")
    print("  - fixed_blocks")
    print("  - plans")
    print("  - plan_items")
    print("  - cache")


if __name__ == "__main__":
    main()
