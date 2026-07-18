"""
backend/eval/inspect_data.py

Quick sanity-check script - loads the processed CSV properly (with headers)
and prints a specific project's rows in a readable format, so we can
compare directly against a portal screenshot without misreading raw CSV text.
"""

import pandas as pd
from pathlib import Path

# anchor to repo root - this file is at backend/eval/, so parents[2] = repo root
REPO_ROOT = Path(__file__).resolve().parents[2]

# load with pandas so column names/headers are respected, not guessed
df = pd.read_csv(REPO_ROOT / "data" / "processed" / "ccr_resale_transactions.csv")

# print column names and their order - confirms exactly what each column IS
print("Columns in order:", list(df.columns))
print()

# print data types - this will reveal if numbers got read as text, mixed types etc
print("Data types:")
print(df.dtypes)
print()

# filter to just D'Leedon so we can directly compare against your portal screenshot
dleedon = df[df["project"].str.contains("LEEDON", case=False, na=False)]

# print full rows, with column headers, no truncation
pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)
print(f"Found {len(dleedon)} D'Leedon rows:")
print(dleedon.to_string())