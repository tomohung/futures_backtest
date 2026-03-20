"""日內波段策略方向研究（Step 0 探索）

方向 A：早盤方向偵測 + 波幅目標
方向 B：波幅預測 + 區間邊緣交易
方向 C：單次機會策略（One Clean Shot）

用法:
    uv run python src/analysis/early_session_direction.py
    uv run python src/analysis/early_session_direction.py --direction A
    uv run python src/analysis/early_session_direction.py --direction B
    uv run python src/analysis/early_session_direction.py --direction C
"""

import argparse
import sys
from datetime import time as dtime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

DB_PATH = "data/futures.duckdb"

YEARS = [
    ("2021", "2021-01-01", "2021-12-31"),
    ("2022", "2022-01-01", "2022-12-31"),
    ("2023", "2023-01-01", "2023-12-31"),
    ("2024", "2024-01-01", "2024-12-31"),
    ("2025", "2025-01-01", "2025-12-31"),
    ("2026", "2026-01-01", None),
]


# ── Formatting helpers ────────────────────────────────────────────────────────

def fv(v, w=7, dec=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—".rjust(w)
    if isinstance(v, float):
        return f"{v:.{dec}f}".rjust(w)
    return str(v).rjust(w)


# ── Data loading ──────────────────────────────────────────────────────────────

def load_minute_bars() -> pd.DataFrame:
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME BETWEEN '08:45' AND '13:45'
            ORDER BY timestamp
        """).fetchdf()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df["time"] = df["timestamp"].dt.time
    return df


def load_daily_summary() -> pd.DataFrame:
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT
                timestamp::DATE AS trade_date,
                MIN_BY(open, timestamp) AS day_open,
                MAX(high) AS day_high,
                MIN(low) AS day_low,
                MAX_BY(close, timestamp) AS day_close,
                SUM(volume) AS day_volume,
                MAX(high) - MIN(low) AS day_range,
                ARG_MAX(timestamp, high)::TIME AS high_time,
                ARG_MIN(timestamp, low)::TIME AS low_time
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME BETWEEN '08:45' AND '13:45'
            GROUP BY 1
            ORDER BY 1
        """).fetchdf()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["day_range_pct"] = df["day_range"] / df["day_open"] * 100
    df["year"] = df["trade_date"].dt.year
    df["is_up"] = (df["day_close"] > df["day_open"]).astype(int)
    return df


def build_session_features(df_bars: pd.DataFrame, df_daily: pd.DataFrame) -> pd.DataFrame:
    """Build per-day features from early session bars."""
    daily_map = df_daily.set_index("trade_date").to_dict("index")
    dates = sorted(df_bars["date"].unique())

    records = []
    for date in dates:
        td = pd.Timestamp(date)
        if td not in daily_map:
            continue
        info = daily_map[td]
        day = df_bars[df_bars["date"] == date].sort_values("time")
        if len(day) < 100:
            continue

        day_open = info["day_open"]
        day_close = info["day_close"]
        day_high = info["day_high"]
        day_low = info["day_low"]
        day_range = info["day_range"]
        is_up = info["is_up"]

        # ── Early session windows ──
        for window_end, label in [
            (dtime(9, 0), "15m"),
            (dtime(9, 15), "30m"),
            (dtime(9, 30), "45m"),
            (dtime(9, 45), "60m"),
        ]:
            window = day[(day["time"] >= dtime(8, 45)) & (day["time"] < window_end)]
            if len(window) < 5:
                continue

            w_open = window.iloc[0]["open"]
            w_close = window.iloc[-1]["close"]
            w_high = window["high"].max()
            w_low = window["low"].min()
            w_range = w_high - w_low

            # High/low time within window (minute index from 08:45)
            high_idx = window["high"].idxmax()
            low_idx = window["low"].idxmin()
            high_bar = window.loc[high_idx]
            low_bar = window.loc[low_idx]
            high_min = high_bar["time"].hour * 60 + high_bar["time"].minute - 525  # offset from 08:45
            low_min = low_bar["time"].hour * 60 + low_bar["time"].minute - 525
            window_len = (window_end.hour * 60 + window_end.minute) - 525

            # Pattern classification
            half = window_len // 2
            low_first_half = low_min < half
            high_first_half = high_min < half
            low_last5 = low_min >= window_len - 5
            high_last5 = high_min >= window_len - 5
            low_first5 = low_min < 5
            high_first5 = high_min < 5

            if high_last5 and low_first5:
                pattern = "trending_up"
            elif low_last5 and high_first5:
                pattern = "trending_down"
            elif low_first_half and w_close > w_open:
                pattern = "V"
            elif high_first_half and w_close < w_open:
                pattern = "inv_V"
            else:
                pattern = "range"

            # Direction indicators
            or_direction = 1 if w_close > w_open else (-1 if w_close < w_open else 0)
            shadow_ratio = (w_close - w_low) / w_range if w_range > 0 else 0.5
            vol_weighted_dir = 0.0
            total_vol = window["volume"].sum()
            if total_vol > 0:
                vol_weighted_dir = ((window["close"] - window["open"]) * window["volume"]).sum() / total_vol

            low_time_ratio = low_min / window_len if window_len > 0 else 0.5

            # First half vs second half close
            half_idx = len(window) // 2
            first_half_close = window.iloc[half_idx - 1]["close"] if half_idx > 0 else w_open
            momentum = 1 if w_close > first_half_close else -1

            # After-window outcome
            after = day[day["time"] >= window_end]
            if after.empty:
                continue
            after_close = after.iloc[-1]["close"]  # 13:45 close
            after_open = after.iloc[0]["open"]
            move_after = after_close - after_open  # move from window_end to day close

            # OR% (window range as % of open)
            or_pct = w_range / w_open * 100

            records.append({
                "date": date,
                "year": td.year,
                "window": label,
                "window_end": window_end,
                "day_open": day_open,
                "day_close": day_close,
                "day_high": day_high,
                "day_low": day_low,
                "day_range": day_range,
                "day_range_pct": day_range / day_open * 100,
                "is_up": is_up,
                "w_open": w_open,
                "w_close": w_close,
                "w_high": w_high,
                "w_low": w_low,
                "w_range": w_range,
                "or_pct": or_pct,
                "pattern": pattern,
                "or_direction": or_direction,
                "shadow_ratio": shadow_ratio,
                "vol_weighted_dir": vol_weighted_dir,
                "low_time_ratio": low_time_ratio,
                "momentum": momentum,
                "after_open": after_open,
                "after_close": after_close,
                "move_after": move_after,
                "move_after_pct": move_after / after_open * 100,
            })

    return pd.DataFrame(records)


