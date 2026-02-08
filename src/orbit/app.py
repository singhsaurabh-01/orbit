"""Orbit v0 - Plan my errands for a day with minimal input."""

import streamlit as st
import folium
from streamlit_folium import st_folium
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode
from uuid import uuid4

from orbit import db
from orbit.models import Task, Settings
from orbit.services import planner, packing, places, routing
from orbit.services.optimizer import optimize_route, reorder_items, OptimizedRoute
from orbit.services.resolver import (
    resolve_place,
    select_candidate,
    ResolvedPlace,
    ResolutionDecision,
    ScoredCandidate,
    SelectionReason,
)
from orbit.services.prep import get_prep_notes, format_prep_notes, PrepNote


# === UNIT CONVERSION ===

def km_to_miles(km: float) -> float:
    """Convert kilometers to miles."""
    return km * 0.621371


# === GOOGLE MAPS URL BUILDER ===

def build_google_maps_url(
    origin_lat: float,
    origin_lon: float,
    waypoints: list[tuple[float, float]],
    destination_lat: float | None = None,
    destination_lon: float | None = None,
    return_home: bool = True,
) -> str | None:
    """
    Build a Google Maps directions URL.

    Args:
        origin_lat: Starting point latitude (home)
        origin_lon: Starting point longitude (home)
        waypoints: List of (lat, lon) tuples for intermediate stops
        destination_lat: End point latitude (None = use last waypoint or home)
        destination_lon: End point longitude (None = use last waypoint or home)
        return_home: If True and no destination specified, return to origin

    Returns:
        Google Maps URL string, or None if insufficient waypoints
    """
    # Filter valid waypoints
    valid_waypoints = [(lat, lon) for lat, lon in waypoints if lat and lon]

    # Need at least 1 stop to create a route
    if not valid_waypoints:
        return None

    # Build URL parameters
    params = {
        "api": "1",
        "origin": f"{origin_lat},{origin_lon}",
        "travelmode": "driving",
    }

    # Determine destination
    if destination_lat is not None and destination_lon is not None:
        params["destination"] = f"{destination_lat},{destination_lon}"
    elif return_home:
        params["destination"] = f"{origin_lat},{origin_lon}"
    else:
        # Last waypoint is destination
        last = valid_waypoints[-1]
        params["destination"] = f"{last[0]},{last[1]}"
        valid_waypoints = valid_waypoints[:-1]

    # Add waypoints (intermediate stops)
    if valid_waypoints:
        waypoint_strs = [f"{lat},{lon}" for lat, lon in valid_waypoints]
        params["waypoints"] = "|".join(waypoint_strs)

    # Build URL
    base_url = "https://www.google.com/maps/dir/"
    return base_url + "?" + urlencode(params)


def get_route_waypoints(result, settings) -> list[tuple[float, float]]:
    """
    Extract ordered waypoints from plan result.

    Returns list of (lat, lon) tuples for stops (excluding home).
    """
    waypoints = []
    for item in result.items:
        if item.type == "task" and item.lat and item.lon:
            waypoints.append((item.lat, item.lon))
    return waypoints


# === PAGE CONFIG ===

