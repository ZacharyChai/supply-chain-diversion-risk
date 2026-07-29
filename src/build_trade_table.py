"""Parse raw Comtrade JSON dumps into one tidy long-format table -> SQLite.

Comtrade's preview endpoint returns reporterISO/partnerISO/cmdDesc as null (only
the authenticated endpoint fills those in), so this script re-resolves ISO3 codes
from the numeric reporterCode/partnerCode via the same live reference lookup
fetch_comtrade.py uses, rather than hardcoding a second copy of that table.

Note on comparability: Comtrade serves each year under whichever HS revision (H4/H5/
H6) was in effect for that reporting period even when the request asks generically
for "HS" classification -- e.g. 2017 data came back tagged H4, 2023 data H6. The
cmdCode label (e.g. 854239) is stable across these revisions for this project's
codes, but this is worth stating in findings.md's limitations section rather than
assuming silently that every year is on identical footing.
"""

import json
import os
import sqlite3

import pandas as pd

from config import DB_PATH, PROCESSED_DIR, RAW_DIR
from fetch_comtrade import _reporter_codes

CORRIDOR_FILE = f"{RAW_DIR}/comtrade_annual_corridors.json"
BASELINE_FILE = f"{RAW_DIR}/comtrade_annual_world_baseline.json"
REEXPORTS_FILE = f"{RAW_DIR}/comtrade_annual_reexports.json"
TOTAL_BASELINE_FILE = f"{RAW_DIR}/comtrade_annual_total_baseline.json"


def _rows_to_df(rows: list[dict], code_to_iso3: dict) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["reporter_iso3"] = df["reporterCode"].map(code_to_iso3)
    df["partner_iso3"] = df["partnerCode"].map(lambda c: code_to_iso3.get(c, "WLD" if c == 0 else str(c)))
    return df[[
        "reporter_iso3", "partner_iso3", "period", "refYear", "cmdCode",
        "classificationCode", "primaryValue", "qty", "flowCode",
    ]].rename(columns={
        "cmdCode": "hs6",
        "classificationCode": "hs_revision",
        "primaryValue": "trade_value_usd",
        "refYear": "year",
    })


def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    code_to_iso3 = {v: k for k, v in _reporter_codes().items()}

    with open(CORRIDOR_FILE) as f:
        corridor_rows = json.load(f)
    with open(BASELINE_FILE) as f:
        baseline_rows = json.load(f)
    with open(REEXPORTS_FILE) as f:
        reexport_rows = json.load(f)
    with open(TOTAL_BASELINE_FILE) as f:
        total_baseline_rows = json.load(f)

    corridors = _rows_to_df(corridor_rows, code_to_iso3)
    corridors["series"] = "corridor"
    baseline = _rows_to_df(baseline_rows, code_to_iso3)
    baseline["series"] = "world_baseline"  # hub imports of target HS codes from World
    reexports = _rows_to_df(reexport_rows, code_to_iso3)
    reexports["series"] = "reexport"  # hub exports of target HS codes, to World or China
    total_baseline = _rows_to_df(total_baseline_rows, code_to_iso3)
    total_baseline["series"] = "total_trade_baseline"  # hub's all-commodity imports from World

    trade = pd.concat([corridors, baseline, reexports, total_baseline], ignore_index=True)
    trade.to_csv(f"{PROCESSED_DIR}/trade_long.csv", index=False)

    conn = sqlite3.connect(DB_PATH)
    trade.to_sql("trade", conn, if_exists="replace", index=False)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_key ON trade(reporter_iso3, partner_iso3, hs6, year)")
    conn.commit()
    conn.close()

    print(f"Wrote {len(trade)} tidy rows to {PROCESSED_DIR}/trade_long.csv and {DB_PATH}")


if __name__ == "__main__":
    main()
