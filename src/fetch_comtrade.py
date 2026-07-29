"""Pull bilateral trade data from UN Comtrade.

Two endpoints, chosen automatically:
  - No COMTRADE_API_KEY set: uses the free, unauthenticated /public/v1/preview/
    endpoint. Verified live (2026-07-29) to return real HS6 bilateral data back to
    2017, one period per call but ALL requested cmdCodes in a single call. No
    account/registration needed -- this is the default path.
  - COMTRADE_API_KEY set: uses the authenticated /data/v1/get/ endpoint (higher
    rate limits, needed for bulk monthly pulls beyond what the preview endpoint
    comfortably supports). Register a free key at https://comtradeplus.un.org if
    you want this path; the pipeline runs correctly without it.

The preview endpoint rate-limits aggressively (observed a 429 after ~45 calls at a
0.5s gap in live testing) with no Retry-After header, so every call is cached to
data/raw/comtrade_cache/ as its own file and retried with exponential backoff on
429/5xx. Reruns skip cached (reporter, partner, period) combinations entirely --
`make fetch` is safe to re-invoke after a rate-limit interruption without losing
progress or re-hitting calls that already succeeded.

Two pulls:
  1. Annual, full grid: every corridor in config.CORRIDORS x every HS code x
     TRADE_START_YEAR..TRADE_END_YEAR. This is the main series for the
     rate-of-growth-gap and absorption-gap signals.
  2. Annual, World-partner baseline: each reporter's imports of the same HS codes
     from the WORLD (partnerCode=0), used to compute each hub's overall trade
     growth baseline (rules out "hub trade grew generally that year").

Monthly data for the event-proximity signal is pulled separately and only for the
corridor(s) driver analysis flags as highest-risk -- see fetch_monthly() and its
call site in drivers.py. Pulling monthly data for the full grid up front would mean
~500+ unauthenticated calls against a free preview service for months of data most
corridors will never need; better to fetch it once the top-tier corridor is known.
"""

import json
import os
import time

import requests

from config import (
    CORRIDORS,
    COMTRADE_API_KEY,
    HS_CODES,
    ISO3_TO_NAME,
    RAW_DIR,
    REQUEST_DELAY_SECONDS,
    TRADE_END_YEAR,
    TRADE_START_YEAR,
)

PREVIEW_BASE = "https://comtradeapi.un.org/public/v1/preview/C"
AUTH_BASE = "https://comtradeapi.un.org/data/v1/get/C"
REFERENCE_REPORTERS_URL = "https://comtradeapi.un.org/files/v1/app/reference/Reporters.json"

CMD_CODES = ",".join(HS_CODES.keys())
CACHE_DIR = f"{RAW_DIR}/comtrade_cache"

MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 8  # 8, 16, 32, 64, 128s on successive 429/5xx


def _reporter_codes() -> dict:
    """ISO3 -> Comtrade numeric reporterCode, resolved live (not hardcoded)."""
    resp = requests.get(REFERENCE_REPORTERS_URL, timeout=30)
    resp.raise_for_status()
    out = {}
    for r in resp.json()["results"]:
        iso3 = r.get("reporterCodeIsoAlpha3")
        if iso3 in ISO3_TO_NAME and iso3 not in out:
            out[iso3] = r["reporterCode"]
    missing = set(ISO3_TO_NAME) - set(out)
    if missing:
        raise RuntimeError(f"Comtrade reference lookup missing codes for: {missing}")
    return out


def _cache_path(freq: str, reporter_code: int, partner_code: int, period: str,
                 flow_code: str, cmd_label: str) -> str:
    return f"{CACHE_DIR}/{freq}_{reporter_code}_{partner_code}_{period}_{flow_code}_{cmd_label}.json"


def _get_cached(freq: str, reporter_code: int, partner_code: int, period: str,
                 flow_code: str = "M", cmd_code: str = CMD_CODES) -> list[dict]:
    cmd_label = "TOTAL" if cmd_code == "TOTAL" else "hs6set"
    path = _cache_path(freq, reporter_code, partner_code, period, flow_code, cmd_label)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)

    params = {
        "reporterCode": reporter_code,
        "partnerCode": partner_code,
        "period": period,
        "cmdCode": cmd_code,
        "flowCode": flow_code,  # M = imports, X = exports (re-exports), as reported by `reporter`
    }
    if COMTRADE_API_KEY:
        url = f"{AUTH_BASE}/{freq}/HS"
        headers = {"Ocp-Apim-Subscription-Key": COMTRADE_API_KEY}
    else:
        url = f"{PREVIEW_BASE}/{freq}/HS"
        headers = {}

    for attempt in range(MAX_RETRIES):
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = BACKOFF_BASE_SECONDS * (2 ** attempt)
            print(f"  {resp.status_code} on {reporter_code}/{partner_code}/{period}, "
                  f"backing off {wait}s (attempt {attempt + 1}/{MAX_RETRIES})")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        body = resp.json()
        if body.get("error"):
            raise RuntimeError(f"Comtrade error for {params}: {body['error']}")
        data = body.get("data", [])
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)
        return data

    raise RuntimeError(
        f"Exceeded {MAX_RETRIES} retries for {reporter_code}/{partner_code}/{period}; "
        f"rerun `make fetch` later to resume from cache."
    )


