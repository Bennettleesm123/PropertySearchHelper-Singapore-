"""
backend/eval/find_name_collisions.py

Dumps every CCR project name URA returns, with transaction counts, and flags
substring collisions between them.

Motivation: 'LEEDON' matched both D'LEEDON and LEEDON GREEN - two different
projects, different tenure, different sites. Any substring-based filter is a
trap. This finds every other place that trap exists before we build the
mapping table on top of it.
"""

import pandas as pd
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CSV = REPO_ROOT / "data" / "processed" / "ccr_resale_transactions.csv"

df = pd.read_csv(CSV)

# transaction count per project - this is also our liquidity signal later
counts = df["project"].value_counts()

print(f"{len(counts)} distinct CCR resale condo projects\n")
print("=" * 70)
print("ALL PROJECTS BY TRANSACTION COUNT (last ~5y)")
print("=" * 70)
for name, n in counts.items():
    print(f"{n:>5}  {name}")

# --- collision detection -------------------------------------------------
# If project A's name is a substring of project B's name, then ANY
# str.contains() filter for A will silently pull in B's rows too.
names = sorted(counts.index.astype(str))

print("\n" + "=" * 70)
print("SUBSTRING COLLISIONS - these will break str.contains() filters")
print("=" * 70)

collisions = []
for a in names:
    for b in names:
        if a != b and a.upper() in b.upper():
            collisions.append((a, b))
            print(f"  {a!r}")
            print(f"    is contained in -> {b!r}\n")

if not collisions:
    print("  none found")

print(f"\n{len(collisions)} collision pairs found")