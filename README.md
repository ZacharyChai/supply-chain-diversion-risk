# Semiconductor Trade Diversion Risk: Singapore and Hong Kong

**Hong Kong's imports of semiconductor manufacturing equipment have grown far
faster than its own economy since 2022, and the share re-exported to China has
climbed from 58% to 91% with no sign of leveling off, but a proper monthly
event-window test shows no spike right after the controls took effect, just a
sustained multi-year trend.** A live, reproducible risk screen over real UN
Comtrade trade data: data pipeline, auditable SQL scoring model, and an analyst
memo that survives its own rule-out checks, including a substantial revision
after external methodology review caught a real flaw in the original design.

![Origin decomposition: Hong Kong semiconductor equipment imports by exporting country](analysis/charts/04_origin_decomposition.png)

**[Read the full memo →](analysis/findings.md)**

## The result

| Tier | Count | HS code x Hub |
|---|---|---|
| High | 0 | - |
| Elevated | 3 | HKG / semiconductor mfg. equipment, SGP / processors & controllers, SGP / inspection instruments |
| Watch | 6 | - |
| Low | 4 | - |

All three "Elevated" flags looked identical on the mechanical four-signal screen.
Driver analysis pulled them apart: Hong Kong's flag holds up under an origin
decomposition (growth concentrated, though not exclusively, in the two most
tightly export-controlled origin countries), an inventory-lag test (the
import/re-export mismatch gets *worse*, not better, at longer lags: an
unresolved anomaly, reported as such rather than explained away), and a
threshold-sensitivity check (the flag survives 100% of 27 reasonable alternative
cutoffs). Singapore's processor/controller flag doesn't hold up the same way:
its growth tracks a real, independently documented $30B+ fab buildout
(GlobalFoundries, UMC, Micron all expanding there), and its China re-export share
is flat, not rising. Reporting findings that *don't* survive scrutiny, right
alongside the one that does, is the point: a screen that flags everything is
worthless.

## What this demonstrates

- **Revising a flawed design after real feedback, not defending it.** An
  external methodology review found that the original risk model's "absorption
  gap" signal double-counted China re-export concentration as two supposedly
  independent pieces of evidence. Rather than patch around it, the signal set
  was redesigned, which surfaced a third genuine finding the flawed version had
  masked. The full before/after reasoning is in
  [`build_risk_score.sql`](src/build_risk_score.sql)'s revision note and
  [`findings.md`](analysis/findings.md) Section 2.
- **Data engineering under real-world constraints**: a resumable fetch pipeline
  (retry-with-backoff on both HTTP error codes and raw network timeouts,
  per-call caching) against a public API that rate-limits aggressively, built
  after discovering live that the "obvious" paid-API path in the original
  project plan was unnecessary.
- **Auditable analytical logic**: the entire four-signal risk model lives in
  one readable SQL file, not a black-box model. Anyone can check the math
  against the conclusion.