# ══════════════════════════════════════════════════════════════════════════════
# 方向 A：早盤方向偵測
# ══════════════════════════════════════════════════════════════════════════════

def direction_a(feat: pd.DataFrame, df_bars: pd.DataFrame = None):
    print("\n" + "=" * 72)
    print("方向 A：早盤方向偵測 + 波幅目標")
    print("=" * 72)

    # ── A1: Pattern classification ──
    print("\n" + "-" * 72)
    print("A1: 開盤型態分類 → 全日方向預測")
    print("-" * 72)

    for wl in ["15m", "30m", "45m", "60m"]:
        wf = feat[feat["window"] == wl]
        print(f"\n  [{wl} 觀察窗口] n={len(wf)}")
        print(f"  {'型態':<16} {'n':>5} {'佔比%':>7} {'上漲率%':>8}"
              f" {'按型態做 avg pnl':>16} {'按型態做 total':>14}")
        print(f"  {'-'*16} {'-'*5} {'-'*7} {'-'*8} {'-'*16} {'-'*14}")

        for pat in ["V", "inv_V", "trending_up", "trending_down", "range"]:
            sub = wf[wf["pattern"] == pat]
            if len(sub) < 5:
                continue
            pct = len(sub) / len(wf) * 100
            up_rate = sub["is_up"].mean() * 100

            # PnL if we trade in pattern direction
            if pat in ("V", "trending_up"):
                pnl = sub["move_after"]  # long
            elif pat in ("inv_V", "trending_down"):
                pnl = -sub["move_after"]  # short
            else:
                pnl = pd.Series([0.0] * len(sub))  # skip range

            avg_pnl = pnl.mean()
            total_pnl = pnl.sum()

            print(f"  {pat:<16} {len(sub):>5} {pct:>6.1f}% {up_rate:>7.1f}%"
                  f" {avg_pnl:>+15.1f} {total_pnl:>+13.0f}")

    # ── A2: Direction indicators ──
    print("\n" + "-" * 72)
    print("A2: 方向指標 vs 全日方向（point-biserial correlation）")
    print("-" * 72)

    indicators = [
        ("or_direction", "OR close 方向"),
        ("shadow_ratio", "影線比"),
        ("vol_weighted_dir", "量加權方向"),
        ("low_time_ratio", "低點時序比"),
        ("momentum", "前後半動能"),
    ]

    for wl in ["15m", "30m", "45m", "60m"]:
        wf = feat[feat["window"] == wl]
        print(f"\n  [{wl}]")
        print(f"  {'指標':<16} {'r(方向)':>10} {'r(損益)':>10}")
        print(f"  {'-'*16} {'-'*10} {'-'*10}")
        for col, name in indicators:
            r_dir = wf[col].corr(wf["is_up"])
            r_pnl = wf[col].corr(wf["move_after"])
            print(f"  {name:<16} {r_dir:>+10.3f} {r_pnl:>+10.3f}")

    # ── A2 quartile analysis for best indicator (shadow_ratio, 30m) ──
    print("\n" + "-" * 72)
    print("A2b: 影線比分位數 × 全日損益（各觀察窗口）")
    print("-" * 72)

    for wl in ["15m", "30m", "45m", "60m"]:
        wf = feat[feat["window"] == wl].copy()
        if len(wf) < 40:
            continue
        wf["q"] = pd.qcut(wf["shadow_ratio"], 4, labels=["Q1(低)", "Q2", "Q3", "Q4(高)"])
        print(f"\n  [{wl}]")
        print(f"  {'分位':<8} {'n':>5} {'上漲率%':>8} {'avg move':>9} {'total':>8}")
        print(f"  {'-'*8} {'-'*5} {'-'*8} {'-'*9} {'-'*8}")
        for q_label, grp in wf.groupby("q", observed=True):
            up_rate = grp["is_up"].mean() * 100
            avg = grp["move_after"].mean()
            total = grp["move_after"].sum()
            print(f"  {str(q_label):<8} {len(grp):>5} {up_rate:>7.1f}%"
                  f" {avg:>+8.1f} {total:>+7.0f}")

    # ── A3: Entry timing comparison ──
    print("\n" + "-" * 72)
    print("A3: 進場時機比較（用影線比 > 0.5 做多, < 0.5 做空）")
    print("-" * 72)

    print(f"\n  {'Window':<8} {'n':>5} {'trades':>7} {'勝率%':>7}"
          f" {'avg pnl':>9} {'total':>8} {'PF':>7}")
    print(f"  {'-'*8} {'-'*5} {'-'*7} {'-'*7} {'-'*9} {'-'*8} {'-'*7}")

    for wl in ["15m", "30m", "45m", "60m"]:
        wf = feat[feat["window"] == wl].copy()
        # Direction based on shadow_ratio
        wf["signal"] = np.where(wf["shadow_ratio"] > 0.5, 1, -1)
        wf["pnl"] = wf["signal"] * wf["move_after"]
        n = len(wf)
        wins = (wf["pnl"] > 0).sum()
        win_rate = wins / n * 100
        avg_pnl = wf["pnl"].mean()
        total = wf["pnl"].sum()
        gross_win = wf.loc[wf["pnl"] > 0, "pnl"].sum()
        gross_loss = wf.loc[wf["pnl"] < 0, "pnl"].abs().sum()
        pf = gross_win / gross_loss if gross_loss > 0 else float("inf")

        print(f"  {wl:<8} {n:>5} {n:>7} {win_rate:>6.1f}%"
              f" {avg_pnl:>+8.1f} {total:>+7.0f} {pf:>7.2f}")

    # ── A3 year-by-year for 30m ──
    print(f"\n  逐年（30m 影線比信號）")
    print(f"  {'Year':<6} {'n':>5} {'勝率%':>7} {'avg':>8} {'total':>8} {'PF':>7}")
    print(f"  {'-'*6} {'-'*5} {'-'*7} {'-'*8} {'-'*8} {'-'*7}")

    wf30 = feat[feat["window"] == "30m"].copy()
    wf30["signal"] = np.where(wf30["shadow_ratio"] > 0.5, 1, -1)
    wf30["pnl"] = wf30["signal"] * wf30["move_after"]

    for yr, _, _ in YEARS:
        yr_data = wf30[wf30["year"] == int(yr)]
        if yr_data.empty:
            continue
        wins = (yr_data["pnl"] > 0).sum()
        win_rate = wins / len(yr_data) * 100
        avg = yr_data["pnl"].mean()
        total = yr_data["pnl"].sum()
        gw = yr_data.loc[yr_data["pnl"] > 0, "pnl"].sum()
        gl = yr_data.loc[yr_data["pnl"] < 0, "pnl"].abs().sum()
        pf = gw / gl if gl > 0 else float("inf")
        print(f"  {yr:<6} {len(yr_data):>5} {win_rate:>6.1f}% {avg:>+7.1f}"
              f" {total:>+7.0f} {pf:>7.2f}")

    # ── A4 ──
    if df_bars is not None:
        direction_a4(feat, df_bars)


