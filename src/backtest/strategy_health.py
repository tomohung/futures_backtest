#!/usr/bin/env python3
"""Strategy Health Monitor — regime metrics + strategy cross-analysis.

Computes daily market regime indicators (range%, efficiency ratio, swing count)
and cross-references with EstHL / Reversal strategy performance to identify
early warning signals for strategy degradation.

Usage:
    uv run python src/backtest/strategy_health.py
    uv run python src/backtest/strategy_health.py --recent-only
    uv run python src/backtest/strategy_health.py --lookback 30
"""
import argparse
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.explore_regime import (
    DB_PATH,
    compute_indicators,
    load_daily_ohlcv,
)
from src.backtest.runner import load_data_for_orb_est_hl, load_data_for_reversal
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy
from src.strategies.reversal import ReversalStrategy

YEARS = [
    ("2021", "2021-01-01", "2021-12-31"),
    ("2022", "2022-01-01", "2022-12-31"),
    ("2023", "2023-01-01", "2023-12-31"),
    ("2024", "2024-01-01", "2024-12-31"),
    ("2025", "2025-01-01", "2025-12-31"),
    ("2026", "2026-01-01", None),
]


# ── Daily regime metrics ─────────────────────────────────────────────────────

def compute_1m_metrics() -> pd.DataFrame:
    """Compute per-day efficiency ratio and swing count from 1m bars."""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT timestamp, close
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ORDER BY timestamp
        """).df()

    df["trade_date"] = pd.to_datetime(df["timestamp"]).dt.normalize()
    results = []

    for date, grp in df.groupby("trade_date"):
        closes = grp["close"].values
        if len(closes) < 2:
            continue

        # Efficiency ratio: |net move| / sum(|step moves|)
        net_move = abs(closes[-1] - closes[0])
        step_moves = np.abs(np.diff(closes))
        total_move = step_moves.sum()
        er = net_move / total_move if total_move > 0 else 0.0

        # Swing count: sign changes in consecutive close diffs
        diffs = np.diff(closes)
        signs = np.sign(diffs)
        signs_nz = signs[signs != 0]  # ignore flat bars
        swing_count = np.sum(np.diff(signs_nz) != 0) if len(signs_nz) > 1 else 0

        results.append({
            "trade_date": date,
            "efficiency_ratio": er,
            "swing_count": int(swing_count),
        })

    out = pd.DataFrame(results)
    out["trade_date"] = pd.to_datetime(out["trade_date"])
    return out.set_index("trade_date")


def compute_daily_regime() -> pd.DataFrame:
    """Combine all daily regime metrics into one DataFrame."""
    print("Loading daily OHLCV...", flush=True)
    df_daily = load_daily_ohlcv()

    print("Computing ATR%, ADX, RealVol...", flush=True)
    indicators = compute_indicators(df_daily)

    print("Computing 1m efficiency ratio & swing count...", flush=True)
    metrics_1m = compute_1m_metrics()

    # Range percentage
    df_daily["range_pct"] = (df_daily["high"] - df_daily["low"]) / df_daily["open"] * 100
    df_daily["ema_range_pct_20"] = df_daily["range_pct"].ewm(span=20, adjust=False).mean()

    # Merge all
    regime = df_daily[["open", "high", "low", "close", "range_pct", "ema_range_pct_20"]].copy()
    regime = regime.join(indicators)
    regime = regime.join(metrics_1m)

    # ER EMA
    regime["ema_er_20"] = regime["efficiency_ratio"].ewm(span=20, adjust=False).mean()

    print(f"  {len(regime):,} trading days  "
          f"{regime.index[0].date()} ~ {regime.index[-1].date()}")
    return regime


# ── Strategy trade runs ──────────────────────────────────────────────────────

def run_esthl() -> pd.DataFrame:
    """Run EstHL strategy on full history, return trades with pnl_pct."""
    print("Running EstHL strategy...", flush=True)
    df = load_data_for_orb_est_hl()
    bt = Backtest(df, ORBWithEstHLExitStrategy,
                  cash=200_000, commission=0.0, trade_on_close=True)
    trades = bt.run(
        sl_ema_fraction=0.25,
        long_only=True,
        bigcost_days=2,
        skip_thursday=True,
        skip_friday=True,
    )["_trades"].copy()
    trades["entry_date"] = pd.to_datetime(trades["EntryTime"]).dt.normalize()
    trades["pnl_pct"] = trades["PnL"] / trades["EntryPrice"] * 100
    trades["win"] = (trades["PnL"] > 0).astype(int)
    trades["direction"] = trades["Size"].apply(lambda x: "long" if x > 0 else "short")
    trades["strategy"] = "EstHL"
    print(f"  EstHL: {len(trades)} trades")
    return trades


def run_reversal() -> pd.DataFrame:
    """Run Reversal strategy on full history, return trades with pnl_pct."""
    print("Running Reversal strategy...", flush=True)
    df = load_data_for_reversal()
    bt = Backtest(df, ReversalStrategy,
                  cash=200_000, commission=0.0, trade_on_close=True)
    trades = bt.run()["_trades"].copy()
    trades["entry_date"] = pd.to_datetime(trades["EntryTime"]).dt.normalize()
    trades["pnl_pct"] = trades["PnL"] / trades["EntryPrice"] * 100
    trades["win"] = (trades["PnL"] > 0).astype(int)
    trades["direction"] = trades["Size"].apply(lambda x: "long" if x > 0 else "short")
    trades["strategy"] = "Reversal"
    print(f"  Reversal: {len(trades)} trades")
    return trades


# ── Formatting helpers ───────────────────────────────────────────────────────

def fv(v, w=7, dec=2):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—".rjust(w)
    if isinstance(v, float):
        return f"{v:.{dec}f}".rjust(w)
    return str(v).rjust(w)


# ── Analysis sections ────────────────────────────────────────────────────────

def print_yearly_regime(regime: pd.DataFrame):
    """Section 1: Year-by-year regime indicator averages."""
    print("\n" + "=" * 80)
    print("1. YEAR-BY-YEAR REGIME METRICS")
    print("=" * 80)
    print(f"  {'Year':<6}  {'range%':>8}  {'ER':>7}  {'swing':>7}  "
          f"{'ATR%':>7}  {'ADX':>7}  {'RealVol':>8}  {'days':>5}")
    print(f"  {'-'*6}  {'-'*8}  {'-'*7}  {'-'*7}  "
          f"{'-'*7}  {'-'*7}  {'-'*8}  {'-'*5}")
    for yr, start, end in YEARS:
        mask = regime.index >= start
        if end:
            mask &= regime.index <= end
        r = regime[mask]
        if len(r) == 0:
            continue
        print(f"  {yr:<6}  {fv(r['range_pct'].mean(), 8)}"
              f"  {fv(r['efficiency_ratio'].mean(), 7, 3)}"
              f"  {fv(r['swing_count'].mean(), 7, 0)}"
              f"  {fv(r['atr_pct'].mean(), 7)}"
              f"  {fv(r['adx'].mean(), 7, 1)}"
              f"  {fv(r['real_vol'].mean(), 8, 1)}"
              f"  {len(r):>5}")


def quartile_analysis(trades: pd.DataFrame, col: str, label: str,
                      pnl_col: str = "pnl_pct"):
    """Print quartile breakdown of a regime metric vs strategy performance."""
    valid = trades[trades[col].notna()].copy()
    if len(valid) < 20:
        print(f"  Insufficient data for {label} (n={len(valid)})")
        return
    try:
        valid["q"] = pd.qcut(valid[col], 4,
                             labels=["Q1(low)", "Q2", "Q3", "Q4(high)"])
    except ValueError:
        print(f"  Cannot create quartiles for {label} (too many identical values)")
        return
    print(f"\n  [{label}]")
    print(f"  {'Quartile':<10}  {'n':>5}  {'win%':>7}  {'avg_pnl%':>9}  "
          f"{'total_pnl%':>11}  {'value range':>16}")
    print(f"  {'-'*10}  {'-'*5}  {'-'*7}  {'-'*9}  {'-'*11}  {'-'*16}")
    for q_label, grp in valid.groupby("q", observed=True):
        pnl = grp[pnl_col]
        win = len(pnl[pnl > 0]) / len(pnl) * 100 if len(pnl) > 0 else 0
        lo = grp[col].min()
        hi = grp[col].max()
        print(f"  {str(q_label):<10}  {len(pnl):>5}  {win:>6.1f}%"
              f"  {fv(pnl.mean(), 9, 3)}  {fv(pnl.sum(), 11, 2)}"
              f"  {lo:.3f} ~ {hi:.3f}")


def print_cross_analysis(trades: pd.DataFrame, regime: pd.DataFrame,
                         strategy_name: str):
    """Section 2/3: Cross-reference regime metrics with strategy trades."""
    print(f"\n{'=' * 80}")
    print(f"CROSS ANALYSIS — {strategy_name}")
    print("=" * 80)

    merged = trades.join(regime, on="entry_date", rsuffix="_regime")

    # Quartile analysis
    print("\n  ── Quartile Analysis (regime metric vs strategy pnl%) ──")
    for col, label in [
        ("range_pct", f"Range% — {strategy_name}"),
        ("efficiency_ratio", f"Efficiency Ratio — {strategy_name}"),
        ("swing_count", f"Swing Count — {strategy_name}"),
        ("atr_pct", f"ATR% — {strategy_name}"),
        ("adx", f"ADX — {strategy_name}"),
    ]:
        if col in merged.columns:
            quartile_analysis(merged, col, label)

    # Correlation analysis
    print(f"\n  ── Point-Biserial Correlation (indicator vs win) — {strategy_name} ──")
    indicators = [
        ("range_pct",        "Range%"),
        ("efficiency_ratio", "ER"),
        ("swing_count",      "Swing Count"),
        ("atr_pct",          "ATR%"),
        ("adx",              "ADX"),
    ]
    print(f"  {'Indicator':<16}  {'r(all)':>8}  {'r(long)':>9}  {'r(short)':>10}  {'n':>5}")
    print(f"  {'-'*16}  {'-'*8}  {'-'*9}  {'-'*10}  {'-'*5}")
    for col, name in indicators:
        if col not in merged.columns:
            continue
        valid = merged[merged[col].notna()]
        if len(valid) < 10:
            continue
        r_all = valid[col].corr(valid["win"])
        longs = valid[valid["direction"] == "long"]
        shorts = valid[valid["direction"] == "short"]
        r_long = longs[col].corr(longs["win"]) if len(longs) > 5 else np.nan
        r_short = shorts[col].corr(shorts["win"]) if len(shorts) > 5 else np.nan
        print(f"  {name:<16}  {r_all:>+8.3f}  {fv(r_long, 9, 3)}"
              f"  {fv(r_short, 10, 3)}  {len(valid):>5}")

    return merged


def print_health_dashboard(regime: pd.DataFrame,
                           all_trades: dict[str, pd.DataFrame],
                           lookback: int = 20):
    """Final section: recent regime health vs historical calibration."""
    print("\n" + "=" * 80)
    print(f"HEALTH DASHBOARD — Latest {lookback} Trading Days")
    print("=" * 80)

    recent = regime.tail(lookback)
    print(f"\n  Period: {recent.index[0].date()} ~ {recent.index[-1].date()}")

    # Regime metrics comparison
    metrics = [
        ("range_pct",        "Range% mean",    2),
        ("ema_range_pct_20", "Range% EMA20",   2),
        ("efficiency_ratio", "ER mean",        3),
        ("ema_er_20",        "ER EMA20",       3),
        ("swing_count",      "Swing Count",    0),
        ("atr_pct",          "ATR%",           2),
        ("adx",              "ADX",            1),
    ]

    print(f"\n  {'Metric':<18}  {'Current':>9}  {'All-Time':>9}  {'2024+':>9}  {'2021-23':>9}")
    print(f"  {'-'*18}  {'-'*9}  {'-'*9}  {'-'*9}  {'-'*9}")

    mask_2024_plus = regime.index >= "2024-01-01"
    mask_2021_23 = (regime.index >= "2021-01-01") & (regime.index < "2024-01-01")

    for col, label, dec in metrics:
        if col not in regime.columns:
            continue
        cur = recent[col].mean()
        hist = regime[col].mean()
        recent_good = regime.loc[mask_2024_plus, col].mean()
        early = regime.loc[mask_2021_23, col].mean()
        def ff(v, dec=dec):
            return f"{v:.{dec}f}".rjust(9)
        print(f"  {label:<18}  {ff(cur)}  {ff(hist)}  {ff(recent_good)}  {ff(early)}")

    # Strategy health
    print(f"\n  ── Strategy Performance (recent vs historical, in %) ──")
    print(f"  {'Strategy':<12}  {'recent WR':>10}  {'recent EV%':>11}  "
          f"{'hist WR':>8}  {'hist EV%':>9}  {'signal':>8}")
    print(f"  {'-'*12}  {'-'*10}  {'-'*11}  {'-'*8}  {'-'*9}  {'-'*8}")

    for name, trades in all_trades.items():
        if len(trades) == 0:
            print(f"  {name:<12}  {'no trades':>10}")
            continue
        recent_trades = trades.tail(lookback)
        r_wr = (recent_trades["win"].mean() * 100) if len(recent_trades) > 0 else np.nan
        r_ev = recent_trades["pnl_pct"].mean() if len(recent_trades) > 0 else np.nan
        h_wr = trades["win"].mean() * 100
        h_ev = trades["pnl_pct"].mean()

        # Signal logic
        if r_ev > h_ev * 0.5 and r_wr > h_wr * 0.8:
            signal = "OK"
        elif r_ev > 0:
            signal = "WATCH"
        else:
            signal = "DANGER"

        print(f"  {name:<12}  {r_wr:>9.1f}%  {r_ev:>+10.3f}%"
              f"  {h_wr:>7.1f}%  {h_ev:>+8.3f}%  {signal:>8}")


def print_yearly_strategy_pct(all_trades: dict[str, pd.DataFrame]):
    """Bonus: Year-by-year strategy performance in percentage terms."""
    print("\n" + "=" * 80)
    print("YEAR-BY-YEAR STRATEGY PERFORMANCE (percentage-based)")
    print("=" * 80)

    for name, trades in all_trades.items():
        print(f"\n  ── {name} ──")
        print(f"  {'Year':<6}  {'n':>5}  {'WR':>7}  {'avg_pnl%':>9}  "
              f"{'total_pnl%':>11}  {'PF':>6}  {'pts':>8}")
        print(f"  {'-'*6}  {'-'*5}  {'-'*7}  {'-'*9}  "
              f"{'-'*11}  {'-'*6}  {'-'*8}")
        for yr, start, end in YEARS:
            mask = trades["entry_date"] >= start
            if end:
                mask &= trades["entry_date"] <= end
            t = trades[mask]
            if len(t) == 0:
                continue
            wr = t["win"].mean() * 100
            avg_pnl = t["pnl_pct"].mean()
            total_pnl = t["pnl_pct"].sum()
            wins = t.loc[t["PnL"] > 0, "pnl_pct"]
            losses = t.loc[t["PnL"] < 0, "pnl_pct"]
            pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 and losses.sum() != 0 else np.inf
            pts = t["PnL"].sum()
            print(f"  {yr:<6}  {len(t):>5}  {wr:>6.1f}%  {avg_pnl:>+8.3f}%"
                  f"  {total_pnl:>+10.2f}%  {pf:>6.2f}  {pts:>+8.0f}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Strategy Health Monitor")
    parser.add_argument("--recent-only", action="store_true",
                        help="Skip full cross-analysis, show dashboard only")
    parser.add_argument("--lookback", type=int, default=20,
                        help="Lookback days for health dashboard (default: 20)")
    args = parser.parse_args()

    print("=" * 80)
    print("Strategy Health Monitor")
    print("=" * 80)

    # 1. Compute regime metrics
    regime = compute_daily_regime()

    # 2. Run strategies
    trades_esthl = run_esthl()
    trades_rev = run_reversal()
    all_trades = {"EstHL": trades_esthl, "Reversal": trades_rev}

    if not args.recent_only:
        # 3. Year-by-year regime
        print_yearly_regime(regime)

        # 4. Year-by-year strategy performance in %
        print_yearly_strategy_pct(all_trades)

        # 5. Cross-analysis
        for name, trades in all_trades.items():
            print_cross_analysis(trades, regime, name)

    # 6. Health dashboard
    print_health_dashboard(regime, all_trades, lookback=args.lookback)

    print()


if __name__ == "__main__":
    main()
