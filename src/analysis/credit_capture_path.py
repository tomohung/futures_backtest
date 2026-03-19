"""
Credit Capture Path Analysis for EstRange Credit Spread

Step 0: Observe how credit is captured over time for each weekday/DTE.
For each trade, scan from touch_time to exit_time every minute,
lookup both legs' last known prices, compute captured_pct.

Usage:
    uv run python src/analysis/credit_capture_path.py
"""

from datetime import date, time, timedelta

import duckdb
import numpy as np
import pandas as pd

from src.backtest.backtest_estrange_options import (
    DB_PATH,
    load_1m_data,
    preload_daily_contracts,
    select_contract,
    get_expiry_date,
    lookup_option_price,
    round_to_100,
    _third_wednesday,
)
from src.backtest.estimate_hl import compute_vol_estimated_range

# Finalized params
WEEKDAY_EXIT = {"Mon": "11:30", "Tue": "11:30", "Wed": "10:30", "Fri": "12:00"}
FRACTION = 0.65
SPREAD_PCT = 0.50
MAX_SPREAD = 200
MIN_GAP = 50
MIN_DTE = 0
MIN_CREDIT = 5


def lookup_last_price(
    conn: duckdb.DuckDBPyConnection,
    trade_date: date,
    contract: str,
    strike: int,
    put_call: str,
    at_time: time,
) -> float | None:
    """Find the last trade price at or before the given time."""
    row = conn.execute(
        """
        SELECT price FROM ticks_options
        WHERE trade_date = ? AND contract = ? AND strike = ?
          AND put_call = ? AND trade_time <= ?
        ORDER BY trade_time DESC
        LIMIT 1
        """,
        [trade_date, contract, strike, put_call, at_time],
    ).fetchone()
    return float(row[0]) if row else None


