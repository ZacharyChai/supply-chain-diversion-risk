"""Driver analysis: what's actually pushing the Elevated-tier HS-code/hub combos?

Runs for EVERY "Elevated" row (not just the single top one -- an earlier version
of this script only looked at the highest-tier row, which was reasonable when
there was one candidate but stopped being reasonable once the redesigned signal
set surfaced three). For each:

  1. "Legitimate domestic demand grew" -- checked via the retention-gap signal
     (imports minus ALL re-exports minus a domestic-consumption estimate) plus
     the estimate's own documented 0-placeholder caveat.
  2. "Re-exports shifted to a legitimate third country, not China" -- checked via
     the china_concentration signal: is China's SHARE of re-exports elevated and
     rising, independent of the retention gap's magnitude (these were conflated
     into one number in an earlier version -- see build_risk_score.sql's revision
     note for why that was wrong).

Plus, for the single strongest substantive finding (Hong Kong / HS 848620 -- no
domestic fab industry, so the rule-out logic is cleanest there):
  - origin_decomposition(): is growth broad-based across all equipment-exporting
    countries, or concentrated in controlled-origin suppliers specifically?
  - inventory_lag_test(): does the apparent "re-exports exceed same-year imports"
    anomaly resolve if re-exports are compared against a 1-2 year LAGGED import
    figure (capital equipment plausibly sits in inventory before re-export)?
  - event_window_analysis(): a monthly before/after window comparison around the
    October 2022 BIS package -- more defensible than the annual-grain proxy in
    build_risk_score.sql, though still not a full fixed-effects event study
    (not attempted: one series, nine years of monthly data, isn't enough
     observations to support one either -- an honest-sized tool for the data).
  - sensitivity_table(): do the Elevated classifications survive reasonable
     alternative threshold choices, or are they artifacts of the specific cutoffs?

Usage:
    python src/drivers.py
"""

import json
import os
import sqlite3
import sys

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (  # noqa: E402
    BIS_CONTROL_DATES_PATH,
    DB_PATH,
    HS_CODES,
    ORIGIN_DECOMPOSITION_COUNTRIES,
    ORIGIN_DECOMPOSITION_TARGET,
    RAW_DIR,
    TRADE_END_YEAR,
    TRADE_START_YEAR,
)
from fetch_comtrade import _reporter_codes, fetch_monthly  # noqa: E402

CHARTS_DIR = "analysis/charts"

TIER_ORDER = ["High", "Elevated", "Watch", "Low"]
TIER_COLOR = {"Low": "#0ca30c", "Watch": "#fab219", "Elevated": "#ec835a", "High": "#d03b3b"}
SEQ_BLUE = "#2a78d6"
SEQ_PALETTE = ["#2a78d6", "#6fa8dc", "#a64ca6", "#e69138", "#38761d"]
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
SURFACE = "#fcfcfb"

plt.rcParams.update({
    "font.family": "sans-serif",
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "axes.edgecolor": GRIDLINE,
    "axes.labelcolor": INK_SECONDARY,
    "text.color": INK_PRIMARY,
    "xtick.color": INK_MUTED,
    "ytick.color": INK_MUTED,
    "axes.grid": False,
    "savefig.facecolor": SURFACE,
})

# The Oct-2022 BIS package is the first and largest control action in scope --
# the natural anchor for the event-window analysis, consistent with the pre/post
# split build_risk_score.sql already uses.
PRIMARY_EVENT_DATE = pd.Timestamp("2022-10-07")


def load_risk_score(conn) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM risk_score", conn)
    df["hs6_label"] = df["hs6"].map(lambda c: f"{c} ({HS_CODES.get(c, c)[:28]})")
    return df


def chart_tier_distribution(df: pd.DataFrame):
    counts = df["risk_tier"].value_counts().reindex(TIER_ORDER).fillna(0)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(counts.index, counts.values, color=[TIER_COLOR[t] for t in counts.index])
    ax.set_ylabel("HS-code x corridor combinations")
    ax.set_title("Risk tier distribution")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig(f"{CHARTS_DIR}/01_tier_distribution.png", dpi=150)
    plt.close(fig)


