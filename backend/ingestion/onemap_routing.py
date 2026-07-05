"""
backend/ingestion/onemap_routing.py

Tests OneMap's routing service - calculates walking distance/time
between two coordinate points. This is different from search/geocoding
(which just finds WHERE something is) - routing tells you HOW to get
from point A to point B and how long it takes.
"""

import requests
import os
from dotenv import load_dotenv  # loads .env file contents into environment

load_dotenv()  # must run before reading any os.environ values below

ONEMAP_TOKEN_URL = "https://www.onemap.gov.sg/api/auth/post/getToken"
ONEMAP_ROUTING_URL = "https://www.onemap.gov.sg/api/public/routingsvc/route"

# OneMap's routing endpoint is more sensitive to bot-detection than search,
# so we send the same browser-like headers that fixed the URA WAF issue earlier
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json",
}


def get_onemap_token(email: str, password: str) -> str:
    """
    Same token logic as onemap_client.py - kept here too so this script
    can run independently without importing from another file.
    """
    payload = {"email": email, "password": password}
    response = requests.post(ONEMAP_TOKEN_URL, json=payload, headers=BROWSER_HEADERS)
    response.raise_for_status()
    return response.json()["access_token"]


def get_walking_route(start_lat: float, start_lng: float,
                       end_lat: float, end_lng: float,
                       token: str) -> dict:
    """
    Requests a walking route between two points.

    Args:
        start_lat, start_lng: coordinates of the starting point (e.g. a condo)
        end_lat, end_lng: coordinates of the destination (e.g. nearest MRT station)
        token: OneMap access token

    Returns:
        JSON response containing total distance (meters) and time (seconds),
        plus the actual route path.
    """
    # OneMap expects coordinates as a "lat,lng" string, not separate params
    params = {
        "start": f"{start_lat},{start_lng}",
        "end": f"{end_lat},{end_lng}",
        "routeType": "walk",  # options in web is: walk, drive, cycle, pt (public transport)
    }

    headers = {**BROWSER_HEADERS, "Authorization": f"Bearer {token}"}

    response = requests.get(ONEMAP_ROUTING_URL, params=params, headers=headers)

    # TEMP DEBUG: print raw response in case of errors - remove once confirmed working
    print("Status code:", response.status_code)

    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    email = os.environ.get("ONEMAP_EMAIL")
    password = os.environ.get("ONEMAP_PASSWORD")

    if not email or not password:
        raise EnvironmentError("ONEMAP_EMAIL and ONEMAP_PASSWORD must be set in .env")

    token = get_onemap_token(email, password)
    print("Token retrieved.")

    # Test route: d'Leedon (from your earlier geocoding test) -> Farrer Road MRT
    # d'Leedon coordinates come from the search result you already got
    start_lat, start_lng = 1.31442165521267, 103.803912974494  # d'Leedon
    end_lat, end_lng = 1.30756, 103.80732  # approx Farrer Road MRT

    route = get_walking_route(start_lat, start_lng, end_lat, end_lng, token)

    # OneMap nests the useful summary info inside route_summary
    summary = route.get("route_summary", {})
    print("Total distance (meters):", summary.get("total_distance"))
    print("Total time (seconds):", summary.get("total_time"))