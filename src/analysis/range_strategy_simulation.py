"""波幅策略延伸測試

基於 range_estimation_compare.py 的發現，測試：
  1. 兩段式出場：Fib 1.618 出半倉 + OR×2.0 出剩餘
  2. 成交量篩選：清淡日不做
  3. 跳空條件篩選
  4. 組合篩選
  5. Fib 1.618 vs OR×2.0 單段出場比較
  6. 加入 SL 的完整模擬

用法:
    uv run python src/analysis/range_strategy_simulation.py
"""

import sys
from datetime import time as dtime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

DB_PATH = "data/futures.duckdb"

YEARS = [
    ("2021", 2021), ("2022", 2022), ("2023", 2023),
    ("2024", 2024), ("2025", 2025), ("2026", 2026),
]


def fv(v, w=7, dec=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—".rjust(w)
    if isinstance(v, float):
        return f"{v:.{dec}f}".rjust(w)
    return str(v).rjust(w)


def _pf(wins_sum, losses_sum):
    return wins_sum / losses_sum if losses_sum > 0 else float("inf")


def _print_summary(label, trades_df, indent="  "):
    """Print standard summary for a trades DataFrame with 'pnl' column."""
    if trades_df.empty:
        print(f"{indent}{label}: 無交易")
        return
    n = len(trades_df)
    pnl = trades_df["pnl"]
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    win_rate = len(wins) / n * 100
    avg = pnl.mean()
    total = pnl.sum()
    pf = _pf(wins.sum(), losses.abs().sum())
    print(f"{indent}{label:<24} n={n:>4}  勝率={win_rate:>5.1f}%"
          f"  avg={avg:>+7.1f}  total={total:>+7.0f}  PF={pf:>5.2f}")


# ── Data loading ──────────────────────────────────────────────────────────────

def load_data():
    """Load 1-min bars + daily features."""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df_bars = conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME BETWEEN '08:45' AND '13:45'
            ORDER BY timestamp
        """).fetchdf()

        df_daily = conn.execute("""
            SELECT
                timestamp::DATE AS trade_date,
                MIN_BY(open, timestamp) AS day_open,
                MAX(high) AS day_high,
                MIN(low) AS day_low,
                MAX_BY(close, timestamp) AS day_close,
                SUM(volume) AS day_volume,
                MAX(high) - MIN(low) AS day_range
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME BETWEEN '08:45' AND '13:45'
            GROUP BY 1
            ORDER BY 1
        """).fetchdf()

    df_bars["timestamp"] = pd.to_datetime(df_bars["timestamp"])
    df_bars["date"] = df_bars["timestamp"].dt.date
    df_bars["time"] = df_bars["timestamp"].dt.time

    df_daily["trade_date"] = pd.to_datetime(df_daily["trade_date"])
    df_daily = df_daily.set_index("trade_date").sort_index()
    df_daily["year"] = df_daily.index.year
    df_daily["weekday"] = df_daily.index.dayofweek

    # Volume ratio — 三種無 lookahead 的量比
    # 1. 前日量比：昨天成交量 / 20日均量（完全無 lookahead）
    df_daily["vol_prev"] = df_daily["day_volume"].shift(1)
    df_daily["vol_20ma"] = df_daily["day_volume"].shift(1).rolling(20, min_periods=10).mean()
    df_daily["vol_ratio_prev"] = df_daily["vol_prev"] / df_daily["vol_20ma"]

    # 2. 近5日均量趨勢：近5日均量 / 近20日均量
    vol_5ma = df_daily["day_volume"].shift(1).rolling(5, min_periods=3).mean()
    df_daily["vol_ratio_trend"] = vol_5ma / df_daily["vol_20ma"]

    # Legacy: 當日量比（有 lookahead，僅作對照）
    df_daily["vol_ratio_today"] = df_daily["day_volume"] / df_daily["vol_20ma"]

    # Gap
    df_daily["gap"] = df_daily["day_open"] - df_daily["day_close"].shift(1)
    df_daily["gap_pct"] = df_daily["gap"] / df_daily["day_close"].shift(1) * 100

    return df_bars, df_daily


def compute_or_features(df_bars: pd.DataFrame) -> dict:
    """Compute OR (08:45–09:30) features per day, including OR session volume."""
    or_bars = df_bars[(df_bars["time"] >= dtime(8, 45)) & (df_bars["time"] <= dtime(9, 30))]
    or_features = {}
    for date, group in or_bars.groupby("date"):
        or_high = group["high"].max()
        or_low = group["low"].min()
        or_width = or_high - or_low
        or_volume = group["volume"].sum()
        or_features[date] = {
            "or_high": or_high,
            "or_low": or_low,
            "or_width": or_width,
            "or_volume": or_volume,
        }
    return or_features


def compute_or_vol_ratio(or_features: dict) -> dict:
    """Compute OR volume ratio: today's OR volume / 20-day avg OR volume."""
    dates = sorted(or_features.keys())
    or_vols = pd.Series({d: or_features[d]["or_volume"] for d in dates})
    or_vol_20ma = or_vols.rolling(20, min_periods=10).mean().shift(1)
    ratios = {}
    for d in dates:
        if d in or_vol_20ma.index and not np.isnan(or_vol_20ma[d]):
            ratios[d] = or_vols[d] / or_vol_20ma[d]
        else:
            ratios[d] = np.nan
    return ratios


# ── Trade simulation ──────────────────────────────────────────────────────────

def simulate_trades(df_bars: pd.DataFrame, df_daily: pd.DataFrame,
                    or_features: dict,
                    tp1_mult: float = 1.618,
                    tp2_mult: float | None = 2.0,
                    sl_mult: float = 0.5,
                    entry_start: dtime = dtime(9, 31),
                    entry_end: dtime = dtime(11, 0),
                    exit_time: dtime = dtime(13, 30),
                    vol_filter: tuple | None = None,
                    vol_col: str = "vol_ratio_prev",
                    or_vol_ratios: dict | None = None,
                    gap_filter: str | None = None,
                    weekday_skip: list | None = None,
                    ) -> pd.DataFrame:
    """Simulate OR breakout trades with configurable TP/SL.

    Parameters:
    - tp1_mult: first TP as OR width multiplier (from OR high)
    - tp2_mult: second TP (None = single exit), from OR high
    - sl_mult: SL as OR width multiplier below entry
    - vol_filter: (min_ratio, max_ratio) or None
    - vol_col: which volume ratio column to use ("vol_ratio_prev", "vol_ratio_trend", "or_vol")
    - or_vol_ratios: dict of date->ratio for OR volume (used when vol_col="or_vol")
    - gap_filter: "big_down" | "no_flat" | None
    - weekday_skip: list of weekday ints to skip (3=Thu, 4=Fri)
    """
    daily_map = df_daily.to_dict("index")
    dates = sorted(df_bars["date"].unique())

    trades = []
    for date in dates:
        td = pd.Timestamp(date)
        if td not in daily_map or date not in or_features:
            continue
        info = daily_map[td]
        orf = or_features[date]
        or_high = orf["or_high"]
        or_low = orf["or_low"]
        or_width = orf["or_width"]

        if or_width <= 0:
            continue

        # Filters
        if weekday_skip and info["weekday"] in weekday_skip:
            continue
        if vol_filter:
            if vol_col == "or_vol" and or_vol_ratios:
                vr = or_vol_ratios.get(date, np.nan)
            else:
                vr = info.get(vol_col, np.nan)
            if np.isnan(vr) or vr < vol_filter[0] or vr > vol_filter[1]:
                continue
        if gap_filter == "big_down_only":
            gp = info.get("gap_pct", np.nan)
            if np.isnan(gp) or gp >= -0.5:
                continue
        if gap_filter == "no_flat":
            gp = info.get("gap_pct", np.nan)
            if not np.isnan(gp) and -0.1 <= gp <= 0.1:
                continue

        day = df_bars[df_bars["date"] == date].sort_values("time")
        entry_window = day[(day["time"] >= entry_start) & (day["time"] <= entry_end)]

        # Look for long breakout above OR high
        entered = False
        for _, bar in entry_window.iterrows():
            if bar["high"] > or_high:
                entry_price = or_high  # assume fill at OR high (limit order)
                entered = True

                tp1_price = entry_price + or_width * tp1_mult
                tp2_price = entry_price + or_width * tp2_mult if tp2_mult else None
                sl_price = entry_price - or_width * sl_mult

                # Simulate bar-by-bar after entry
                after_entry = day[day["time"] > bar["time"]]
                exit_price = None
                exit_reason = None
                tp1_filled = False
                partial_pnl = 0.0

                for _, ebar in after_entry.iterrows():
                    if ebar["time"] > exit_time:
                        break

                    # Check SL first
                    if ebar["low"] <= sl_price:
                        if tp2_mult and tp1_filled:
                            # Only half position left, SL on remaining
                            exit_price = sl_price
                            exit_reason = "SL(半倉)"
                        else:
                            exit_price = sl_price
                            exit_reason = "SL"
                        break

                    # Check TP1
                    if not tp1_filled and ebar["high"] >= tp1_price:
                        if tp2_mult:
                            # Two-stage: close half at TP1
                            tp1_filled = True
                            partial_pnl = (tp1_price - entry_price) * 0.5
                        else:
                            exit_price = tp1_price
                            exit_reason = "TP"
                            break

                    # Check TP2
                    if tp2_mult and tp1_filled and ebar["high"] >= tp2_price:
                        exit_price = tp2_price
                        exit_reason = "TP2"
                        break

                # Force exit at exit_time
                if exit_price is None:
                    force_bar = day[day["time"] == exit_time]
                    if not force_bar.empty:
                        exit_price = force_bar.iloc[0]["close"]
                    else:
                        exit_price = day.iloc[-1]["close"]
                    exit_reason = "FORCE"

                if tp2_mult:
                    if tp1_filled and exit_reason != "TP2":
                        # Half closed at TP1 + half at exit
                        pnl = partial_pnl + (exit_price - entry_price) * 0.5
                    elif tp1_filled and exit_reason == "TP2":
                        pnl = partial_pnl + (tp2_price - entry_price) * 0.5
                    else:
                        # Neither TP1 hit — full position exit
                        pnl = exit_price - entry_price
                else:
                    pnl = exit_price - entry_price

                trades.append({
                    "date": date,
                    "year": td.year,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "exit_reason": exit_reason,
                    "pnl": pnl,
                    "pnl_pct": pnl / entry_price * 100,
                    "or_width": or_width,
                    "tp1_filled": tp1_filled if tp2_mult else None,
                })
                break  # one trade per day

    return pd.DataFrame(trades)


def print_yearly(trades: pd.DataFrame, label: str):
    print(f"\n  逐年（{label}）")
    print(f"  {'Year':<6} {'n':>4} {'勝率%':>7} {'avg':>8} {'total':>8} {'PF':>7}")
    print(f"  {'-'*6} {'-'*4} {'-'*7} {'-'*8} {'-'*8} {'-'*7}")
    for yr_label, yr in YEARS:
        yr_data = trades[trades["year"] == yr]
        if yr_data.empty:
            continue
        pnl = yr_data["pnl"]
        wins = pnl[pnl > 0]
        losses = pnl[pnl < 0]
        wr = len(wins) / len(pnl) * 100
        pf = _pf(wins.sum(), losses.abs().sum())
        print(f"  {yr_label:<6} {len(pnl):>4} {wr:>6.1f}% {pnl.mean():>+7.1f}"
              f" {pnl.sum():>+7.0f} {pf:>7.2f}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 72)
    print("波幅策略延伸測試")
    print("=" * 72)

    print("\n載入資料...", flush=True)
    df_bars, df_daily = load_data()
    or_features = compute_or_features(df_bars)
    print(f"  {len(df_daily)} 交易日, OR 特徵 {len(or_features)} 天")

    # ══════════════════════════════════════════════════════════════════════
    # Test 1: Single TP comparisons
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 72)
    print("Test 1: 單段出場 — 不同 TP 乘數比較（SL = OR×0.5）")
    print("=" * 72)

    tp_mults = [1.0, 1.5, 1.618, 2.0, 2.618, 3.0]
    for tp in tp_mults:
        trades = simulate_trades(df_bars, df_daily, or_features,
                                 tp1_mult=tp, tp2_mult=None, sl_mult=0.5)
        _print_summary(f"TP=OR×{tp:.3f}", trades)

    # Best single TP year-by-year
    trades_fib = simulate_trades(df_bars, df_daily, or_features,
                                  tp1_mult=1.618, tp2_mult=None, sl_mult=0.5)
    print_yearly(trades_fib, "TP=OR×1.618, SL=OR×0.5")

    trades_2x = simulate_trades(df_bars, df_daily, or_features,
                                 tp1_mult=2.0, tp2_mult=None, sl_mult=0.5)
    print_yearly(trades_2x, "TP=OR×2.0, SL=OR×0.5")

    # ══════════════════════════════════════════════════════════════════════
    # Test 2: Two-stage exit
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 72)
    print("Test 2: 兩段式出場 — TP1 出半倉 + TP2 出剩餘")
    print("=" * 72)

    two_stage_configs = [
        (1.0, 2.0, "TP1=1.0 + TP2=2.0"),
        (1.5, 2.5, "TP1=1.5 + TP2=2.5"),
        (1.618, 2.0, "TP1=Fib1.618 + TP2=2.0"),
        (1.618, 2.618, "TP1=Fib1.618 + TP2=Fib2.618"),
        (1.0, 1.618, "TP1=1.0 + TP2=Fib1.618"),
    ]

    for tp1, tp2, label in two_stage_configs:
        trades = simulate_trades(df_bars, df_daily, or_features,
                                 tp1_mult=tp1, tp2_mult=tp2, sl_mult=0.5)
        _print_summary(label, trades)

    # Best two-stage year-by-year
    trades_2s = simulate_trades(df_bars, df_daily, or_features,
                                 tp1_mult=1.618, tp2_mult=2.618, sl_mult=0.5)
    print_yearly(trades_2s, "TP1=Fib1.618 + TP2=Fib2.618")

    # Exit reason breakdown
    if not trades_2s.empty:
        print(f"\n  出場原因分佈（TP1=Fib1.618 + TP2=Fib2.618）")
        for reason in ["TP2", "SL", "SL(半倉)", "FORCE"]:
            sub = trades_2s[trades_2s["exit_reason"] == reason]
            if sub.empty:
                continue
            pct = len(sub) / len(trades_2s) * 100
            avg_pnl = sub["pnl"].mean()
            print(f"  {reason:<12} {len(sub):>5} ({pct:>5.1f}%)  avg pnl={avg_pnl:>+7.1f}")

    # ══════════════════════════════════════════════════════════════════════
    # Test 3: SL sensitivity
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 72)
    print("Test 3: SL 敏感度（固定 TP=OR×1.618）")
    print("=" * 72)

    sl_mults = [0.3, 0.4, 0.5, 0.618, 0.75, 1.0]
    for sl in sl_mults:
        trades = simulate_trades(df_bars, df_daily, or_features,
                                 tp1_mult=1.618, tp2_mult=None, sl_mult=sl)
        _print_summary(f"SL=OR×{sl:.3f}", trades)

    # ══════════════════════════════════════════════════════════════════════
    # Test 4: Volume filter (NO LOOKAHEAD)
    # ══════════════════════════════════════════════════════════════════════
    or_vol_ratios = compute_or_vol_ratio(or_features)

    print("\n" + "=" * 72)
    print("Test 4: 成交量篩選（TP=OR×1.618, SL=OR×0.5）")
    print("  ※ 修正：不使用當日總量（lookahead），改用可事前取得的量比")
    print("=" * 72)

    print(f"\n  --- 4a: 前日量比（昨日量 / 20日均量）---")
    for vf, label in [
        (None, "無篩選"),
        ((0.7, 999), "前日量比 >= 0.7"),
        ((1.0, 999), "前日量比 >= 1.0"),
        ((0.7, 1.5), "前日量比 0.7-1.5"),
    ]:
        trades = simulate_trades(df_bars, df_daily, or_features,
                                 tp1_mult=1.618, tp2_mult=None, sl_mult=0.5,
                                 vol_filter=vf, vol_col="vol_ratio_prev")
        _print_summary(label, trades)

    print(f"\n  --- 4b: 近5日量趨勢（5日均量 / 20日均量）---")
    for vf, label in [
        (None, "無篩選"),
        ((0.8, 999), "5日趨勢 >= 0.8"),
        ((1.0, 999), "5日趨勢 >= 1.0"),
    ]:
        trades = simulate_trades(df_bars, df_daily, or_features,
                                 tp1_mult=1.618, tp2_mult=None, sl_mult=0.5,
                                 vol_filter=vf, vol_col="vol_ratio_trend")
        _print_summary(label, trades)

    print(f"\n  --- 4c: OR 段量比（當日OR量 / 20日OR均量，09:30已知）---")
    for vf, label in [
        (None, "無篩選"),
        ((0.7, 999), "OR量比 >= 0.7"),
        ((1.0, 999), "OR量比 >= 1.0"),
        ((1.5, 999), "OR量比 >= 1.5"),
    ]:
        trades = simulate_trades(df_bars, df_daily, or_features,
                                 tp1_mult=1.618, tp2_mult=None, sl_mult=0.5,
                                 vol_filter=vf, vol_col="or_vol",
                                 or_vol_ratios=or_vol_ratios)
        _print_summary(label, trades)

    print(f"\n  --- 4d: 對照（當日量比，有 LOOKAHEAD，僅參考）---")
    for vf, label in [
        ((0.7, 999), "⚠ 當日量比>=0.7 (LOOKAHEAD)"),
        ((1.0, 999), "⚠ 當日量比>=1.0 (LOOKAHEAD)"),
    ]:
        trades = simulate_trades(df_bars, df_daily, or_features,
                                 tp1_mult=1.618, tp2_mult=None, sl_mult=0.5,
                                 vol_filter=vf, vol_col="vol_ratio_today")
        _print_summary(label, trades)

    # ══════════════════════════════════════════════════════════════════════
    # Test 5: Gap filter
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 72)
    print("Test 5: 跳空篩選（TP=OR×1.618, SL=OR×0.5）")
    print("=" * 72)

    gap_filters = [
        (None, "無篩選"),
        ("no_flat", "排除平開（|gap| < 0.1%）"),
        ("big_down_only", "只做大跳空下（gap < -0.5%）"),
    ]
    for gf, label in gap_filters:
        trades = simulate_trades(df_bars, df_daily, or_features,
                                 tp1_mult=1.618, tp2_mult=None, sl_mult=0.5,
                                 gap_filter=gf)
        _print_summary(label, trades)

    # ══════════════════════════════════════════════════════════════════════
    # Test 6: Weekday filter
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 72)
    print("Test 6: 星期篩選（TP=OR×1.618, SL=OR×0.5）")
    print("=" * 72)

    weekday_filters = [
        (None, "無篩選"),
        ([4], "跳過週五"),
        ([3, 4], "跳過週四週五"),
        ([0], "跳過週一"),
    ]
    for wf, label in weekday_filters:
        trades = simulate_trades(df_bars, df_daily, or_features,
                                 tp1_mult=1.618, tp2_mult=None, sl_mult=0.5,
                                 weekday_skip=wf)
        _print_summary(label, trades)

    # ══════════════════════════════════════════════════════════════════════
    # Test 7: Combined best filters
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 72)
    print("Test 7: 組合篩選")
    print("=" * 72)

    # (tp1, tp2, sl, vol, vol_col, gap, weekday_skip, label)
    combos = [
        (1.618, None, 0.5, None, "vol_ratio_prev", None, None, "基準（無篩選）"),
        (1.618, None, 0.5, (0.7, 999), "vol_ratio_prev", None, None, "前日量>=0.7"),
        (1.618, None, 0.5, (0.7, 999), "or_vol", None, None, "OR量>=0.7"),
        (1.618, None, 0.5, None, "vol_ratio_prev", None, [3, 4], "跳週四五"),
        (1.618, None, 0.5, (0.7, 999), "vol_ratio_prev", None, [3, 4], "前日量>=0.7 + 跳週四五"),
        (1.618, None, 0.5, (0.7, 999), "or_vol", None, [3, 4], "OR量>=0.7 + 跳週四五"),
        (1.618, None, 0.5, (1.0, 999), "or_vol", None, [3, 4], "OR量>=1.0 + 跳週四五"),
    ]

    for tp1, tp2, sl, vf, vc, gf, ws, label in combos:
        trades = simulate_trades(df_bars, df_daily, or_features,
                                 tp1_mult=tp1, tp2_mult=tp2, sl_mult=sl,
                                 vol_filter=vf, vol_col=vc, gap_filter=gf,
                                 weekday_skip=ws,
                                 or_vol_ratios=or_vol_ratios if vc == "or_vol" else None)
        _print_summary(label, trades)

    # Year-by-year for top combos
    print(f"\n  --- 最佳組合逐年 ---")
    for tp1, tp2, sl, vf, vc, gf, ws, label in combos[4:7]:
        trades = simulate_trades(df_bars, df_daily, or_features,
                                 tp1_mult=tp1, tp2_mult=tp2, sl_mult=sl,
                                 vol_filter=vf, vol_col=vc, gap_filter=gf,
                                 weekday_skip=ws,
                                 or_vol_ratios=or_vol_ratios if vc == "or_vol" else None)
        print_yearly(trades, label)

    # ══════════════════════════════════════════════════════════════════════
    # Test 8: vs ORBLong (backtesting.py)
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 72)
    print("Test 8: 與現有 ORBLong 策略比較")
    print("=" * 72)

    from backtesting import Backtest
    from src.backtest.runner import load_data_with_night_ma
    from src.strategies.orb import ORBLongStrategy

    print("  載入 ORBLong 資料...", flush=True)
    df_orb = load_data_with_night_ma(trend_ma_days=10)

    orb_configs = [
        ("ORBLong 現有最佳", dict(
            sl_pct=0.004, tp_or_multiplier=1.5, trend_ma_days=10,
            or_pct_min=0.3, or_pct_max=1.0, thu_or_pct_min=0.7,
        )),
        ("ORBLong + Fib TP", dict(
            sl_pct=0.004, tp_or_multiplier=1.618, trend_ma_days=10,
            or_pct_min=0.3, or_pct_max=1.0, thu_or_pct_min=0.7,
        )),
    ]

    for label, params in orb_configs:
        bt = Backtest(df_orb, ORBLongStrategy,
                      cash=200_000, commission=0.0, trade_on_close=True)
        stats = bt.run(**params)
        trades_orb = stats["_trades"].copy()
        trades_orb["year"] = pd.to_datetime(trades_orb["EntryTime"]).dt.year
        trades_orb["pnl"] = trades_orb["PnL"]
        _print_summary(label, trades_orb)

    # Year-by-year for both
    for label, params in orb_configs:
        bt = Backtest(df_orb, ORBLongStrategy,
                      cash=200_000, commission=0.0, trade_on_close=True)
        stats = bt.run(**params)
        trades_orb = stats["_trades"].copy()
        trades_orb["year"] = pd.to_datetime(trades_orb["EntryTime"]).dt.year
        trades_orb["pnl"] = trades_orb["PnL"]
        print_yearly(trades_orb, label)

    # Our best simulation configs for direct comparison
    print(f"\n  本研究最佳組合（對照）")
    best_configs = [
        (1.618, None, 0.5, None, "vol_ratio_prev", None, None, "Fib策略 無篩選"),
        (1.618, None, 0.5, (0.7, 999), "or_vol", None, [3, 4], "Fib策略 OR量>=0.7+跳週四五"),
        (1.618, None, 0.5, (1.0, 999), "or_vol", None, [3, 4], "Fib策略 OR量>=1.0+跳週四五"),
    ]
    for tp1, tp2, sl, vf, vc, gf, ws, label in best_configs:
        trades = simulate_trades(df_bars, df_daily, or_features,
                                 tp1_mult=tp1, tp2_mult=tp2, sl_mult=sl,
                                 vol_filter=vf, vol_col=vc, gap_filter=gf,
                                 weekday_skip=ws,
                                 or_vol_ratios=or_vol_ratios if vc == "or_vol" else None)
        _print_summary(label, trades)
        print_yearly(trades, label)

    print("\n" + "=" * 72)
    print("分析完成")
    print("=" * 72)


if __name__ == "__main__":
    main()
