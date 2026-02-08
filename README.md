# Orbit

**Tasks, time, and routes — perfectly aligned.**

Orbit is a local-first personal day planner. Enter your errands, and Orbit generates an optimized route that minimizes driving while getting everything done.

## Features

- **Simple Input**: Just enter place names and times
- **Smart Place Search**: Finds places near your home automatically
- **Route Optimization**: Minimizes total travel distance using TSP solver
- **Visual Map**: See your route with numbered stops
- **Business Hours**: Optionally set open/close times for time-window scheduling
- **Prep Notes**: Get suggestions for what documents and items to bring based on your purpose (e.g., "license renewal" → bring ID, proof of residency)
- **Google Maps Integration**: One-click navigation to follow your route

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

```bash
cd orbit
uv sync
```

### Run the App

```bash
uv run streamlit run src/orbit/app.py
```

Open **http://localhost:8501** in your browser.

## How to Use

1. **Set your home address** (first time only)
2. **Enter leave/return times**
3. **Add errands** - just type place names (e.g., "Target", "Post Office")
4. **(Optional) Add details** - expand "Details" to add:
   - **Purpose**: What you're doing (e.g., "license renewal", "pickup order")
   - **Hours**: Business hours (e.g., opens 9:00, closes 17:00)
5. **Click "Find Places"** - Orbit resolves place names to actual locations
6. **Click "Generate Plan"**
7. **View your optimized route** with times, distances, map, and prep notes

## Example

```
Leave home: 9:00 AM
Return by: 5:00 PM

Errands:
- DMV (purpose: license renewal, hours: 8:30-16:30)
- Post Office (purpose: mail package)
- Target (purpose: return item)

→ Find Places → Generate Plan

Result:
- 3 stops | 12.4 mi total | 25 min driving
- Map with numbered route
- Prep Notes:
  - DMV: Photo ID, Proof of residency, Cash/card for fees
  - Post Office: Package securely packed, Address
  - Target: Receipt, Item to return
```

## Project Structure

```
orbit/
├── src/orbit/
│   ├── app.py           # Main single-page app
│   ├── config.py        # Configuration
│   ├── db.py            # SQLite database
│   ├── models.py        # Data models
│   └── services/
│       ├── planner.py   # Schedule generation with time windows
│       ├── optimizer.py # TSP route optimization (brute-force/2-opt)
│       ├── resolver.py  # Fuzzy place resolution
│       ├── routing.py   # Distance calculations (OSRM/fallback)
│       ├── places.py    # Geocoding (OpenStreetMap Nominatim)
│       ├── packing.py   # Category-based checklist suggestions
│       └── prep.py      # Purpose-based prep notes (what to bring)
├── tests/
└── pyproject.toml
```

## Running Tests

```bash
uv sync --extra dev
uv run pytest
```

## Services Used

- **Geocoding**: OpenStreetMap Nominatim (free, cached)
- **Routing**: OSRM public server (free, with fallback)
- **Maps**: Folium / OpenStreetMap

## Limitations (v0)

- Single-day planning only
- Driving routes only (no transit/walking)
- No calendar export yet
- No saved errand lists
- Business hours must be entered manually (no automatic lookup)
- Prep notes are rule-based, not AI-generated

## Roadmap (v1+)

- ICS calendar export
- Custom duration per errand
- Auto-fetch business hours from Google Places / OpenStreetMap
- AI-enhanced prep notes
- Save/load errand lists
- Multi-day planning

## License

MIT