# ── A4: Pullback entry ──────────────────────────────────────────────────────

def direction_a4(feat: pd.DataFrame, df_bars: pd.DataFrame):
    """A4: 回拉進場 — 確認方向後等回拉再進場"""
    print("\n" + "-" * 72)
    print("A4: 回拉進場 — 確認方向後不追價，等回拉")
    print("-" * 72)

    # Use 30m window (best balance of direction accuracy vs remaining range)
    wf30 = feat[feat["window"] == "30m"].copy()

    # Pullback targets relative to window range
    pullback_levels = [
        ("OR 中點", 0.5),     # pullback to OR midpoint
        ("OR 1/3", 0.33),     # pullback to lower 1/3
        ("OR 低點+α", 0.1),   # pullback near OR low
    ]

    records = []
    for _, row in wf30.iterrows():
        date = row["date"]
        signal = 1 if row["shadow_ratio"] > 0.5 else -1
        day = df_bars[df_bars["date"] == date].sort_values("time")
        after = day[day["time"] >= row["window_end"]]
        if len(after) < 10:
            continue

        w_high = row["w_high"]
        w_low = row["w_low"]
        w_range = w_high - w_low
        if w_range <= 0:
            continue

        day_close = after.iloc[-1]["close"]

        for label, frac in pullback_levels:
            if signal == 1:  # long: wait for pullback DOWN
                limit_price = w_low + w_range * frac
                # Check if price pulls back to limit_price
                hit = after[after["low"] <= limit_price]
                if hit.empty:
                    records.append({
                        "date": date, "year": row["year"], "signal": signal,
                        "level": label, "filled": False,
                        "pnl": 0, "pnl_pct": 0,
                    })
                    continue
                entry_price = limit_price
                pnl = day_close - entry_price
            else:  # short: wait for pullback UP
                limit_price = w_high - w_range * frac
                hit = after[after["high"] >= limit_price]
                if hit.empty:
                    records.append({
                        "date": date, "year": row["year"], "signal": signal,
                        "level": label, "filled": False,
                        "pnl": 0, "pnl_pct": 0,
                    })
                    continue
                entry_price = limit_price
                pnl = entry_price - day_close

            records.append({
                "date": date, "year": row["year"], "signal": signal,
                "level": label, "filled": True,
                "entry_price": entry_price,
                "pnl": pnl,
                "pnl_pct": pnl / entry_price * 100,
            })

    rdf = pd.DataFrame(records)

    # Also add chase entry (A3 baseline) for comparison
    print(f"\n  比較：追價 vs 回拉進場（30m 影線比信號）")
    print(f"  {'進場方式':<14} {'總天數':>6} {'成交率%':>8} {'成交筆':>6}"
          f" {'勝率%':>7} {'avg pnl':>9} {'total':>8} {'PF':>7}")
    print(f"  {'-'*14} {'-'*6} {'-'*8} {'-'*6} {'-'*7} {'-'*9} {'-'*8} {'-'*7}")

    # Chase entry baseline
    wf30["signal"] = np.where(wf30["shadow_ratio"] > 0.5, 1, -1)
    wf30["pnl"] = wf30["signal"] * wf30["move_after"]
    n = len(wf30)
    wins = (wf30["pnl"] > 0).sum()
    gw = wf30.loc[wf30["pnl"] > 0, "pnl"].sum()
    gl = wf30.loc[wf30["pnl"] < 0, "pnl"].abs().sum()
    pf = gw / gl if gl > 0 else float("inf")
    print(f"  {'追價(baseline)':<14} {n:>6} {'100.0%':>8} {n:>6}"
          f" {wins/n*100:>6.1f}% {wf30['pnl'].mean():>+8.1f}"
          f" {wf30['pnl'].sum():>+7.0f} {pf:>7.2f}")

    # Pullback entries
    for label, _ in pullback_levels:
        sub = rdf[rdf["level"] == label]
        total_days = len(sub)
        filled = sub[sub["filled"]]
        fill_rate = len(filled) / total_days * 100 if total_days > 0 else 0
        if len(filled) < 10:
            print(f"  {label:<14} {total_days:>6} {fill_rate:>7.1f}% {len(filled):>6}"
                  f" {'—':>7} {'—':>9} {'—':>8} {'—':>7}")
            continue
        wins = (filled["pnl"] > 0).sum()
        win_rate = wins / len(filled) * 100
        avg = filled["pnl"].mean()
        total = filled["pnl"].sum()
        gw = filled.loc[filled["pnl"] > 0, "pnl"].sum()
        gl = filled.loc[filled["pnl"] < 0, "pnl"].abs().sum()
        pf = gw / gl if gl > 0 else float("inf")
        print(f"  {label:<14} {total_days:>6} {fill_rate:>7.1f}% {len(filled):>6}"
              f" {win_rate:>6.1f}% {avg:>+8.1f} {total:>+7.0f} {pf:>7.2f}")

    # Year-by-year for best pullback level
    print(f"\n  逐年（OR 中點回拉）")
    print(f"  {'Year':<6} {'成交筆':>6} {'勝率%':>7} {'avg':>8} {'total':>8} {'PF':>7}")
    print(f"  {'-'*6} {'-'*6} {'-'*7} {'-'*8} {'-'*8} {'-'*7}")
    mid = rdf[(rdf["level"] == "OR 中點") & rdf["filled"]]
    for yr, _, _ in YEARS:
        yr_data = mid[mid["year"] == int(yr)]
        if len(yr_data) < 5:
            continue
        wins = (yr_data["pnl"] > 0).sum()
        win_rate = wins / len(yr_data) * 100
        avg = yr_data["pnl"].mean()
        total = yr_data["pnl"].sum()
        gw = yr_data.loc[yr_data["pnl"] > 0, "pnl"].sum()
        gl = yr_data.loc[yr_data["pnl"] < 0, "pnl"].abs().sum()
        pf = gw / gl if gl > 0 else float("inf")
        print(f"  {yr:<6} {len(yr_data):>6} {win_rate:>6.1f}% {avg:>+7.1f}"
              f" {total:>+7.0f} {pf:>7.2f}")

    # Long vs Short breakdown for OR 中點
    print(f"\n  OR 中點回拉：多空分解")
    print(f"  {'方向':>6} {'n':>5} {'勝率%':>7} {'avg':>8} {'total':>8} {'PF':>7}")
    print(f"  {'-'*6} {'-'*5} {'-'*7} {'-'*8} {'-'*8} {'-'*7}")
    for sig, label in [(1, "做多"), (-1, "做空")]:
        sub = mid[mid["signal"] == sig]
        if len(sub) < 10:
            continue
        wins = (sub["pnl"] > 0).sum()
        win_rate = wins / len(sub) * 100
        avg = sub["pnl"].mean()
        total = sub["pnl"].sum()
        gw = sub.loc[sub["pnl"] > 0, "pnl"].sum()
        gl = sub.loc[sub["pnl"] < 0, "pnl"].abs().sum()
        pf = gw / gl if gl > 0 else float("inf")
        print(f"  {label:>6} {len(sub):>5} {win_rate:>6.1f}% {avg:>+7.1f}"
              f" {total:>+7.0f} {pf:>7.2f}")


