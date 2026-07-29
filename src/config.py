"""Shared configuration.

API keys are read from environment variables, never hardcoded. Copy .env.example to
.env (gitignored) or export them in your shell before running `make fetch`.
"""

import os

# --- Secrets (env vars, not committed) ----------------------------------------
COMTRADE_API_KEY = os.environ.get("COMTRADE_API_KEY", "")
CENSUS_API_KEY = os.environ.get("CENSUS_API_KEY", "")  # optional: Census intltrade
                                                          # works unauthenticated at
                                                          # low volume, but a key
                                                          # raises the rate limit.

# federalregister.gov requires no auth.

# --- Paths (relative to repo root) --------------------------------------------
RAW_DIR = "data/raw"
PROCESSED_DIR = "data/processed"
DB_PATH = "data/processed/trade.db"

REQUEST_DELAY_SECONDS = 1.0  # be a polite citizen on all three public APIs;
                              # Comtrade's free preview endpoint 429s aggressively

# --- HS6 code registry ----------------------------------------------------------
# Verified live against the UN Stats Classification Registry
# (https://unstats.un.org/unsd/classifications/Econ/Detail/EN/2089/8542) on
# 2026-07-29, NOT pulled from memory — see project brief's warning that these
# groupings get revised. Heading 8542 has exactly five HS6 children in both HS2017
# and HS2022: 854231/32/33/39/90. The brief's original list included 854242 and
# 854243, which do not exist under current WCO nomenclature (854239 already covers
# "other ICs, n.e.c."), so they are dropped here rather than pulled forward as-is.
HS_CODES = {
    "854231": "Processors and controllers (whether or not combined with memories, "
              "converters, logic circuits, amplifiers, clock/timing circuits)",
    "854232": "Memories",
    "854233": "Amplifiers",
    "854239": "Other electronic integrated circuits, n.e.c.",
    "848620": "Machines and apparatus for the manufacture of semiconductor devices "
              "or of electronic integrated circuits",
    "903141": "Optical instruments/appliances for inspecting semiconductor wafers "
              "or devices, or for inspecting photomasks/reticles",
}

# --- Corridor registry -----------------------------------------------------------
# reporter = the country whose customs data we're reading; partner = counterparty.
# Controlled-origin inflow corridors: reporter=USA, so these are pulled with
# flowCode="X" (USA's EXPORTS to the partner) -- reporting from the US side, as the
# brief specifies ("Reporter = USA, Partner = SGP/HKG/CHN"). Do NOT read these as
# flowCode="M"; that would be "USA's imports from partner", the reverse flow.
# Hub->China re-export corridors (Singapore->China, Hong Kong->China) are NOT listed
# here -- they're pulled by fetch_annual_reexports() as reporter=hub, partner=CHN,
# flowCode="X" (hub's exports/re-exports to China), which is the same physical
# quantity the absorption-gap signal already needs; a duplicate entry here would
# just be the identical call under a different label.
CORRIDORS = [
    {"reporter": "USA", "partner": "SGP", "label": "US -> Singapore"},
    {"reporter": "USA", "partner": "HKG", "label": "US -> Hong Kong"},
    {"reporter": "USA", "partner": "CHN", "label": "US -> China (direct, baseline)"},
]

# UN Comtrade Plus reporter/partner codes are ISO numeric, not alpha-3. Comtrade
# Plus's own /public/v1/getReference endpoint is the authoritative source for these
# and is queried at fetch time rather than hardcoded here (M49 codes are stable, but
# looking them up live avoids yet another silently-stale table in this file).
ISO3_TO_NAME = {
    "USA": "United States of America",
    "SGP": "Singapore",
    "HKG": "China, Hong Kong SAR",
    "CHN": "China",
}

TRADE_START_YEAR = 2017
TRADE_END_YEAR = 2026

# --- Federal Register pull ------------------------------------------------------
FEDERAL_REGISTER_API = "https://www.federalregister.gov/api/v1/articles.json"
BIS_CONTROL_DATES_PATH = f"{RAW_DIR}/bis_control_dates.json"
# BIS export control tightening on advanced semiconductors began in earnest here;
# see project brief. Pulled live each run — do not hardcode specific rule dates.
BIS_SEARCH_START_DATE = "2022-10-01"
# Verified live against https://www.federalregister.gov/api/v1/agencies.json on
# 2026-07-29 — the FR API's slug for BIS is "industry-and-security-bureau", not the
# more intuitive "bureau-of-industry-and-security".
BIS_AGENCY_SLUG = "industry-and-security-bureau"
