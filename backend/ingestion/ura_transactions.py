"""
backend/ingestion/ura_transactions.py

Pulls private residential transaction data from URA's PMI_Resi_Transaction
service, filters to resale-only CCR condos, and saves the cleaned
result to data/processed/.
"""

import requests   # for the API call
import os         # for reading env vars
import json       # for saving raw JSON responses
import pandas as pd  # for flattening/filtering the nested transaction data

from ura_auth import get_ura_token  # reuse the token function from Script 1
from dotenv import load_dotenv  # loads variables from .env into the environment

load_dotenv()  # call this once, before you read any os.environ values below
URA_DATA_URL = "https://eservice.ura.gov.sg/uraDataService/invokeUraDS/v1"

def fetch_ura_transactions(access_key: str, token: str, batch: int = 1) -> dict:
    """
    Calls URA's PMI_Resi_Transaction service.

    Args:
        access_key: your URA AccessKey
        token: today's token (from get_ura_token)
        batch: URA splits transaction data into batches (1, 2, 3, 4)
               to cover the full rolling 5-year window - you generally
               need to pull all batches to get complete data

    Returns:
        Raw JSON response as a Python dict
    """
    # both AccessKey and Token are required headers for every data call
    headers = {
        "AccessKey": access_key,
        "Token": token,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "application/json",
    }

    # service name and batch number go in the query string
    params = {
        "service": "PMI_Resi_Transaction",
        "batch": batch
    }

    response = requests.get(URA_DATA_URL, headers=headers, params=params)
    response.raise_for_status()

    return response.json()

def parse_ura_contract_date(raw_date) -> str:
    """
    URA packs contract date as month+year with no separator or leading zero,
    e.g. '725' = July 2025, '1225' = December 2025, '125' = January 2025.
    Converts this into a standard 'YYYY-MM' string for proper sorting/filtering.
    """
    if raw_date is None:
        return None

    raw_str = str(raw_date)

    # last 2 digits are always the year, everything before that is the month
    year_part = raw_str[-2:]
    month_part = raw_str[:-2]

    # URA uses 2-digit years - assume 2000s since this is post-2015 rolling data
    full_year = f"20{year_part}"

    # pad month to 2 digits (e.g. '7' becomes '07')
    month_padded = month_part.zfill(2)

    return f"{full_year}-{month_padded}"  # e.g. "2025-07"


def flatten_transactions(raw_json: dict) -> pd.DataFrame:
    """
    URA nests district, tenure, and propertyType INSIDE each transaction,
    not at the project level - only project name, market segment, and
    street live at the project level. This flattens correctly.
    """
    rows = []

    for project_entry in raw_json.get("Result", []):
        project_name = project_entry.get("project")
        market_segment = project_entry.get("marketSegment")  # CCR / RCR / OCR - directly from URA

        for txn in project_entry.get("transaction", []):
            # URA returns area in square meters (sqm), not sqft, despite no unit
            # label in the raw field name - convert here so downstream PSF
            # calculations and portal comparisons are correct
            area_sqm = txn.get("area")
            area_sqft = None
            if area_sqm is not None:
                # 1 sqm = 10.7639 sqft - standard conversion factor
                area_sqft = round(float(area_sqm) * 10.7639, 1)

            rows.append({
                "project": project_name,
                "market_segment": market_segment,
                "district": txn.get("district"),
                "tenure": txn.get("tenure"),
                "property_type": txn.get("propertyType"),
                "price": txn.get("price"),
                "area_sqm": area_sqm,       # keep the original raw value too, for transparency/debugging
                "area_sqft": area_sqft,     # converted value - this is what you'll actually use downstream
                "contract_date_raw": txn.get("contractDate"),         # original URA encoding, kept for reference
                "contract_date": parse_ura_contract_date(txn.get("contractDate")),  # parsed, sortable "YYYY-MM"
                "type_of_sale": txn.get("typeOfSale"),
                "floor_range": txn.get("floorRange"),
            })

    return pd.DataFrame(rows)


def filter_resale_ccr(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filters to resale transactions (typeOfSale == '3') within CCR only,
    using URA's own marketSegment field rather than reconstructing
    region from district codes.
    """
    resale_only = df[df["type_of_sale"] == "3"]
    ccr_only = resale_only[resale_only["market_segment"] == "CCR"]
    return ccr_only

if __name__ == "__main__":
    access_key = os.environ.get("URA_ACCESS_KEY")
    if not access_key:
        raise EnvironmentError("URA_ACCESS_KEY environment variable not set")

    # get a fresh token before every run
    token = get_ura_token(access_key)

    # URA splits data into up to 4 batches - pull all of them and combine
    all_transactions = []
    for batch_num in [1, 2, 3, 4]:
        raw = fetch_ura_transactions(access_key, token, batch=batch_num)
        flattened = flatten_transactions(raw)
        all_transactions.append(flattened)

    # combine all batches into a single dataframe
    combined_df = pd.concat(all_transactions, ignore_index=True)

    # CCR = districts 9, 10, 11 (Downtown Core/Sentosa codes vary by encoding - verify against your sample pull)
    ccr_resale_df = filter_resale_ccr(combined_df)

    # save the raw combined pull (untouched) to data/raw
    combined_df.to_csv("data/raw/ura_transactions/all_transactions_raw.csv", index=False)

    # save the filtered CCR resale subset to data/processed
    ccr_resale_df.to_csv("data/processed/ccr_resale_transactions.csv", index=False)

    print(f"Pulled {len(combined_df)} total transactions")
    print(f"Filtered to {len(ccr_resale_df)} CCR resale transactions")