- **Catching your own mistakes before they become the finding.** Two
  flow-direction bugs (pulling trade in the wrong direction) were caught in this
  project: one before it reached the scoring stage, one after it had already
  produced an incorrect chart and an incorrect claim in an earlier draft of the
  memo. Both are documented, not quietly fixed and forgotten; see
  [Notes from the build](#notes-from-the-build).
- **Knowing when a finding doesn't hold up, and saying so precisely.** Two of
  the three Elevated-tier flags are reported alongside the reasoning for why
  they're less concerning than the third, rather than either suppressed or
  inflated to match the headline.

## How it works

Four-signal risk score per HS-code/hub combination, run against live UN
Comtrade bilateral trade data and a Federal Register-sourced timeline of BIS/EAR
export control actions since October 2022:

1. **Rate-of-growth gap**: corridor import growth vs. the hub's own overall
   trade growth, pre- vs. post-2022.
2. **Retention gap**: hub imports minus ALL re-exports minus an estimated
   domestic-consumption baseline (destination-agnostic; see the redesign note
   above for why this used to be conflated with signal 3).
3. **China concentration trend**: is the *share* of re-exports going to China
   both elevated and rising, independent of the retention gap's magnitude.
4. **Event proximity**: does growth cluster right after a control date
   (annual approximation; a proper monthly event-window analysis is run
   separately for the top finding).

Two of four signals aligning tiers a row "Elevated"; three or four, "High." Full
logic, with the reasoning behind every threshold (plus a threshold-sensitivity
check in `drivers.py` that tests whether the findings survive reasonable
alternative cutoffs), is in [`src/build_risk_score.sql`](src/build_risk_score.sql).

## Data sources: all live, none synthetic

- **[UN Comtrade](https://comtradeplus.un.org)**: HS6-level bilateral trade,
  2017-2025, pulled from the free public endpoint (no account needed; see
  [`fetch_comtrade.py`](src/fetch_comtrade.py)).
- **[US Census Bureau](https://www.census.gov/foreign-trade/)**: pipeline
  cross-check on the US-reported side ([`fetch_census.py`](src/fetch_census.py)).
- **[Federal Register](https://www.federalregister.gov)**: BIS/EAR rule
  effective dates and Entity List actions, pulled live
  ([`fetch_control_dates.py`](src/fetch_control_dates.py)).
- HS6 codes verified against the current UN Stats Classification Registry, not
  assumed from the original project brief (two of the originally-specified codes
  turned out not to exist under current nomenclature).

## Repository structure

```
supply-chain-diversion-risk/
  data/
    raw/                      <- downloaded Comtrade, Census, and Federal Register pulls
    processed/                <- tidy long-format trade table, event timeline table
  src/
    config.py                 <- HS code list, corridor definitions, API keys (gitignored)
    fetch_comtrade.py         <- pulls bilateral series from Comtrade (free preview endpoint)
    fetch_census.py           <- pulls US export cross-check data (requires CENSUS_API_KEY)
    fetch_control_dates.py    <- pulls BIS/EAR rule effective dates from Federal Register
    build_risk_score.sql      <- diversion risk scoring logic
    drivers.py                <- driver analysis, origin decomposition, sensitivity checks, charts
  analysis/
    findings.md               <- the full memo
    charts/
  requirements.txt
  Makefile
```

## Running it

```
make all
```

Reproduces the full pipeline from a clean clone: fetch, parse, build the event
timeline, score, and driver analysis with charts. No cloud, no external services
beyond the public sources above.

## Notes from the build

A few things that only showed up by checking live sources instead of trusting
assumptions, kept here because they're representative of how the rest of the
project was built:

- The original plan assumed a paid Comtrade API key was required. It wasn't:
  the free public endpoint returns the same data; the paid key only matters at
  higher volume.
- Two of the originally-specified HS codes (`854242`, `854243`) don't exist
  under current WCO nomenclature. Caught by checking the UN Stats registry
  directly rather than trusting the code list as given.
- The Federal Register API's slug for the Bureau of Industry and Security is
  `industry-and-security-bureau`, not the more intuitive
  `bureau-of-industry-and-security`, found by querying the agency list, not
  guessing.
- The Census trade API silently rejects a plausible-looking `"YYYY-MM:YYYY-MM"`
  date-range parameter with a 400 error; a bare year works.
- **Two separate flow-direction bugs**, caught at different stages. The first
  (pulling "US imports from Singapore" instead of "US exports to Singapore") was
  caught before it reached the scoring stage. The second was subtler: the
  monthly-data helper used for the event-window chart silently defaulted to the
  same wrong direction, producing a chart and a "sharp spike right after the
  controls" claim that both looked plausible and were both wrong, caught by
  cross-checking a monthly sum against a known-correct annual figure ($1.7M vs.
  the correct $49.5M, a 30x gap that a smaller error could have hidden). The
  fetch helper's `flow_code` parameter is no longer defaulted, specifically so
  this class of bug can't recur silently.
- The original three-signal risk model conflated two different pieces of
  evidence into one number (see "What this demonstrates" above), caught by
  external review, not internally, and fixed by redesigning the signal rather
  than patching the symptom.
- The free Comtrade endpoint's rate-limit backoff only retried on HTTP error
  codes; a raw network read-timeout crashed a ~120-call fetch after 67 calls had
  already succeeded. Fixed to retry on connection-level exceptions too, not just
  4xx/5xx status codes.

## Limitations

This is a screening methodology, not a finding of wrongdoing, and its error
sources run in both directions: aggregate customs data structurally
*understates* diversion (a shipment re-labeled in transit wouldn't appear as a
hub-to-China flow at all), while the residual-based screening assumptions
(a zero domestic-consumption placeholder, import/export valuation differences,
inventory-timing effects) can produce false positives. The Census cross-check
confirms this pipeline parses the source data correctly, not that a second,
independent agency corroborates the finding; a genuinely independent check
(Singapore's own SingStat, or Hong Kong's own trade statistics) remains open.
Full discussion (including the origin decomposition, inventory-lag test, and
threshold-sensitivity results, and exactly what would and wouldn't change the
headline finding) is in [`analysis/findings.md`](analysis/findings.md).
