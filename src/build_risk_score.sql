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
-- PRE/POST WINDOW: split at 2022 (the Oct-2022 BIS package is the first and largest
-- control action in scope; see project brief). pre = 2017-2021, post = 2023-latest;
-- 2022 itself is excluded from both windows since the controls took effect mid-year
-- (Oct 2022) and averaging a split year into either side would blur the comparison.
--
-- DOMESTIC-CONSUMPTION ESTIMATE: see domestic_consumption_estimate CTE below --
-- placeholder pending Day 10-11 driver-analysis research against public EDB/fab
-- capacity figures (per project brief). Until populated, the absorption-gap signal
-- is a deliberate UPPER BOUND on the unexplained residual (imports minus re-exports,
-- not yet netting out any domestic use), stated as a named limitation in findings.md.

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

-- === Signal 2: absorption gap ========================================================
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

-- PLACEHOLDER pending Day 10-11 research (see header comment) -- 0 for both hubs
-- until populated from EDB (Singapore) / published fab capacity figures. Hong Kong
-- has no meaningful wafer-fab industry, so 0 there is a defensible estimate, not
-- just a placeholder; Singapore genuinely has fab capacity (GlobalFoundries, Micron,
-- STMicro, Infineon backend among others) and 0 there understates domestic use --
-- meaning Singapore's absorption-gap residual below is the one most likely to
-- overstate diversion risk until this is filled in.
CREATE TEMP TABLE domestic_consumption_estimate (hub TEXT, usd REAL);
INSERT INTO domestic_consumption_estimate VALUES ('SGP', 0), ('HKG', 0);

CREATE TEMP TABLE absorption_gap AS
SELECT
    i.hub, i.hs6, i.year,
    i.value_usd AS hub_imports_usd,
    COALESCE(r.reexport_world_usd, 0) - COALESCE(r.reexport_china_usd, 0) AS reexport_to_nonchina_usd,
    d.usd AS domestic_consumption_estimate_usd,
    i.value_usd
        - (COALESCE(r.reexport_world_usd, 0) - COALESCE(r.reexport_china_usd, 0))
        - d.usd AS absorption_gap_usd
FROM hub_imports i
LEFT JOIN hub_reexports r ON r.hub = i.hub AND r.hs6 = i.hs6 AND r.year = i.year
JOIN domestic_consumption_estimate d ON d.hub = i.hub
WHERE i.year >= 2023;  -- post-control period only; the gap is a diversion signal for
                        -- the period controls were actually in effect

CREATE TEMP TABLE absorption_gap_latest AS
SELECT hub, hs6, AVG(absorption_gap_usd) AS absorption_gap_avg_usd
FROM absorption_gap
GROUP BY hub, hs6;

-- === Signal 3: event proximity =======================================================
-- Annual-grain approximation: does the corridor's growth accelerate in years
-- immediately following a semiconductor-relevant BIS event, vs. a smooth trend
-- across the full window? True month-level clustering (the stronger version of this
-- signal per the project brief) is checked separately for the highest-risk
-- corridor/hs6 once identified -- see drivers.py, which pulls targeted monthly data
-- via fetch_comtrade.fetch_monthly() and overlays it against bis_events for the
-- timeline chart. This SQL-level version is a coarse first pass, not the final word.
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

-- === Combine + tier ===================================================================
CREATE TABLE risk_score AS
SELECT
    g.hub,
    g.hs6,
    ROUND(g.corridor_growth_rate, 3)        AS corridor_growth_rate,
    ROUND(g.hub_total_trade_growth_rate, 3) AS hub_total_trade_growth_rate,
    ROUND(g.growth_gap_score, 3)            AS growth_gap_score,
    ROUND(a.absorption_gap_avg_usd, 0)      AS absorption_gap_avg_usd,
    ROUND(e.event_proximity_score, 3)       AS event_proximity_score,
    -- Tiering rule, stated plainly so a reader can check it against the numbers above:
    -- HIGH     = growth clearly outpaces the hub baseline AND accelerates right after
    --            a control date AND leaves an unexplained (positive) import residual.
    -- ELEVATED = two of the three signals point the same direction.
    -- WATCH    = exactly one signal points the same direction.
    -- LOW      = none do.
    CASE
        WHEN (g.growth_gap_score > 0.15) + (e.event_proximity_score > 0.10)
             + (a.absorption_gap_avg_usd > 0) >= 3 THEN 'High'
        WHEN (g.growth_gap_score > 0.15) + (e.event_proximity_score > 0.10)
             + (a.absorption_gap_avg_usd > 0) = 2 THEN 'Elevated'
        WHEN (g.growth_gap_score > 0.15) + (e.event_proximity_score > 0.10)
             + (a.absorption_gap_avg_usd > 0) = 1 THEN 'Watch'
        ELSE 'Low'
    END AS risk_tier
FROM growth_gap g
JOIN absorption_gap_latest a ON a.hub = g.hub AND a.hs6 = g.hs6
JOIN event_proximity e ON e.hub = g.hub AND e.hs6 = g.hs6
ORDER BY
    CASE risk_tier WHEN 'High' THEN 1 WHEN 'Elevated' THEN 2 WHEN 'Watch' THEN 3 ELSE 4 END,
    growth_gap_score DESC;

SELECT * FROM risk_score;
