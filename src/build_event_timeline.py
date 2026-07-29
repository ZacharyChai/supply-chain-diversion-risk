"""Merge the Federal Register BIS/EAR pull into a per-year event-count table used by
the event-proximity signal in build_risk_score.sql.

The raw pull (fetch_control_dates.py) searches broad terms ("semiconductor",
"advanced computing", "Entity List") against BIS's own Federal Register output,
which also catches unrelated BIS rulemaking that happens to share a search term --
e.g. drone-export streamlining, or silencer/suppressor EAR classification, turned up
in the live pull alongside genuine semiconductor rules. A title-keyword filter here
narrows to the semiconductor-relevant subset. Generic "Entity List" additions/
revisions are kept as a SEPARATE lower-confidence flag rather than folded into the
same relevant=True bucket, because a title alone doesn't say whether the entities
added are semiconductor-supply-chain parties -- that would need each rule's full
text or the Entity List itself, out of scope for this pass. State this explicitly
in findings.md: the event-proximity signal is weighted toward title-confirmed
semiconductor rules, with Entity List actions as corroborating-but-unverified
context, not floor-level truth.
"""

import json
import os
import sqlite3

import pandas as pd

from config import BIS_CONTROL_DATES_PATH, DB_PATH, PROCESSED_DIR

SEMICONDUCTOR_KEYWORDS = [
    "semiconductor", "advanced computing", "integrated circuit",
    "microelectronic", "chip", "wafer", "lithography", "gaas", "hbm",
]


def classify(title: str) -> dict:
    lower = title.lower()
    return {
        "semiconductor_relevant": any(kw in lower for kw in SEMICONDUCTOR_KEYWORDS),
        "entity_list_action": "entity list" in lower,
    }


def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    with open(BIS_CONTROL_DATES_PATH) as f:
        docs = json.load(f)

    rows = []
    for d in docs:
        flags = classify(d["title"])
        rows.append({
            "document_number": d["document_number"],
            "title": d["title"],
            "publication_date": d["publication_date"],
            "effective_on": d["effective_on"] or d["publication_date"],
            "type": d["type"],
            "html_url": d["html_url"],
            **flags,
        })

    events = pd.DataFrame(rows)
    events["effective_year"] = pd.to_datetime(events["effective_on"]).dt.year

    conn = sqlite3.connect(DB_PATH)
    events.to_sql("bis_events", conn, if_exists="replace", index=False)
    conn.commit()
    conn.close()

    events.to_csv(f"{PROCESSED_DIR}/bis_events.csv", index=False)

    relevant = events["semiconductor_relevant"].sum()
    entity = events["entity_list_action"].sum()
    print(f"Wrote {len(events)} BIS/EAR events "
          f"({relevant} title-confirmed semiconductor-relevant, "
          f"{entity} Entity List actions) to {DB_PATH} and bis_events.csv")


if __name__ == "__main__":
    main()
