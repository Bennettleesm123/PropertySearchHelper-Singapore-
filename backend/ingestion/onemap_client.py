"""
backend/ingestion/onemap_client.py

Handles OneMap authentication and basic geocoding/search calls.
Supports two modes:
1. Use a cached token directly (quick, but expires in ~3 days)
2. Auto-generate a fresh token from email/password (more durable)
"""

import requests
import os
from dotenv import load_dotenv  # loads .env file contents into environment variables

load_dotenv()  # run this once at the top so os.environ picks up .env values

ONEMAP_TOKEN_URL = "https://www.onemap.gov.sg/api/auth/post/getToken"
ONEMAP_SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"


def get_onemap_token(email: str, password: str) -> str:
    """
    Logs into OneMap using registered email/password and returns
    a fresh access token. Use this when you want auto-refreshing
    tokens rather than relying on a cached one that expires in 3 days.
    """
    payload = {"email": email, "password": password}
    response = requests.post(ONEMAP_TOKEN_URL, json=payload)

    response.raise_for_status()
    return response.json()["access_token"]


def search_address(query: str, token: str) -> dict:
    """
    Searches for an address/building/postal code, returns lat/long
    and address details.
    """
    params = {
        "searchVal": query,
        "returnGeom": "Y",
        "getAddrDetails": "Y",
    }
    headers = {"Authorization": f"Bearer {token}"}

    response = requests.get(ONEMAP_SEARCH_URL, params=params, headers=headers)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    # OPTION A: use the cached token directly from .env (fast, but expires in ~3 days)
    cached_token = os.environ.get("ONEMAP_TOKEN")

    # OPTION B: auto-generate a fresh token from email/password (more durable long-term)
    email = os.environ.get("ONEMAP_EMAIL")
    password = os.environ.get("ONEMAP_PASSWORD")

    if email and password:
        # prefer generating a fresh token if credentials are available
        token = get_onemap_token(email, password)
        print("Generated a fresh OneMap token via email/password.")
    elif cached_token:
        # fall back to the cached token if no email/password is set yet
        token = cached_token
        print("Using cached OneMap token from .env (check it hasn't expired).")
    else:
        raise EnvironmentError("No OneMap credentials found in .env")

    # test geocoding with a sample CCR project name
    result = search_address("d'Leedon", token=token)
    print(result)