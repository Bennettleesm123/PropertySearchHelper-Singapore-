"""
backend/ingestion/onemap_routing.py

Calculates walking distance/time between two coordinate points using OneMap's
routing service. This is different from search/geocoding (which just finds WHERE
something is) - routing tells you HOW to get from A to B and how long it takes.

Every route is sanity-checked against straight-line distance, so a silently
wrong route doesn't look the same as a correct one.
"""

import requests
import os
import sys
from math import radians, sin, cos, asin, sqrt
from pathlib import Path

# lets `from onemap_client import ...` work regardless of which folder you run from
sys.path.insert(0, str(Path(__file__).resolve().parent))

from onemap_client import get_onemap_token  # single source of truth for auth
from dotenv import load_dotenv  # loads .env file contents into environment

load_dotenv()  # must run before reading any os.environ values below

ONEMAP_ROUTING_URL = "https://www.onemap.gov.sg/api/public/routingsvc/route"

# OneMap's routing endpoint is more sensitive to bot-detection than search,
# so we send the same browser-like headers that fixed the URA WAF issue earlier
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json",
}


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Straight-line ('as the crow flies') distance in meters."""
    R = 6371000  # earth radius in meters
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * R * asin(sqrt(a))


def sanity_check_route(start_lat, start_lng, end_lat, end_lng, route_distance_m) -> float:
    """
    Compares the routed distance to the straight-line distance.
    Real Singapore walking routes land around 1.2-1.6x. Outside that range,
    go verify the route by hand on onemap.gov.sg before trusting it.
    """
    straight = haversine_m(start_lat, start_lng, end_lat, end_lng)
    ratio = route_distance_m / straight if straight else float("inf")

    print(f"  straight-line: {straight:.0f}m | routed: {route_distance_m:.0f}m | ratio: {ratio:.2f}")

    if ratio < 1.05:
        print("  WARNING: ratio ~1.0 - the router may have fallen back to a straight line")
    elif ratio > 2.0:
        print("  WARNING: ratio >2.0 - major detour (canal? expressway?) - verify on the map")

    return ratio


def get_walking_route(start_lat: float, start_lng: float,
                      end_lat: float, end_lng: float,
                      token: str, route_type: str = "walk") -> dict:
    """
    Requests a route between two points.

    Args:
        start_lat, start_lng: coordinates of the starting point (e.g. a condo gate)
        end_lat, end_lng: coordinates of the destination (e.g. an MRT exit)
        token: OneMap access token
        route_type: walk, drive, or cycle ('pt' is not supported here - see below)

    Returns:
        JSON response containing total distance (meters) and time (seconds),
        plus the actual route path.
    """
    # 'pt' returns a completely different response shape (plan.itineraries, not
    # route_summary) and needs date/time/mode params. Fail loudly rather than
    # returning None and looking like a routing failure.
    if route_type == "pt":
        raise NotImplementedError(
            "routeType='pt' returns plan.itineraries, not route_summary, and requires "
            "date/time/mode/maxWalkDistance/numItineraries. Write a separate function."
        )

    # OneMap expects coordinates as a "lat,lng" string, not separate params
    params = {
        "start": f"{start_lat},{start_lng}",
        "end": f"{end_lat},{end_lng}",
        "routeType": route_type,  # walk, drive, cycle
    }

    headers = {**BROWSER_HEADERS, "Authorization": f"Bearer {token}"}

    response = requests.get(ONEMAP_ROUTING_URL, params=params, headers=headers, timeout=20)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    email = os.environ.get("ONEMAP_EMAIL")
    password = os.environ.get("ONEMAP_PASSWORD")

    if not email or not password:
        raise EnvironmentError("ONEMAP_EMAIL and ONEMAP_PASSWORD must be set in .env")

    token = get_onemap_token(email, password)
    print("Token retrieved.")

    # Test route: d'Leedon -> Farrer Road MRT
    # NOTE: both of these are still approximations - d'Leedon's geocoded centroid
    # is not where a resident actually walks out, and this is the station centroid
    # rather than a specific exit. Fixing that is the LTA-exits work item.
    start_lat, start_lng = 1.31442165521267, 103.803912974494  # d'Leedon
    end_lat, end_lng = 1.30756, 103.80732  # approx Farrer Road MRT

    route = get_walking_route(start_lat, start_lng, end_lat, end_lng, token)

    # OneMap nests the useful summary info inside route_summary
    summary = route.get("route_summary", {})
    distance_m = summary.get("total_distance")
    time_s = summary.get("total_time")

    if distance_m is None:
        raise ValueError(f"No route_summary in response. Raw keys: {list(route.keys())}")

    print(f"Total distance: {distance_m}m")
    print(f"Total time:     {time_s}s ({time_s / 60:.1f} min)")

    sanity_check_route(start_lat, start_lng, end_lat, end_lng, distance_m)