def chart_growth_gap(df: pd.DataFrame):
    ordered = df.sort_values("growth_gap_score", ascending=True)
    fig, ax = plt.subplots(figsize=(8, max(4, 0.4 * len(ordered))))
    colors = [TIER_COLOR[t] for t in ordered["risk_tier"]]
    labels = ordered["hub"] + " / " + ordered["hs6_label"]
    ax.barh(labels, ordered["growth_gap_score"], color=colors)
    ax.set_xlabel("Growth-gap score (corridor growth minus hub baseline growth)")
    ax.set_title("Rate-of-growth gap by HS code x hub")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig(f"{CHARTS_DIR}/02_growth_gap.png", dpi=150)
    plt.close(fig)


def rule_out_alternatives(conn, row: pd.Series) -> pd.DataFrame:
    """Print the two alternative-explanation checks for one Elevated-tier row."""
    hub, hs6 = row["hub"], row["hs6"]
    reexp = pd.read_sql(
        "SELECT year, reexport_world_usd, reexport_china_usd, "
        "reexport_china_usd * 1.0 / NULLIF(reexport_world_usd, 0) AS china_share "
        "FROM (SELECT reporter_iso3 AS hub, hs6, year, "
        "SUM(CASE WHEN partner_iso3='WLD' THEN trade_value_usd ELSE 0 END) AS reexport_world_usd, "
        "SUM(CASE WHEN partner_iso3='CHN' THEN trade_value_usd ELSE 0 END) AS reexport_china_usd "
        "FROM trade WHERE series='reexport' GROUP BY reporter_iso3, hs6, year) "
        "WHERE hub = ? AND hs6 = ? ORDER BY year",
        conn, params=[hub, hs6],
    )
    print(f"\n=== Rule-out checks: {hub} / {hs6} ({HS_CODES.get(hs6, '')}) ===")
    print(f"retention_gap_avg_usd (2023+, imports minus ALL re-exports minus domestic "
          f"consumption est.): {row['retention_gap_avg_usd']:,.0f}")
    print(f"china_share: {row['china_share_pre']:.1%} (2017-21 avg) -> "
          f"{row['china_share_post']:.1%} (2023+ avg), "
          f"concentration_score={row['china_concentration_score']:+.3f}")
    print(reexp.to_string(index=False))
    print(
        "NOTE: domestic_consumption_estimate is a 0-placeholder for both hubs (see "
        "build_risk_score.sql header). Defensible for Hong Kong (negligible real fab "
        "capacity); understates Singapore's genuine domestic demand -- so Singapore's "
        "retention-gap figures are directional, not literal."
    )
    return reexp


def origin_decomposition(conn):
    """Growth by ACTUAL origin country for the top substantive finding (HKG/848620)
    -- does growth concentrate in controlled-origin suppliers, or is it broad-based
    across all equipment exporters (which would argue for legitimate hub-wide
    demand instead)?"""
    path = f"{RAW_DIR}/comtrade_origin_decomposition.json"
    if not os.path.exists(path):
        print("\nOrigin decomposition data not yet fetched; skipping.")
        return None
    with open(path) as f:
        rows = json.load(f)
    reporter_codes = _reporter_codes()
    code_to_iso3 = {v: k for k, v in reporter_codes.items()}
    df = pd.DataFrame(rows)
    if df.empty:
        print("\nOrigin decomposition returned no rows; skipping.")
        return None
    df["origin"] = df["reporterCode"].map(code_to_iso3)
    df["year"] = df["refYear"]
    annual = df.groupby(["origin", "year"])["primaryValue"].sum().reset_index()

    pivot = annual.pivot(index="year", columns="origin", values="primaryValue").fillna(0)
    pivot = pivot.reindex(columns=ORIGIN_DECOMPOSITION_COUNTRIES, fill_value=0)

    print(f"\n=== Origin decomposition: {ORIGIN_DECOMPOSITION_TARGET['partner']} / "
          f"{ORIGIN_DECOMPOSITION_TARGET['hs6']} imports by origin country ===")
    print(pivot.to_string())

    pre = pivot.loc[pivot.index.isin(range(2017, 2022))].mean()
    post = pivot.loc[pivot.index >= 2023].mean()
    growth = ((post - pre) / pre.replace(0, pd.NA) * 100).round(0)
    print("\nPer-origin growth, pre-2022 avg -> post-2022 avg:")
    for origin in ORIGIN_DECOMPOSITION_COUNTRIES:
        pre_v, post_v, g = pre[origin], post[origin], growth[origin]
        g_str = f"{g:+.0f}%" if pd.notna(g) else "n/a (near-zero base)"
        print(f"  {origin}: ${pre_v:,.0f} -> ${post_v:,.0f}  ({g_str})")

    fig, ax = plt.subplots(figsize=(9, 5))
    bottom = pd.Series(0.0, index=pivot.index)
    for i, origin in enumerate(ORIGIN_DECOMPOSITION_COUNTRIES):
        ax.bar(pivot.index, pivot[origin], bottom=bottom,
               label=origin, color=SEQ_PALETTE[i % len(SEQ_PALETTE)])
        bottom += pivot[origin]
    ax.axvline(2022.5, color=INK_MUTED, linestyle="--", linewidth=0.8)
    ax.set_ylabel("Annual export value to Hong Kong (USD)")
    ax.set_title(f"HKG / {ORIGIN_DECOMPOSITION_TARGET['hs6']} imports by origin country")
    ax.legend(loc="upper left", frameon=False)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig(f"{CHARTS_DIR}/04_origin_decomposition.png", dpi=150)
    plt.close(fig)
    return pivot


