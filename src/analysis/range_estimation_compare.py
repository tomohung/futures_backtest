"""波幅預估方法比較

比較多種日波幅預估方式的「觸及率」和實用性：
  1. EstHL（現有基準：EMA(20) of H-L，成交量加權）
  2. 百分位數（p25/p50/p75 of recent 20-day H-L）
  3. ATR(14)
  4. OR 寬度 × 乘數
  5. 夜盤波幅混合
  6. VIXTWN 縮放

用法:
    uv run python src/analysis/range_estimation_compare.py
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


# ── Data loading ──────────────────────────────────────────────────────────────

def load_daily_ohlcv() -> pd.DataFrame:
    """Day-session daily OHLCV + OR width + night range."""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
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

        # OR width (08:45–09:30)
        or_df = conn.execute("""
            SELECT
                timestamp::DATE AS trade_date,
                MAX(high) - MIN(low) AS or_width
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME BETWEEN '08:45' AND '09:30'
            GROUP BY 1
        """).fetchdf()

        # Night session range (previous day 15:00 ~ today 05:00)
        night_df = conn.execute("""
            SELECT
                timestamp::DATE AS trade_date,
                MAX(high) - MIN(low) AS night_range
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME NOT BETWEEN '08:45' AND '13:45'
            GROUP BY 1
        """).fetchdf()

    df["trade_date"] = pd.to_datetime(df["trade_date"])
    or_df["trade_date"] = pd.to_datetime(or_df["trade_date"])
    night_df["trade_date"] = pd.to_datetime(night_df["trade_date"])

    df = df.merge(or_df, on="trade_date", how="left")
    # Night range: shift by 1 to get previous night's range for today
    night_df = night_df.sort_values("trade_date")
    night_df["night_range_prev"] = night_df["night_range"].shift(1)
    df = df.merge(night_df[["trade_date", "night_range_prev"]], on="trade_date", how="left")

    df["year"] = df["trade_date"].dt.year
    return df.set_index("trade_date").sort_index()


def load_vixtwn() -> pd.Series:
    """Load VIXTWN daily data."""
    try:
        with duckdb.connect(DB_PATH, read_only=True) as conn:
            vdf = conn.execute("SELECT date, vix FROM vixtwn ORDER BY date").fetchdf()
        vdf["date"] = pd.to_datetime(vdf["date"])
        return vdf.set_index("date")["vix"]
    except Exception:
        # Try CSV fallback
        csv_path = Path("data/external_sources/VIXTWN.csv")
        if csv_path.exists():
            vdf = pd.read_csv(csv_path)
            vdf.columns = ["date", "vix"]
            vdf["date"] = pd.to_datetime(vdf["date"])
            return vdf.set_index("date")["vix"]
        return pd.Series(dtype=float)


def load_minute_bars_for_checkpoints() -> pd.DataFrame:
    """Load 1-min bars for checkpoint analysis."""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT timestamp, high, low, close
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME BETWEEN '08:45' AND '13:45'
            ORDER BY timestamp
        """).fetchdf()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df["time"] = df["timestamp"].dt.time
    return df


# ── Range estimation methods ─────────────────────────────────────────────────

