"""Test script to verify deployment works correctly."""

import sys
import os

print("="*70)
print("DEPLOYMENT TEST")
print("="*70)

# Test 1: Check Python version
print(f"\n1. Python version: {sys.version}")

# Test 2: Check environment variables
print(f"\n2. Environment variables:")
print(f"   GOOGLE_PLACES_API_KEY: {'✅ Set' if os.getenv('GOOGLE_PLACES_API_KEY') else '❌ Not set'}")

# Test 3: Check imports
print(f"\n3. Checking imports...")
errors = []

try:
    import streamlit
    print(f"   ✅ streamlit: {streamlit.__version__}")
except ImportError as e:
    errors.append(f"streamlit: {e}")
    print(f"   ❌ streamlit")

try:
    import googlemaps
    print(f"   ✅ googlemaps")
except ImportError as e:
    errors.append(f"googlemaps: {e}")
    print(f"   ❌ googlemaps")

try:
    from orbit.config import GOOGLE_PLACES_API_KEY
    print(f"   ✅ orbit.config")
    print(f"   API Key loaded: {'✅ Yes' if GOOGLE_PLACES_API_KEY else '❌ No'}")
except ImportError as e:
    errors.append(f"orbit.config: {e}")
    print(f"   ❌ orbit.config")

try:
    from orbit.services.simple_resolver import resolve_place
    print(f"   ✅ simple_resolver")
except ImportError as e:
    errors.append(f"simple_resolver: {e}")
    print(f"   ❌ simple_resolver: {e}")

# Test 4: Try a simple resolution
print(f"\n4. Testing place resolution...")
try:
    from orbit import db
    from orbit.services.simple_resolver import resolve_place

    settings = db.get_settings()
    if settings.has_home_location:
        result = resolve_place("Target", settings)
        if result.is_resolved:
            print(f"   ✅ Resolution works!")
            print(f"      Found: {result.selected.display_name}")
        else:
            print(f"   ⚠️  Resolution returned no match: {result.decision_reason}")
    else:
        print(f"   ⚠️  No home location set (expected for first run)")
except Exception as e:
    errors.append(f"resolution: {e}")
    print(f"   ❌ Resolution error: {e}")
    import traceback
    traceback.print_exc()

# Summary
print(f"\n" + "="*70)
if errors:
    print(f"❌ DEPLOYMENT TEST FAILED")
    print(f"\nErrors found:")
    for error in errors:
        print(f"  - {error}")
else:
    print(f"✅ DEPLOYMENT TEST PASSED")
print("="*70)
