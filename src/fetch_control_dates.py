"""Pull BIS/EAR rule effective dates from the Federal Register public API.

Builds the event timeline overlaid on the trade series in build_risk_score.sql. No
auth required. Rule/Entity-List dates move fast enough that a live pull is worth the
extra step over hardcoding from memory (confirmed against the API's own agency
registry -- see config.BIS_AGENCY_SLUG -- rather than assumed).
"""

import json
import os
import time

import requests

from config import (
    BIS_AGENCY_SLUG,
    BIS_CONTROL_DATES_PATH,
    BIS_SEARCH_START_DATE,
    FEDERAL_REGISTER_API,
    RAW_DIR,
    REQUEST_DELAY_SECONDS,
)

FIELDS = [
    "document_number",
    "title",
    "publication_date",
    "effective_on",
    "html_url",
    "type",
    "agencies",
]

# Terms chosen to catch the rule families named in the project brief: the Oct 2022
# advanced-computing/semiconductor-manufacturing controls, subsequent tightenings,
# and Entity List actions naming semiconductor-relevant parties.
SEARCH_TERMS = [
    "semiconductor",
    "advanced computing",
    "Entity List",
]


def fetch_term(term: str) -> list[dict]:
    results = []
    page = 1
    while True:
        params = {
            "conditions[term]": term,
            "conditions[agencies][]": BIS_AGENCY_SLUG,
            "conditions[publication_date][gte]": BIS_SEARCH_START_DATE,
            "conditions[type][]": "RULE",
            "per_page": 100,
            "page": page,
            "order": "oldest",
        }
        # requests needs repeated fields[] as a list of tuples, not a dict value
        query = list(params.items()) + [("fields[]", f) for f in FIELDS]
        resp = requests.get(FEDERAL_REGISTER_API, params=query, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data["results"])
        if page >= data["total_pages"]:
            break
        page += 1
        time.sleep(REQUEST_DELAY_SECONDS)
    return results


def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    by_doc = {}
    for term in SEARCH_TERMS:
        for doc in fetch_term(term):
            by_doc[doc["document_number"]] = doc
        time.sleep(REQUEST_DELAY_SECONDS)

    events = sorted(by_doc.values(), key=lambda d: d["publication_date"])
    with open(BIS_CONTROL_DATES_PATH, "w") as f:
        json.dump(events, f, indent=2)

    print(f"Wrote {len(events)} BIS/EAR rule documents to {BIS_CONTROL_DATES_PATH}")


if __name__ == "__main__":
    main()
