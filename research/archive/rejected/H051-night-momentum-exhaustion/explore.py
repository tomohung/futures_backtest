#!/usr/bin/env python3
"""H051 — Night Session Momentum Exhaustion: Phase 1 Distribution Exploration.

Identifies S003 condition days, computes 4 night-session exhaustion indicators,
and compares subsequent day-session reversal performance.

Usage:
    uv run python research/active/H051-night-momentum-exhaustion/explore.py
"""

import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

DB_PATH = "data/futures.duckdb"
OUT_DIR = Path("research/active/H051-night-momentum-exhaustion/results")

# ─── S003 parameters ────────────────────────────────────────────────────────
MIN_ORB_PCT = 0.25
SKIP_WEEKDAYS = {2, 3}  # Wed=2, Thu=3


def load_day_session():
    """Load day-session 1m bars with S003 indicators (replicating runner.py logic)."""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df_day = conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ORDER BY timestamp
        """).df().set_index("timestamp")

    df_day.columns = ["Open", "High", "Low", "Close", "Volume"]

    # ── 5m 120MA (≈ 30m 20MA), shift(1) to avoid lookahead ──
    s5_day = df_day["Close"].resample("5min").last().dropna()
    ma5m_120 = s5_day.rolling(120, min_periods=120).mean()
    df_day["MA30_20"] = ma5m_120.shift(1).reindex(df_day.index, method="ffill")
    df_day["MA30_20_Prev"] = ma5m_120.shift(2).reindex(df_day.index, method="ffill")

    # ── 30m BB%B(20, open) ──
    s30_open = df_day["Open"].resample("30min", offset="15min").first().dropna()
    bb_ma = s30_open.rolling(20, min_periods=20).mean()
    bb_std = s30_open.rolling(20, min_periods=20).std(ddof=1)
    bb_upper = bb_ma + 2 * bb_std
    bb_lower = bb_ma - 2 * bb_std
    bb_pctb = (s30_open - bb_lower) / (bb_upper - bb_lower)

    bb_pctb_df = bb_pctb.to_frame("bbpct")
    bb_pctb_df["date"] = bb_pctb_df.index.normalize()
    first_bb = bb_pctb_df.groupby("date")["bbpct"].first()
    day_dates = pd.DatetimeIndex(df_day.index).normalize()
    df_day["BB30_Above"] = first_bb.reindex(day_dates).values > 1.0
    df_day["BB30_Below"] = first_bb.reindex(day_dates).values < 0.0
    df_day["BB30_pctb"] = first_bb.reindex(day_dates).values

    # ── Night session new high/low ──
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df_ext = conn.execute("""
            WITH bars AS (
                SELECT
                    CASE
                        WHEN timestamp::TIME >= TIME '08:45:00'
                             AND timestamp::TIME <= TIME '13:45:00'
                            THEN timestamp::DATE
                        WHEN timestamp::TIME >= TIME '15:00:00'
                            THEN timestamp::DATE
                        WHEN timestamp::TIME < TIME '05:01:00'
                            THEN timestamp::DATE - INTERVAL '1 day'
                        ELSE NULL
                    END AS ext_date,
                    high, low
                FROM ohlcv_1m
                WHERE symbol = 'TX'
            )
            SELECT ext_date::DATE AS date,
                   MAX(high) AS ext_high,
                   MIN(low) AS ext_low
            FROM bars
            WHERE ext_date IS NOT NULL
            GROUP BY ext_date
            ORDER BY ext_date
        """).df()
    df_ext["date"] = pd.to_datetime(df_ext["date"])
    df_ext = df_ext.set_index("date")

    daily_hl = df_day.groupby(df_day.index.normalize()).agg(
        day_high=("High", "max"), day_low=("Low", "min")
    )
    recent2_high = daily_hl["day_high"].rolling(2).max().shift(1)
    recent2_low = daily_hl["day_low"].rolling(2).min().shift(1)

    ext_high_prev = df_ext["ext_high"].shift(1)
    ext_low_prev = df_ext["ext_low"].shift(1)

    night_new_high = ext_high_prev > recent2_high
    night_new_low = ext_low_prev < recent2_low

    df_day["NightNewHigh"] = night_new_high.reindex(day_dates).fillna(False).values
    df_day["NightNewLow"] = night_new_low.reindex(day_dates).fillna(False).values

    return df_day


def load_night_session_1m():
    """Load night-session 1m bars (15:00~05:00), keyed by next trading day."""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df_night = conn.execute("""
            SELECT
                CASE
                    WHEN timestamp::TIME >= TIME '15:00:00'
                        THEN timestamp::DATE
                    WHEN timestamp::TIME < TIME '05:01:00'
                        THEN timestamp::DATE - INTERVAL '1 day'
                    ELSE NULL
                END AS night_date,
                timestamp,
                open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND (timestamp::TIME >= TIME '15:00:00' OR timestamp::TIME < TIME '05:01:00')
            ORDER BY timestamp
        """).df()
    df_night["night_date"] = pd.to_datetime(df_night["night_date"])
    return df_night


def identify_s003_signal_days(df_day):
    """Identify days where S003 entry conditions are met (without ORB breakout check).

    Returns a DataFrame with one row per signal day.
    """
    # Build per-day info
    days = df_day.groupby(df_day.index.normalize()).agg(
        day_open=("Open", "first"),
        day_high=("High", "max"),
        day_low=("Low", "min"),
        day_close=("Close", "last"),
        ma30_20=("MA30_20", "first"),
        ma30_20_prev=("MA30_20_Prev", "first"),
        bb_above=("BB30_Above", "first"),
        bb_below=("BB30_Below", "first"),
        bb_pctb=("BB30_pctb", "first"),
        night_new_high=("NightNewHigh", "first"),
        night_new_low=("NightNewLow", "first"),
    )

    # ORB: first 14 bars (08:45~08:58)
    orb_data = []
    for date, grp in df_day.groupby(df_day.index.normalize()):
        orb_bars = grp.between_time("08:45", "08:58")
        if len(orb_bars) == 0:
            continue
        orb_high = orb_bars["High"].max()
        orb_low = orb_bars["Low"].min()
        day_open = float(grp["Open"].iloc[0])
        orb_pct = (orb_high - orb_low) / day_open * 100 if day_open > 0 else 0
        orb_data.append({"date": date, "orb_high": orb_high, "orb_low": orb_low,
                         "orb_pct": orb_pct})
    orb_df = pd.DataFrame(orb_data).set_index("date")
    days = days.join(orb_df)

    # Check if ORB was broken in opposite direction (09:00~10:30)
    breakout_data = []
    for date, grp in df_day.groupby(df_day.index.normalize()):
        entry_bars = grp.between_time("09:00", "10:30")
        if len(entry_bars) == 0:
            breakout_data.append({"date": date, "orb_broken_low": False, "orb_broken_high": False,
                                  "entry_price": np.nan, "entry_time": pd.NaT})
            continue
        orb_info = orb_df.loc[date] if date in orb_df.index else None
        if orb_info is None:
            breakout_data.append({"date": date, "orb_broken_low": False, "orb_broken_high": False,
                                  "entry_price": np.nan, "entry_time": pd.NaT})
            continue

        broken_low = False
        broken_high = False
        entry_price = np.nan
        entry_time = pd.NaT
        for ts, row in entry_bars.iterrows():
            if not broken_low and row["Close"] < orb_info["orb_low"]:
                broken_low = True
                if pd.isna(entry_price):
                    entry_price = row["Close"]
                    entry_time = ts
            if not broken_high and row["Close"] > orb_info["orb_high"]:
                broken_high = True
                if pd.isna(entry_price):
                    entry_price = row["Close"]
                    entry_time = ts
        breakout_data.append({"date": date, "orb_broken_low": broken_low,
                              "orb_broken_high": broken_high,
                              "entry_price": entry_price, "entry_time": entry_time})
    breakout_df = pd.DataFrame(breakout_data).set_index("date")
    days = days.join(breakout_df)

    # Filter S003 conditions
    ma_up = days["ma30_20"] > days["ma30_20_prev"]
    ma_down = days["ma30_20"] < days["ma30_20_prev"]

    # Bull exhaustion → short: MA up + BB above + night new high + ORB low broken
    bull_exh = ma_up & days["bb_above"] & days["night_new_high"] & days["orb_broken_low"]
    # Bear exhaustion → long: MA down + BB below + night new low + ORB high broken
    bear_exh = ma_down & days["bb_below"] & days["night_new_low"] & days["orb_broken_high"]

    # ORB% filter
    orb_ok = days["orb_pct"] >= MIN_ORB_PCT
    # Weekday filter
    wd_ok = ~days.index.weekday.isin(SKIP_WEEKDAYS)

    signals = (bull_exh | bear_exh) & orb_ok & wd_ok
    result = days[signals].copy()
    result["direction"] = "short"
    result.loc[bear_exh & orb_ok & wd_ok, "direction"] = "long"

    return result


def compute_day_session_pnl(df_day, signal_days):
    """Compute day-session PnL for S003 signals (simplified: entry→13:30 close)."""
    pnl_data = []
    for date, sig in signal_days.iterrows():
        grp = df_day[df_day.index.normalize() == date]
        if len(grp) == 0:
            continue
        entry_price = sig["entry_price"]
        if pd.isna(entry_price):
            continue
        # Use 13:30 close or last bar as exit
        exit_bars = grp[grp.index.time <= pd.Timestamp("13:30").time()]
        if len(exit_bars) == 0:
            continue
        exit_price = float(exit_bars["Close"].iloc[-1])

        if sig["direction"] == "short":
            pnl_pts = entry_price - exit_price
        else:
            pnl_pts = exit_price - entry_price

        pnl_pct = pnl_pts / entry_price * 100
        pnl_data.append({
            "date": date,
            "direction": sig["direction"],
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl_pts": pnl_pts,
            "pnl_pct": pnl_pct,
            "win": pnl_pts > 0,
        })
    return pd.DataFrame(pnl_data).set_index("date")


def compute_night_exhaustion_indicators(df_night, signal_days):
    """Compute 4 exhaustion indicators for each S003 signal day's preceding night session.

    1. RSI divergence: price made new extreme but RSI(14) didn't
    2. Extreme time: when night H/L occurred (earlier = more exhaustion)
    3. Tail retracement: how much price pulled back from extreme in 03:00~05:00
    4. Volume decay: ratio of tail-segment volume to push-segment volume
    """
    results = []
    for date, sig in signal_days.iterrows():
        direction = sig["direction"]

        # Get the preceding night session (night_date = previous trading day)
        # Night session for a given ext_date spans 15:00 that day to 05:00 next day
        # For signal on `date`, we need the night session that ended before 08:45 on `date`
        # That night session belongs to ext_date = the previous trading day
        # But in df_night, night_date = calendar date when 15:00 starts
        # So we need night bars where the next trading day = date
        # Approximation: get night bars ending on date (early morning) + previous day (15:00+)
        night_bars = df_night[
            (df_night["night_date"] < pd.Timestamp(date)) &
            (df_night["night_date"] >= pd.Timestamp(date) - pd.Timedelta(days=5))
        ].copy()
        # Get the latest night_date that's before signal date
        if len(night_bars) == 0:
            results.append({"date": date, "rsi_divergence": np.nan,
                            "extreme_time_hour": np.nan, "tail_retracement": np.nan,
                            "volume_decay": np.nan})
            continue

        latest_night_date = night_bars["night_date"].max()
        night_bars = night_bars[night_bars["night_date"] == latest_night_date]
        night_bars = night_bars.sort_values("timestamp")

        if len(night_bars) < 30:
            results.append({"date": date, "rsi_divergence": np.nan,
                            "extreme_time_hour": np.nan, "tail_retracement": np.nan,
                            "volume_decay": np.nan})
            continue

        prices = night_bars["close"].values.astype(float)
        highs = night_bars["high"].values.astype(float)
        lows = night_bars["low"].values.astype(float)
        volumes = night_bars["volume"].values.astype(float)
        timestamps = night_bars["timestamp"].values

        # ── 1. RSI(14) divergence ──
        rsi_period = 14
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        # EMA-style RSI
        avg_gain = np.zeros(len(deltas))
        avg_loss = np.zeros(len(deltas))
        if len(deltas) >= rsi_period:
            avg_gain[rsi_period - 1] = gains[:rsi_period].mean()
            avg_loss[rsi_period - 1] = losses[:rsi_period].mean()
            for i in range(rsi_period, len(deltas)):
                avg_gain[i] = (avg_gain[i - 1] * (rsi_period - 1) + gains[i]) / rsi_period
                avg_loss[i] = (avg_loss[i - 1] * (rsi_period - 1) + losses[i]) / rsi_period

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            rs = avg_gain / np.where(avg_loss == 0, 1e-10, avg_loss)
        rsi = 100 - 100 / (1 + rs)
        # Pad RSI to match prices length (offset by 1 due to diff)
        rsi_full = np.full(len(prices), np.nan)
        rsi_full[1:] = rsi

        if direction == "short":
            # Bull exhaustion: price made high, check if RSI made lower high
            price_extreme_idx = np.argmax(highs)
            # Find RSI peak near price peak (±10 bars)
            window = slice(max(0, price_extreme_idx - 10), min(len(rsi_full), price_extreme_idx + 11))
            rsi_at_peak = np.nanmax(rsi_full[window])
            # Check second half RSI max
            second_half = rsi_full[len(rsi_full) // 2:]
            rsi_second_half_max = np.nanmax(second_half) if len(second_half) > 0 else np.nan
            first_half = rsi_full[:len(rsi_full) // 2]
            rsi_first_half_max = np.nanmax(first_half) if len(first_half) > 0 else np.nan
            # Divergence: price high in second half but RSI lower than first half
            price_high_first = np.max(highs[:len(highs) // 2])
            price_high_second = np.max(highs[len(highs) // 2:])
            rsi_div = (price_high_second >= price_high_first and
                       rsi_second_half_max < rsi_first_half_max)
        else:
            # Bear exhaustion: price made low, check if RSI made higher low
            price_extreme_idx = np.argmin(lows)
            # RSI divergence (bullish): price lower low but RSI higher low
            second_half = rsi_full[len(rsi_full) // 2:]
            rsi_second_half_min = np.nanmin(second_half) if len(second_half) > 0 else np.nan
            first_half = rsi_full[:len(rsi_full) // 2]
            rsi_first_half_min = np.nanmin(first_half) if len(first_half) > 0 else np.nan
            price_low_first = np.min(lows[:len(lows) // 2])
            price_low_second = np.min(lows[len(lows) // 2:])
            rsi_div = (price_low_second <= price_low_first and
                       rsi_second_half_min > rsi_first_half_min)

        # ── 2. Extreme time ──
        ts_series = pd.to_datetime(timestamps)
        if direction == "short":
            extreme_idx = np.argmax(highs)
        else:
            extreme_idx = np.argmin(lows)
        extreme_ts = ts_series[extreme_idx]
        # Convert to fractional hour (15:00=15.0, 03:00=27.0 for continuity)
        ext_hour = extreme_ts.hour + extreme_ts.minute / 60
        if ext_hour < 12:  # early morning: add 24 for continuity
            ext_hour += 24
        # "Early" means further from 05:00 → lower hour = more exhaustion? No.
        # Actually earlier extreme = more time to "run out of steam"
        # We want: how early the extreme was relative to session end (05:00 = 29.0)
        # Earlier extreme (e.g., 20:00) means it peaked early → more time to decay

        # ── 3. Tail retracement (03:00~05:00) ──
        tail_mask = ts_series.time >= pd.Timestamp("03:00").time()
        night_range = np.max(highs) - np.min(lows)
        if tail_mask.any() and night_range > 0:
            tail_bars = night_bars[tail_mask]
            if direction == "short":
                # Bull exhaustion: how much price fell from high in tail
                tail_retracement = (np.max(highs) - tail_bars["close"].iloc[-1]) / night_range
            else:
                # Bear exhaustion: how much price rose from low in tail
                tail_retracement = (tail_bars["close"].iloc[-1] - np.min(lows)) / night_range
        else:
            tail_retracement = np.nan

        # ── 4. Volume decay ──
        # Push segment: first 2/3 of session; Tail segment: last 1/3
        n_bars = len(night_bars)
        push_end = n_bars * 2 // 3
        push_vol = volumes[:push_end].sum()
        tail_vol = volumes[push_end:].sum()
        if push_vol > 0:
            # Normalize per-bar
            push_avg = push_vol / push_end
            tail_avg = tail_vol / max(1, n_bars - push_end)
            volume_decay = tail_avg / push_avg  # < 1 means volume declining
        else:
            volume_decay = np.nan

        results.append({
            "date": date,
            "rsi_divergence": rsi_div,
            "extreme_time_hour": ext_hour,
            "tail_retracement": float(tail_retracement),
            "volume_decay": float(volume_decay),
        })

    return pd.DataFrame(results).set_index("date")


def print_group_stats(df, label):
    """Print summary stats for a group of trades."""
    n = len(df)
    if n == 0:
        print(f"  {label}: N=0")
        return
    wins = df["win"].sum()
    wr = wins / n * 100
    avg_pnl = df["pnl_pts"].mean()
    gross_profit = df.loc[df["pnl_pts"] > 0, "pnl_pts"].sum()
    gross_loss = abs(df.loc[df["pnl_pts"] < 0, "pnl_pts"].sum())
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    avg_win = df.loc[df["pnl_pts"] > 0, "pnl_pts"].mean() if wins > 0 else 0
    avg_loss = df.loc[df["pnl_pts"] < 0, "pnl_pts"].mean() if (n - wins) > 0 else 0
    print(f"  {label}: N={n}, WR={wr:.1f}%, PF={pf:.2f}, "
          f"AvgPnL={avg_pnl:.1f}pt, AvgWin={avg_win:.1f}pt, AvgLoss={avg_loss:.1f}pt")


def main():
    print("=" * 70)
    print("H051 — Night Session Momentum Exhaustion: Phase 1 Exploration")
    print("=" * 70)

    # ── Step 1: Load data ──
    print("\n[1/4] Loading day-session data with S003 indicators...")
    df_day = load_day_session()
    print(f"  Loaded {len(df_day):,} day-session bars [{df_day.index[0]} → {df_day.index[-1]}]")

    print("\n[1/4] Loading night-session 1m bars...")
    df_night = load_night_session_1m()
    print(f"  Loaded {len(df_night):,} night-session bars")

    # ── Step 2: Night session volume trend ──
    print("\n[2/4] Night session volume yearly trend:")
    yearly_vol = df_night.groupby(df_night["night_date"].dt.year).agg(
        total_vol=("volume", "sum"),
        bar_count=("volume", "count"),
    )
    yearly_vol["avg_vol_per_bar"] = (yearly_vol["total_vol"] / yearly_vol["bar_count"]).round(1)
    print(yearly_vol.to_string())

    # ── Step 3: Identify S003 signal days ──
    print("\n[3/4] Identifying S003 signal days...")
    signal_days = identify_s003_signal_days(df_day)
    print(f"  Found {len(signal_days)} S003 signal days")
    print(f"  Direction breakdown: {signal_days['direction'].value_counts().to_dict()}")
    print(f"  Year breakdown: {signal_days.groupby(signal_days.index.year).size().to_dict()}")

    # ── Step 4: Compute PnL ──
    print("\n[3/4] Computing day-session PnL (entry → 13:30)...")
    pnl_df = compute_day_session_pnl(df_day, signal_days)
    print(f"  Computed PnL for {len(pnl_df)} trades")
    print_group_stats(pnl_df, "All S003 trades (simplified)")

    # ── Step 5: Compute exhaustion indicators ──
    print("\n[4/4] Computing night-session exhaustion indicators...")
    exh_df = compute_night_exhaustion_indicators(df_night, signal_days)

    # Merge
    merged = pnl_df.join(exh_df, how="inner")
    print(f"  Merged {len(merged)} trades with exhaustion indicators")

    # ── Analysis: each indicator ──
    print("\n" + "=" * 70)
    print("EXHAUSTION INDICATOR ANALYSIS")
    print("=" * 70)

    # 1. RSI Divergence
    print("\n── 1. RSI Divergence (price new extreme, RSI didn't) ──")
    rsi_valid = merged.dropna(subset=["rsi_divergence"])
    rsi_yes = rsi_valid[rsi_valid["rsi_divergence"] == True]
    rsi_no = rsi_valid[rsi_valid["rsi_divergence"] == False]
    print_group_stats(rsi_yes, "RSI divergence YES")
    print_group_stats(rsi_no, "RSI divergence NO")

    # 2. Extreme Time
    print("\n── 2. Extreme Time (hour of night H/L) ──")
    ext_valid = merged.dropna(subset=["extreme_time_hour"])
    if len(ext_valid) > 0:
        median_hour = ext_valid["extreme_time_hour"].median()
        print(f"  Median extreme time: {median_hour:.1f}h "
              f"(= {int(median_hour % 24):02d}:{int((median_hour % 1) * 60):02d})")
        early = ext_valid[ext_valid["extreme_time_hour"] <= median_hour]
        late = ext_valid[ext_valid["extreme_time_hour"] > median_hour]
        print_group_stats(early, f"Extreme EARLY (≤{median_hour:.1f}h)")
        print_group_stats(late, f"Extreme LATE (>{median_hour:.1f}h)")

        # Also try cutoff at 01:00 (=25.0)
        print("\n  Alternative cutoff: 01:00 (hour=25.0)")
        before_1am = ext_valid[ext_valid["extreme_time_hour"] <= 25.0]
        after_1am = ext_valid[ext_valid["extreme_time_hour"] > 25.0]
        print_group_stats(before_1am, "Extreme ≤01:00")
        print_group_stats(after_1am, "Extreme >01:00")

    # 3. Tail Retracement (03:00~05:00)
    print("\n── 3. Tail Retracement (03:00~05:00 pullback / night range) ──")
    tail_valid = merged.dropna(subset=["tail_retracement"])
    if len(tail_valid) > 0:
        median_tail = tail_valid["tail_retracement"].median()
        print(f"  Median tail retracement: {median_tail:.3f}")
        high_retrace = tail_valid[tail_valid["tail_retracement"] >= median_tail]
        low_retrace = tail_valid[tail_valid["tail_retracement"] < median_tail]
        print_group_stats(high_retrace, f"High retracement (≥{median_tail:.3f})")
        print_group_stats(low_retrace, f"Low retracement (<{median_tail:.3f})")

        # Also try fixed cutoff
        print("\n  Alternative cutoff: retracement ≥ 0.3")
        retrace_high = tail_valid[tail_valid["tail_retracement"] >= 0.3]
        retrace_low = tail_valid[tail_valid["tail_retracement"] < 0.3]
        print_group_stats(retrace_high, "Retracement ≥ 0.3")
        print_group_stats(retrace_low, "Retracement < 0.3")

    # 4. Volume Decay
    print("\n── 4. Volume Decay (tail avg vol / push avg vol) ──")
    vol_valid = merged.dropna(subset=["volume_decay"])
    if len(vol_valid) > 0:
        median_decay = vol_valid["volume_decay"].median()
        print(f"  Median volume decay ratio: {median_decay:.3f}")
        decay_yes = vol_valid[vol_valid["volume_decay"] < median_decay]
        decay_no = vol_valid[vol_valid["volume_decay"] >= median_decay]
        print_group_stats(decay_yes, f"Volume decaying (<{median_decay:.3f})")
        print_group_stats(decay_no, f"Volume sustained (≥{median_decay:.3f})")

        # Fixed cutoff at 0.8
        print("\n  Alternative cutoff: decay ratio < 0.8")
        decay_08_yes = vol_valid[vol_valid["volume_decay"] < 0.8]
        decay_08_no = vol_valid[vol_valid["volume_decay"] >= 0.8]
        print_group_stats(decay_08_yes, "Volume decaying (<0.8)")
        print_group_stats(decay_08_no, "Volume sustained (≥0.8)")

    # ── Combined: any 2+ indicators ──
    print("\n── Combined: 2+ exhaustion signals ──")
    combined = merged.copy()
    combined["exh_count"] = 0
    if "rsi_divergence" in combined.columns:
        combined["exh_count"] += combined["rsi_divergence"].fillna(False).astype(int)
    if "extreme_time_hour" in combined.columns:
        combined["exh_count"] += (combined["extreme_time_hour"] <= 25.0).fillna(False).astype(int)
    if "tail_retracement" in combined.columns:
        combined["exh_count"] += (combined["tail_retracement"] >= 0.3).fillna(False).astype(int)
    if "volume_decay" in combined.columns:
        combined["exh_count"] += (combined["volume_decay"] < 0.8).fillna(False).astype(int)

    for threshold in [0, 1, 2, 3, 4]:
        grp = combined[combined["exh_count"] >= threshold]
        print_group_stats(grp, f"≥{threshold} exhaustion signals")

    # ── Year-based analysis (early vs recent) ──
    print("\n" + "=" * 70)
    print("YEAR-BASED ANALYSIS (Early vs Recent)")
    print("=" * 70)
    if len(merged) > 0:
        early_years = merged[merged.index.year <= 2023]
        recent_years = merged[merged.index.year >= 2024]
        print_group_stats(early_years, "2021-2023 (early)")
        print_group_stats(recent_years, "2024-2026 (recent)")

        # RSI divergence by era
        if len(rsi_valid) > 0:
            print("\n  RSI divergence by era:")
            for era, label in [(rsi_valid[rsi_valid.index.year <= 2023], "2021-2023"),
                               (rsi_valid[rsi_valid.index.year >= 2024], "2024-2026")]:
                era_yes = era[era["rsi_divergence"] == True]
                era_no = era[era["rsi_divergence"] == False]
                print(f"    {label}:")
                print_group_stats(era_yes, f"  RSI div YES")
                print_group_stats(era_no, f"  RSI div NO")

    # ── Save detailed results ──
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_csv(OUT_DIR / "h051_explore_trades.csv")
    print(f"\nDetailed trades saved → {OUT_DIR / 'h051_explore_trades.csv'}")

    # ── Summary table ──
    print("\n" + "=" * 70)
    print("SUMMARY TABLE")
    print("=" * 70)
    summary_rows = []
    for name, yes_df, no_df in [
        ("RSI Divergence", rsi_yes, rsi_no),
        (f"Extreme Time ≤01:00", before_1am if len(ext_valid) > 0 else pd.DataFrame(),
         after_1am if len(ext_valid) > 0 else pd.DataFrame()),
        ("Tail Retracement ≥0.3", retrace_high if len(tail_valid) > 0 else pd.DataFrame(),
         retrace_low if len(tail_valid) > 0 else pd.DataFrame()),
        ("Volume Decay <0.8", decay_08_yes if len(vol_valid) > 0 else pd.DataFrame(),
         decay_08_no if len(vol_valid) > 0 else pd.DataFrame()),
    ]:
        def calc_stats(d):
            if len(d) == 0:
                return {"N": 0, "WR": "-", "PF": "-", "AvgPnL": "-"}
            n = len(d)
            wr = d["win"].sum() / n * 100
            gp = d.loc[d["pnl_pts"] > 0, "pnl_pts"].sum()
            gl = abs(d.loc[d["pnl_pts"] < 0, "pnl_pts"].sum())
            pf = gp / gl if gl > 0 else float("inf")
            return {"N": n, "WR": f"{wr:.1f}%", "PF": f"{pf:.2f}", "AvgPnL": f"{d['pnl_pts'].mean():.1f}"}

        yes_stats = calc_stats(yes_df)
        no_stats = calc_stats(no_df)
        summary_rows.append({
            "Indicator": name,
            "YES_N": yes_stats["N"], "YES_WR": yes_stats["WR"],
            "YES_PF": yes_stats["PF"], "YES_AvgPnL": yes_stats["AvgPnL"],
            "NO_N": no_stats["N"], "NO_WR": no_stats["WR"],
            "NO_PF": no_stats["PF"], "NO_AvgPnL": no_stats["AvgPnL"],
        })

    summary_df = pd.DataFrame(summary_rows)
    print(summary_df.to_string(index=False))

    print("\nDone.")


if __name__ == "__main__":
    main()
