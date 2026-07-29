"""Pull US Census international trade data as a cross-check on the US-reported side
of the Comtrade pull, the same way the CRE project cross-checked parsed loan data
against original term sheets.

Unlike UN Comtrade (see fetch_comtrade.py), the Census intltrade timeseries API has
NO unauthenticated path -- a request without a key redirects to an HTML "Missing
Key" page even for a single query (verified live 2026-07-29). Registering a key is
lightweight (name + email, https://api.census.gov/data/key_signup.html) but is still
account creation, so it's on you, not something this script does automatically.

Set CENSUS_API_KEY (see src/config.py) before running this. Census is a secondary
cross-check series in this project, not the primary one -- the annual risk scoring
in build_risk_score.sql runs on Comtrade data alone, so a missing key here doesn't
block the rest of `make all`; it only skips this cross-check step.
"""

import json
import os
import sys
import time

import requests

from config import (
    CENSUS_API_KEY,
    HS_CODES,
    RAW_DIR,
    REQUEST_DELAY_SECONDS,
    TRADE_END_YEAR,
    TRADE_START_YEAR,
)

BASE_URL = "https://api.census.gov/data/timeseries/intltrade/exports/hs"

# Census reports destination by a 3-digit numeric country code distinct from both
# ISO3 and Comtrade's M49 reporterCode -- CTY_CODE per the Census Country/Area codes
# list, resolved live rather than hardcoded (same rationale as reporter_codes() in
# fetch_comtrade.py: these tables occasionally get revised).
COUNTRY_CODES_URL = "https://api.census.gov/data/timeseries/intltrade/exports/hs?get=CTY_CODE,CTY_NAME&COMM_LVL=HS6&time=2024-01&E_COMMODITY=854231&key={key}"

DESTINATIONS = ["SGP", "HKG", "CHN"]  # ISO3, matched against CTY_NAME below
DEST_NAME_HINTS = {
    "SGP": "SINGAPORE",
    "HKG": "HONG KONG",
    "CHN": "CHINA",
}


def _country_codes() -> dict:
    url = COUNTRY_CODES_URL.format(key=CENSUS_API_KEY)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    rows = resp.json()
    header, records = rows[0], rows[1:]
    idx = {name: i for i, name in enumerate(header)}
    out = {}
    for rec in records:
        name = rec[idx["CTY_NAME"]].upper()
        for iso3, hint in DEST_NAME_HINTS.items():
            if hint in name and iso3 not in out:
                out[iso3] = rec[idx["CTY_CODE"]]
    missing = set(DESTINATIONS) - set(out)
    if missing:
        raise RuntimeError(f"Census country-code lookup missing: {missing}")
    return out


def fetch_hs_destination(hs_code: str, cty_code: str, year: int) -> list[dict]:
    params = {
        "get": "CTY_CODE,CTY_NAME,ALL_VAL_MO,E_COMMODITY,E_COMMODITY_LDESC",
        "COMM_LVL": "HS6",
        "time": str(year),  # bare year returns all 12 months; the "YYYY-MM:YYYY-MM"
                            # range syntax this originally used 400s ("unsupported
                            # date/time format") -- verified live against the API.
        "E_COMMODITY": hs_code,
        "CTY_CODE": cty_code,
        "key": CENSUS_API_KEY,
    }
    resp = requests.get(BASE_URL, params=params, timeout=30)
    resp.raise_for_status()
    rows = resp.json()
    header, records = rows[0], rows[1:]
    return [dict(zip(header, rec)) for rec in records]


def main():
    if not CENSUS_API_KEY:
        print(
            "CENSUS_API_KEY not set -- skipping the Census cross-check pull.\n"
            "Register a free key at https://api.census.gov/data/key_signup.html and "
            "export CENSUS_API_KEY to enable this step. The main pipeline (Comtrade "
            "-> risk scoring) does not depend on this.",
            file=sys.stderr,
        )
        return

    os.makedirs(RAW_DIR, exist_ok=True)
    country_codes = _country_codes()

    rows = []
    for hs_code in HS_CODES:
        for iso3 in DESTINATIONS:
            cty_code = country_codes[iso3]
            for year in range(TRADE_START_YEAR, TRADE_END_YEAR + 1):
                rows.extend(fetch_hs_destination(hs_code, cty_code, year))
                time.sleep(REQUEST_DELAY_SECONDS)

    out_path = f"{RAW_DIR}/census_exports_crosscheck.json"
    with open(out_path, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"Wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