def inventory_lag_test(conn, hub: str, hs6: str):
    """Does hub_imports_t vs. reexport_china_{t+1, t+2} resolve the apparent
    "re-exports exceed same-year imports" mismatch better than the same-year
    comparison does? Tests the inventory/bonded-warehouse-timing explanation
    directly instead of just asserting it."""
    imports = pd.read_sql(
        "SELECT year, SUM(trade_value_usd) AS imports_usd FROM trade "
        "WHERE series='world_baseline' AND reporter_iso3=? AND hs6=? GROUP BY year",
        conn, params=[hub, hs6],
    ).set_index("year")["imports_usd"]
    reexports_china = pd.read_sql(
        "SELECT year, SUM(trade_value_usd) AS reexport_china_usd FROM trade "
        "WHERE series='reexport' AND reporter_iso3=? AND partner_iso3='CHN' AND hs6=? "
        "GROUP BY year",
        conn, params=[hub, hs6],
    ).set_index("year")["reexport_china_usd"]

    print(f"\n=== Inventory-lag test: {hub} / {hs6} ===")
    print("Comparing same-year imports against re-exports to China at lag 0/1/2 years:")
    rows = []
    for year in sorted(imports.index):
        imp = imports.get(year)
        row = {"import_year": year, "imports_usd": imp}
        for lag in (0, 1, 2):
            reexp = reexports_china.get(year + lag)
            row[f"reexport_china_t+{lag}"] = reexp
            row[f"ratio_t+{lag}"] = (reexp / imp) if (imp and reexp) else None
        rows.append(row)
    result = pd.DataFrame(rows)
    print(result.to_string(index=False, float_format=lambda x: f"{x:,.0f}" if abs(x) > 10 else f"{x:.2f}"))

    avg_ratio = {lag: result[f"ratio_t+{lag}"].mean() for lag in (0, 1, 2)}
    print("\nAverage reexport/import ratio by lag (closer to a stable, sub-1.0 "
          "ratio at some lag would support the inventory-timing explanation; a "
          "ratio that STAYS above 1.0 at every lag does not):")
    for lag, r in avg_ratio.items():
        print(f"  lag {lag}: {r:.2f}" if r is not None else f"  lag {lag}: n/a")
    return result


def sensitivity_table(df: pd.DataFrame):
    """Do the Elevated classifications survive reasonable alternative threshold
    choices? The specific cutoffs in build_risk_score.sql (0.15, 0, 0.05, 0.10) are
    analyst choices, not calibrated values -- this checks whether that matters."""
    growth_thresholds = [0.10, 0.15, 0.20]
    concentration_thresholds = [0.03, 0.05, 0.08]
    event_thresholds = [0.05, 0.10, 0.20]

    print("\n=== Threshold sensitivity: tier under alternative cutoffs ===")
    rows = []
    for _, r in df.iterrows():
        for gt in growth_thresholds:
            for ct in concentration_thresholds:
                for et in event_thresholds:
                    signals = (
                        (r["growth_gap_score"] > gt)
                        + (r["retention_gap_avg_usd"] > 0)
                        + (r["china_concentration_score"] > ct)
                        + (r["event_proximity_score"] > et)
                    )
                    tier = ["Low", "Watch", "Elevated", "High", "High"][signals]
                    rows.append({
                        "hub": r["hub"], "hs6": r["hs6"],
                        "growth_thresh": gt, "concentration_thresh": ct, "event_thresh": et,
                        "tier": tier,
                    })
    sens = pd.DataFrame(rows)
    summary = sens.groupby(["hub", "hs6"])["tier"].value_counts(normalize=True).unstack(fill_value=0)
    n_combos = len(growth_thresholds) * len(concentration_thresholds) * len(event_thresholds)
    print(f"Share of {n_combos} threshold combinations landing in each tier, per HS/hub:")
    print((summary * 100).round(0).astype(int).astype(str).radd("").to_string())
    return summary


