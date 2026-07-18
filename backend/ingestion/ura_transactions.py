"""
backend/ingestion/ura_transactions.py

Pulls private residential transaction data from URA's PMI_Resi_Transaction
service, filters to resale-only CCR condos, and saves the cleaned
result to data/processed/.
"""

import sys
from pathlib import Path

# Makes `from ura_auth import ...` work no matter which folder you run from.
# This MUST sit above the ura_auth import below, or it won't help.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests      # for the API call
import os            # for reading env vars
import pandas as pd  # for flattening/filtering the nested transaction data

from ura_auth import get_ura_token  # reuse the token function from Script 1
from dotenv import load_dotenv      # loads variables from .env into the environment

load_dotenv()  # call this once, before read any os.environ values below

URA_DATA_URL = "https://eservice.ura.gov.sg/uraDataService/invokeUraDS/v1"

# Absolute paths anchored to the repo root, so output always lands in the same
# place regardless of your working directory.
# This file is at backend/ingestion/, so: parents[0]=ingestion, [1]=backend, [2]=repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "ura_transactions"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

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
    if raw_date is None or pd.isna(raw_date):
        return None

    raw_str = str(raw_date).strip()

    # Valid URA encodings are exactly 3 or 4 digits: MYY (e.g. '725') or MMYY ('1225').
    # Anything else is malformed - return None rather than inventing a date.
    if not raw_str.isdigit() or len(raw_str) not in (3, 4):
        return None

    year_part = raw_str[-2:]     # last 2 digits are always the year
    month_part = raw_str[:-2]    # everything before that is the month

    month = int(month_part)
    if not 1 <= month <= 12:
        return None

    # URA uses 2-digit years - assume 2000s since this is post-2015 rolling data
    return f"20{year_part}-{month:02d}"  # e.g. "2025-07"


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
                "no_of_units": txn.get("noOfUnits"),    # >1 means a bulk/multi-unit caveat
                "type_of_area": txn.get("typeOfArea"),  # 'Strata' vs 'Land' - cross-check on property_type
                "price": txn.get("price"),
                "area_sqm": area_sqm,       # keep the original raw value too, for transparency/debugging
                "area_sqft": area_sqft,     # converted value - this is what you'll actually use downstream
                "contract_date_raw": txn.get("contractDate"),         # original URA encoding, kept for reference
                "contract_date": parse_ura_contract_date(txn.get("contractDate")),  # parsed, sortable "YYYY-MM"
                "type_of_sale": txn.get("typeOfSale"),
                "floor_range": txn.get("floorRange"),
            })

    return pd.DataFrame(rows)


# Verify these exact strings against your raw pull before trusting them.
# Run: pd.read_csv(RAW_DIR / "all_transactions_raw.csv")["property_type"].unique()
CONDO_PROPERTY_TYPES = {"Apartment", "Condominium"}


def filter_resale_ccr(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filters to single-unit resale condo/apartment transactions in CCR,
    using URA's own marketSegment field rather than reconstructing
    region from district codes.

    Prints a funnel so you can see exactly what each filter removes.
    """
    df = df.copy()  # don't mutate the caller's dataframe

    # URA's types come back inconsistently across batches - force the comparison
    df["type_of_sale"] = df["type_of_sale"].astype(str)
    df["no_of_units"] = pd.to_numeric(df["no_of_units"], errors="coerce")

    print("\nFilter funnel:")
    print(f"  start:             {len(df):>7,}")

    df = df[df["type_of_sale"] == "3"]
    print(f"  after resale:      {len(df):>7,}")

    df = df[df["market_segment"] == "CCR"]
    print(f"  after CCR:         {len(df):>7,}")

    df = df[df["property_type"].isin(CONDO_PROPERTY_TYPES)]
    print(f"  after condo-only:  {len(df):>7,}")

    df = df[df["no_of_units"] == 1]
    print(f"  after single-unit: {len(df):>7,}")

    return df

if __name__ == "__main__":
    access_key = os.environ.get("URA_ACCESS_KEY")
    if not access_key:
        raise EnvironmentError("URA_ACCESS_KEY environment variable not set")

    # get a fresh token before every run
    token = get_ura_token(access_key)

   # URA splits data into up to 4 batches - pull all of them and combine.
    # One failing batch shouldn't destroy the whole run.
    all_transactions = []
    for batch_num in [1, 2, 3, 4]:
        try:
            raw = fetch_ura_transactions(access_key, token, batch=batch_num)
            flattened = flatten_transactions(raw)
            print(f"Batch {batch_num}: {len(flattened):,} transactions")
            all_transactions.append(flattened)
        except Exception as e:
            print(f"Batch {batch_num} FAILED: {e}")

    if not all_transactions:
        raise RuntimeError("All batches failed - check your token and AccessKey")

    # combine all batches into a single dataframe
    combined_df = pd.concat(all_transactions, ignore_index=True)

    ccr_resale_df = filter_resale_ccr(combined_df)

    # make sure the output folders exist before writing
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # save the raw combined pull (untouched) to data/raw
    combined_df.to_csv(RAW_DIR / "all_transactions_raw.csv", index=False)

    # save the filtered CCR resale subset to data/processed
    ccr_resale_df.to_csv(PROCESSED_DIR / "ccr_resale_transactions.csv", index=False)

    # data-quality check: how many contract dates failed to parse?
    bad_dates = combined_df["contract_date"].isna().sum()
    print(f"\nPulled {len(combined_df):,} total transactions")
    print(f"Filtered to {len(ccr_resale_df):,} CCR resale condo transactions")
    print(f"Unparseable contract dates: {bad_dates:,} ({bad_dates / len(combined_df):.2%})")