def add_minutes(t: time, minutes: int) -> time:
    """Add minutes to a time object, capping at 13:45."""
    total = t.hour * 60 + t.minute + minutes
    total = min(total, 13 * 60 + 45)
    return time(total // 60, total % 60)


def run_capture_path_analysis():
    start = "2025-07-01"
    end = "2026-03-19"

    print("Loading 1-min data and computing EstRange...")
    df = load_1m_data()
    dates = sorted(df.index.normalize().unique())
    dates = [d for d in dates if pd.Timestamp(start) <= d <= pd.Timestamp(end)]
    print(f"  Trading days: {len(dates)}")

    # Settlement dates
    settlement_dates: set[date] = set()
    for y in range(int(start[:4]), int(end[:4]) + 1):
        for m in range(1, 13):
            settlement_dates.add(_third_wednesday(y, m))

    entry_start = time(9, 30)
    all_paths = []

    with duckdb.connect(DB_PATH, read_only=True) as conn:
        daily_contracts = preload_daily_contracts(conn, start, end)

        for dt in dates:
            td = dt.date()
            weekday = td.weekday()
            weekday_name = ["Mon", "Tue", "Wed", "Thu", "Fri"][weekday]

            if weekday_name not in WEEKDAY_EXIT:
                continue
            if td in settlement_dates:
                continue

            exit_time_str = WEEKDAY_EXIT[weekday_name]
            exit_time = time(int(exit_time_str.split(":")[0]), int(exit_time_str.split(":")[1]))

            # Get day's bars and find touch
            day_mask = df.index.normalize() == dt
            day_df = df[day_mask]

            session_high = -np.inf
            session_low = np.inf
            er = np.nan

            for idx, row in day_df.iterrows():
                if idx.time() >= entry_start:
                    break
                session_high = max(session_high, float(row["High"]))
                session_low = min(session_low, float(row["Low"]))

            if session_high == -np.inf:
                continue

            scan_bars = day_df[
                (day_df.index.time >= entry_start) & (day_df.index.time <= exit_time)
            ]

            touched_side = None
            touch_time = None

            for idx, row in scan_bars.iterrows():
                h, l = float(row["High"]), float(row["Low"])
                session_high = max(session_high, h)
                session_low = min(session_low, l)

                bar_er = row.get("EstRange")
                if pd.notna(bar_er) and bar_er > 0:
                    er = float(bar_er)

                if np.isnan(er):
                    continue

                est_high = session_low + er * FRACTION
                est_low = session_high - er * FRACTION

                if h >= est_high:
                    touched_side = "high"
                    touch_time = idx.time()
                    break
                if l <= est_low:
                    touched_side = "low"
                    touch_time = idx.time()
                    break

            if touched_side is None:
                continue

            if est_high - est_low < MIN_GAP:
                continue

            # Select contract & strikes (same as backtest)
            contract, _ = select_contract(td, daily_contracts, False, MIN_DTE, None, False)
            if contract is None:
                continue

            spread_width = max(round_to_100(er * SPREAD_PCT), 100)
            spread_width = min(spread_width, MAX_SPREAD)

            if touched_side == "high":
                sell_strike = round_to_100(est_low)
                buy_strike = sell_strike - spread_width
                put_call = "P"
            else:
                sell_strike = round_to_100(est_high)
                buy_strike = sell_strike + spread_width
                put_call = "C"

            # Get entry premiums
            touch_end = time(
                min(touch_time.hour + (touch_time.minute + 5) // 60, 13),
                (touch_time.minute + 5) % 60,
            )
            sell_premium = lookup_option_price(
                conn, td, contract, sell_strike, put_call, touch_time, touch_end
            )
            buy_premium = lookup_option_price(
                conn, td, contract, buy_strike, put_call, touch_time, touch_end
            )
            if sell_premium is None or buy_premium is None:
                touch_end2 = time(
                    min(touch_time.hour + (touch_time.minute + 15) // 60, 13),
                    (touch_time.minute + 15) % 60,
                )
                if sell_premium is None:
                    sell_premium = lookup_option_price(
                        conn, td, contract, sell_strike, put_call, touch_time, touch_end2
                    )
                if buy_premium is None:
                    buy_premium = lookup_option_price(
                        conn, td, contract, buy_strike, put_call, touch_time, touch_end2
                    )

            if sell_premium is None or buy_premium is None:
                continue

            credit = sell_premium - buy_premium
            if credit <= 0 or credit < MIN_CREDIT:
                continue

            # Compute DTE
            expiry = get_expiry_date(contract)
            dte = (expiry - td).days if expiry else None

            # Scan every minute from touch_time to exit_time
            t = add_minutes(touch_time, 1)
            minute_offset = 1
            while t <= exit_time:
                sell_now = lookup_last_price(conn, td, contract, sell_strike, put_call, t)
                buy_now = lookup_last_price(conn, td, contract, buy_strike, put_call, t)

                if sell_now is not None and buy_now is not None:
                    debit_now = sell_now - buy_now
                    unrealized_pnl = credit - debit_now
                    captured_pct = unrealized_pnl / credit * 100 if credit > 0 else 0

                    all_paths.append({
                        "date": td,
                        "weekday": weekday_name,
                        "dte": dte,
                        "minute_offset": minute_offset,
                        "time": t,
                        "credit": credit,
                        "sell_now": sell_now,
                        "buy_now": buy_now,
                        "debit_now": debit_now,
                        "unrealized_pnl": unrealized_pnl,
                        "captured_pct": captured_pct,
                    })

                t = add_minutes(t, 1)
                minute_offset += 1

            print(f"  {td} {weekday_name} DTE={dte} credit={credit:.1f} scanned {minute_offset-1} min")

    df_paths = pd.DataFrame(all_paths)
    return df_paths


def print_summary(df_paths: pd.DataFrame):
    if df_paths.empty:
        print("No data.")
        return

    print("\n" + "=" * 80)
    print("Credit Capture Path Analysis — captured_pct by Weekday × Minute Offset")
    print("=" * 80)

    for wd in ["Mon", "Tue", "Wed", "Fri"]:
        sub = df_paths[df_paths["weekday"] == wd]
        if sub.empty:
            continue

        dte_mode = sub.groupby("date")["dte"].first().mode().iloc[0]
        n_trades = sub["date"].nunique()
        print(f"\n--- {wd} (DTE={dte_mode}, n={n_trades} trades) ---")
        print(f"{'min':>5} {'mean':>8} {'median':>8} {'std':>8} {'p25':>8} {'p75':>8} {'n':>5}")

        # Show every 5 minutes + last
        offsets = sorted(sub["minute_offset"].unique())
        show_offsets = [o for o in offsets if o % 5 == 0 or o == 1 or o == max(offsets)]
        show_offsets = sorted(set(show_offsets))

        for offset in show_offsets:
            rows = sub[sub["minute_offset"] == offset]["captured_pct"]
            if len(rows) < 3:
                continue
            print(
                f"{offset:>5} {rows.mean():>8.1f}% {rows.median():>8.1f}% "
                f"{rows.std():>8.1f}% {rows.quantile(0.25):>8.1f}% "
                f"{rows.quantile(0.75):>8.1f}% {len(rows):>5}"
            )

    # Summary: at what minute does mean captured_pct reach 50/70/80/90%?
    print("\n" + "=" * 80)
    print("Minutes to reach captured_pct thresholds (based on mean)")
    print("=" * 80)
    print(f"{'Day':>5} {'50%':>8} {'70%':>8} {'80%':>8} {'90%':>8}")

    for wd in ["Mon", "Tue", "Wed", "Fri"]:
        sub = df_paths[df_paths["weekday"] == wd]
        if sub.empty:
            continue

        mean_by_offset = sub.groupby("minute_offset")["captured_pct"].mean()
        results = {}
        for threshold in [50, 70, 80, 90]:
            reached = mean_by_offset[mean_by_offset >= threshold]
            results[threshold] = f"{reached.index.min():>3} min" if not reached.empty else "  never"

        print(f"{wd:>5} {results[50]:>8} {results[70]:>8} {results[80]:>8} {results[90]:>8}")


if __name__ == "__main__":
    df_paths = run_capture_path_analysis()

    out_path = "output/credit_capture_path.csv"
    df_paths.to_csv(out_path, index=False)
    print(f"\nRaw data saved → {out_path}")

    print_summary(df_paths)