def event_window_analysis(hub: str, hs6: str):
    """Monthly before/after window comparison around the Oct-2022 BIS package --
    more defensible than the annual-grain event-proximity signal, though still
    not a full fixed-effects event study (one series isn't enough observations to
    support one; a window-average comparison is the right-sized tool here)."""
    months = [
        f"{y}{m:02d}"
        for y in range(TRADE_START_YEAR, TRADE_END_YEAR + 1)
        for m in range(1, 13)
    ]
    monthly_rows = fetch_monthly("USA", hub, months, flow_code="X")
    monthly = pd.DataFrame(monthly_rows)
    if monthly.empty:
        print(f"\nNo monthly data returned for USA->{hub}; skipping event-window analysis.")
        return None
    monthly = monthly[monthly["cmdCode"] == hs6].copy()
    monthly["date"] = pd.to_datetime(monthly["period"], format="%Y%m")
    monthly = monthly.groupby("date")["primaryValue"].sum().reset_index()
    monthly["months_from_event"] = (
        (monthly["date"].dt.year - PRIMARY_EVENT_DATE.year) * 12
        + (monthly["date"].dt.month - PRIMARY_EVENT_DATE.month)
    )

    windows = [(-12, -6), (-6, -3), (-3, 0), (0, 3), (3, 6), (6, 12)]
    print(f"\n=== Event-window analysis: USA -> {hub}, HS {hs6} around "
          f"{PRIMARY_EVENT_DATE.date()} (Oct-2022 BIS package) ===")
    print("Monthly average trade value by window (months relative to the event):")
    window_avgs = []
    for lo, hi in windows:
        mask = (monthly["months_from_event"] >= lo) & (monthly["months_from_event"] < hi)
        avg = monthly.loc[mask, "primaryValue"].mean()
        label = f"[{lo:+d}, {hi:+d})"
        window_avgs.append({"window": label, "avg_monthly_usd": avg})
        print(f"  {label:>10}: ${avg:,.0f}" if pd.notna(avg) else f"  {label:>10}: n/a")

    # write monthly + BIS dates chart with corrected flow direction
    with open(BIS_CONTROL_DATES_PATH) as f:
        events = json.load(f)
    event_dates = [
        pd.to_datetime(e["effective_on"] or e["publication_date"])
        for e in events
        if any(kw in e["title"].lower() for kw in
               ["semiconductor", "advanced computing", "integrated circuit", "chip"])
    ]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(monthly["date"], monthly["primaryValue"], color=SEQ_BLUE, linewidth=1.8)
    for i, ed in enumerate(event_dates):
        ax.axvline(ed, color=TIER_COLOR["High"], linestyle="--", linewidth=0.7, alpha=0.6,
                   label="BIS/EAR semiconductor rule" if i == 0 else None)
    ax.set_ylabel("Monthly trade value (USD)")
    ax.set_title(f"USA -> {hub}, HS {hs6}: monthly EXPORTS vs. BIS control dates")
    ax.legend(loc="upper left", frameon=False)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig(f"{CHARTS_DIR}/03_top_corridor_timeline.png", dpi=150)
    plt.close(fig)

    return pd.DataFrame(window_avgs)


def main():
    os.makedirs(CHARTS_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    df = load_risk_score(conn)

    print(df.to_string(index=False))
    chart_tier_distribution(df)
    chart_growth_gap(df)

    elevated = df[df["risk_tier"].isin(["High", "Elevated"])]
    if elevated.empty:
        elevated = df.sort_values("growth_gap_score", ascending=False).head(1)
        print(f"\nNo row reached Elevated; using the highest growth-gap row instead.")

    for _, row in elevated.iterrows():
        rule_out_alternatives(conn, row)

    origin_decomposition(conn)
    inventory_lag_test(conn, "HKG", "848620")
    sensitivity_table(df)
    event_window_analysis("HKG", "848620")

    conn.close()
    print(f"\nCharts written to {CHARTS_DIR}/")


if __name__ == "__main__":
    main()
