"""Tavily web search service for place resolution fallback."""

import re
from typing import Optional
from tavily import TavilyClient

from orbit.config import TAVILY_API_KEY, ENABLE_TAVILY_FALLBACK
from orbit.models import PlaceSearchResult
from orbit.services import places


# Initialize Tavily client
tavily_client = TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else None


def search_place_with_tavily(
    query: str,
    city: str,
    state: str,
) -> Optional[PlaceSearchResult]:
    """
    Search for a place using Tavily web search and geocode the result.

    Args:
        query: User's place query (e.g., "Target", "CVS")
        city: User's city
        state: User's state

    Returns:
        PlaceSearchResult if found and geocoded, None otherwise
    """
    if not ENABLE_TAVILY_FALLBACK or not tavily_client:
        return None

    # Construct search query
    search_query = f"{query} near {city}, {state}"

    try:
        print(f"[Tavily] Searching for: '{search_query}'")

        # Perform search
        response = tavily_client.search(
            query=search_query,
            search_depth="basic",
            max_results=3,
            include_answer=True,
            include_domains=["google.com/maps", "yelp.com", "yellowpages.com"],
        )

        print(f"[Tavily] Response: {response}")

        # Try to extract address or business name from results
        address = None
        business_name = None

        # First, try the AI-generated answer
        if response.get("answer"):
            address = extract_address_from_text(response["answer"])

        # If no address in answer, try top search results
        if not address and response.get("results"):
            for result in response["results"][:3]:
                content = result.get("content", "")
                title = result.get("title", "")
                url = result.get("url", "")

                # Check if this looks like the right business
                # E.g., "Carter's Babies & Kids" or "Carters" for query "Carter's"
                # Normalize: remove apostrophes and special chars for matching
                query_normalized = query.lower().replace("'", "").replace("'", "")
                title_normalized = title.lower().replace("'", "").replace("'", "")
                content_normalized = content.lower().replace("'", "").replace("'", "")

                if query_normalized in title_normalized or query_normalized in content_normalized:
                    # Look for business name pattern: "Carter's Babies & Kids"
                    # Usually appears before " - " separator
                    import re

                    # Try content first
                    match = re.search(rf"({re.escape(query)}[^-\n\.]*(?:Babies|Kids|Store|Shop)?)", content, re.IGNORECASE)
                    if match:
                        potential_name = match.group(1).strip()
                        # Clean up: remove trailing punctuation and "near me"
                        potential_name = re.sub(r'\s*-\s*.*', '', potential_name)
                        potential_name = re.sub(r'\s+near me.*', '', potential_name, flags=re.IGNORECASE)
                        if len(potential_name) < 50:  # Reasonable business name length
                            business_name = potential_name

                    # Try title if not found
                    if not business_name:
                        match = re.search(rf"({re.escape(query)}[^-\n\.]*(?:Babies|Kids|Store|Shop)?)", title, re.IGNORECASE)
                        if match:
                            potential_name = match.group(1).strip()
                            potential_name = re.sub(r'\s*-\s*.*', '', potential_name)
                            if len(potential_name) < 50:
                                business_name = potential_name

                    # Try to find address in combined text
                    combined = f"{title} {content}"
                    potential_address = extract_address_from_text(combined)
                    if potential_address:
                        address = potential_address
                        break

        # If we found an address, geocode it
        if address:
            geocoded = places.geocode_address(address)
            if geocoded:
                print(f"[Tavily] Geocoded address: {address}")
                return geocoded

        # If we found a business name, try to extract city from Tavily results
        nearby_city = None
        if business_name:
            # Look for city names in the content/title
            # Common patterns: "near [City], [State]" or "[City], [State]"
            import re

            for result in response.get("results", [])[:3]:
                content = result.get("content", "")
                title = result.get("title", "")
                combined = f"{title} {content}"

                # Pattern: Look for "City, State" or "City, TX"
                # Must be a proper city name (starts with capital, reasonable length)
                city_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?),\s*(' + state + r')\b'
                matches = re.findall(city_pattern, combined)

                for match_city, match_state in matches:
                    match_city = match_city.strip()

                    # Skip if it looks like a business type or common word
                    skip_words = ['ALTERATIONS', 'SEWING', 'Western', 'Wear', 'Stores', 'Best']
                    if any(skip in match_city for skip in skip_words):
                        continue

                    # Check if it's in the same state and looks like a real city
                    if match_state == state and 2 <= len(match_city) <= 30:
                        # Found a nearby city
                        nearby_city = match_city
                        print(f"[Tavily] Extracted nearby city: {nearby_city}")
                        break

                if nearby_city:
                    break

            # Try geocoding with nearby city if found
            if nearby_city:
                search_term = f"{business_name}, {nearby_city}, {state}"
                print(f"[Tavily] Trying geocode with nearby city: {search_term}")
                geocoded = places.geocode_address(search_term)
                if geocoded:
                    return geocoded

            # Try original city
            search_term = f"{business_name}, {city}, {state}"
            print(f"[Tavily] Trying geocode with original city: {search_term}")
            geocoded = places.geocode_address(search_term)
            if geocoded:
                return geocoded

        # Final fallback: try using just the query + nearby city (if found) or original city
        if nearby_city:
            fallback_address = f"{query}, {nearby_city}, {state}"
            print(f"[Tavily] Fallback with nearby city: {fallback_address}")
        else:
            fallback_address = f"{query}, {city}, {state}"
            print(f"[Tavily] Fallback with original city: {fallback_address}")

        geocoded = places.geocode_address(fallback_address)
        return geocoded

    except Exception as e:
        print(f"Tavily search error: {e}")
        return None


def extract_address_from_text(text: str) -> Optional[str]:
    """
    Extract a street address from text using regex patterns.

    Args:
        text: Text that might contain an address

    Returns:
        Extracted address string or None
    """
    # Pattern for US addresses: number + street + city + state + zip
    # Example: "123 Main St, Springfield, IL 62701"
    patterns = [
        # Full address with ZIP
        r'\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|Way|Court|Ct|Parkway|Pkwy)\.?\s*,\s*[A-Za-z\s]+,\s*[A-Z]{2}\s+\d{5}',
        # Address without ZIP
        r'\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|Way|Court|Ct|Parkway|Pkwy)\.?\s*,\s*[A-Za-z\s]+,\s*[A-Z]{2}',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)

    return None


def format_location_from_search(
    query: str,
    city: str,
    state: str,
    search_result: dict,
) -> Optional[str]:
    """
    Format a location string from Tavily search result.

    Args:
        query: Original query
        city: User's city
        state: User's state
        search_result: Tavily search result dict

    Returns:
        Formatted address string or None
    """
    content = search_result.get("content", "")
    title = search_result.get("title", "")

    # Try to extract structured address info
    address = extract_address_from_text(f"{title} {content}")

    if address:
        return address

    # Fallback: construct from query + city + state
    return f"{query}, {city}, {state}"