st.set_page_config(
    page_title="Orbit",
    page_icon="🌍",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Clean CSS - centered, high contrast, calm design
st.markdown("""
<style>
    /* Hide sidebar completely */
    [data-testid="stSidebar"] { display: none; }

    /* Clean centered layout */
    .block-container {
        max-width: 700px;
        padding: 2rem 1rem;
    }

    /* Header styling */
    h1 {
        text-align: center;
        margin-bottom: 0.5rem;
    }

    .tagline {
        text-align: center;
        color: #888;
        margin-bottom: 2rem;
        font-size: 1.1rem;
    }

    /* Section dividers */
    .section-header {
        font-size: 1.1rem;
        font-weight: 600;
        margin: 1.5rem 0 0.75rem 0;
        color: #222;
    }

    /* Stop cards - green accent, high contrast */
    .stop-card {
        background: #1a472a;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 0.75rem;
        border-left: 4px solid #4CAF50;
        color: #fff;
    }
    .stop-card strong {
        color: #fff;
        font-size: 1.05rem;
    }
    .stop-card .meta {
        color: #a5d6a7;
        font-size: 0.9rem;
        margin-top: 0.25rem;
    }

    /* Travel cards - orange accent, high contrast */
    .travel-card {
        background: #4a3728;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        margin-bottom: 0.75rem;
        border-left: 4px solid #FF9800;
        color: #fff;
        font-size: 0.9rem;
    }
    .travel-card .meta {
        color: #ffcc80;
        font-size: 0.85rem;
    }

    /* Summary card - blue accent */
    .summary-card {
        background: #1a365d;
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
        color: #fff;
        text-align: center;
    }
    .summary-card strong {
        color: #90caf9;
    }

    /* Warning card - red accent */
    .warning-card {
        background: #5d1a1a;
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
        border-left: 4px solid #f44336;
        color: #ffcdd2;
    }

    /* Resolved place indicator */
    .resolved-place {
        background: #1a3a1a;
        border-radius: 6px;
        padding: 0.5rem 0.75rem;
        margin-top: 0.25rem;
        font-size: 0.85rem;
        color: #a5d6a7;
        border-left: 3px solid #4CAF50;
    }

    /* Pending resolution indicator */
    .pending-place {
        background: #3a3a1a;
        border-radius: 6px;
        padding: 0.5rem 0.75rem;
        margin-top: 0.25rem;
        font-size: 0.85rem;
        color: #fff59d;
        border-left: 3px solid #FFC107;
    }

    /* No match indicator */
    .no-match-place {
        background: #3a1a1a;
        border-radius: 6px;
        padding: 0.5rem 0.75rem;
        margin-top: 0.25rem;
        font-size: 0.85rem;
        color: #ffcdd2;
        border-left: 3px solid #f44336;
    }

    /* Hide Streamlit branding */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }

    /* Fix input widths */
    .stTextInput > div > div > input {
        width: 100%;
    }

    /* Map container */
    .map-container {
        border-radius: 8px;
        overflow: hidden;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """Initialize session state for errands list."""
    if "errands" not in st.session_state:
        # Each errand: {id, name, address, synced_address, resolved_name}
        st.session_state.errands = [{
            "id": str(uuid4()),
            "name": "",
            "address": "",
            "synced_address": "",
            "resolved_name": "",
        }]
    if "resolved_places" not in st.session_state:
        st.session_state.resolved_places = {}  # errand_id -> ResolvedPlace
    if "plan_result" not in st.session_state:
        st.session_state.plan_result = None
    if "plan_error" not in st.session_state:
        st.session_state.plan_error = None
    if "places_resolved" not in st.session_state:
        st.session_state.places_resolved = False
    # Starting point management
    if "starting_point_override" not in st.session_state:
        st.session_state.starting_point_override = None  # (lat, lon, address) or None
    if "editing_home" not in st.session_state:
        st.session_state.editing_home = False
    if "optimization_result" not in st.session_state:
        st.session_state.optimization_result = None  # OptimizedRoute
    # Home address setup
    if "home_geocode_options" not in st.session_state:
        st.session_state.home_geocode_options = []  # List of GeocodedAddress
    if "home_precision" not in st.session_state:
        st.session_state.home_precision = "exact"  # "exact", "street", "city", "region"
    if "home_address_typed" not in st.session_state:
        st.session_state.home_address_typed = ""  # Address as user typed it
    if "errand_prep_notes" not in st.session_state:
        st.session_state.errand_prep_notes = {}  # name -> PrepNote


def add_errand():
    """Add a new errand to the list."""
    st.session_state.errands.append({
        "id": str(uuid4()),
        "name": "",
        "address": "",
        "synced_address": "",
        "resolved_name": "",
    })
    st.session_state.places_resolved = False


def remove_errand(errand_id: str):
    """Remove an errand from the list."""
    st.session_state.errands = [e for e in st.session_state.errands if e["id"] != errand_id]
    if errand_id in st.session_state.resolved_places:
        del st.session_state.resolved_places[errand_id]
    if not st.session_state.errands:
        add_errand()
    st.session_state.places_resolved = False


def clear_resolution():
    """Clear resolved places when errands change."""
    st.session_state.places_resolved = False
    st.session_state.plan_result = None
    st.session_state.optimization_result = None


def clear_errand_resolution(errand_id: str):
    """Clear resolution for a specific errand."""
    if errand_id in st.session_state.resolved_places:
        del st.session_state.resolved_places[errand_id]
    # Clear synced data for this errand
    for errand in st.session_state.errands:
        if errand["id"] == errand_id:
            errand["synced_address"] = ""
            errand["resolved_name"] = ""
            break
    st.session_state.places_resolved = False
    st.session_state.plan_result = None
    st.session_state.optimization_result = None


def get_effective_starting_point(settings: Settings) -> tuple[float, float, str]:
    """
    Get the effective starting point (override or home).

    Returns:
        (lat, lon, address) tuple
    """
    if st.session_state.starting_point_override:
        return st.session_state.starting_point_override
    return (settings.home_lat, settings.home_lon, settings.home_address)


def clear_starting_point_override():
    """Clear the starting point override."""
    st.session_state.starting_point_override = None
    st.session_state.plan_result = None
    st.session_state.optimization_result = None


def resolve_all_places(settings: Settings):
    """Resolve all errands to places using effective starting point."""
    # Get effective starting point for distance calculations
    start_lat, start_lon, _ = get_effective_starting_point(settings)

    for idx, errand in enumerate(st.session_state.errands):
        errand_id = errand["id"]
        name = errand.get("name", "").strip()
        address = errand.get("address", "").strip()

        if not name:
            continue

        # If address provided, use it directly
        if address:
            result = places.geocode_address(address)
            if result:
                # Create a resolved place from the geocoded address
                from orbit.services.resolver import ScoredCandidate, ResolvedPlace, ResolutionDecision
                distance = km_to_miles(routing.haversine_distance(
                    start_lat, start_lon,
                    result.lat, result.lon
                ))
                candidate = ScoredCandidate(
                    place=result,
                    distance_miles=round(distance, 1),
                    name_similarity=100.0,
                    combined_score=100.0,
                )
                resolved = ResolvedPlace(
                    query=name,
                    selected=candidate,
                    candidates=[candidate],
                    decision=ResolutionDecision.AUTO_BEST,
                    decision_reason=f"{distance:.1f} mi from start (address provided)",
                )
                st.session_state.resolved_places[errand_id] = resolved
                # Sync address immediately when resolved
                _sync_errand_address_immediate(idx, resolved)
            else:
                # Address geocoding failed
                resolved = ResolvedPlace(
                    query=name,
                    selected=None,
                    candidates=[],
                    decision=ResolutionDecision.NO_MATCH,
                    decision_reason=f"Could not find address: {address}",
                )
                st.session_state.resolved_places[errand_id] = resolved
        else:
            # Resolve by place name using effective starting point
            # Create temporary settings with starting point as "home" for resolver
            temp_settings = Settings(
                home_lat=start_lat,
                home_lon=start_lon,
                home_address=settings.home_address,
                home_name=settings.home_name,
            )
            resolved = resolve_place(name, temp_settings)
            st.session_state.resolved_places[errand_id] = resolved
            # Sync address immediately if auto-resolved
            if resolved.is_resolved:
                _sync_errand_address_immediate(idx, resolved)

    st.session_state.places_resolved = True


def _sync_errand_address_immediate(errand_idx: int, resolved: ResolvedPlace):
    """Immediately sync resolved address to errand (called during resolution)."""
    if resolved.is_resolved and resolved.selected:
        st.session_state.errands[errand_idx]["synced_address"] = resolved.selected.full_address
        st.session_state.errands[errand_idx]["resolved_name"] = resolved.selected.display_name


def get_resolution_status():
    """Get counts of resolution statuses."""
    resolved_count = 0
    pending_count = 0
    failed_count = 0

    for errand in st.session_state.errands:
        errand_id = errand["id"]
        name = errand.get("name", "").strip()
        if not name:
            continue

        if errand_id in st.session_state.resolved_places:
            rp = st.session_state.resolved_places[errand_id]
            if rp.is_resolved:
                resolved_count += 1
            elif rp.needs_disambiguation:
                pending_count += 1
            else:
                failed_count += 1

    return resolved_count, pending_count, failed_count


def all_errands_resolved() -> bool:
    """Check if all errands are resolved."""
    for errand in st.session_state.errands:
        errand_id = errand["id"]
        name = errand.get("name", "").strip()
        if not name:
            continue

        if errand_id not in st.session_state.resolved_places:
            return False
        rp = st.session_state.resolved_places[errand_id]
        if not rp.is_resolved:
            return False

    return True


def generate_plan(settings: Settings, leave_time: time, return_time: time):
    """Generate a plan from resolved places with route optimization."""
    today = date.today()

    # Get effective starting point
    start_lat, start_lon, start_address = get_effective_starting_point(settings)

    # Clear any previous tasks
    existing = db.get_tasks(status="todo")
    for t in existing:
        if t.title.startswith("[Orbit] "):
            db.delete_task(t.id)

    # Collect resolved errands with their coordinates
    resolved_errands = []  # List of (errand, rp) tuples
    failed_errands = []

    for errand in st.session_state.errands:
        errand_id = errand["id"]
        name = errand.get("name", "").strip()

        if not name:
            continue

        if errand_id not in st.session_state.resolved_places:
            failed_errands.append((name, "Not resolved"))
            continue

        rp = st.session_state.resolved_places[errand_id]

        if not rp.is_resolved or not rp.selected:
            failed_errands.append((name, rp.decision_reason))
            continue

        resolved_errands.append((errand, rp))

    if not resolved_errands:
        st.session_state.optimization_result = None
        return None, failed_errands, "No errands could be scheduled."

    # Extract stop coordinates for optimization
    stops = [(rp.selected.place.lat, rp.selected.place.lon) for _, rp in resolved_errands]

    # Run route optimization
    optimization = optimize_route(
        start_lat=start_lat,
        start_lon=start_lon,
        stops=stops,
        return_to_start=True,
    )
    st.session_state.optimization_result = optimization

    # Reorder errands according to optimized route
    optimized_errands = reorder_items(resolved_errands, optimization.stop_order)

    # Create tasks in optimized order (with priority to preserve order)
    created_tasks = []
    errand_prep_notes = {}  # Store prep notes for display

    for priority_idx, (errand, rp) in enumerate(optimized_errands):
        name = errand.get("name", "").strip()
        candidate = rp.selected

        task = Task(
            title=f"[Orbit] {name}",
            category="errand",
            priority=100 - priority_idx,  # Higher priority = earlier in sequence
            duration_minutes=30,
            location_name=candidate.display_name,
            address=candidate.place.address,
            lat=candidate.place.lat,
            lon=candidate.place.lon,
            purpose=None,
            open_time_local=None,
            close_time_local=None,
        )
        db.save_task(task)
        created_tasks.append(task)

    # Store prep notes in session state for results display
    st.session_state.errand_prep_notes = errand_prep_notes

    # Update settings with times and effective starting point
    settings.default_work_start = f"{leave_time.hour:02d}:{leave_time.minute:02d}"
    settings.default_work_end = f"{return_time.hour:02d}:{return_time.minute:02d}"

    # Temporarily set home to starting point for planner
    original_home = (settings.home_lat, settings.home_lon, settings.home_name, settings.home_address)
    if st.session_state.starting_point_override:
        settings.home_lat = start_lat
        settings.home_lon = start_lon
        settings.home_name = "Start"
        settings.home_address = start_address

    db.save_settings(settings)

    # Generate plan
    try:
        result = planner.generate_plan(today, settings, return_home=True)

        # Restore original home settings if overridden
        if st.session_state.starting_point_override:
            settings.home_lat, settings.home_lon, settings.home_name, settings.home_address = original_home
            db.save_settings(settings)

        return result, failed_errands, None
    except Exception as e:
        # Restore original home settings on error
        if st.session_state.starting_point_override:
            settings.home_lat, settings.home_lon, settings.home_name, settings.home_address = original_home
            db.save_settings(settings)
        return None, failed_errands, str(e)


def render_map(result, settings: Settings):
    """Render map with route markers and lines."""
    # Get effective starting point
    start_lat, start_lon, start_address = get_effective_starting_point(settings)
    is_override = st.session_state.starting_point_override is not None
    start_name = "Start" if is_override else "Home"

    waypoints = []

    # Add starting point
    waypoints.append({
        "lat": start_lat,
        "lon": start_lon,
        "name": start_name,
        "type": "home",
        "order": 0,
    })

    # Add scheduled stops in order
    stop_num = 1
    for item in result.items:
        if item.type == "task" and item.lat and item.lon:
            title = item.title.replace("[Orbit] ", "")
            waypoints.append({
                "lat": item.lat,
                "lon": item.lon,
                "name": title,
                "type": "stop",
                "order": stop_num,
            })
            stop_num += 1

    if len(waypoints) < 2:
        st.info("Not enough locations to show a route.")
        return

    # Calculate map center
    lats = [w["lat"] for w in waypoints]
    lons = [w["lon"] for w in waypoints]
    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)

    # Create map
    m = folium.Map(location=[center_lat, center_lon], zoom_start=12)

    # Add markers
    for wp in waypoints:
        if wp["type"] == "home":
            folium.Marker(
                [wp["lat"], wp["lon"]],
                popup=wp["name"],
                tooltip=f"{wp['name']} (Start/End)",
                icon=folium.Icon(color="green", icon="home", prefix="fa"),
            ).add_to(m)
        else:
            folium.Marker(
                [wp["lat"], wp["lon"]],
                popup=f"{wp['order']}. {wp['name']}",
                tooltip=f"{wp['order']}. {wp['name']}",
                icon=folium.DivIcon(
                    html=f'<div style="background:#1a472a;color:#fff;border-radius:50%;width:28px;height:28px;text-align:center;line-height:28px;font-weight:bold;border:2px solid #4CAF50;">{wp["order"]}</div>',
                    icon_size=(28, 28),
                    icon_anchor=(14, 14),
                ),
            ).add_to(m)

    # Draw route lines
    route_coords = [[wp["lat"], wp["lon"]] for wp in waypoints]
    route_coords.append([waypoints[0]["lat"], waypoints[0]["lon"]])

    folium.PolyLine(
        route_coords,
        weight=3,
        color="#FF9800",
        opacity=0.8,
        dash_array="5, 10",
    ).add_to(m)

    # Fit bounds
    sw = [min(lats), min(lons)]
    ne = [max(lats), max(lons)]
    m.fit_bounds([sw, ne], padding=[30, 30])

    st_folium(m, height=350, use_container_width=True)


def render_results(result, failed_errands: list, settings: Settings):
    """Render the plan results."""
    st.markdown('<div class="section-header">Your Plan</div>', unsafe_allow_html=True)

    # Get effective starting point for display
    start_lat, start_lon, _ = get_effective_starting_point(settings)

    # Summary
    task_count = len([i for i in result.items if i.type == "task"])
    total_miles = km_to_miles(result.total_travel_km)
    st.markdown(f"""
    <div class="summary-card">
        <strong>{task_count} stops</strong> &nbsp;|&nbsp;
        <strong>{total_miles:.1f} mi</strong> total travel &nbsp;|&nbsp;
        <strong>{int(result.total_travel_minutes)} min</strong> driving
    </div>
    """, unsafe_allow_html=True)

    # Show optimization info
    optimization = st.session_state.optimization_result
    if optimization and optimization.savings_km > 0:
        savings_miles = km_to_miles(optimization.savings_km)
        naive_miles = km_to_miles(optimization.naive_distance_km)
        st.caption(
            f"Route optimized for shortest travel distance. "
            f"Saved {savings_miles:.1f} mi vs naive order ({naive_miles:.1f} mi)."
        )
    elif optimization:
        st.caption("Route optimized for shortest total travel distance.")

    # Google Maps button - use effective starting point
    waypoints = get_route_waypoints(result, settings)
    maps_url = build_google_maps_url(
        origin_lat=start_lat,
        origin_lon=start_lon,
        waypoints=waypoints,
        return_home=True,
    )

    if maps_url and len(waypoints) >= 1:
        st.link_button(
            "🗺️ Open in Google Maps",
            maps_url,
            use_container_width=True,
            help="Open turn-by-turn navigation in Google Maps",
        )
        st.caption("Use Google Maps for turn-by-turn navigation.")
    else:
        st.button(
            "🗺️ Open in Google Maps",
            disabled=True,
            use_container_width=True,
            help="Need at least 1 stop with valid coordinates",
        )

    st.write("")

    # Timeline - build list for later prep notes linking
    task_titles = []

    for item in result.items:
        start_str = item.start.strftime("%H:%M")
        end_str = item.end.strftime("%H:%M")
        duration = int((item.end - item.start).total_seconds() / 60)

        if item.type == "task":
            title = item.title.replace("[Orbit] ", "")
            task_titles.append(title)

            st.markdown(f"""
            <div class="stop-card">
                <strong>{title}</strong>
                <div class="meta">{start_str} – {end_str} ({duration} min)</div>
            </div>
            """, unsafe_allow_html=True)

        elif item.type == "travel":
            from_place = (item.from_place or "Previous").replace("[Orbit] ", "")
            to_place = (item.to_place or "Next").replace("[Orbit] ", "")
            miles = km_to_miles(item.distance_km) if item.distance_km else 0
            st.markdown(f"""
            <div class="travel-card">
                🚗 {from_place} → {to_place}
                <div class="meta">{miles:.1f} mi, {item.travel_minutes} min</div>
            </div>
            """, unsafe_allow_html=True)

    # Map section
    st.markdown('<div class="section-header">Route Map</div>', unsafe_allow_html=True)
    render_map(result, settings)

    # Could not schedule
    if result.overflow or failed_errands:
        st.markdown('<div class="section-header">Could Not Schedule</div>', unsafe_allow_html=True)
        not_scheduled = []

        for item in result.overflow:
            title = item.task.title.replace("[Orbit] ", "")
            not_scheduled.append(f"<strong>{title}</strong>: {item.reason}")

        for name, reason in failed_errands:
            not_scheduled.append(f"<strong>{name}</strong>: {reason}")

        if not_scheduled:
            st.markdown(f"""
            <div class="warning-card">
                {"<br>".join(not_scheduled)}
            </div>
            """, unsafe_allow_html=True)

    # Prep Notes section (what to bring)
    st.markdown('<div class="section-header">What to Bring</div>', unsafe_allow_html=True)

    prep_notes = st.session_state.get("errand_prep_notes", {})

    if prep_notes:
        # Consolidated checklist from all prep notes
        all_documents = []
        all_items = []
        seen = set()

        for title in task_titles:
            if title in prep_notes:
                prep = prep_notes[title]
                for doc in prep.documents:
                    if doc not in seen:
                        all_documents.append(doc)
                        seen.add(doc)
                for item in prep.items:
                    if item not in seen:
                        all_items.append(item)
                        seen.add(item)

        if all_documents:
            st.markdown("**Documents:**")
            for doc in all_documents:
                st.checkbox(doc, key=f"doc_{hash(doc)}")

        if all_items:
            st.markdown("**Items:**")
            for item in all_items:
                st.checkbox(item, key=f"item_{hash(item)}")

        # Per-stop details with tips
        with st.expander("Per-stop details & tips"):
            for title in task_titles:
                if title in prep_notes:
                    prep = prep_notes[title]
                    st.markdown(f"**{title}**")

                    if prep.documents:
                        for doc in prep.documents:
                            st.write(f"  📄 {doc}")
                    if prep.items:
                        for item in prep.items:
                            st.write(f"  📦 {item}")
                    if prep.tips:
                        for tip in prep.tips:
                            st.write(f"  💡 {tip}")
                    if prep.crowdedness_hint:
                        st.write(f"  ⏰ {prep.crowdedness_hint}")
                    st.write("")
                else:
                    st.markdown(f"**{title}**")
                    st.write("  No specific preparation needed.")
                    st.write("")
    else:
        # Fall back to old packing service if no prep notes
        scheduled_tasks = [i.task for i in result.items if i.task]
        consolidated = packing.get_consolidated_checklist(scheduled_tasks)

        if consolidated:
            for item in consolidated:
                st.checkbox(item, key=f"carry_{hash(item)}")
        else:
            st.write("No special items needed.")


def render_home_setup(settings: Settings):
    """Render home setup prompt with multiple options if ambiguous."""
    st.warning("Please set your home address to get started.")

    address = st.text_input(
        "Home Address",
        placeholder="Enter your home address...",
        value=st.session_state.home_address_typed,
    )

    # If we have geocode options, show them for selection
    if st.session_state.home_geocode_options:
        st.markdown("**Select the correct address:**")
        options = st.session_state.home_geocode_options[:5]

        for i, opt in enumerate(options):
            precision_note = ""
            if opt.precision == "street":
                precision_note = " (street-level)"
            elif opt.precision == "city":
                precision_note = " (city-level)"
            elif opt.precision == "region":
                precision_note = " (region-level)"

            if st.button(f"{opt.address}{precision_note}", key=f"home_opt_{i}"):
                settings.home_name = "Home"
                settings.home_address = opt.address
                settings.home_lat = opt.lat
                settings.home_lon = opt.lon
                st.session_state.home_precision = opt.precision
                st.session_state.home_address_typed = address
                db.save_settings(settings)
                st.session_state.home_geocode_options = []
                st.success("Home location saved!")
                st.rerun()

        if st.button("Try different address"):
            st.session_state.home_geocode_options = []
            st.rerun()
    else:
        if st.button("Find Address"):
            if address:
                st.session_state.home_address_typed = address
                # Get multiple geocode options
                options = places.geocode_address_multi(address, limit=5)

                if not options:
                    st.error("Could not find that address. Please try a more specific address.")
                elif len(options) == 1:
                    # Single result - use it directly
                    opt = options[0]
                    settings.home_name = "Home"
                    settings.home_address = opt.address
                    settings.home_lat = opt.lat
                    settings.home_lon = opt.lon
                    st.session_state.home_precision = opt.precision
                    db.save_settings(settings)
                    if opt.is_approximate():
                        st.success(f"Home location saved (street-level)!")
                    else:
                        st.success("Home location saved!")
                    st.rerun()
                else:
                    # Multiple options - let user choose
                    st.session_state.home_geocode_options = options
                    st.rerun()
            else:
                st.error("Please enter an address.")


def sync_errand_address(errand_idx: int, errand_id: str):
    """Sync resolved address to errand when place is selected."""
    if errand_id in st.session_state.resolved_places:
        rp = st.session_state.resolved_places[errand_id]
        if rp.is_resolved and rp.selected:
            # Update errand with resolved info
            st.session_state.errands[errand_idx]["synced_address"] = rp.selected.full_address
            st.session_state.errands[errand_idx]["resolved_name"] = rp.selected.display_name


def render_errand_resolution(errand: dict, errand_idx: int, settings: Settings):
    """Render resolution status and disambiguation UI for an errand."""
    errand_id = errand["id"]
    name = errand.get("name", "").strip()

    if not name:
        return

    if errand_id not in st.session_state.resolved_places:
        return

    rp = st.session_state.resolved_places[errand_id]

    if rp.decision == ResolutionDecision.AUTO_BEST and rp.selected:
        # Sync address
        sync_errand_address(errand_idx, errand_id)

        # Get selection reason
        reason_text = rp.selected.get_reason_text() if rp.selected.selection_reason else "Auto-selected"

        # Show resolved info with reason
        st.markdown(f"""
        <div class="resolved-place">
            ✓ <strong>{rp.selected.display_name}</strong><br>
            <span style="font-size:0.85em;">{rp.selected.full_address}</span><br>
            <span style="font-size:0.8em; color:#81c784;">📍 {rp.selected.distance_miles} mi • {reason_text}</span>
        </div>
        """, unsafe_allow_html=True)

    elif rp.decision == ResolutionDecision.USER_SELECTED and rp.selected:
        # Sync address
        sync_errand_address(errand_idx, errand_id)

        # User selected
        st.markdown(f"""
        <div class="resolved-place">
            ✓ <strong>{rp.selected.display_name}</strong><br>
            <span style="font-size:0.85em;">{rp.selected.full_address}</span><br>
            <span style="font-size:0.8em; color:#81c784;">📍 {rp.selected.distance_miles} mi • User selected</span>
        </div>
        """, unsafe_allow_html=True)

    elif rp.decision == ResolutionDecision.PENDING:
        # Needs disambiguation
        st.markdown(f"""
        <div class="pending-place">
            ⚠ Multiple matches found — please select one
        </div>
        """, unsafe_allow_html=True)

        # Show detailed candidate list
        candidates = rp.candidates[:5]
        for i, c in enumerate(candidates):
            with st.container():
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.markdown(f"""
                    **{i+1}. {c.display_name}**
                    {c.full_address}
                    📍 {c.distance_miles} mi from home
                    """)
                with col2:
                    if st.button("Select", key=f"sel_{errand_id}_{i}"):
                        updated = select_candidate(rp, i)
                        st.session_state.resolved_places[errand_id] = updated
                        sync_errand_address(errand_idx, errand_id)
                        st.rerun()

    elif rp.decision == ResolutionDecision.NO_MATCH:
        # No match found
        st.markdown(f"""
        <div class="no-match-place">
            ✗ {rp.decision_reason}
        </div>
        """, unsafe_allow_html=True)


def main():
    """Main app entry point."""
    # Initialize
    db.init_db()
    init_session_state()
    settings = db.get_settings()

    # Header
    st.title("🌍 Orbit")
    st.markdown('<p class="tagline">Plan your errands with minimal input</p>', unsafe_allow_html=True)

    # Check home location
    if not settings.has_home_location:
        render_home_setup(settings)
        return

    # === STARTING POINT MANAGEMENT ===

    # Check if editing home
    if st.session_state.editing_home:
        st.markdown("**Edit Home Address**")
        new_home_address = st.text_input(
            "New home address",
            value=settings.home_address or "",
            placeholder="Enter your home address...",
            label_visibility="collapsed",
        )
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Save Home", use_container_width=True):
                if new_home_address:
                    result = places.geocode_address(new_home_address)
                    if result:
                        settings.home_name = "Home"
                        settings.home_address = result.address
                        settings.home_lat = result.lat
                        settings.home_lon = result.lon
                        db.save_settings(settings)
                        st.session_state.editing_home = False
                        clear_resolution()
                        st.success("Home location updated!")
                        st.rerun()
                    else:
                        st.error("Could not find that address.")
                else:
                    st.error("Please enter an address.")
        with col2:
            if st.button("Cancel", use_container_width=True):
                st.session_state.editing_home = False
                st.rerun()
        st.divider()
    else:
        # Show starting point with options
        start_lat, start_lon, start_address = get_effective_starting_point(settings)
        is_override = st.session_state.starting_point_override is not None

        # Display current starting point
        start_display = start_address[:50] + "..." if len(start_address or "") > 50 else start_address

        # Check if home is approximate
        home_precision = st.session_state.home_precision
        is_approximate = home_precision in ("street", "city", "region")

        if is_override:
            st.caption(f"📍 Starting from: {start_display} (custom)")
        elif is_approximate:
            st.caption(f"📍 Starting from: {start_display} (Home, approximate - {home_precision}-level)")
        else:
            st.caption(f"📍 Starting from: {start_display} (Home)")

        # Starting point options in expander
        with st.expander("Change starting point"):
            st.caption("Default is your saved Home address.")

            # Override starting point
            override_address = st.text_input(
                "Start from different location",
                placeholder="Enter address to start from...",
                key="override_address_input",
                label_visibility="collapsed",
            )

            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("Set Start", use_container_width=True):
                    if override_address:
                        result = places.geocode_address(override_address)
                        if result:
                            st.session_state.starting_point_override = (
                                result.lat, result.lon, result.address
                            )
                            clear_resolution()
                            st.success("Starting point updated!")
                            st.rerun()
                        else:
                            st.error("Could not find that address.")
                    else:
                        st.warning("Enter an address to set as starting point.")
            with col2:
                if is_override:
                    if st.button("Use Home", use_container_width=True):
                        clear_starting_point_override()
                        st.rerun()
            with col3:
                if st.button("Edit Home", use_container_width=True):
                    st.session_state.editing_home = True
                    st.rerun()

        st.divider()

    # === INPUTS SECTION ===

    # Time inputs
    col1, col2 = st.columns(2)
    with col1:
        leave_time = st.time_input("Leave", value=time(9, 0))
    with col2:
        return_time = st.time_input("Return by", value=time(17, 0))

    st.write("")

    # Errands list
    st.markdown("**Errands**")

    for i, errand in enumerate(st.session_state.errands):
        errand_id = errand["id"]

        # Check if this errand has a synced address from resolution
        synced_addr = errand.get("synced_address", "")
        resolved_name = errand.get("resolved_name", "")
        has_sync = bool(synced_addr and st.session_state.places_resolved)

        # Main row: Place name, Address, Delete button
        col1, col2, col3 = st.columns([3, 4, 1])

        with col1:
            name = st.text_input(
                "Place",
                value=errand["name"],
                key=f"name_{errand_id}",
                placeholder="e.g., Target, DMV",
                label_visibility="collapsed",
                on_change=lambda eid=errand_id: clear_errand_resolution(eid),
            )
            # If name changed, clear the synced values
            if name != errand["name"]:
                st.session_state.errands[i]["synced_address"] = ""
                st.session_state.errands[i]["resolved_name"] = ""
            st.session_state.errands[i]["name"] = name

            # Show "Resolved to" if canonical name differs
            if has_sync and resolved_name and resolved_name.lower() != name.lower():
                st.caption(f"→ Resolved to: {resolved_name}")

        with col2:
            # Show synced address if available, otherwise user input
            display_addr = synced_addr if has_sync else errand.get("address", "")
            address = st.text_input(
                "Address",
                value=display_addr,
                key=f"addr_{errand_id}",
                placeholder="Address (auto-filled)" if has_sync else "Address (optional)",
                label_visibility="collapsed",
                on_change=lambda eid=errand_id: clear_errand_resolution(eid),
                disabled=has_sync,  # Disable when synced
            )
            if not has_sync:
                st.session_state.errands[i]["address"] = address

        with col3:
            if len(st.session_state.errands) > 1:
                if st.button("✕", key=f"del_{errand_id}"):
                    remove_errand(errand_id)
                    st.rerun()

        # Show resolution status if places are resolved
        if st.session_state.places_resolved:
            render_errand_resolution(errand, i, settings)

    # Add errand button
    if st.button("+ Add errand"):
        add_errand()
        st.rerun()

    st.write("")

    # === RESOLVE / GENERATE BUTTONS ===

    has_errands = any(e["name"].strip() for e in st.session_state.errands)

    if not st.session_state.places_resolved:
        # Show "Find Places" button
        if st.button("Find Places", type="primary", use_container_width=True):
            if not has_errands:
                st.error("Please add at least one errand.")
            else:
                with st.spinner("Finding places near you..."):
                    resolve_all_places(settings)
                st.rerun()
    else:
        # Places resolved - show status and generate button
        resolved, pending, failed = get_resolution_status()

        if pending > 0:
            st.info(f"📍 {resolved} resolved, {pending} need selection, {failed} not found")
        elif failed > 0:
            st.warning(f"📍 {resolved} resolved, {failed} not found")
        else:
            st.success(f"📍 All {resolved} places found!")

        # Generate button (only if all resolved)
        if all_errands_resolved():
            if st.button("Generate Plan", type="primary", use_container_width=True):
                if return_time <= leave_time:
                    st.error("Return time must be after leave time.")
                else:
                    with st.spinner("Optimizing your route..."):
                        result, failed, error = generate_plan(settings, leave_time, return_time)

                        if error:
                            st.session_state.plan_error = error
                            st.session_state.plan_result = None
                        else:
                            st.session_state.plan_result = (result, failed)
                            st.session_state.plan_error = None

                    st.rerun()
        else:
            st.button("Generate Plan", type="primary", use_container_width=True, disabled=True)
            st.caption("Please resolve all places first")

        # Reset button
        if st.button("Reset Places"):
            st.session_state.places_resolved = False
            st.session_state.resolved_places = {}
            st.session_state.plan_result = None
            st.rerun()

    # === RESULTS SECTION ===

    if st.session_state.plan_error:
        st.error(f"Could not generate plan: {st.session_state.plan_error}")

    if st.session_state.plan_result:
        st.divider()
        result, failed = st.session_state.plan_result
        render_results(result, failed, settings)


if __name__ == "__main__":
    main()
