"""
9:05 出量 K 棒方向預測分析

假設：開盤 20 分鐘後（9:05），若出現明顯放量的 1 分 K，
其多空方向可能預示當日後續走勢。

出量定義（兩種）：
1. 當日均量法：09:05 volume > N × mean(08:45–09:04 volume)
2. 歷史同時段法：09:05 volume > N × 過去 20 天 09:05 平均 volume

用法: uv run python src/analysis/explore_volume_signal.py
"""

import duckdb
import pandas as pd
import numpy as np

DB_PATH = "data/futures.duckdb"


def load_day_session_bars() -> pd.DataFrame:
    """Load TX day-session 1-min bars (08:45–13:45)."""
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


def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    """For each trading day, compute volume signal at 09:05."""
    from datetime import time as dtime

    t_0905 = dtime(9, 5)
    t_0845 = dtime(8, 45)
    t_0904 = dtime(9, 4)
    t_1330 = dtime(13, 30)

    records = []
    dates = sorted(df["date"].unique())

    # Pre-compute historical 09:05 volumes for rolling lookback
    bar_0905_all = df[df["time"] == t_0905].set_index("date")

    for date in dates:
        day = df[df["date"] == date]

        # Get 09:05 bar
        bar_0905 = day[day["time"] == t_0905]
        if bar_0905.empty:
            continue
        bar_0905 = bar_0905.iloc[0]

        vol_0905 = bar_0905["volume"]
        open_0905 = bar_0905["open"]
        close_0905 = bar_0905["close"]

        # Skip doji
        if close_0905 == open_0905:
            continue

        direction = "bullish" if close_0905 > open_0905 else "bearish"

        # --- Method 1: intraday mean volume (08:45–09:04) ---
        early_bars = day[(day["time"] >= t_0845) & (day["time"] <= t_0904)]
        if early_bars.empty:
            continue
        intraday_mean = early_bars["volume"].mean()
        intraday_ratio = vol_0905 / intraday_mean if intraday_mean > 0 else 0

        # --- Method 2: historical 09:05 mean (past 20 days) ---
        past_dates = [d for d in dates if d < date][-20:]
        if len(past_dates) >= 5:
            hist_vols = bar_0905_all.loc[
                bar_0905_all.index.isin(past_dates), "volume"
            ]
            hist_mean = hist_vols.mean() if len(hist_vols) > 0 else 0
        else:
            hist_mean = 0
        hist_ratio = vol_0905 / hist_mean if hist_mean > 0 else 0

        # --- Outcome: 13:30 close ---
        bar_1330 = day[day["time"] == t_1330]
        if bar_1330.empty:
            # Use last bar of day as fallback
            bar_1330 = day.iloc[-1]
            close_1330 = bar_1330["close"]
        else:
            close_1330 = bar_1330.iloc[0]["close"]

        move = close_1330 - close_0905
        outcome_dir = "up" if move > 0 else ("down" if move < 0 else "flat")

        # --- OR breakout direction (08:45–09:30 range) ---
        or_bars = day[(day["time"] >= t_0845) & (day["time"] <= dtime(9, 30))]
        if not or_bars.empty:
            or_high = or_bars["high"].max()
            or_low = or_bars["low"].min()
            # Check which side breaks first after OR period
            post_or = day[day["time"] > dtime(9, 30)]
            or_break = None
            for _, row in post_or.iterrows():
                if row["high"] > or_high:
                    or_break = "up"
                    break
                if row["low"] < or_low:
                    or_break = "down"
                    break
        else:
            or_break = None

        year = date.year if hasattr(date, "year") else pd.Timestamp(date).year

        records.append({
            "date": date,
            "year": year,
            "vol_0905": vol_0905,
            "intraday_mean": intraday_mean,
            "intraday_ratio": intraday_ratio,
            "hist_mean": hist_mean,
            "hist_ratio": hist_ratio,
            "direction": direction,
            "close_0905": close_0905,
            "close_1330": close_1330,
            "move": move,
            "move_pct": move / close_0905 * 100,
            "outcome_dir": outcome_dir,
            "or_break": or_break,
        })

    return pd.DataFrame(records)


def analyze_by_threshold(signals: pd.DataFrame, method: str, thresholds: list[float]):
    """Analyze accuracy for each threshold and direction."""
    ratio_col = f"{method}_ratio"

    print(f"\n{'='*70}")
    print(f"Method: {method} (ratio = vol_0905 / {method}_mean)")
    print(f"{'='*70}")
    print(f"Total trading days with valid 09:05 bar: {len(signals)}")

    for n in thresholds:
        triggered = signals[signals[ratio_col] >= n]
        n_triggered = len(triggered)
        trigger_rate = n_triggered / len(signals) * 100 if len(signals) > 0 else 0

        print(f"\n--- Threshold N = {n:.1f} | Triggered: {n_triggered} ({trigger_rate:.0f}%) ---")

        if n_triggered == 0:
            print("  No signals.")
            continue

        for dir_label in ["bullish", "bearish"]:
            subset = triggered[triggered["direction"] == dir_label]
            n_sub = len(subset)
            if n_sub == 0:
                print(f"  {dir_label}: 0 signals")
                continue

            # Accuracy: does move direction match signal direction?
            if dir_label == "bullish":
                correct = (subset["move"] > 0).sum()
            else:
                correct = (subset["move"] < 0).sum()

            accuracy = correct / n_sub * 100
            avg_move = subset["move"].mean()
            avg_move_pct = subset["move_pct"].mean()

            # OR consistency
            if dir_label == "bullish":
                or_match = (subset["or_break"] == "up").sum()
            else:
                or_match = (subset["or_break"] == "down").sum()
            or_consistency = or_match / n_sub * 100

            print(
                f"  {dir_label:8s}: n={n_sub:4d} | "
                f"accuracy={accuracy:5.1f}% | "
                f"avg_move={avg_move:+7.1f} pts ({avg_move_pct:+.3f}%) | "
                f"OR_match={or_consistency:5.1f}%"
            )

        # Combined accuracy (direction-aware)
        bull = triggered[triggered["direction"] == "bullish"]
        bear = triggered[triggered["direction"] == "bearish"]
        correct_total = (bull["move"] > 0).sum() + (bear["move"] < 0).sum()
        overall_acc = correct_total / n_triggered * 100
        avg_move_all = triggered["move"].mean()
        print(
            f"  {'combined':8s}: n={n_triggered:4d} | "
            f"accuracy={overall_acc:5.1f}% | "
            f"avg_abs_move={triggered['move'].abs().mean():.1f} pts"
        )