def compute_all_estimates(df: pd.DataFrame, vixtwn: pd.Series) -> pd.DataFrame:
    """Compute all range estimation methods. All use only past data (no lookahead)."""
    out = df.copy()
    hl = df["day_range"]
    n = len(df)

    # 1. EstHL (EMA 20 of H-L) — simplified version without volume weighting
    alpha = 2.0 / 21
    ema_hl = np.full(n, np.nan)
    for i in range(n):
        if i == 0:
            ema_hl[i] = hl.iloc[i]
        else:
            ema_hl[i] = hl.iloc[i] * alpha + ema_hl[i - 1] * (1 - alpha)
    # Shift by 1 to use yesterday's EMA for today
    out["est_ema20"] = pd.Series(np.roll(ema_hl, 1), index=df.index)
    out.iloc[0, out.columns.get_loc("est_ema20")] = np.nan

    # 2. Percentiles (p25, p50, p75 of past 20 days)
    for p, label in [(25, "est_p25"), (50, "est_p50"), (75, "est_p75")]:
        out[label] = hl.shift(1).rolling(20, min_periods=10).quantile(p / 100)

    # 3. ATR(14) — Wilder's smoothed True Range
    tr = np.full(n, np.nan)
    close_arr = df["day_close"].values
    high_arr = df["day_high"].values
    low_arr = df["day_low"].values
    for i in range(1, n):
        tr[i] = max(
            high_arr[i] - low_arr[i],
            abs(high_arr[i] - close_arr[i - 1]),
            abs(low_arr[i] - close_arr[i - 1]),
        )
    # Wilder smoothing
    period = 14
    atr = np.full(n, np.nan)
    for i in range(period, n):
        window = tr[i - period + 1: i + 1]
        if not np.any(np.isnan(window)):
            atr[i] = window.mean()
            break
    start = np.argmax(~np.isnan(atr))
    if not np.all(np.isnan(atr)):
        for i in range(start + 1, n):
            if not np.isnan(tr[i]):
                atr[i] = atr[i - 1] * (period - 1) / period + tr[i] / period
    # Shift by 1
    out["est_atr14"] = pd.Series(np.roll(atr, 1), index=df.index)
    out.iloc[0, out.columns.get_loc("est_atr14")] = np.nan

    # 4. OR width × multipliers (including Fibonacci)
    or_w = df["or_width"]
    or_mults = [
        (1.0, "est_or_1.0"),
        (1.5, "est_or_1.5"),
        (1.618, "est_or_fib1.618"),
        (2.0, "est_or_2.0"),
        (2.5, "est_or_2.5"),
        (2.618, "est_or_fib2.618"),
        (3.0, "est_or_3.0"),
        (4.236, "est_or_fib4.236"),
    ]
    for mult, label in or_mults:
        out[label] = or_w * mult  # OR width is known at 09:30, no shift needed

    # 5. Night range blend: 0.4 × night + 0.6 × EMA(20)
    out["est_night_blend"] = 0.4 * df["night_range_prev"] + 0.6 * out["est_ema20"]

    # 6. VIXTWN scaling: EMA(20) × (VIX_today / VIX_20d_avg)
    if not vixtwn.empty:
        vix_aligned = vixtwn.reindex(df.index)
        vix_20ma = vix_aligned.rolling(20, min_periods=10).mean()
        vix_ratio = vix_aligned / vix_20ma
        out["est_vix_scaled"] = out["est_ema20"] * vix_ratio
    else:
        out["est_vix_scaled"] = np.nan

    return out


# ── Hit rate analysis ─────────────────────────────────────────────────────────

def analyze_hit_rates(df: pd.DataFrame, methods: list[tuple[str, str]]):
    """For each method, compute hit rate: did price reach running_low + estimate?"""
    print("\n" + "=" * 72)
    print("觸及率比較 — 各方法的預估波幅 vs 實際波幅")
    print("=" * 72)

    # Simple approach: compare estimate vs actual day_range
    print(f"\n  定義：觸及率 = P(day_range >= estimate)")
    print(f"  （實際日波幅 >= 預估值的天數比例）\n")

    print(f"  {'方法':<18} {'n':>5} {'觸及率%':>8} {'avg估值':>8} {'avg實際':>8}"
          f" {'估/實':>6} {'MAE':>7}")
    print(f"  {'-'*18} {'-'*5} {'-'*8} {'-'*8} {'-'*8} {'-'*6} {'-'*7}")

    results = {}
    for label, col in methods:
        valid = df[df[col].notna() & df["day_range"].notna()].copy()
        if len(valid) < 50:
            continue
        hit = (valid["day_range"] >= valid[col]).mean() * 100
        avg_est = valid[col].mean()
        avg_actual = valid["day_range"].mean()
        ratio = avg_est / avg_actual if avg_actual > 0 else 0
        mae = (valid["day_range"] - valid[col]).abs().mean()

        results[label] = {"hit": hit, "n": len(valid), "col": col}

        print(f"  {label:<18} {len(valid):>5} {hit:>7.1f}%"
              f" {avg_est:>8.0f} {avg_actual:>8.0f}"
              f" {ratio:>6.2f} {mae:>7.0f}")

    return results


