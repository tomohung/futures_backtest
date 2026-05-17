#!/usr/bin/env python3
"""H092 Phase 2 — Night vol → Day session direction / volatility structure.

純市場結構描述,不綁定任何策略 filter。

4 tiers (fixed cutoffs, user-preferred memorable boundaries):
    deep STOP   : night_norm < 0.8
    mid STOP    : 0.8 ≤ night_norm < 1.0
    mid GO      : 1.0 ≤ night_norm < 1.2
    strong GO   : night_norm ≥ 1.2

5 modules:
    A. Day signed return = (close - open) / open × 100 分布
    B. Day volatility (HL / EmaHL) 分布
    C. Extreme timing — day high / low 在何時形成
    D. Day path shape — 4 類:up-trending / down-trending / L-then-H / H-then-L
    E. Average intraday trajectory (mean + p25/p75)

使用方式:
    uv run python research/active/H092-nvf-reach-direction/phase2_market_structure.py
"""

import bisect
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DB_PATH = "data/futures.duckdb"
OUT_DIR = Path("research/active/H092-nvf-reach-direction/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SYMBOL = "TX"
NVF_MIN_HISTORY_NIGHTS = 60
NVF_FALLBACK_THRESHOLD = 0.93

TIER_CUTS = [0.8, 1.0, 1.2]
TIER_LABELS = ["deep STOP", "mid STOP", "mid GO", "strong GO"]
TIER_COLORS = {
    "deep STOP": "#1e88e5",
    "mid STOP": "#66bb6a",
    "mid GO": "#fb8c00",
    "strong GO": "#e53935",
}

# Path shape thresholds (minute indices within 0-300 session)
EARLY_MIN = 60   # first hour
LATE_MIN = 240   # last hour


def tier_of(norm: float) -> str:
    if norm < TIER_CUTS[0]:
        return TIER_LABELS[0]
    if norm < TIER_CUTS[1]:
        return TIER_LABELS[1]
    if norm < TIER_CUTS[2]:
        return TIER_LABELS[2]
    return TIER_LABELS[3]


def load_data():
    print("Loading 1m bars and aggregates...")
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        bars = conn.execute(
            """
            SELECT timestamp, open, high, low, close
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            ORDER BY timestamp
            """,
            [SYMBOL],
        ).df()
        bars["timestamp"] = pd.to_datetime(bars["timestamp"])
        bars["trade_date"] = bars["timestamp"].dt.normalize()
        secs = (bars["timestamp"] - bars["trade_date"]).dt.total_seconds()
        bars["minute_idx"] = (secs / 60 - (8 * 60 + 45)).astype(int)

        day = conn.execute(
            """
            SELECT timestamp::DATE AS td,
                   arg_min(open, timestamp)  AS day_open,
                   arg_max(close, timestamp) AS day_close,
                   MAX(high) AS day_high,
                   MIN(low)  AS day_low,
                   MAX(high) - MIN(low) AS day_hl
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            GROUP BY td
            ORDER BY td
            """,
            [SYMBOL],
        ).df()
        day["td"] = pd.to_datetime(day["td"])
        day = day.set_index("td").sort_index()

        night_raw = conn.execute(
            """
            SELECT timestamp, high, low
            FROM ohlcv_1m
            WHERE symbol = ?
              AND (timestamp::TIME >= '15:00:00' OR timestamp::TIME < '05:00:00')
            ORDER BY timestamp
            """,
            [SYMBOL],
        ).df()
    night_raw["timestamp"] = pd.to_datetime(night_raw["timestamp"])

    day_dates_list = sorted(day.index.tolist())

    def find_next(ts):
        cal_time = ts.time()
        if cal_time >= pd.Timestamp("15:00").time():
            search_date = (ts + pd.Timedelta(days=1)).normalize()
        else:
            search_date = ts.normalize()
        idx = bisect.bisect_left(day_dates_list, search_date)
        return day_dates_list[idx] if idx < len(day_dates_list) else None

    night_raw["trade_date"] = night_raw["timestamp"].apply(find_next)
    night_raw = night_raw.dropna(subset=["trade_date"])
    night = night_raw.groupby("trade_date").agg(
        night_high=("high", "max"),
        night_low=("low", "min"),
        n_bars=("high", "count"),
    )
    night["night_range"] = night["night_high"] - night["night_low"]
    night = night[night["n_bars"] >= 100].copy().sort_index()
    night["ema20"] = night["night_range"].ewm(span=20, adjust=False).mean()
    night["night_norm"] = night["night_range"] / night["ema20"]

    norms = night["night_norm"].values
    thresholds = np.empty(len(norms))
    for i in range(len(norms)):
        h = norms[:i]
        h = h[~np.isnan(h)]
        thresholds[i] = float(np.median(h)) if len(h) >= NVF_MIN_HISTORY_NIGHTS else NVF_FALLBACK_THRESHOLD
    night["threshold"] = thresholds

    day["ema_hl"] = day["day_hl"].ewm(span=20, adjust=False).mean().shift(1)

    merged = day.join(night[["night_norm", "threshold"]], how="inner")
    merged = merged.dropna(subset=["ema_hl", "night_norm"])

    merged["tier"] = merged["night_norm"].apply(tier_of)
    merged["signed_ret"] = (merged["day_close"] - merged["day_open"]) / merged["day_open"] * 100
    merged["hl_ratio"] = merged["day_hl"] / merged["ema_hl"]
    merged["year"] = merged.index.year

    # Group bars by trade_date once
    print("Computing high/low formation minute per day...")
    bars_by_date = {d: g for d, g in bars.groupby("trade_date", sort=False)}

    high_times, low_times = [], []
    for d in merged.index:
        day_bars = bars_by_date.get(d)
        if day_bars is None or len(day_bars) == 0:
            high_times.append(np.nan)
            low_times.append(np.nan)
            continue
        dh = merged.at[d, "day_high"]
        dl = merged.at[d, "day_low"]
        hi_match = day_bars[day_bars["high"] >= dh - 1e-9]
        lo_match = day_bars[day_bars["low"] <= dl + 1e-9]
        high_times.append(int(hi_match.iloc[0]["minute_idx"]) if len(hi_match) else np.nan)
        low_times.append(int(lo_match.iloc[0]["minute_idx"]) if len(lo_match) else np.nan)
    merged["high_minute"] = high_times
    merged["low_minute"] = low_times

    def classify_shape(row):
        h, l = row["high_minute"], row["low_minute"]
        if pd.isna(h) or pd.isna(l):
            return "unknown"
        if h == l:
            return "unknown"
        # "Trending" requires one extreme in first hour, the other in last hour
        if l < EARLY_MIN and h > LATE_MIN:
            return "up-trending"
        if h < EARLY_MIN and l > LATE_MIN:
            return "down-trending"
        if l < h:
            return "L-then-H"
        return "H-then-L"

    merged["shape"] = merged.apply(classify_shape, axis=1)

    return merged, bars, bars_by_date


def quantiles(arr, qs):
    arr = arr.dropna()
    if len(arr) == 0:
        return {f"p{int(q*100)}": np.nan for q in qs}
    return {f"p{int(q*100)}": float(arr.quantile(q)) for q in qs}


def main():
    print("=" * 90)
    print("H092 Phase 2 — Night vol → Day session structure (descriptive)")
    print("=" * 90)
    print(f"Tier cuts: <{TIER_CUTS[0]} / <{TIER_CUTS[1]} / <{TIER_CUTS[2]} / ≥{TIER_CUTS[2]}")

    merged, bars, bars_by_date = load_data()
    print(f"\nTotal days: {len(merged)}, range: {merged.index[0].date()} ~ {merged.index[-1].date()}")
    print("\nTier sample sizes:")
    for label in TIER_LABELS:
        n = (merged["tier"] == label).sum()
        pct = n / len(merged) * 100
        print(f"  {label:12s}  N={n:>4}  ({pct:.1f}%)")

    # ── A. Signed return ──
    print("\n" + "─" * 90)
    print("A. Day signed return: (close − open) / open × 100  [%]")
    print("─" * 90)
    rows = []
    for t in TIER_LABELS:
        s = merged[merged["tier"] == t]["signed_ret"]
        rows.append({
            "tier": t, "N": len(s),
            "mean_%": s.mean(),
            "median_%": s.median(),
            "std_%": s.std(),
            "p10_%": s.quantile(0.10),
            "p25_%": s.quantile(0.25),
            "p75_%": s.quantile(0.75),
            "p90_%": s.quantile(0.90),
            "%_positive": (s > 0).mean() * 100,
        })
    a_df = pd.DataFrame(rows)
    print(a_df.to_string(index=False, formatters={
        "mean_%": lambda v: f"{v:+.3f}",
        "median_%": lambda v: f"{v:+.3f}",
        "std_%": lambda v: f"{v:.3f}",
        "p10_%": lambda v: f"{v:+.3f}",
        "p25_%": lambda v: f"{v:+.3f}",
        "p75_%": lambda v: f"{v:+.3f}",
        "p90_%": lambda v: f"{v:+.3f}",
        "%_positive": lambda v: f"{v:.1f}",
    }))
    a_df.to_csv(OUT_DIR / "tier_signed_return.csv", index=False)

    # ── B. Day volatility ──
    print("\n" + "─" * 90)
    print("B. Day HL / EmaHL distribution (volatility magnitude)")
    print("─" * 90)
    rows = []
    for t in TIER_LABELS:
        s = merged[merged["tier"] == t]["hl_ratio"]
        rows.append({
            "tier": t, "N": len(s),
            "mean": s.mean(), "median": s.median(), "std": s.std(),
            "p10": s.quantile(0.10), "p25": s.quantile(0.25),
            "p75": s.quantile(0.75), "p90": s.quantile(0.90),
        })
    b_df = pd.DataFrame(rows)
    print(b_df.to_string(index=False, formatters={
        c: (lambda v: f"{v:.3f}")
        for c in b_df.columns if c not in ("tier", "N")
    }))
    b_df.to_csv(OUT_DIR / "tier_volatility.csv", index=False)

    # ── C. Extreme timing ──
    print("\n" + "─" * 90)
    print("C. Day high / low formation minute (0=08:45, 300=13:45)")
    print("─" * 90)
    rows = []
    for t in TIER_LABELS:
        s = merged[merged["tier"] == t]
        rows.append({
            "tier": t, "N": len(s),
            "H_mean": s["high_minute"].mean(),
            "H_p25": s["high_minute"].quantile(0.25),
            "H_p50": s["high_minute"].median(),
            "H_p75": s["high_minute"].quantile(0.75),
            "L_mean": s["low_minute"].mean(),
            "L_p25": s["low_minute"].quantile(0.25),
            "L_p50": s["low_minute"].median(),
            "L_p75": s["low_minute"].quantile(0.75),
        })
    c_df = pd.DataFrame(rows)
    print(c_df.to_string(index=False, formatters={
        c: (lambda v: f"{v:.0f}") for c in c_df.columns if c not in ("tier", "N")
    }))
    c_df.to_csv(OUT_DIR / "tier_extreme_timing.csv", index=False)

    # ── D. Path shape ──
    print("\n" + "─" * 90)
    print("D. Day path shape distribution (%)")
    print("─" * 90)
    shape_order = ["up-trending", "L-then-H", "H-then-L", "down-trending", "unknown"]
    pivot = pd.crosstab(merged["tier"], merged["shape"], normalize="index") * 100
    pivot = pivot.reindex(TIER_LABELS)
    pivot = pivot.reindex(columns=[s for s in shape_order if s in pivot.columns])
    print(pivot.to_string(float_format=lambda v: f"{v:.1f}%"))
    pivot.to_csv(OUT_DIR / "tier_path_shape.csv")

    # ── E. Average trajectory ──
    print("\n" + "─" * 90)
    print("E. Average intraday trajectory per tier")
    print("─" * 90)
    traj_data = {}
    for t in TIER_LABELS:
        tier_dates = merged[merged["tier"] == t].index
        if len(tier_dates) == 0:
            traj_data[t] = None
            continue
        series_list = []
        for d in tier_dates:
            db = bars_by_date.get(d)
            if db is None or len(db) == 0:
                continue
            day_open = float(db.iloc[0]["open"])
            ser = (db["close"] / day_open - 1) * 100
            ser.index = db["minute_idx"].values
            ser = ser[~ser.index.duplicated(keep="last")]
            ser = ser.reindex(range(0, 301), method="ffill")
            series_list.append(ser)
        if not series_list:
            traj_data[t] = None
            continue
        mat = pd.concat(series_list, axis=1)
        traj_data[t] = {
            "mean": mat.mean(axis=1),
            "p25": mat.quantile(0.25, axis=1),
            "p50": mat.median(axis=1),
            "p75": mat.quantile(0.75, axis=1),
            "N": mat.shape[1],
        }
        finals = mat.iloc[-1]
        print(f"  {t:12s}  N={mat.shape[1]:>4}  final mean={finals.mean():+.3f}%  "
              f"median={finals.median():+.3f}%  pct_positive_final={(finals > 0).mean():.1%}")

    # ── Yearly direction stability ──
    print("\n" + "─" * 90)
    print("Yearly signed_ret mean by tier")
    print("─" * 90)
    pivot_yr = merged.pivot_table(index="year", columns="tier", values="signed_ret",
                                  aggfunc="mean").reindex(columns=TIER_LABELS)
    print(pivot_yr.to_string(float_format=lambda v: f"{v:+.3f}%" if not pd.isna(v) else "—"))
    pivot_yr.to_csv(OUT_DIR / "yearly_signed_return.csv")

    print("\n  Yearly signed_ret median by tier")
    pivot_yr_med = merged.pivot_table(index="year", columns="tier", values="signed_ret",
                                       aggfunc="median").reindex(columns=TIER_LABELS)
    print(pivot_yr_med.to_string(float_format=lambda v: f"{v:+.3f}%" if not pd.isna(v) else "—"))
    pivot_yr_med.to_csv(OUT_DIR / "yearly_signed_return_median.csv")

    # ── Plots ──
    fig, axes = plt.subplots(3, 2, figsize=(16, 16))
    fig.suptitle("H092 Phase 2 — Night vol tier → Day session structure",
                 fontsize=14, fontweight="bold")

    colors_list = [TIER_COLORS[t] for t in TIER_LABELS]

    # (a) Signed return boxplot
    ax = axes[0, 0]
    data_a = [merged[merged["tier"] == t]["signed_ret"].values for t in TIER_LABELS]
    bp = ax.boxplot(data_a, labels=TIER_LABELS, patch_artist=True, showfliers=False)
    for patch, c in zip(bp["boxes"], colors_list):
        patch.set_facecolor(c)
        patch.set_alpha(0.5)
    ax.axhline(0, color="black", linewidth=0.7)
    ax.set_ylabel("(close − open) / open × 100 [%]")
    ax.set_title("(a) Day signed return by tier")
    ax.grid(alpha=0.3, axis="y")
    for i, t in enumerate(TIER_LABELS):
        m = merged[merged["tier"] == t]["signed_ret"].mean()
        ax.annotate(f"μ={m:+.2f}%", xy=(i + 1, m), xytext=(0, 8),
                    textcoords="offset points", ha="center",
                    fontsize=8, fontweight="bold")

    # (b) Volatility boxplot
    ax = axes[0, 1]
    data_b = [merged[merged["tier"] == t]["hl_ratio"].values for t in TIER_LABELS]
    bp = ax.boxplot(data_b, labels=TIER_LABELS, patch_artist=True, showfliers=False)
    for patch, c in zip(bp["boxes"], colors_list):
        patch.set_facecolor(c)
        patch.set_alpha(0.5)
    ax.axhline(1.0, color="black", linewidth=0.7, linestyle="--", label="EmaHL = 1.0")
    ax.set_ylabel("day HL / EmaHL")
    ax.set_title("(b) Day volatility by tier")
    ax.legend()
    ax.grid(alpha=0.3, axis="y")

    # (c) High formation timing
    ax = axes[1, 0]
    for t in TIER_LABELS:
        s = merged[merged["tier"] == t]["high_minute"].dropna()
        ax.hist(s, bins=30, alpha=0.45, color=TIER_COLORS[t], label=f"{t} (N={len(s)})")
    ax.set_xlabel("minute since 08:45 (300 = 13:45)")
    ax.set_ylabel("count")
    ax.set_title("(c) Day HIGH formation timing")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # (d) Low formation timing
    ax = axes[1, 1]
    for t in TIER_LABELS:
        s = merged[merged["tier"] == t]["low_minute"].dropna()
        ax.hist(s, bins=30, alpha=0.45, color=TIER_COLORS[t], label=f"{t} (N={len(s)})")
    ax.set_xlabel("minute since 08:45 (300 = 13:45)")
    ax.set_ylabel("count")
    ax.set_title("(d) Day LOW formation timing")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # (e) Path shape stacked bar
    ax = axes[2, 0]
    shape_colors = {
        "up-trending": "#43a047",
        "L-then-H": "#a5d6a7",
        "H-then-L": "#ef9a9a",
        "down-trending": "#e53935",
        "unknown": "grey",
    }
    bottoms = np.zeros(len(TIER_LABELS))
    for s in [c for c in shape_order if c in pivot.columns]:
        vals = pivot[s].values
        ax.bar(TIER_LABELS, vals, bottom=bottoms, label=s,
               color=shape_colors.get(s, "grey"))
        bottoms += vals
    ax.set_ylabel("% of days")
    ax.set_title("(e) Path shape composition")
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(alpha=0.3, axis="y")
    ax.set_ylim(0, 100)

    # (f) Average trajectory
    ax = axes[2, 1]
    minutes = np.arange(0, 301)
    for t in TIER_LABELS:
        td = traj_data.get(t)
        if td is None:
            continue
        c = TIER_COLORS[t]
        ax.plot(minutes, td["mean"].values, color=c, linewidth=1.8,
                label=f"{t} (N={td['N']})")
        ax.fill_between(minutes, td["p25"].values, td["p75"].values,
                        color=c, alpha=0.08)
    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_xlabel("minute since 08:45")
    ax.set_ylabel("close / day_open − 1 [%]")
    ax.set_title("(f) Average intraday trajectory (mean + p25/p75 shaded)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    plt.tight_layout()
    out_png = OUT_DIR / "h092_phase2_market_structure.png"
    plt.savefig(out_png, dpi=140)
    print(f"\nPlot saved: {out_png}")


if __name__ == "__main__":
    main()
