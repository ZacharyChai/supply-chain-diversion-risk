# Semiconductor Trade Diversion Risk: Singapore and Hong Kong

*UN Comtrade bilateral trade data, HS6-level, 2017-2025 (2026 excluded — incomplete
reporting year), against a live-pulled timeline of BIS/EAR export control actions
since October 2022.*

## 1. Recommendation

**Flag Hong Kong's imports of semiconductor manufacturing equipment (HS 848620) for
enhanced due diligence; do not flag Singapore's processor/controller growth (HS
854231) on the current evidence.** Both HS-code/hub combinations scored "Elevated"
on the mechanical three-signal screen, but they survive the rule-out analysis very
differently. Hong Kong's total imports of semiconductor manufacturing machines from
the world grew roughly **10x in three years** — from $304.6M (2022) to $3.04B
(2025) — while its re-exports of the same equipment to China specifically grew even
faster, from $1.22B (2022) to $4.58B (2025), now **exceeding the same-year import
total** and rising from 76% to 94% of all of Hong Kong's re-exports of this
equipment. Hong Kong has no meaningful domestic semiconductor-fab industry to
explain that volume as internal use. Singapore's growth in processor/controller
imports, by contrast, tracks a well-documented, real domestic capacity buildout
(GlobalFoundries' $4B Woodlands expansion, UMC's $5B new fab, Micron's $24B
greenfield fab announced January 2026), and its share of re-exports going to China
is modest (13-22%) and *not* rising. The mechanical screen flagged both; the driver
analysis says only one of them holds up.

## 2. The screen

Every HS-code/hub combination was scored on three signals — rate-of-growth gap
(corridor growth vs. the hub's own overall trade growth), absorption gap (imports
minus re-exports to non-China destinations minus a domestic-consumption estimate),
and event proximity (does growth cluster right after a BIS control date) — and
tiered by how many of the three point the same direction. Full logic in
[`src/build_risk_score.sql`](../src/build_risk_score.sql).

| Tier | Count | HS x Hub |
|---|---|---|
| High | 0 | — |
| Elevated | 2 | HKG/848620, SGP/854231 |
| Watch | 8 | SGP/903141, HKG/854232, HKG/854231, HKG/903141, HKG/854239, SGP/854239, SGP/854233, HKG/854233 |
| Low | 2 | SGP/848620, SGP/854232 |

![Tier distribution](charts/01_tier_distribution.png)
![Rate-of-growth gap by HS code x hub](charts/02_growth_gap.png)

No combination hit all three signals at once — a genuinely useful negative result.
This is a screen that found two things worth a closer look, not a dataset that
screams diversion everywhere you point it, which is itself evidence the method
isn't just mechanically flagging every growing trade line.

## 3. Driver analysis: Hong Kong / HS 848620 (semiconductor manufacturing machines)

**The growth is real, large, and increasingly concentrated on China — and Hong
Kong's own explanation for absorbing it domestically doesn't exist.**

- Total HK imports of HS 848620 from the world: $78.7M (2017) → $504.4M (2021) →
  $304.6M (2022, a dip) → **$1.08B (2023) → $2.11B (2024) → $3.04B (2025)**.
- HK's re-exports of the same code to China: $60.6M (2017) → $695.9M (2021) →
  $1.22B (2022) → $1.15B (2023) → $2.00B (2024) → **$4.58B (2025)**.
- China's share of HK's total re-exports of this equipment: 39% (2018) → 63%
  (2021) → 76% (2022) → 88% (2023) → 91% (2024) → **94% (2025)**. A steadily
  rising, now-dominant concentration — the opposite of what you'd expect if
  Hong Kong were diversifying its re-export customer base *away* from China in
  response to controls.
- The USA-reported bilateral corridor (USA → HKG, the slice of this growth
  directly attributable to declared US-origin equipment) shows the same
  direction at smaller scale: a 73% level increase in average annual value
  post-2022 vs. pre-2022, against Hong Kong's overall trade growing only 18%
  over the same comparison — and a sharp, well-timed monthly spike (to ~$920K,
  versus a prior peak of ~$530K) in the months immediately following the
  October 2022 control package's effective date.