def analyze_hit_rates_by_year(df: pd.DataFrame, methods: list[tuple[str, str]]):
    """Year-by-year hit rate for each method."""
    print(f"\n  逐年觸及率")

    # Header
    method_labels = [m[0] for m in methods]
    header = f"  {'Year':<6}"
    for ml in method_labels:
        header += f" {ml[:8]:>9}"
    print(header)
    print(f"  {'-'*6}" + "".join(f" {'-'*9}" for _ in methods))

    for yr_label, yr in YEARS:
        yr_data = df[df["year"] == yr]
        if len(yr_data) < 20:
            continue
        row = f"  {yr_label:<6}"
        for _, col in methods:
            valid = yr_data[yr_data[col].notna()]
            if valid.empty:
                row += f" {'—':>9}"
                continue
            hit = (valid["day_range"] >= valid[col]).mean() * 100
            row += f" {hit:>8.1f}%"
        print(row)


def analyze_checkpoint_hit_rates(df_daily: pd.DataFrame, df_bars: pd.DataFrame,
                                  methods: list[tuple[str, str]]):
    """Hit rate at different intraday checkpoints: does price reach
    running_low + estimate (for upside) after the checkpoint?"""
    print("\n" + "=" * 72)
    print("時間點觸及率 — 各 checkpoint 後價格是否到達預估高點")
    print("=" * 72)

    checkpoints = [dtime(9, 15), dtime(9, 30), dtime(9, 45), dtime(10, 0)]
    daily_map = df_daily.to_dict("index")
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

        for cp in checkpoints:
            before = day[day["time"] < cp]
            after = day[day["time"] >= cp]
            if before.empty or after.empty:
                continue

            run_low = before["low"].min()
            run_high = before["high"].max()
            max_after = after["high"].max()
            min_after = after["low"].min()

            for label, col in methods:
                est = info.get(col, np.nan)
                if np.isnan(est):
                    continue
                est_high = run_low + est
                est_low = run_high - est
                hit_high = max_after >= est_high
                hit_low = min_after <= est_low

                records.append({
                    "date": date,
                    "checkpoint": cp,
                    "method": label,
                    "hit_high": hit_high,
                    "hit_low": hit_low,
                })

    rdf = pd.DataFrame(records)

    for cp in checkpoints:
        cp_data = rdf[rdf["checkpoint"] == cp]
        if cp_data.empty:
            continue
        print(f"\n  Checkpoint {cp}")
        print(f"  {'方法':<18} {'n':>5} {'觸及高%':>8} {'觸及低%':>8}")
        print(f"  {'-'*18} {'-'*5} {'-'*8} {'-'*8}")
        for label, _ in methods:
            sub = cp_data[cp_data["method"] == label]
            if sub.empty:
                continue
            print(f"  {label:<18} {len(sub):>5}"
                  f" {sub['hit_high'].mean()*100:>7.1f}%"
                  f" {sub['hit_low'].mean()*100:>7.1f}%")


def analyze_as_tp_target(df: pd.DataFrame, methods: list[tuple[str, str]]):
    """If we use the estimate as TP target (from day open), what's the performance?"""
    print("\n" + "=" * 72)
    print("假設策略：開盤做多，以預估值為 TP，13:30 強制平倉")
    print("=" * 72)

    print(f"\n  {'方法':<18} {'n':>5} {'TP觸及率%':>9} {'avg pnl':>9}"
          f" {'total':>8} {'勝率%':>7}")
    print(f"  {'-'*18} {'-'*5} {'-'*9} {'-'*9} {'-'*8} {'-'*7}")

    for label, col in methods:
        valid = df[df[col].notna()].copy()
        if len(valid) < 50:
            continue

        tp_target = valid[col]
        actual_range = valid["day_high"] - valid["day_open"]  # upside from open
        hit_tp = actual_range >= tp_target

        # PnL: min(tp_target, actual close - open)
        close_pnl = valid["day_close"] - valid["day_open"]
        pnl = np.where(hit_tp, tp_target, close_pnl)

        tp_rate = hit_tp.mean() * 100
        avg_pnl = pnl.mean()
        total_pnl = pnl.sum()
        win_rate = (pnl > 0).mean() * 100

        print(f"  {label:<18} {len(valid):>5} {tp_rate:>8.1f}%"
              f" {avg_pnl:>+8.1f} {total_pnl:>+7.0f} {win_rate:>6.1f}%")


# ── Fibonacci retracement entry ───────────────────────────────────────────────

