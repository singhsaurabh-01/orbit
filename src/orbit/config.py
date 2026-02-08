"""Configuration settings for Orbit."""

import os
from pathlib import Path

# Try to load .env file if it exists (for local development)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not available (e.g., on Streamlit Cloud) - that's OK
    # Streamlit Cloud uses secrets.toml instead
    pass

# Base paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "orbit.db"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Nominatim settings
NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"
NOMINATIM_USER_AGENT = "Orbit/0.1.0 (personal day planner)"
NOMINATIM_RATE_LIMIT_SECONDS = 1.0

# OSRM settings
OSRM_BASE_URL = "https://router.project-osrm.org"
OSRM_TIMEOUT_SECONDS = 10

# Cache settings
CACHE_TTL_DAYS = 7

# Default settings
DEFAULT_TIMEZONE = "America/Chicago"
DEFAULT_WORK_START = "09:00"
DEFAULT_WORK_END = "18:00"
DEFAULT_SEARCH_RADIUS_KM = 10
DEFAULT_CITY_SPEED_KMH = 40  # ~25 mph for fallback travel time estimation

# Packing rules - mapping keywords to suggested items
PACKING_RULES = {
    # DMV/License related
    "dmv": ["Driver's license/ID", "Proof of address", "Payment method", "Appointment confirmation"],
    "license": ["Driver's license/ID", "Proof of address", "Payment method", "Appointment confirmation"],
    "registration": ["Driver's license/ID", "Vehicle registration", "Insurance card", "Payment method"],

    # Banking/Financial
    "bank": ["ID", "Documents to sign", "Payment method", "Account information"],
    "notary": ["ID", "Documents to sign", "Payment method"],
    "tax": ["ID", "Tax documents", "W-2/1099 forms", "Payment method"],

    # Vehicle
    "car service": ["Car keys", "Insurance card", "Service appointment details"],
    "service center": ["Car keys", "Insurance card", "Service appointment details"],
    "mechanic": ["Car keys", "Insurance card", "Service appointment details"],
    "oil change": ["Car keys", "Service coupon"],
    "inspection": ["Car keys", "Insurance card", "Vehicle registration"],

    # Medical
    "doctor": ["ID", "Insurance card", "List of medications", "Appointment confirmation"],
    "hospital": ["ID", "Insurance card", "List of medications", "Emergency contact info"],
    "pharmacy": ["ID", "Insurance card", "Prescription"],
    "dentist": ["ID", "Insurance card", "Appointment confirmation"],

    # School/Education
    "school": ["Forms", "ID", "Payment method"],
    "university": ["Student ID", "Forms", "Laptop"],

    # Government
    "passport": ["Current passport", "ID", "Passport photos", "Payment method", "Supporting documents"],
    "court": ["ID", "Court summons", "Documents"],
    "post office": ["ID", "Package/mail", "Tracking number"],

    # Shopping
    "grocery": ["Reusable bags", "Shopping list"],
    "returns": ["Receipt", "Item to return", "ID"],

    # Default essentials (always suggested)
    "_default": ["Phone", "Wallet"],
}

# Task categories
TASK_CATEGORIES = [
    "errand",
    "appointment",
    "deep_work",
    "personal",
    "health",
    "financial",
    "shopping",
    "other",
]

# Priority levels
PRIORITY_LEVELS = {
    1: "Low",
    2: "Medium",
    3: "High",
    4: "Urgent",
}

# Task statuses
TASK_STATUSES = ["todo", "in_progress", "done"]

# API Keys - Lazy loading function (called at runtime, not import time)
_api_keys_cache = {}

def get_api_key(key_name: str) -> str:
    """
    Get API key from Streamlit secrets (Cloud) or environment (local).
    Uses caching to avoid repeated lookups.
    """
    if key_name in _api_keys_cache:
        return _api_keys_cache[key_name]

    value = ""
    try:
        # Try Streamlit secrets first (Streamlit Cloud)
        import streamlit as st
        value = st.secrets.get(key_name, "")
        if value:
            print(f"[Config] Loaded {key_name} from st.secrets")
    except Exception:
        # Fall back to environment variables (local development)
        value = os.getenv(key_name, "")
        if value:
            print(f"[Config] Loaded {key_name} from environment")

    _api_keys_cache[key_name] = value
    return value

# Expose as module-level variables for backwards compatibility
# These will be empty at import time, use get_api_key() for runtime access
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# Place resolution settings
ENABLE_LLM_RESOLUTION = bool(GEMINI_API_KEY)  # Enable if API key is set
ENABLE_GOOGLE_PLACES = bool(GOOGLE_PLACES_API_KEY)  # Enable if API key is set
ENABLE_TAVILY_FALLBACK = bool(TAVILY_API_KEY)  # Enable if API key is set
OSM_SEARCH_RADIUS_MILES = 10  # Initial search radius
OSM_EXPANDED_RADIUS_MILES = 25  # Expanded radius if no results