![HKG 848620 monthly trade vs. BIS control dates](charts/03_top_corridor_timeline.png)

**Ruling out the alternatives:**
- *Legitimate domestic demand?* Hong Kong has no meaningful wafer-fab industry —
  its only active semiconductor manufacturing projects are small, early-stage SiC
  and GaN pilot lines (a ~$900M SiC fab targeting 240,000 wafers/year by 2028, a
  GaN pilot line targeting 10,000 units/year by 2027), nothing on the scale that
  would absorb billions of dollars a year in fab-grade manufacturing equipment.
  This alternative does not hold.
- *Legitimate re-export diversification to non-China buyers?* The opposite is
  happening — China's share of Hong Kong's re-exports of this equipment has risen
  every year since 2018 and now sits at 94%. This alternative does not hold either.
- One honest wrinkle: HK's re-exports of this code *exceed* same-year imports in
  2025 ($4.87B re-exported vs. $3.04B imported). The more plausible explanation is
  inventory/bonded-warehouse timing lag on capital equipment (imported one year,
  installed or re-shipped later) rather than a reporting error — but it does mean
  the precise annual absorption-gap dollar figure should be read as directional,
  not literal.

## 4. Driver analysis: Singapore / HS 854231 (processors and controllers)

**This one doesn't survive the rule-out.** The mechanical screen flagged it because
USA→Singapore exports of this code jumped to $436M in 2025 (vs. a $200M pre-2022
average) and because that growth clustered near BIS control dates. But:

- Singapore's re-exports of this code to China are a modest, *falling* share of its
  total re-exports: 19.2% (2023) → 21.5% (2024) → **13.5% (2025)** — the opposite
  of the concentration pattern seen in the Hong Kong finding above.
- Singapore's total imports of this code from the world are also growing fast
  ($11.5B in 2017 to $62.3B in 2025), consistent with a real, independently
  documented capacity buildout: GlobalFoundries' $4B Woodlands campus expansion
  (+300,000 wafers/year), UMC's $5B new fab (targeting >1M wafers/year by 2026),
  and Micron's newly-announced $24B Singapore fab (groundbreaking January 2026).
  Finished processors and controllers moving through Singapore's ecosystem for
  assembly, test, and packaging — not just pass-through re-export — is the more
  likely explanation for import growth this large.
- The absorption-gap signal for this row is *negative* ($-2.1B): Singapore's
  re-exports of this code already exceed its same-year imports, before any
  domestic-consumption offset. That's consistent with Singapore acting as a
  genuine value-adding production location for this code, not merely an entrepot —
  a distinction Hong Kong's negligible fab base doesn't offer as an explanation.

**Conclusion: keep on the Watch list, not Elevated.** The volume growth is real,
but the legitimate-demand and legitimate-re-export explanations both hold up here,
which is exactly the outcome the rule-out step is supposed to produce when the
underlying activity isn't diversion.

## 5. Data-integrity check: Census vs. Comtrade

The US Census Bureau's export data (the US-reported side of these same corridors)
was pulled and compared against the Comtrade figures used above. The two match
closely: **HKG/848620 matches to the exact dollar for every year 2017-2025**, and
SGP/854231 matches within 0.001%. This is a genuine, useful result, but it should
be read precisely — it confirms this project's fetch/parse pipeline correctly
reproduced the underlying US Census data (no transcription or unit-conversion
errors), **not** an independent second-methodology corroboration. Comtrade's
USA-reported figures are themselves sourced from the US Census Bureau, so an
exact match is closer to a pipeline-integrity check than a cross-agency
validation. A genuinely independent check would need Singapore's or Hong Kong's
*own* customs statistics (SingStat, for example) reporting the same corridor from
the receiving side — not run in this pass; see Limitations.

## 6. Recommendation, for two audiences