def analyze_by_year(signals: pd.DataFrame, method: str, threshold: float):
    """Year-by-year breakdown for a specific method/threshold."""
    ratio_col = f"{method}_ratio"
    triggered = signals[signals[ratio_col] >= threshold]

    print(f"\n{'='*70}")
    print(f"Year-by-year: {method}, N={threshold}")
    print(f"{'='*70}")
    print(f"{'Year':>6s} {'Total':>6s} {'Trig':>6s} {'Rate':>6s} "
          f"{'Bull':>6s} {'BullAcc':>8s} {'Bear':>6s} {'BearAcc':>8s} "
          f"{'Overall':>8s}")
    print("-" * 70)

    for year in sorted(signals["year"].unique()):
        yr_all = signals[signals["year"] == year]
        yr_trig = triggered[triggered["year"] == year]
        n_trig = len(yr_trig)
        rate = n_trig / len(yr_all) * 100 if len(yr_all) > 0 else 0

        bull = yr_trig[yr_trig["direction"] == "bullish"]
        bear = yr_trig[yr_trig["direction"] == "bearish"]
        bull_acc = (bull["move"] > 0).sum() / len(bull) * 100 if len(bull) > 0 else 0
        bear_acc = (bear["move"] < 0).sum() / len(bear) * 100 if len(bear) > 0 else 0

        correct = (bull["move"] > 0).sum() + (bear["move"] < 0).sum()
        overall = correct / n_trig * 100 if n_trig > 0 else 0

        print(
            f"{year:>6d} {len(yr_all):>6d} {n_trig:>6d} {rate:>5.0f}% "
            f"{len(bull):>6d} {bull_acc:>7.1f}% {len(bear):>6d} {bear_acc:>7.1f}% "
            f"{overall:>7.1f}%"
        )


def analyze_profit_potential(signals: pd.DataFrame, method: str, threshold: float):
    """If we trade in the signal direction, what's the cumulative PnL?"""
    ratio_col = f"{method}_ratio"
    triggered = signals[signals[ratio_col] >= threshold].copy()

    if triggered.empty:
        return

    # PnL: long if bullish, short if bearish
    triggered["pnl"] = triggered.apply(
        lambda r: r["move"] if r["direction"] == "bullish" else -r["move"], axis=1
    )
    triggered["pnl_pct"] = triggered.apply(
        lambda r: r["move_pct"] if r["direction"] == "bullish" else -r["move_pct"],
        axis=1,
    )

    print(f"\n{'='*70}")
    print(f"Profit potential: {method}, N={threshold}")
    print(f"{'='*70}")

    for year in sorted(triggered["year"].unique()):
        yr = triggered[triggered["year"] == year]
        total_pnl = yr["pnl"].sum()
        avg_pnl = yr["pnl"].mean()
        win_rate = (yr["pnl"] > 0).sum() / len(yr) * 100
        pf_wins = yr.loc[yr["pnl"] > 0, "pnl"].sum()
        pf_losses = yr.loc[yr["pnl"] < 0, "pnl"].abs().sum()
        pf = pf_wins / pf_losses if pf_losses > 0 else float("inf")
        print(
            f"  {year}: trades={len(yr):3d} | "
            f"PnL={total_pnl:+7.0f} pts | "
            f"avg={avg_pnl:+6.1f} | "
            f"win={win_rate:4.1f}% | "
            f"PF={pf:.2f}"
        )

    total = triggered["pnl"].sum()
    avg = triggered["pnl"].mean()
    win = (triggered["pnl"] > 0).sum() / len(triggered) * 100
    print(f"  {'TOTAL':>5s}: trades={len(triggered):3d} | PnL={total:+7.0f} pts | "
          f"avg={avg:+6.1f} | win={win:4.1f}%")


def main():
    print("Loading 1-min bars...")
    df = load_day_session_bars()
    print(f"Loaded {len(df):,} bars, {df['date'].nunique()} trading days")
    print(f"Date range: {df['date'].min()} ~ {df['date'].max()}")

    print("\nComputing 09:05 volume signals...")
    signals = compute_signals(df)
    print(f"Valid signals: {len(signals)} days (excl. doji)")

    thresholds = [1.5, 2.0, 3.0]

    # --- Threshold analysis ---
    for method in ["intraday", "hist"]:
        analyze_by_threshold(signals, method, thresholds)

    # --- Year-by-year for best candidates ---
    for method in ["intraday", "hist"]:
        for n in thresholds:
            analyze_by_year(signals, method, n)

    # --- Profit potential ---
    for method in ["intraday", "hist"]:
        for n in thresholds:
            analyze_profit_potential(signals, method, n)


if __name__ == "__main__":
    main()
