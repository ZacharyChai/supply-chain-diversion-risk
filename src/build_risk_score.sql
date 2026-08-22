-- Three-signal semiconductor diversion risk score, per HS6 code x hub (SGP/HKG).
-- Auditable by a compliance reader, not a black box -- same rationale as
-- cre-credit-risk's segment.sql. Run via `sqlite3 data/processed/trade.db < this file`.
--
-- Inputs (written by build_trade_table.py / build_event_timeline.py):
--   trade(reporter_iso3, partner_iso3, period, year, hs6, hs_revision,
--         trade_value_usd, qty, flowCode, series)
--     series='corridor'            : USA (reporter) -> {SGP,HKG,CHN} (partner), flow=X
--                                     (USA's exports -- the controlled-origin inflow
--                                     into the hub, or the direct-to-China baseline)
--     series='world_baseline'      : hub (reporter) -> WLD, flow=M (hub's total
--                                     imports of the target HS codes, any origin)
--     series='reexport'            : hub (reporter) -> {WLD,CHN}, flow=X (hub's
--                                     exports/re-exports of the target HS codes)
--     series='total_trade_baseline': hub (reporter) -> WLD, flow=M, hs6='TOTAL'
--                                     (hub's whole-economy import growth control)
--   bis_events(document_number, title, publication_date, effective_on, type,
--              html_url, semiconductor_relevant, entity_list_action, effective_year)
--
-- REVISION NOTE (v2): the original version of this signal set defined "absorption
-- gap" as imports minus RE-EXPORTS-TO-NON-CHINA minus domestic consumption. With
-- domestic consumption at its 0-placeholder, that reduces algebraically to
-- (imports - total_reexports + china_reexports) -- meaning a larger China
-- re-export stream MECHANICALLY inflated the absorption-gap residual, while
-- China's re-export concentration was ALSO used as separate qualitative rule-out
-- evidence in the driver analysis. Same underlying phenomenon, counted twice
-- across two supposedly independent signals. Caught in external review; fixed by
-- splitting into two genuinely independent measurements:
--   - retention_gap: imports minus ALL re-exports minus domestic consumption --
--     "how much of what came in didn't leave at all" (destination-agnostic).
--   - china_concentration: is the SHARE of re-exports going to China elevated
--     and RISING over time -- independent of the retention gap's magnitude.
-- A hub could score high on one signal and low on the other (e.g., heavy
-- domestic retention with re-exports evenly spread across destinations, or thin
-- retention with re-exports overwhelmingly concentrated on China) -- exactly the
-- kind of case the old formula couldn't distinguish.
--
-- PRE/POST WINDOW: split at 2022 (the Oct-2022 BIS package is the first and largest
-- control action in scope; see project brief). pre = 2017-2021, post = 2023-latest;
-- 2022 itself is excluded from both windows since the controls took effect mid-year
-- (Oct 2022) and averaging a split year into either side would blur the comparison.
--
-- DOMESTIC-CONSUMPTION ESTIMATE: see domestic_consumption_estimate CTE below --
-- a 0-placeholder, qualitatively defensible for Hong Kong (negligible real fab
-- capacity) but understating Singapore's genuine domestic demand -- named
-- explicitly in findings.md rather than presented as a precise figure.

DROP TABLE IF EXISTS risk_score;

CREATE TEMP TABLE corridor_yearly AS
SELECT
    partner_iso3 AS hub,       -- SGP, HKG, or CHN (direct baseline)
    hs6,
    year,
    SUM(trade_value_usd) AS value_usd
FROM trade
WHERE series = 'corridor'
GROUP BY partner_iso3, hs6, year;

CREATE TEMP TABLE total_baseline_yearly AS
SELECT reporter_iso3 AS hub, year, SUM(trade_value_usd) AS value_usd
FROM trade
WHERE series = 'total_trade_baseline'
GROUP BY reporter_iso3, year;

-- === Signal 1: rate-of-growth gap ===================================================
CREATE TEMP TABLE corridor_window_growth AS
SELECT
    hub, hs6,
    AVG(CASE WHEN year BETWEEN 2017 AND 2021 THEN value_usd END) AS pre_avg,
    AVG(CASE WHEN year >= 2023 THEN value_usd END) AS post_avg
FROM corridor_yearly
GROUP BY hub, hs6;

CREATE TEMP TABLE baseline_window_growth AS
SELECT
    hub,
    AVG(CASE WHEN year BETWEEN 2017 AND 2021 THEN value_usd END) AS pre_avg,
    AVG(CASE WHEN year >= 2023 THEN value_usd END) AS post_avg
FROM total_baseline_yearly
GROUP BY hub;

CREATE TEMP TABLE growth_gap AS
SELECT
    c.hub, c.hs6,
    c.pre_avg AS corridor_pre_avg_usd,
    c.post_avg AS corridor_post_avg_usd,
    (c.post_avg - c.pre_avg) / NULLIF(c.pre_avg, 0) AS corridor_growth_rate,
    (b.post_avg - b.pre_avg) / NULLIF(b.pre_avg, 0) AS hub_total_trade_growth_rate,
    ((c.post_avg - c.pre_avg) / NULLIF(c.pre_avg, 0))
        - ((b.post_avg - b.pre_avg) / NULLIF(b.pre_avg, 0)) AS growth_gap_score
FROM corridor_window_growth c
JOIN baseline_window_growth b ON b.hub = c.hub
WHERE c.hub IN ('SGP', 'HKG');  -- direct-to-China (CHN) is reported for context, not scored
-- NOTE (external review): this compares a single-origin corridor (USA -> hub)
-- against the hub's ALL-ORIGIN total trade growth -- three different universes
-- (US->hub, World->hub, hub->China) that this signal does not fully separate.
-- An origin decomposition (US/Japan/Netherlands/Taiwan/Korea -> hub) for the
-- top-tier finding is run separately -- see drivers.py's origin_decomposition()
-- and analysis/findings.md Section 3a.

-- === Signal 2: retention gap (destination-agnostic; was "absorption gap") ===========
CREATE TEMP TABLE hub_imports AS
SELECT reporter_iso3 AS hub, hs6, year, SUM(trade_value_usd) AS value_usd
FROM trade WHERE series = 'world_baseline'
GROUP BY reporter_iso3, hs6, year;

CREATE TEMP TABLE hub_reexports AS
SELECT
    reporter_iso3 AS hub, hs6, year,
    SUM(CASE WHEN partner_iso3 = 'WLD' THEN trade_value_usd ELSE 0 END) AS reexport_world_usd,
    SUM(CASE WHEN partner_iso3 = 'CHN' THEN trade_value_usd ELSE 0 END) AS reexport_china_usd
FROM trade WHERE series = 'reexport'
GROUP BY reporter_iso3, hs6, year;

-- PLACEHOLDER -- 0 for both hubs until populated from EDB (Singapore) / published
-- fab capacity figures. Hong Kong has no meaningful wafer-fab industry, so 0 there
-- is a defensible estimate, not just a placeholder; Singapore genuinely has fab
-- capacity (GlobalFoundries, Micron, UMC among others) and 0 there understates
-- domestic use -- meaning Singapore's retention-gap residual is the one most
-- likely to overstate diversion risk until this is filled in with real figures.
CREATE TEMP TABLE domestic_consumption_estimate (hub TEXT, usd REAL);
INSERT INTO domestic_consumption_estimate VALUES ('SGP', 0), ('HKG', 0);

CREATE TEMP TABLE retention_gap AS
SELECT
    i.hub, i.hs6, i.year,
    i.value_usd AS hub_imports_usd,
    COALESCE(r.reexport_world_usd, 0) AS reexport_total_usd,
    d.usd AS domestic_consumption_estimate_usd,
    i.value_usd - COALESCE(r.reexport_world_usd, 0) - d.usd AS retention_gap_usd
FROM hub_imports i
LEFT JOIN hub_reexports r ON r.hub = i.hub AND r.hs6 = i.hs6 AND r.year = i.year
JOIN domestic_consumption_estimate d ON d.hub = i.hub
WHERE i.year >= 2023;  -- post-control period only

CREATE TEMP TABLE retention_gap_latest AS
SELECT hub, hs6, AVG(retention_gap_usd) AS retention_gap_avg_usd
FROM retention_gap
GROUP BY hub, hs6;

-- === Signal 3: China re-export concentration trend (NEW -- replaces the old ========
-- === non-China carve-out that double-counted with the qualitative narrative) =======
-- Is the SHARE of the hub's re-exports going to China both elevated and RISING,
-- independent of the total volume retained. A hub with heavy retention gap but a
-- flat or falling China share (e.g., legitimately diversifying re-export
-- customers) reads differently than one with a rising China share regardless of
-- retention -- these are two distinct questions this split lets the model ask
-- separately instead of conflating into one number.
CREATE TEMP TABLE china_share_yearly AS
SELECT
    hub, hs6, year,
    reexport_china_usd * 1.0 / NULLIF(reexport_world_usd, 0) AS china_share
FROM hub_reexports;

CREATE TEMP TABLE china_concentration AS
SELECT
    hub, hs6,
    AVG(CASE WHEN year BETWEEN 2017 AND 2021 THEN china_share END) AS china_share_pre,
    AVG(CASE WHEN year >= 2023 THEN china_share END) AS china_share_post,
    AVG(CASE WHEN year >= 2023 THEN china_share END)
        - AVG(CASE WHEN year BETWEEN 2017 AND 2021 THEN china_share END) AS china_concentration_score
FROM china_share_yearly
GROUP BY hub, hs6;

-- === Signal 4: event proximity (unchanged annual-grain approximation; see =========
-- === drivers.py for the monthly event-window analysis run on the top finding) =====
CREATE TEMP TABLE event_years AS
SELECT DISTINCT effective_year AS year
FROM bis_events
WHERE semiconductor_relevant = 1;

CREATE TEMP TABLE yoy_growth AS
SELECT
    hub, hs6, year,
    value_usd,
    (value_usd - LAG(value_usd) OVER (PARTITION BY hub, hs6 ORDER BY year))
        / NULLIF(LAG(value_usd) OVER (PARTITION BY hub, hs6 ORDER BY year), 0) AS yoy_growth_rate
FROM corridor_yearly
WHERE hub IN ('SGP', 'HKG');

CREATE TEMP TABLE event_proximity AS
SELECT
    y.hub, y.hs6,
    AVG(CASE WHEN e.year IS NOT NULL THEN y.yoy_growth_rate END) AS avg_growth_in_event_years,
    AVG(CASE WHEN e.year IS NULL THEN y.yoy_growth_rate END) AS avg_growth_in_other_years,
    AVG(CASE WHEN e.year IS NOT NULL THEN y.yoy_growth_rate END)
        - AVG(CASE WHEN e.year IS NULL THEN y.yoy_growth_rate END) AS event_proximity_score
FROM yoy_growth y
LEFT JOIN event_years e ON e.year = y.year - 1  -- growth attributed to the year AFTER an event's effective year
GROUP BY y.hub, y.hs6;
-- CAVEAT (external review, kept here not just in prose): nine annual observations
-- is a fragile base for an event-effect estimate, BIS control dates are not
-- exogenous to trade trends already underway, and this groups heterogeneous rule
-- types (equipment controls, advanced-computing controls, Entity List actions)
-- into one "semiconductor_relevant" bucket. Treat this signal as suggestive, not
-- as a causal estimate -- the monthly event-window analysis in drivers.py is the
-- more defensible version, run on the flagged top corridor as investigative
-- follow-up, not as part of this ex-ante screen.

-- === Combine + tier (now FOUR signals; threshold sensitivity checked separately in ==
-- === drivers.py's sensitivity_table(), since these cutoffs are analyst choices, ====
-- === not calibrated values) =========================================================
CREATE TABLE risk_score AS
SELECT
    g.hub,
    g.hs6,
    ROUND(g.corridor_growth_rate, 3)          AS corridor_growth_rate,
    ROUND(g.hub_total_trade_growth_rate, 3)   AS hub_total_trade_growth_rate,
    ROUND(g.growth_gap_score, 3)              AS growth_gap_score,
    ROUND(rg.retention_gap_avg_usd, 0)        AS retention_gap_avg_usd,
    ROUND(cc.china_share_pre, 3)              AS china_share_pre,
    ROUND(cc.china_share_post, 3)             AS china_share_post,
    ROUND(cc.china_concentration_score, 3)    AS china_concentration_score,
    ROUND(e.event_proximity_score, 3)         AS event_proximity_score,
    -- Tiering rule, stated plainly so a reader can check it against the numbers above.
    -- Each signal answers a genuinely different question:
    --   growth_gap_score > 0.15        -- corridor grew faster than the hub's own economy
    --   retention_gap_avg_usd > 0      -- meaningful volume isn't being re-exported at all
    --   china_concentration_score>0.05 -- of what IS re-exported, China's share is rising
    --   event_proximity_score > 0.10   -- growth clusters right after a control date
    -- HIGH = 3-4 signals agree. ELEVATED = 2. WATCH = 1. LOW = 0.
    CASE
        WHEN (g.growth_gap_score > 0.15) + (rg.retention_gap_avg_usd > 0)
             + (cc.china_concentration_score > 0.05) + (e.event_proximity_score > 0.10) >= 3 THEN 'High'
        WHEN (g.growth_gap_score > 0.15) + (rg.retention_gap_avg_usd > 0)
             + (cc.china_concentration_score > 0.05) + (e.event_proximity_score > 0.10) = 2 THEN 'Elevated'
        WHEN (g.growth_gap_score > 0.15) + (rg.retention_gap_avg_usd > 0)
             + (cc.china_concentration_score > 0.05) + (e.event_proximity_score > 0.10) = 1 THEN 'Watch'
        ELSE 'Low'
    END AS risk_tier
FROM growth_gap g
JOIN retention_gap_latest rg ON rg.hub = g.hub AND rg.hs6 = g.hs6
JOIN china_concentration cc ON cc.hub = g.hub AND cc.hs6 = g.hs6
JOIN event_proximity e ON e.hub = g.hub AND e.hs6 = g.hs6
ORDER BY
    CASE risk_tier WHEN 'High' THEN 1 WHEN 'Elevated' THEN 2 WHEN 'Watch' THEN 3 ELSE 4 END,
    growth_gap_score DESC;

SELECT * FROM risk_score;
