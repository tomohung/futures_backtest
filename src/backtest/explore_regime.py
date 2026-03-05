#!/usr/bin/env python3
"""Phase 6 Step 0: Explore regime indicators.

Compute daily ATR%, ADX(14), realized volatility, and rolling ORB win rate.
Analyze which indicator best distinguishes "good" vs "bad" days for the ORB strategy.

Analysis sections:
  1. Year-by-year regime indicator averages (validate 2021 was structurally different)
  2. Indicator quartile × strategy performance (win%, exp, total PnL)
  3. Point-biserial correlation: indicator value vs trade win/loss
  4. Long-only breakdown (longs drive most of the 2021 problem)
  5. Rolling ORB win rate analysis (self-adaptive filter potential)
  6. Decision gate summary

Usage:
    uv run python src/backtest/explore_regime.py
"""
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_with_night_ma
from src.strategies.orb import ORBLongStrategy

DB_PATH = "data/futures.duckdb"

PH4H_PARAMS = dict(
    range_end_minute=90, entry_end_minute=120,
    sl_pct=0.004, tp_or_multiplier=1.5, or_min_width=20.0,
    tp_multiplier=1.5, trail_activate_minute=45, trend_ma_days=10,
    min_rolling_or=0.0,
)

YEARS = [
    ("2021", "2021-01-01", "2021-12-31"),
    ("2022", "2022-01-01", "2022-12-31"),
    ("2023", "2023-01-01", "2023-12-31"),
    ("2024", "2024-01-01", "2024-12-31"),
    ("2025", "2025-01-01", "2025-12-31"),
    ("2026", "2026-01-01", None),
]


# ── Indicator computation ─────────────────────────────────────────────────────

def wilder_smooth(arr: np.ndarray, period: int) -> np.ndarray:
    """Wilder's smoothing (RMA): used in ATR and ADX."""
    out = np.full(len(arr), np.nan)
    # Find the first window where all values are valid
    for i in range(period - 1, len(arr)):
        window = arr[i - period + 1: i + 1]
        if not np.any(np.isnan(window)):
            out[i] = window.mean()
            break
    start = np.argmax(~np.isnan(out))
    if np.all(np.isnan(out)):
        return out
    for i in range(start + 1, len(arr)):
        if not np.isnan(arr[i]):
            out[i] = out[i - 1] * (period - 1) / period + arr[i] / period
    return out


def compute_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                period: int = 14) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (ADX, +DI, -DI) arrays."""
    n = len(high)
    tr   = np.full(n, np.nan)
    dm_p = np.full(n, np.nan)
    dm_m = np.full(n, np.nan)

    for i in range(1, n):
        tr[i]   = max(high[i] - low[i],
                      abs(high[i] - close[i - 1]),
                      abs(low[i]  - close[i - 1]))
        up   = high[i] - high[i - 1]
        down = low[i - 1] - low[i]
        dm_p[i] = up   if (up > down and up > 0)   else 0.0
        dm_m[i] = down if (down > up and down > 0) else 0.0

    atr_s = wilder_smooth(tr,   period)
    dmp_s = wilder_smooth(dm_p, period)
    dmm_s = wilder_smooth(dm_m, period)

    di_p = 100 * dmp_s / (atr_s + 1e-10)
    di_m = 100 * dmm_s / (atr_s + 1e-10)
    dx   = 100 * np.abs(di_p - di_m) / (di_p + di_m + 1e-10)
    adx  = wilder_smooth(dx, period)
    return adx, di_p, di_m


def load_daily_ohlcv() -> pd.DataFrame:
    """Synthesize daily OHLCV from 1-min day session bars."""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT
                CAST(timestamp AS DATE)          AS trade_date,
                MIN_BY(open,  timestamp)         AS open,
                MAX(high)                        AS high,
                MIN(low)                         AS low,
                MAX_BY(close, timestamp)         AS close,
                SUM(volume)                      AS volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            GROUP BY 1
            ORDER BY 1
        """).df()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df.set_index("trade_date")


def compute_indicators(df_daily: pd.DataFrame,
                       adx_period: int = 14,
                       atr_period: int = 14,
                       vol_period: int = 21) -> pd.DataFrame:
    high  = df_daily["high"].values
    low   = df_daily["low"].values
    close = df_daily["close"].values
    n = len(df_daily)

    # True Range (simple, for ATR%)
    tr = np.full(n, np.nan)
    for i in range(1, n):
        tr[i] = max(high[i] - low[i],
                    abs(high[i] - close[i - 1]),
                    abs(low[i]  - close[i - 1]))
    atr     = pd.Series(tr, index=df_daily.index).rolling(atr_period, min_periods=atr_period).mean()
    atr_pct = atr / pd.Series(close, index=df_daily.index) * 100

    # ADX
    adx_arr, di_p_arr, di_m_arr = compute_adx(high, low, close, period=adx_period)
    adx   = pd.Series(adx_arr,   index=df_daily.index)
    di_p  = pd.Series(di_p_arr,  index=df_daily.index)
    di_m  = pd.Series(di_m_arr,  index=df_daily.index)

    # Realized volatility (annualized %)
    log_ret = np.concatenate([[np.nan], np.log(close[1:] / close[:-1])])
    real_vol = (pd.Series(log_ret, index=df_daily.index)
                .rolling(vol_period, min_periods=vol_period)
                .std() * np.sqrt(252) * 100)

    return pd.DataFrame({
        "atr_pct":  atr_pct,
        "adx":      adx,
        "di_plus":  di_p,
        "di_minus": di_m,
        "real_vol": real_vol,
    }, index=df_daily.index)