**For an authorized distributor's compliance function:** open enhanced due
diligence on Hong Kong counterparties transacting in HS 848620 (and related
semiconductor manufacturing/inspection equipment codes) where China is the
declared or likely re-export destination. Specifically: verify end-use
certificates and re-export licensing documentation for shipments routed through
Hong Kong in this category, and treat a customer's re-export mix concentrating
further toward China as a standing risk indicator worth periodic re-checking, not
a one-time screen. Singapore counterparties in HS 854231 do not currently warrant
the same elevated scrutiny — standard periodic monitoring is proportionate, given
the legitimate-demand explanation the driver analysis supports.

**For a credit analyst assessing geopolitical/counterparty risk exposure:** a
portfolio with exposure to Hong Kong-domiciled electronics/semiconductor-equipment
trading counterparties carries rising regulatory and reputational tail risk in this
specific corridor — the trend (rising China concentration, absence of a
domestic-use explanation) has been consistent for three consecutive years, not a
one-off spike, and BIS enforcement activity in this space has itself been
increasing (17 semiconductor-relevant rule actions since October 2022 in this
pull alone). Singapore-domiciled counterparties in the processor/controller trade
should be underwritten primarily on the fundamentals of the real capacity buildout
under way there (multi-billion-dollar fab investments create their own
counterparty-concentration and execution risk worth tracking), not on a diversion
narrative this data does not support.

## 7. Limitations

- **This is a screening methodology, not a finding of wrongdoing.** Correlation
  in aggregate trade data is not proof of illegal transshipment. Every flag above
  should be read as "worth a closer look," not "confirmed."
- **Aggregate customs data cannot see through a single re-export step.** A
  shipment that transits Hong Kong or Singapore and is re-labeled before
  continuing to China would not appear as a Hong Kong-to-China or
  Singapore-to-China flow at all in this data. This project structurally
  *understates* diversion rather than overstates it.
- **HS classification is self-reported and inconsistent across countries at the
  6-digit level**, and Comtrade serves each year under whichever HS revision
  (H4/H5/H6) was in effect for that reporting period — the code label is stable
  for this project's HS6 codes across those revisions, but comparability at the
  margins isn't guaranteed.
- **The domestic-consumption estimate in the absorption-gap signal is currently a
  0-placeholder for both hubs**, not a researched dollar figure — see
  `build_risk_score.sql`'s header comment. Qualitative research (Section 3-4
  above) supports treating that as a reasonable estimate for Hong Kong (negligible
  real fab capacity) but a poor one for Singapore's finished-IC codes specifically
  (real production/value-add activity exists); this is why the Singapore
  absorption-gap figures are not leaned on as evidence in Section 4.
- **The event-proximity signal here is an annual-grain approximation.** Only the
  single highest-tier corridor (Hong Kong/848620) was checked against monthly
  data; the other 11 HS-code/hub combinations were not, so a real but
  annually-invisible event-clustering pattern elsewhere in the grid would not
  have been caught by this pass.
- **The Federal Register pull's "semiconductor-relevant" flag is a title
  keyword filter**, not a read of each rule's full text or the Entity List
  itself — a broad "Entity List" action is tracked separately and treated as
  lower-confidence context, not floor-level truth about which specific entities
  were added.
- **The Census cross-check (Section 5) validates pipeline integrity, not
  independent corroboration** — Comtrade's USA-reported figures are themselves
  sourced from Census, so the exact-dollar match confirms this project fetched
  and parsed the data correctly, not that two independent agencies agree.
  **SingStat (Singapore's own statistics office) and Hong Kong's own trade
  statistics — genuinely independent, receiving-side sources — were not pulled
  in this pass** and remain the real open cross-validation step.
- **Domestic-consumption estimates, where used, are directional**, built from
  public fab-capacity reporting (EDB press releases, company announcements), not
  firm-level production or import records.

None of the above changes the direction of the Hong Kong/848620 finding — if
anything, several of these limitations (the single-re-export blind spot
especially) suggest the real picture is at least as concerning as what's
documented here, not less. But they bound how precisely the numbers above should
be read, and none of them license treating "Elevated" as "confirmed."