# ══════════════════════════════════════════════════════════════════════════════
# 方向 B：波幅預測 + 區間邊緣交易
# ══════════════════════════════════════════════════════════════════════════════

def direction_b(df_bars: pd.DataFrame, df_daily: pd.DataFrame):
    print("\n" + "=" * 72)
    print("方向 B：波幅預測 + 區間邊緣交易")
    print("=" * 72)

    from src.backtest.estimate_hl import compute_estimate_hl_zones
    from src.backtest.runner import adjust_settlement_volume

    # Compute EstHL
    df_for_hl = df_bars[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    df_for_hl = df_for_hl.set_index("timestamp")
    df_for_hl.columns = ["Open", "High", "Low", "Close", "Volume"]
    adjust_settlement_volume(df_for_hl)
    print("  計算 EstHL...", flush=True)
    df_hl = compute_estimate_hl_zones(df_for_hl)
    df_hl["date"] = df_hl.index.date

    ema_hl_daily = df_hl.groupby("date")["EmaHL"].apply(
        lambda x: x.dropna().iloc[0] if x.notna().any() else np.nan
    )

    daily_map = df_daily.set_index("trade_date").to_dict("index")
    dates = sorted(df_bars["date"].unique())

    # ── B1: Entry value at different consumption levels ──
    print("\n" + "-" * 72)
    print("B1: 不同波幅消耗水準時進場的剩餘價值")
    print("-" * 72)

    consumption_levels = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    b1_records = []

    for date in dates:
        td = pd.Timestamp(date)
        if td not in daily_map:
            continue
        if date not in ema_hl_daily.index or np.isnan(ema_hl_daily[date]):
            continue
        info = daily_map[td]
        est_hl = ema_hl_daily[date]
        if est_hl <= 0:
            continue

        day = df_bars[df_bars["date"] == date].sort_values("time")
        if len(day) < 100:
            continue

        run_high = -np.inf
        run_low = np.inf
        day_high = info["day_high"]
        day_low = info["day_low"]
        day_close = info["day_close"]

        triggered = {c: False for c in consumption_levels}

        for _, row in day.iterrows():
            run_high = max(run_high, row["high"])
            run_low = min(run_low, row["low"])
            cur_range = run_high - run_low
            consumed = cur_range / est_hl

            for c in consumption_levels:
                if not triggered[c] and consumed >= c:
                    triggered[c] = True
                    # MFE/MAE from this point (for longs)
                    after = day[day["time"] > row["time"]]
                    if after.empty:
                        continue
                    entry_price = row["close"]
                    max_high_after = after["high"].max()
                    min_low_after = after["low"].min()
                    mfe = max_high_after - entry_price
                    mae = entry_price - min_low_after

                    b1_records.append({
                        "date": date,
                        "consumed": c,
                        "entry_price": entry_price,
                        "mfe": mfe,
                        "mae": mae,
                        "mfe_pct": mfe / entry_price * 100,
                        "mae_pct": mae / entry_price * 100,
                        "time": row["time"],
                    })

    b1df = pd.DataFrame(b1_records)

    print(f"\n  {'消耗%':>6} {'n':>6} {'MFE% mean':>10} {'MAE% mean':>10}"
          f" {'MFE/MAE':>8} {'MFE>MAE%':>9}")
    print(f"  {'-'*6} {'-'*6} {'-'*10} {'-'*10} {'-'*8} {'-'*9}")

    for c in consumption_levels:
        sub = b1df[b1df["consumed"] == c]
        if len(sub) < 10:
            continue
        mfe_mean = sub["mfe_pct"].mean()
        mae_mean = sub["mae_pct"].mean()
        ratio = mfe_mean / mae_mean if mae_mean > 0 else float("inf")
        mfe_wins = (sub["mfe"] > sub["mae"]).mean() * 100
        print(f"  {c:>5.0%} {len(sub):>6} {mfe_mean:>10.3f} {mae_mean:>10.3f}"
              f" {ratio:>8.2f} {mfe_wins:>8.1f}%")

    # ── B2: Est high/low as target ──
    print("\n" + "-" * 72)
    print("B2: 預估高低點作為目標的觸及率")
    print("-" * 72)

    b2_records = []
    for date in dates:
        td = pd.Timestamp(date)
        if td not in daily_map:
            continue
        if date not in ema_hl_daily.index or np.isnan(ema_hl_daily[date]):
            continue
        info = daily_map[td]
        est_hl = ema_hl_daily[date]
        if est_hl <= 0:
            continue

        day = df_bars[df_bars["date"] == date].sort_values("time")
        if len(day) < 100:
            continue

        day_open = info["day_open"]
        day_high = info["day_high"]
        day_low = info["day_low"]

        # Check at different checkpoints
        for cp_time in [dtime(9, 15), dtime(9, 30), dtime(9, 45), dtime(10, 0)]:
            before_cp = day[day["time"] < cp_time]
            after_cp = day[day["time"] >= cp_time]
            if before_cp.empty or after_cp.empty:
                continue

            run_low_cp = before_cp["low"].min()
            run_high_cp = before_cp["high"].max()
            est_high = run_low_cp + est_hl
            est_low = run_high_cp - est_hl

            # Did price reach est_high / est_low after checkpoint?
            max_after = after_cp["high"].max()
            min_after = after_cp["low"].min()
            hit_est_high = max_after >= est_high
            hit_est_low = min_after <= est_low

            b2_records.append({
                "date": date,
                "year": td.year,
                "checkpoint": cp_time,
                "est_high": est_high,
                "est_low": est_low,
                "hit_high": hit_est_high,
                "hit_low": hit_est_low,
                "overshoot_high": (max_after - est_high) / day_open * 100 if hit_est_high else np.nan,
                "overshoot_low": (est_low - min_after) / day_open * 100 if hit_est_low else np.nan,
            })

    b2df = pd.DataFrame(b2_records)

    print(f"\n  以 checkpoint 時的 running_low + EstHL 為預估高點")
    print(f"  {'Checkpoint':<11} {'n':>5} {'觸及高%':>8} {'觸及低%':>8}"
          f" {'avg超漲%':>9} {'avg超跌%':>9}")
    print(f"  {'-'*11} {'-'*5} {'-'*8} {'-'*8} {'-'*9} {'-'*9}")

    for cp in [dtime(9, 15), dtime(9, 30), dtime(9, 45), dtime(10, 0)]:
        sub = b2df[b2df["checkpoint"] == cp]
        if sub.empty:
            continue
        hit_h = sub["hit_high"].mean() * 100
        hit_l = sub["hit_low"].mean() * 100
        os_h = sub["overshoot_high"].dropna().mean()
        os_l = sub["overshoot_low"].dropna().mean()
        print(f"  {str(cp):<11} {len(sub):>5} {hit_h:>7.1f}% {hit_l:>7.1f}%"
              f" {fv(os_h, 8, 3):>8}% {fv(os_l, 8, 3):>8}%")

    # Year-by-year for 09:30 checkpoint
    print(f"\n  逐年（09:30 checkpoint）")
    print(f"  {'Year':<6} {'n':>5} {'觸及高%':>8} {'觸及低%':>8}")
    print(f"  {'-'*6} {'-'*5} {'-'*8} {'-'*8}")
    sub_0930 = b2df[b2df["checkpoint"] == dtime(9, 30)]
    for yr, _, _ in YEARS:
        yr_data = sub_0930[sub_0930["year"] == int(yr)]
        if yr_data.empty:
            continue
        print(f"  {yr:<6} {len(yr_data):>5}"
              f" {yr_data['hit_high'].mean()*100:>7.1f}%"
              f" {yr_data['hit_low'].mean()*100:>7.1f}%")

    # ── B3: Consumption direction asymmetry ──
    print("\n" + "-" * 72)
    print("B3: 波幅消耗方向的不對稱性")
    print("-" * 72)

    b3_records = []
    for date in dates:
        td = pd.Timestamp(date)
        if td not in daily_map:
            continue
        if date not in ema_hl_daily.index or np.isnan(ema_hl_daily[date]):
            continue
        info = daily_map[td]
        est_hl = ema_hl_daily[date]
        if est_hl <= 0:
            continue

        day = df_bars[df_bars["date"] == date].sort_values("time")
        if len(day) < 100:
            continue

        run_high = -np.inf
        run_low = np.inf
        day_close = info["day_close"]
        triggered_100 = False

        for _, row in day.iterrows():
            run_high = max(run_high, row["high"])
            run_low = min(run_low, row["low"])
            cur_range = run_high - run_low
            consumed = cur_range / est_hl

            if not triggered_100 and consumed >= 1.0:
                triggered_100 = True
                up_from_open = run_high - info["day_open"]
                dn_from_open = info["day_open"] - run_low
                direction = "up" if up_from_open >= dn_from_open else "down"

                # What happens if we counter-trade?
                move_to_close = day_close - row["close"]

                b3_records.append({
                    "date": date,
                    "year": td.year,
                    "direction": direction,
                    "move_to_close": move_to_close,
                    "move_pct": move_to_close / row["close"] * 100,
                    "time": row["time"],
                    # Counter-trade PnL: short if consumed upward, long if downward
                    "counter_pnl": -move_to_close if direction == "up" else move_to_close,
                })

    b3df = pd.DataFrame(b3_records)

    print(f"\n  100% 消耗後反向交易的期望值")
    print(f"  {'消耗方向':>8} {'n':>5} {'反向做 avg':>10} {'反向做 total':>12}"
          f" {'勝率%':>7}")
    print(f"  {'-'*8} {'-'*5} {'-'*10} {'-'*12} {'-'*7}")

    for d in ["up", "down"]:
        sub = b3df[b3df["direction"] == d]
        if len(sub) < 10:
            continue
        avg = sub["counter_pnl"].mean()
        total = sub["counter_pnl"].sum()
        win = (sub["counter_pnl"] > 0).mean() * 100
        label = "做空" if d == "up" else "做多"
        print(f"  {d+'消耗':>8} {len(sub):>5} {avg:>+9.1f} {total:>+11.0f} {win:>6.1f}%")


# ══════════════════════════════════════════════════════════════════════════════
# 方向 C：單次機會策略
# ══════════════════════════════════════════════════════════════════════════════

def direction_c(feat: pd.DataFrame, df_bars: pd.DataFrame):
    print("\n" + "=" * 72)
    print("方向 C：單次機會策略（One Clean Shot）")
    print("=" * 72)

    # ── C1: Best single entry timing ──
    print("\n" + "-" * 72)
    print("C1: 最佳單次進場時機（影線比信號，13:30 出場）")
    print("-" * 72)

    print(f"\n  {'Window':<8} {'n':>5} {'勝率%':>7} {'avg pnl':>9}"
          f" {'total':>8} {'PF':>7} {'Sharpe':>7}")
    print(f"  {'-'*8} {'-'*5} {'-'*7} {'-'*9} {'-'*8} {'-'*7} {'-'*7}")

    for wl in ["15m", "30m", "45m", "60m"]:
        wf = feat[feat["window"] == wl].copy()
        wf["signal"] = np.where(wf["shadow_ratio"] > 0.5, 1, -1)
        wf["pnl"] = wf["signal"] * wf["move_after"]
        wf["pnl_pct"] = wf["signal"] * wf["move_after_pct"]

        n = len(wf)
        wins = (wf["pnl"] > 0).sum()
        win_rate = wins / n * 100
        avg_pnl = wf["pnl"].mean()
        total = wf["pnl"].sum()
        gw = wf.loc[wf["pnl"] > 0, "pnl"].sum()
        gl = wf.loc[wf["pnl"] < 0, "pnl"].abs().sum()
        pf = gw / gl if gl > 0 else float("inf")

        # Daily Sharpe (annualized)
        daily_pnl = wf.groupby("date")["pnl_pct"].sum()
        sharpe = daily_pnl.mean() / daily_pnl.std() * np.sqrt(248) if daily_pnl.std() > 0 else 0

        print(f"  {wl:<8} {n:>5} {win_rate:>6.1f}% {avg_pnl:>+8.1f}"
              f" {total:>+7.0f} {pf:>7.2f} {sharpe:>7.2f}")

    # ── C2: Fixed risk position sizing ──
    print("\n" + "-" * 72)
    print("C2: 固定風險部位分配（30m 窗口，影線比信號）")
    print("-" * 72)

    wf30 = feat[feat["window"] == "30m"].copy()
    wf30["signal"] = np.where(wf30["shadow_ratio"] > 0.5, 1, -1)

    # Get MAE for each trade from df_bars
    dates = sorted(wf30["date"].unique())
    mae_records = []
    for _, row in wf30.iterrows():
        date = row["date"]
        day = df_bars[df_bars["date"] == date].sort_values("time")
        after = day[day["time"] >= row["window_end"]]
        if after.empty:
            continue
        entry_price = after.iloc[0]["open"]
        if row["signal"] == 1:  # long
            mae = entry_price - after["low"].min()
        else:  # short
            mae = after["high"].max() - entry_price
        mae_records.append({
            "date": date,
            "mae": mae,
            "mae_pct": mae / entry_price * 100,
            "pnl": row["signal"] * row["move_after"],
        })

    mae_df = pd.DataFrame(mae_records)

    risk_levels = [50, 100, 150, 200]  # pts

    print(f"\n  假設每筆最大風險 R 點，SL = MAE p75，部位 = R / SL")
    mae_p75 = mae_df["mae"].quantile(0.75)
    print(f"  MAE p75 = {mae_p75:.0f} pts")

    print(f"\n  {'Risk R':>8} {'部位':>6} {'avg pnl':>9} {'total':>9}"
          f" {'max DD':>8} {'年均':>8}")
    print(f"  {'-'*8} {'-'*6} {'-'*9} {'-'*9} {'-'*8} {'-'*8}")

    for r in risk_levels:
        size = r / mae_p75 if mae_p75 > 0 else 1
        scaled_pnl = mae_df["pnl"] * size
        cum = scaled_pnl.cumsum()
        max_dd = (cum - cum.cummax()).min()
        n_years = len(YEARS)
        print(f"  {r:>7} {size:>6.2f} {scaled_pnl.mean():>+8.1f}"
              f" {scaled_pnl.sum():>+8.0f} {max_dd:>+7.0f}"
              f" {scaled_pnl.sum()/n_years:>+7.0f}")

    # ── C3: Strict filtering ──
    print("\n" + "-" * 72)
    print("C3: 嚴格篩選條件（只做高信心天數）")
    print("-" * 72)

    wf30 = feat[feat["window"] == "30m"].copy()
    wf30["signal"] = np.where(wf30["shadow_ratio"] > 0.5, 1, -1)
    wf30["pnl"] = wf30["signal"] * wf30["move_after"]

    filters = [
        ("無篩選", wf30),
        ("影線比 > 0.6 or < 0.4", wf30[(wf30["shadow_ratio"] > 0.6) | (wf30["shadow_ratio"] < 0.4)]),
        ("影線比 > 0.7 or < 0.3", wf30[(wf30["shadow_ratio"] > 0.7) | (wf30["shadow_ratio"] < 0.3)]),
        ("OR% 0.3-1.0%", wf30[(wf30["or_pct"] >= 0.3) & (wf30["or_pct"] <= 1.0)]),
        ("高信心+OR%", wf30[
            ((wf30["shadow_ratio"] > 0.7) | (wf30["shadow_ratio"] < 0.3)) &
            (wf30["or_pct"] >= 0.3) & (wf30["or_pct"] <= 1.0)
        ]),
    ]

    print(f"\n  {'篩選條件':<22} {'n':>5} {'勝率%':>7} {'avg':>8}"
          f" {'total':>8} {'PF':>7}")
    print(f"  {'-'*22} {'-'*5} {'-'*7} {'-'*8} {'-'*8} {'-'*7}")

    for label, sub in filters:
        if len(sub) < 10:
            continue
        wins = (sub["pnl"] > 0).sum()
        win_rate = wins / len(sub) * 100
        avg = sub["pnl"].mean()
        total = sub["pnl"].sum()
        gw = sub.loc[sub["pnl"] > 0, "pnl"].sum()
        gl = sub.loc[sub["pnl"] < 0, "pnl"].abs().sum()
        pf = gw / gl if gl > 0 else float("inf")
        print(f"  {label:<22} {len(sub):>5} {win_rate:>6.1f}%"
              f" {avg:>+7.1f} {total:>+7.0f} {pf:>7.2f}")

    # Year-by-year for best filter
    best_label = "高信心+OR%"
    best_sub = wf30[
        ((wf30["shadow_ratio"] > 0.7) | (wf30["shadow_ratio"] < 0.3)) &
        (wf30["or_pct"] >= 0.3) & (wf30["or_pct"] <= 1.0)
    ].copy()

    print(f"\n  逐年（{best_label}）")
    print(f"  {'Year':<6} {'n':>5} {'勝率%':>7} {'avg':>8} {'total':>8} {'PF':>7}")
    print(f"  {'-'*6} {'-'*5} {'-'*7} {'-'*8} {'-'*8} {'-'*7}")
    for yr, _, _ in YEARS:
        yr_data = best_sub[best_sub["year"] == int(yr)]
        if yr_data.empty:
            continue
        wins = (yr_data["pnl"] > 0).sum()
        win_rate = wins / len(yr_data) * 100
        avg = yr_data["pnl"].mean()
        total = yr_data["pnl"].sum()
        gw = yr_data.loc[yr_data["pnl"] > 0, "pnl"].sum()
        gl = yr_data.loc[yr_data["pnl"] < 0, "pnl"].abs().sum()
        pf = gw / gl if gl > 0 else float("inf")
        print(f"  {yr:<6} {len(yr_data):>5} {win_rate:>6.1f}%"
              f" {avg:>+7.1f} {total:>+7.0f} {pf:>7.2f}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="日內波段策略方向研究")
    parser.add_argument("--direction", "-d", nargs="*",
                        choices=["A", "B", "C"],
                        help="只跑指定方向 (A/B/C)")
    args = parser.parse_args()

    directions = set(args.direction) if args.direction else {"A", "B", "C"}

    print("=" * 72)
    print("日內波段策略方向研究（Step 0 探索）")
    print("=" * 72)

    print("\n載入資料中...", flush=True)
    df_bars = load_minute_bars()
    df_daily = load_daily_summary()
    print(f"  1 分 K: {len(df_bars):,} 筆, {df_bars['date'].nunique()} 交易日")
    print(f"  日期範圍: {df_bars['date'].min()} ~ {df_bars['date'].max()}")

    need_features = "A" in directions or "C" in directions
    feat = None
    if need_features:
        print("  建構早盤特徵...", flush=True)
        feat = build_session_features(df_bars, df_daily)
        print(f"  特徵筆數: {len(feat):,}")

    if "A" in directions:
        direction_a(feat, df_bars)

    if "B" in directions:
        direction_b(df_bars, df_daily)

    if "C" in directions:
        direction_c(feat, df_bars)

    print("\n" + "=" * 72)
    print("分析完成")
    print("=" * 72)


if __name__ == "__main__":
    main()