def analyze_fib_retracement_entry(df_bars: pd.DataFrame, df_daily: pd.DataFrame):
    """Test Fibonacci retracement of OR breakout as entry levels."""
    print("\n" + "=" * 72)
    print("Fibonacci 回撤進場 — OR 突破後回拉到 Fib 水準再進場")
    print("=" * 72)

    daily_map = df_daily.to_dict("index")
    dates = sorted(df_bars["date"].unique())
    fib_levels = [0.236, 0.382, 0.5, 0.618, 0.786]

    records = []
    for date in dates:
        td = pd.Timestamp(date)
        if td not in daily_map:
            continue
        info = daily_map[td]
        day = df_bars[df_bars["date"] == date].sort_values("time")
        if len(day) < 100:
            continue

        # OR: 08:45–09:30
        or_bars = day[(day["time"] >= dtime(8, 45)) & (day["time"] <= dtime(9, 30))]
        if or_bars.empty:
            continue
        or_high = or_bars["high"].max()
        or_low = or_bars["low"].min()
        or_range = or_high - or_low
        if or_range <= 0:
            continue

        day_close = day.iloc[-1]["close"]

        # After OR: look for breakout then pullback
        after_or = day[day["time"] > dtime(9, 30)]
        if after_or.empty:
            continue

        # Check upside breakout
        broke_up = False
        for _, row in after_or.iterrows():
            if not broke_up and row["high"] > or_high:
                broke_up = True
                breakout_price = or_high
                # Now look for pullback to Fib levels
                for fib in fib_levels:
                    # Fib retracement: pullback from breakout toward OR low
                    entry_price = or_high - or_range * fib
                    remaining = day[day["time"] > row["time"]]
                    hit = remaining[remaining["low"] <= entry_price]
                    filled = not hit.empty

                    if filled:
                        pnl = day_close - entry_price
                    else:
                        pnl = 0

                    records.append({
                        "date": date,
                        "year": td.year,
                        "direction": "long",
                        "fib": fib,
                        "filled": filled,
                        "entry_price": entry_price if filled else np.nan,
                        "pnl": pnl if filled else np.nan,
                    })
                break  # only first breakout

    rdf = pd.DataFrame(records)

    print(f"\n  OR 突破後回拉到 Fibonacci 水準再做多")
    print(f"  {'Fib Level':>10} {'突破天數':>8} {'成交率%':>8} {'成交筆':>6}"
          f" {'勝率%':>7} {'avg pnl':>9} {'total':>8} {'PF':>7}")
    print(f"  {'-'*10} {'-'*8} {'-'*8} {'-'*6} {'-'*7} {'-'*9} {'-'*8} {'-'*7}")

    for fib in fib_levels:
        sub = rdf[(rdf["fib"] == fib) & (rdf["direction"] == "long")]
        total_days = len(sub)
        filled = sub[sub["filled"]]
        fill_rate = len(filled) / total_days * 100 if total_days > 0 else 0

        if len(filled) < 10:
            print(f"  {fib:>10.3f} {total_days:>8} {fill_rate:>7.1f}% {len(filled):>6}")
            continue

        wins = (filled["pnl"] > 0).sum()
        win_rate = wins / len(filled) * 100
        avg = filled["pnl"].mean()
        total = filled["pnl"].sum()
        gw = filled.loc[filled["pnl"] > 0, "pnl"].sum()
        gl = filled.loc[filled["pnl"] < 0, "pnl"].abs().sum()
        pf = gw / gl if gl > 0 else float("inf")
        print(f"  {fib:>10.3f} {total_days:>8} {fill_rate:>7.1f}% {len(filled):>6}"
              f" {win_rate:>6.1f}% {avg:>+8.1f} {total:>+7.0f} {pf:>7.2f}")

    # Year-by-year for 0.382
    print(f"\n  逐年（Fib 0.382 回撤進場）")
    print(f"  {'Year':<6} {'成交筆':>6} {'勝率%':>7} {'avg':>8} {'total':>8} {'PF':>7}")
    print(f"  {'-'*6} {'-'*6} {'-'*7} {'-'*8} {'-'*8} {'-'*7}")
    sub382 = rdf[(rdf["fib"] == 0.382) & rdf["filled"]]
    for yr_label, yr in YEARS:
        yr_data = sub382[sub382["year"] == yr]
        if len(yr_data) < 5:
            continue
        wins = (yr_data["pnl"] > 0).sum()
        win_rate = wins / len(yr_data) * 100
        avg = yr_data["pnl"].mean()
        total = yr_data["pnl"].sum()
        gw = yr_data.loc[yr_data["pnl"] > 0, "pnl"].sum()
        gl = yr_data.loc[yr_data["pnl"] < 0, "pnl"].abs().sum()
        pf = gw / gl if gl > 0 else float("inf")
        print(f"  {yr_label:<6} {len(yr_data):>6} {win_rate:>6.1f}% {avg:>+7.1f}"
              f" {total:>+7.0f} {pf:>7.2f}")


