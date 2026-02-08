"""Gemini-enhanced place resolution service."""

import json
from typing import Optional
from google import genai
from google.genai import types

from orbit.config import GEMINI_API_KEY, ENABLE_LLM_RESOLUTION
from orbit.models import PlaceSearchResult


# Configure Gemini API
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None


def validate_and_rank_candidates(
    query: str,
    candidates: list[PlaceSearchResult],
    user_city: str,
    user_state: str,
    max_distance_miles: float = 25.0,
) -> Optional[dict]:
    """
    Use Gemini to validate and rank place candidates.

    Args:
        query: User's search query (e.g., "Target", "CVS")
        candidates: List of PlaceSearchResult from OSM
        user_city: User's city
        user_state: User's state
        max_distance_miles: Maximum reasonable distance

    Returns:
        Dict with 'best_index' (int or None) and 'reasoning' (str)
        Returns None if LLM is not available
    """
    if not ENABLE_LLM_RESOLUTION or not client:
        return None

    if not candidates:
        return {"best_index": None, "reasoning": "No candidates provided"}

    # Prepare candidates summary for LLM
    candidates_text = []
    for i, c in enumerate(candidates):
        # Extract just the first line of address (city, state, country)
        addr_parts = c.address.split(",")
        short_addr = ", ".join(addr_parts[:3]) if len(addr_parts) >= 3 else c.address

        candidates_text.append(
            f"{i}. {c.name} - {short_addr} (type: {c.place_type or 'unknown'})"
        )

    prompt = f"""You are helping a user find the most likely location for their errand.

User is in: {user_city}, {user_state}, USA
User searched for: "{query}"

Candidate locations from OpenStreetMap:
{chr(10).join(candidates_text)}

Task: Select the MOST LIKELY location the user wants to visit for a typical errand.

Guidelines:
- User wants a location in or near {user_city}, {user_state}
- Reject locations outside the USA
- Reject locations more than {max_distance_miles} miles away (approximately)
- For chain stores (Target, Walmart, CVS, etc.), prefer retail/commercial locations
- For restaurants, prefer the specific restaurant, not the general cuisine type
- If query is clearly a business name, prefer that business over general places
- If all candidates are clearly wrong (wrong country, wrong type), return null

Return ONLY valid JSON in this exact format:
{{
  "best_index": <index number or null>,
  "confidence": "<high|medium|low>",
  "reasoning": "<brief explanation in 1 sentence>"
}}

Example outputs:
{{"best_index": 0, "confidence": "high", "reasoning": "Exact match for Target store in user's city"}}
{{"best_index": null, "confidence": "low", "reasoning": "All results are in wrong country or state"}}
"""

    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,  # Low temperature for consistent results
                max_output_tokens=200,
            )
        )

        # Parse JSON response
        result_text = response.text.strip()

        print(f"[DEBUG] Gemini response for '{query}': {result_text}")

        # Remove markdown code blocks if present
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()

        result = json.loads(result_text)

        # Validate result structure
        if "best_index" in result and "reasoning" in result:
            # Ensure best_index is valid
            if result["best_index"] is not None:
                idx = result["best_index"]
                if not isinstance(idx, int) or idx < 0 or idx >= len(candidates):
                    result["best_index"] = None
                    result["reasoning"] = "Invalid index returned by LLM"

            return result
        else:
            return {
                "best_index": None,
                "reasoning": "LLM returned invalid format"
            }

    except json.JSONDecodeError as e:
        print(f"Gemini JSON parse error: {e}")
        print(f"Response text: {response.text}")
        return {
            "best_index": None,
            "reasoning": "LLM response could not be parsed"
        }
    except Exception as e:
        print(f"Gemini API error: {e}")
        return {
            "best_index": None,
            "reasoning": f"LLM error: {str(e)}"
        }


def should_use_web_search(
    query: str,
    osm_results: list[PlaceSearchResult],
    llm_validation: Optional[dict],
) -> bool:
    """
    Determine if we should fall back to web search (Tavily).

    Args:
        query: User's search query
        osm_results: Results from OSM
        llm_validation: Validation result from Gemini (or None)

    Returns:
        True if we should try Tavily search
    """
    # No OSM results - definitely try web search
    if not osm_results:
        return True

    # LLM not available or returned null with low confidence
    if llm_validation:
        if llm_validation.get("best_index") is None:
            confidence = llm_validation.get("confidence", "low")
            if confidence == "low":
                return True

    # If we have very few results and they seem questionable
    if len(osm_results) < 2:
        return True

    return False


def extract_location_context(address: str) -> tuple[str, str]:
    """
    Extract city and state from a full address.

    Args:
        address: Full address string

    Returns:
        Tuple of (city, state)
    """
    # Map of full state names to abbreviations
    state_map = {
        "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
        "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
        "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
        "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
        "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
        "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
        "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
        "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
        "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
        "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
        "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
        "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
        "wisconsin": "WI", "wyoming": "WY"
    }

    parts = [p.strip() for p in address.split(",")]

    # Common format: "Street, City, County, State, ZIP, Country"
    state = ""
    city = ""

    for i, part in enumerate(parts):
        part_lower = part.lower().strip()

        # Check if this part is a state (full name or abbreviation)
        if part_lower in state_map:
            state = state_map[part_lower]
            # City is usually 1-2 parts before state (skip county if present)
            if i >= 2:
                # Try part before county
                potential_city = parts[i - 2].strip()
                # Check if it looks like a city (not a street address)
                if not any(char.isdigit() for char in potential_city):
                    city = potential_city
            elif i >= 1:
                city = parts[i - 1].strip()
            break

        # Check for 2-letter state abbreviation
        words = part.split()
        for word in words:
            if len(word) == 2 and word.isupper():
                state = word
                if i >= 1:
                    city = parts[i - 1].strip()
                break
        if state:
            break

    return city, state