def get_ph4h_trades() -> pd.DataFrame:
    """Run Ph4 Hybrid on full history and return trades with entry date."""
    df = load_data_with_night_ma(trend_ma_days=10)
    bt = Backtest(df, ORBLongStrategy, cash=200_000,
                  commission=0.0, trade_on_close=True)
    trades = bt.run(**PH4H_PARAMS)["_trades"].copy()
    trades["entry_date"] = pd.to_datetime(trades["EntryTime"]).dt.normalize()
    trades["win"]        = (trades["PnL"] > 0).astype(int)
    trades["direction"]  = trades["Size"].apply(lambda x: "long" if x > 0 else "short")
    return trades


# ── Formatting helpers ────────────────────────────────────────────────────────

def fv(v, w=7, dec=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—".rjust(w)
    if isinstance(v, float):
        return f"{v:.{dec}f}".rjust(w)
    return str(v).rjust(w)


def quartile_table(df_trades: pd.DataFrame, col: str, label: str):
    valid = df_trades[df_trades[col].notna()].copy()
    if len(valid) < 20:
        print(f"  Insufficient data for {label}")
        return
    valid["q"] = pd.qcut(valid[col], 4, labels=["Q1(low)", "Q2", "Q3", "Q4(high)"])
    print(f"\n  [{label}]")
    print(f"  {'Quartile':<10}  {'n':>5}  {'win%':>7}  {'exp':>8}  {'total':>9}  {'value range':>14}")
    print(f"  {'-'*10}  {'-'*5}  {'-'*7}  {'-'*8}  {'-'*9}  {'-'*14}")
    for q_label, grp in valid.groupby("q", observed=True):
        pnl  = grp["PnL"]
        win  = len(pnl[pnl > 0]) / len(pnl) * 100
        lo   = grp[col].min()
        hi   = grp[col].max()
        print(f"  {str(q_label):<10}  {len(pnl):>5}  {win:>6.1f}%  {fv(pnl.mean(), 8):>8}"
              f"  {fv(pnl.sum(), 9, 0):>9}  {lo:.1f} ~ {hi:.1f}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 72)
    print("Phase 6 Step 0 — Regime Indicator Exploration")
    print("=" * 72)

    print("\nLoading daily OHLCV and computing regime indicators...", flush=True)
    df_daily = load_daily_ohlcv()
    reg = compute_indicators(df_daily)
    print(f"  {len(df_daily):,} daily bars  "
          f"{df_daily.index[0].date()} ~ {df_daily.index[-1].date()}")

    print("\nRunning Ph4 Hybrid backtest (full history)...", flush=True)
    trades = get_ph4h_trades()
    print(f"  {len(trades)} total trades")

    # Join trades with indicators on entry date
    trades = trades.join(reg, on="entry_date")

    # ── 1. Year-by-year indicator averages ────────────────────────────────
    print("\n" + "=" * 72)
    print("1. YEAR-BY-YEAR REGIME INDICATOR AVERAGES")
    print("=" * 72)
    print(f"  {'Year':<6}  {'ATR%':>7}  {'ADX':>7}  {'RealVol%':>9}  {'n_days':>7}")
    print(f"  {'-'*6}  {'-'*7}  {'-'*7}  {'-'*9}  {'-'*7}")
    for yr, start, end in YEARS:
        mask = reg.index >= start
        if end:
            mask &= reg.index <= end
        r = reg[mask]
        print(f"  {yr:<6}  {fv(r['atr_pct'].mean()):>7}"
              f"  {fv(r['adx'].mean()):>7}"
              f"  {fv(r['real_vol'].mean()):>9}"
              f"  {len(r):>7}")

    # ── 2. Quartile analysis — all trades ─────────────────────────────────
    print("\n" + "=" * 72)
    print("2. INDICATOR QUARTILE × STRATEGY PERFORMANCE  (all trades)")
    print("=" * 72)
    for col, label in [("atr_pct", "ATR%"), ("adx", "ADX"), ("real_vol", "RealVol%")]:
        quartile_table(trades, col, label)

    # ── 3. Correlation: indicator vs trade win ────────────────────────────
    print("\n" + "=" * 72)
    print("3. POINT-BISERIAL CORRELATION — indicator value vs win (1) / loss (0)")
    print("=" * 72)
    indicators = [("ATR%", "atr_pct"), ("ADX", "adx"), ("RealVol%", "real_vol")]
    for name, col in indicators:
        valid = trades[trades[col].notna()].copy()
        if len(valid) < 10:
            print(f"  {name:<12}: insufficient data")
            continue
        r_all   = valid[col].corr(valid["win"])
        r_long  = valid[valid["direction"] == "long"][col].corr(
                      valid[valid["direction"] == "long"]["win"])
        r_short = valid[valid["direction"] == "short"][col].corr(
                      valid[valid["direction"] == "short"]["win"])
        print(f"  {name:<12}  r(all)={r_all:+.3f}  "
              f"r(long)={r_long:+.3f}  r(short)={r_short:+.3f}")

    # ── 4. Long-only quartile breakdown ──────────────────────────────────
    print("\n" + "=" * 72)
    print("4. LONG TRADES ONLY — QUARTILE BREAKDOWN")
    print("   (Longs drive the 2021 underperformance)")
    print("=" * 72)
    long_trades = trades[trades["direction"] == "long"].copy()
    for col, label in [("atr_pct", "ATR% — Longs"), ("adx", "ADX — Longs"),
                       ("real_vol", "RealVol% — Longs")]:
        quartile_table(long_trades, col, label)

    # ── 5. Rolling ORB win rate ───────────────────────────────────────────
    print("\n" + "=" * 72)
    print("5. ROLLING ORB WIN RATE  (past-N-trade win rate vs current trade outcome)")
    print("=" * 72)
    trades_sorted = trades.sort_values("EntryTime").reset_index(drop=True)
    for window in [10, 20, 30]:
        trades_sorted[f"roll_win_{window}"] = (
            trades_sorted["win"]
            .shift(1)
            .rolling(window, min_periods=window)
            .mean() * 100
        )
    print("\n  Correlation with trade win:")
    for window in [10, 20, 30]:
        col = f"roll_win_{window}"
        valid = trades_sorted[trades_sorted[col].notna()]
        r = valid[col].corr(valid["win"])
        r_l = valid[valid["direction"] == "long"][col].corr(
                  valid[valid["direction"] == "long"]["win"])
        print(f"  N={window:<3}  r(all)={r:+.3f}  r(long)={r_l:+.3f}"
              f"  (n_valid={len(valid)})")

    # Quartile breakdown for best rolling window (N=20)
    col = "roll_win_20"
    valid = trades_sorted[trades_sorted[col].notna()].copy()
    if len(valid) >= 20:
        valid["q"] = pd.qcut(valid[col], 4,
                             labels=["Q1(cold)", "Q2", "Q3", "Q4(hot)"])
        print(f"\n  [Rolling win rate N=20 — all trades]")
        print(f"  {'Quartile':<12}  {'n':>5}  {'win%':>7}  {'exp':>8}  {'total':>9}  {'roll% range':>14}")
        print(f"  {'-'*12}  {'-'*5}  {'-'*7}  {'-'*8}  {'-'*9}  {'-'*14}")
        for q_label, grp in valid.groupby("q", observed=True):
            pnl = grp["PnL"]
            win = len(pnl[pnl > 0]) / len(pnl) * 100
            lo  = grp[col].min()
            hi  = grp[col].max()
            print(f"  {str(q_label):<12}  {len(pnl):>5}  {win:>6.1f}%  {fv(pnl.mean(), 8):>8}"
                  f"  {fv(pnl.sum(), 9, 0):>9}  {lo:.1f}% ~ {hi:.1f}%")

    # ── 6. Decision gate ──────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("6. DECISION GATE")
    print("=" * 72)

    results = {}
    for name, col in indicators:
        valid = trades[trades[col].notna()]
        r = abs(valid[col].corr(valid["win"]))
        results[name] = r

    # Also rolling win rate N=20
    valid_rw = trades_sorted[trades_sorted["roll_win_20"].notna()]
    results["RollWin(20)"] = abs(valid_rw["roll_win_20"].corr(valid_rw["win"]))

    best = max(results, key=results.get)
    print()
    for name, r in sorted(results.items(), key=lambda x: -x[1]):
        if r > 0.15:
            verdict = "★ STRONG  → use as Phase 6 primary filter"
        elif r > 0.08:
            verdict = "◎ MODERATE → worth testing as filter"
        else:
            verdict = "✗ WEAK    → likely not useful as filter"
        marker = "→" if name == best else "  "
        print(f"  {marker} {name:<14}  |r|={r:.3f}  {verdict}")

    print(f"\n  Recommended primary indicator: {best}")
    print()


if __name__ == "__main__":
    main()
