"""Driver analysis: what's actually pushing the top-tier HS-code/corridor combos?

Rules out the two standard alternative explanations explicitly (per project brief,
don't just assert the diversion read):
  1. "Legitimate domestic demand grew" -- checked via the absorption-gap components
     already in risk_score (hub imports vs. re-exports vs. domestic-consumption
     estimate) plus the domestic_consumption_estimate placeholder's own caveat.
  2. "Re-exports shifted to a legitimate third country, not China" -- checked by
     comparing the hub's re-exports to China against its re-exports to the World;
     if China's share of re-exports is falling AND the corridor is still showing an
     absorption gap, that's the diversion-supporting case. If China's share is
     merely being replaced by other destinations' share, that's the legitimate
     explanation and should pull the read back toward Watch, not High.

Also pulls TARGETED monthly Comtrade data (see fetch_comtrade.fetch_monthly) for
just the single highest-risk corridor/hs6 -- not the full grid, see module
docstring in fetch_comtrade.py for why -- to render the event-proximity timeline
chart at the resolution the brief actually asks for.

Usage:
    python src/drivers.py
"""

import os
import sqlite3
import sys

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import BIS_CONTROL_DATES_PATH, DB_PATH, HS_CODES, TRADE_END_YEAR, TRADE_START_YEAR  # noqa: E402
from fetch_comtrade import fetch_monthly  # noqa: E402

CHARTS_DIR = "analysis/charts"

TIER_ORDER = ["High", "Elevated", "Watch", "Low"]
TIER_COLOR = {"Low": "#0ca30c", "Watch": "#fab219", "Elevated": "#ec835a", "High": "#d03b3b"}
SEQ_BLUE = "#2a78d6"
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


def rule_out_alternatives(conn, top_row: pd.Series):
    """Print the two alternative-explanation checks for the single top-tier row."""
    hub, hs6 = top_row["hub"], top_row["hs6"]
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
    print(f"\n=== Rule-out checks for top-tier row: {hub} / {hs6} ({HS_CODES.get(hs6, '')}) ===")
    print("China's share of re-exports by year -- RISING share means the hub's re-export")
    print("base is NOT diversifying away from China as imports grow (diversion-consistent);")
    print("a FALLING share would support the legitimate-shift explanation (China being")
    print("replaced by other destinations' demand):")
    print(reexp.to_string(index=False))
    print(f"\nabsorption_gap_avg_usd (post-2022): {top_row['absorption_gap_avg_usd']:,.0f}")
    print(
        "NOTE: domestic_consumption_estimate is currently a 0-placeholder for both hubs "
        "(see build_risk_score.sql header) -- this absorption gap is an upper bound, not "
        "yet netting out legitimate domestic semiconductor demand. State this plainly in "
        "findings.md; do not present the residual as a confirmed diversion volume."
    )
    return reexp


def chart_timeline_for_top_corridor(top_row: pd.Series):
    hub, hs6 = top_row["hub"], top_row["hs6"]
    months = [
        f"{y}{m:02d}"
        for y in range(TRADE_START_YEAR, TRADE_END_YEAR + 1)
        for m in range(1, 13)
        if y < TRADE_END_YEAR or m <= 12
    ]
    monthly_rows = fetch_monthly("USA", hub, months)
    monthly = pd.DataFrame(monthly_rows)
    if monthly.empty:
        print(f"No monthly data returned for USA->{hub}; skipping timeline chart.")
        return
    monthly = monthly[monthly["cmdCode"] == hs6]
    monthly["date"] = pd.to_datetime(monthly["period"], format="%Y%m")
    monthly = monthly.groupby("date")["primaryValue"].sum().reset_index()

    import json
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
    ax.set_title(f"USA -> {hub}, HS {hs6}: monthly trade vs. BIS control dates")
    ax.legend(loc="upper left", frameon=False)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig(f"{CHARTS_DIR}/03_top_corridor_timeline.png", dpi=150)
    plt.close(fig)


def main():
    os.makedirs(CHARTS_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    df = load_risk_score(conn)

    print(df.to_string(index=False))
    chart_tier_distribution(df)
    chart_growth_gap(df)

    # risk_score is already ordered by tier priority (High > Elevated > Watch > Low),
    # then growth_gap_score DESC within tier -- see build_risk_score.sql's ORDER BY.
    # Take the first row directly rather than re-sorting by growth_gap_score alone,
    # which would surface a high-growth Watch-tier row ahead of a lower-growth but
    # higher-tier Elevated row (a real bug caught in the first run of this script).
    top_row = df.iloc[0]
    if top_row["risk_tier"] != "High":
        print(f"\nNo row reached the High tier; using the top {top_row['risk_tier']}-tier "
              f"row ({top_row['hub']}/{top_row['hs6']}) for the driver deep-dive instead.")

    rule_out_alternatives(conn, top_row)
    chart_timeline_for_top_corridor(top_row)

    conn.close()
    print(f"\nCharts written to {CHARTS_DIR}/")


if __name__ == "__main__":
    main()