def fetch_annual_grid(reporter_codes: dict) -> list[dict]:
    """Controlled-origin inflow: USA's EXPORTS (flow=X) to each partner in
    config.CORRIDORS. See the CORRIDORS comment in config.py for why this must be
    flow=X, not flow=M."""
    rows = []
    for corridor in CORRIDORS:
        r_code = reporter_codes[corridor["reporter"]]
        p_code = reporter_codes[corridor["partner"]]
        for year in range(TRADE_START_YEAR, TRADE_END_YEAR + 1):
            rows.extend(_get_cached("A", r_code, p_code, str(year), flow_code="X"))
            time.sleep(REQUEST_DELAY_SECONDS)
    return rows


def fetch_annual_world_baseline(reporter_codes: dict) -> list[dict]:
    """Each hub's total imports of the target HS codes from the WORLD (partnerCode=0)."""
    rows = []
    hub_reporters = {"SGP", "HKG"}  # the two entrepot hubs the brief asks about
    for iso3 in hub_reporters:
        r_code = reporter_codes[iso3]
        for year in range(TRADE_START_YEAR, TRADE_END_YEAR + 1):
            rows.extend(_get_cached("A", r_code, 0, str(year)))
            time.sleep(REQUEST_DELAY_SECONDS)
    return rows


def fetch_annual_reexports(reporter_codes: dict) -> list[dict]:
    """Each hub's EXPORTS (flow=X) of the target HS codes to the WORLD and to CHINA
    specifically. World-total minus China-specific = re-exports to non-China
    destinations, the second term in the absorption-gap signal (hub imports minus
    re-exports to non-China minus a domestic-consumption estimate = unexplained
    residual)."""
    rows = []
    hub_reporters = {"SGP", "HKG"}
    for iso3 in hub_reporters:
        r_code = reporter_codes[iso3]
        for partner_iso3, p_code in [("WLD", 0), ("CHN", reporter_codes["CHN"])]:
            for year in range(TRADE_START_YEAR, TRADE_END_YEAR + 1):
                rows.extend(_get_cached("A", r_code, p_code, str(year), flow_code="X"))
                time.sleep(REQUEST_DELAY_SECONDS)
    return rows


def fetch_annual_total_trade_baseline(reporter_codes: dict) -> list[dict]:
    """Each hub's TOTAL import value (cmdCode=TOTAL, all commodities) from the WORLD,
    by year -- the "hub's overall trade growth" control for the rate-of-growth-gap
    signal, so a target-HS-code growth spike can be checked against whether the hub's
    whole economy grew that fast that year (rules out "Singapore trade grew
    generally")."""
    rows = []
    hub_reporters = {"SGP", "HKG"}
    for iso3 in hub_reporters:
        r_code = reporter_codes[iso3]
        for year in range(TRADE_START_YEAR, TRADE_END_YEAR + 1):
            rows.extend(_get_cached("A", r_code, 0, str(year), flow_code="M", cmd_code="TOTAL"))
            time.sleep(REQUEST_DELAY_SECONDS)
    return rows


def fetch_monthly(reporter_iso3: str, partner_iso3: str, months: list[str]) -> list[dict]:
    """Targeted monthly pull, e.g. months=["202209","202210",...]. See module docstring
    for why this is not run for the full grid up front."""
    reporter_codes = _reporter_codes()
    r_code = reporter_codes[reporter_iso3]
    p_code = reporter_codes[partner_iso3]
    rows = []
    for period in months:
        rows.extend(_get_cached("M", r_code, p_code, period))
        time.sleep(REQUEST_DELAY_SECONDS)
    return rows


def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    source = "authenticated /data/v1/get/" if COMTRADE_API_KEY else "unauthenticated /public/v1/preview/"
    print(f"Fetching Comtrade data via {source} endpoint...")

    reporter_codes = _reporter_codes()

    grid = fetch_annual_grid(reporter_codes)
    with open(f"{RAW_DIR}/comtrade_annual_corridors.json", "w") as f:
        json.dump(grid, f, indent=2)
    print(f"Wrote {len(grid)} corridor-year-HS6 rows to comtrade_annual_corridors.json")

    baseline = fetch_annual_world_baseline(reporter_codes)
    with open(f"{RAW_DIR}/comtrade_annual_world_baseline.json", "w") as f:
        json.dump(baseline, f, indent=2)
    print(f"Wrote {len(baseline)} hub-world-year-HS6 rows to comtrade_annual_world_baseline.json")

    reexports = fetch_annual_reexports(reporter_codes)
    with open(f"{RAW_DIR}/comtrade_annual_reexports.json", "w") as f:
        json.dump(reexports, f, indent=2)
    print(f"Wrote {len(reexports)} hub-reexport-year-HS6 rows to comtrade_annual_reexports.json")

    total_baseline = fetch_annual_total_trade_baseline(reporter_codes)
    with open(f"{RAW_DIR}/comtrade_annual_total_baseline.json", "w") as f:
        json.dump(total_baseline, f, indent=2)
    print(f"Wrote {len(total_baseline)} hub-total-trade-year rows to comtrade_annual_total_baseline.json")


if __name__ == "__main__":
    main()