# ── Volume and weekday conditioning ──────────────────────────────────────────

def analyze_volume_weekday_conditioning(df: pd.DataFrame):
    """Analyze range estimates conditioned on volume regime and weekday."""
    print("\n" + "=" * 72)
    print("條件分析 — 成交量與星期對波幅的影響")
    print("=" * 72)

    # Volume conditioning
    df = df.copy()
    vol_20ma = df["day_volume"].rolling(20, min_periods=10).mean().shift(1)
    df["vol_ratio"] = df["day_volume"] / vol_20ma

    print(f"\n  成交量條件 × 波幅（量比 = 當日量 / 20 日均量）")
    print(f"  {'量比區間':<14} {'n':>5} {'avg波幅':>8} {'median':>8}"
          f" {'avg波幅%':>9} {'觸及EMA%':>9}")
    print(f"  {'-'*14} {'-'*5} {'-'*8} {'-'*8} {'-'*9} {'-'*9}")

    valid = df[df["vol_ratio"].notna() & df["est_ema20"].notna()]
    bins = [(0, 0.7, "< 0.7 (清淡)"),
            (0.7, 1.0, "0.7-1.0 (正常)"),
            (1.0, 1.5, "1.0-1.5 (活躍)"),
            (1.5, 99, "> 1.5 (爆量)")]

    for lo, hi, label in bins:
        sub = valid[(valid["vol_ratio"] >= lo) & (valid["vol_ratio"] < hi)]
        if len(sub) < 10:
            continue
        avg_r = sub["day_range"].mean()
        med_r = sub["day_range"].median()
        avg_pct = (sub["day_range"] / sub["day_open"] * 100).mean()
        hit_ema = (sub["day_range"] >= sub["est_ema20"]).mean() * 100
        print(f"  {label:<14} {len(sub):>5} {avg_r:>8.0f} {med_r:>8.0f}"
              f" {avg_pct:>8.2f}% {hit_ema:>8.1f}%")

    # Weekday conditioning
    df["weekday"] = df.index.dayofweek  # 0=Mon, 4=Fri
    weekday_names = {0: "週一", 1: "週二", 2: "週三", 3: "週四", 4: "週五"}

    print(f"\n  星期 × 波幅")
    print(f"  {'星期':<6} {'n':>5} {'avg波幅':>8} {'median':>8}"
          f" {'avg波幅%':>9} {'觸及EMA%':>9} {'OR×2觸及%':>10}")
    print(f"  {'-'*6} {'-'*5} {'-'*8} {'-'*8} {'-'*9} {'-'*9} {'-'*10}")

    valid2 = df[df["est_ema20"].notna() & df["est_or_2.0"].notna()]
    for wd in range(5):
        sub = valid2[valid2["weekday"] == wd]
        if len(sub) < 20:
            continue
        avg_r = sub["day_range"].mean()
        med_r = sub["day_range"].median()
        avg_pct = (sub["day_range"] / sub["day_open"] * 100).mean()
        hit_ema = (sub["day_range"] >= sub["est_ema20"]).mean() * 100
        hit_or2 = (sub["day_range"] >= sub["est_or_2.0"]).mean() * 100
        print(f"  {weekday_names[wd]:<6} {len(sub):>5} {avg_r:>8.0f} {med_r:>8.0f}"
              f" {avg_pct:>8.2f}% {hit_ema:>8.1f}% {hit_or2:>9.1f}%")

    # Gap size conditioning
    df["gap"] = df["day_open"] - df["day_close"].shift(1)
    df["gap_pct"] = df["gap"] / df["day_close"].shift(1) * 100

    print(f"\n  跳空大小 × 波幅")
    print(f"  {'Gap 區間':<14} {'n':>5} {'avg波幅':>8} {'avg波幅%':>9}"
          f" {'觸及EMA%':>9}")
    print(f"  {'-'*14} {'-'*5} {'-'*8} {'-'*9} {'-'*9}")

    valid3 = df[df["gap_pct"].notna() & df["est_ema20"].notna()]
    gap_bins = [(-99, -0.5, "大跳空下"),
                (-0.5, -0.1, "小跳空下"),
                (-0.1, 0.1, "平開"),
                (0.1, 0.5, "小跳空上"),
                (0.5, 99, "大跳空上")]

    for lo, hi, label in gap_bins:
        sub = valid3[(valid3["gap_pct"] >= lo) & (valid3["gap_pct"] < hi)]
        if len(sub) < 10:
            continue
        avg_r = sub["day_range"].mean()
        avg_pct = (sub["day_range"] / sub["day_open"] * 100).mean()
        hit_ema = (sub["day_range"] >= sub["est_ema20"]).mean() * 100
        print(f"  {label:<14} {len(sub):>5} {avg_r:>8.0f} {avg_pct:>8.2f}%"
              f" {hit_ema:>8.1f}%")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 72)
    print("波幅預估方法比較（含 Fibonacci + 條件分析）")
    print("=" * 72)

    print("\n載入資料...", flush=True)
    df = load_daily_ohlcv()
    vixtwn = load_vixtwn()
    print(f"  {len(df)} 交易日, {df.index[0].date()} ~ {df.index[-1].date()}")
    if not vixtwn.empty:
        print(f"  VIXTWN: {len(vixtwn)} 筆")
    else:
        print("  VIXTWN: 無資料（跳過 VIX 縮放方法）")

    print("\n計算各種預估值...", flush=True)
    df = compute_all_estimates(df, vixtwn)

    methods = [
        ("EMA(20) H-L", "est_ema20"),
        ("Percentile p25", "est_p25"),
        ("Percentile p50", "est_p50"),
        ("Percentile p75", "est_p75"),
        ("ATR(14)", "est_atr14"),
        ("OR × 1.0", "est_or_1.0"),
        ("OR × 1.5", "est_or_1.5"),
        ("OR × Fib 1.618", "est_or_fib1.618"),
        ("OR × 2.0", "est_or_2.0"),
        ("OR × 2.5", "est_or_2.5"),
        ("OR × Fib 2.618", "est_or_fib2.618"),
        ("OR × 3.0", "est_or_3.0"),
        ("OR × Fib 4.236", "est_or_fib4.236"),
        ("Night blend", "est_night_blend"),
    ]
    if not vixtwn.empty:
        methods.append(("VIX scaled", "est_vix_scaled"))

    # 1. Overall hit rates
    analyze_hit_rates(df, methods)

    # 2. Year-by-year (select key methods to avoid clutter)
    key_methods = [
        ("EMA(20) H-L", "est_ema20"),
        ("Percentile p50", "est_p50"),
        ("OR × 1.5", "est_or_1.5"),
        ("OR × Fib 1.618", "est_or_fib1.618"),
        ("OR × 2.0", "est_or_2.0"),
        ("OR × Fib 2.618", "est_or_fib2.618"),
    ]
    analyze_hit_rates_by_year(df, key_methods)

    # 3. Checkpoint hit rates
    print("\n載入 1 分 K...", flush=True)
    df_bars = load_minute_bars_for_checkpoints()

    top_methods = [
        ("EMA(20) H-L", "est_ema20"),
        ("Percentile p50", "est_p50"),
        ("OR × Fib 1.618", "est_or_fib1.618"),
        ("OR × 2.0", "est_or_2.0"),
        ("OR × Fib 2.618", "est_or_fib2.618"),
    ]
    analyze_checkpoint_hit_rates(df, df_bars, top_methods)

    # 4. As TP target
    analyze_as_tp_target(df, methods)

    # 5. Fibonacci retracement entry
    analyze_fib_retracement_entry(df_bars, df)

    # 6. Volume, weekday, gap conditioning
    analyze_volume_weekday_conditioning(df)

    print("\n" + "=" * 72)
    print("分析完成")
    print("=" * 72)


if __name__ == "__main__":
    main()
