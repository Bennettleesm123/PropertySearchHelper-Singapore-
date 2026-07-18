"""
backend/ingestion/ura_auth.py

Handles authentication with the URA Data Service API.
URA requires a fresh Token every day - this script fetches one
using your AccessKey (obtained after URA approves your account).
"""

import requests  # for making HTTP calls to the URA API
import os        # for reading your AccessKey from an environment variable (never hardcode it)
from dotenv import load_dotenv  # loads variables from .env into the environment

load_dotenv()  # call this once, before you read any os.environ values below

# URA's token endpoint - hitting this returns a new daily token
URA_TOKEN_URL = "https://eservice.ura.gov.sg/uraDataService/insertNewToken/v1"

def get_ura_token(access_key: str) -> str:
    """
    Requests a fresh daily token from URA.

    Args:
        access_key: your personal AccessKey issued by URA after registration

    Returns:
        A token string valid for 24 hours, used alongside AccessKey
        in the header of every subsequent URA API call.
    """
    # URA expects the AccessKey passed as a request header, not a query param
    headers = {
        "AccessKey": access_key,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "application/json",
    }

    # send the GET request to URA's token endpoint
    response = requests.get(URA_TOKEN_URL, headers=headers)

    # raise immediately if the request failed (bad key, network issue, etc.)
    response.raise_for_status()

    # parse the JSON response body
    data = response.json()

    # URA wraps the token inside a "Result" field - pull it out
    token = data.get("Result")

    if not token:
        # if URA didn't return a token, something's wrong (bad key, account not activated yet)
        raise ValueError(f"Failed to get token. URA response: {data}")

    return token


if __name__ == "__main__":
    # read the AccessKey from an environment variable instead of hardcoding it
    # set this in your terminal first: export URA_ACCESS_KEY="your-key-here"
    access_key = os.environ.get("URA_ACCESS_KEY")

    if not access_key:
        raise EnvironmentError("URA_ACCESS_KEY environment variable not set")

    token = get_ura_token(access_key)
    print("Token retrieved successfully:")
    print(token)