"""
EstRange Credit Spread Options Backtest

Strategy (from specs/strategies/2026-03-17-estrange-options.md):
  - At 09:30, compute EstRange; Est High = session_low + ER*fraction,
    Est Low = session_high - ER*fraction
  - 09:30~exit_time: first touch of Est High → sell Put Spread (strike near Est Low),
    first touch of Est Low → sell Call Spread (strike near Est High)
  - Spread width = ER * spread_pct, rounded to nearest 100, min 100
  - Skip Wednesdays
  - Monthly TXO only
  - Max 1 trade per day
  - Loss = strike touched before exit → lose (spread_width - credit)
  - Win = exit without touching sell strike → keep full credit
"""

import argparse
import math
from datetime import date, time, timedelta

import duckdb
import numpy as np
import pandas as pd

from src.backtest.estimate_hl import compute_vol_estimated_range

DB_PATH = "data/futures.duckdb"


def round_to_100(x: float) -> int:
    return int(round(x / 100.0)) * 100


def get_monthly_contract(trade_date: date) -> str:
    """Return the monthly contract code for the given trade date.

    Monthly TXO expires on the 3rd Wednesday of the month.
    If trade_date is after that, use next month's contract.
    """
    y, m = trade_date.year, trade_date.month
    # Find 3rd Wednesday
    first_day = date(y, m, 1)
    # weekday: 0=Mon, 2=Wed
    first_wed = first_day + timedelta(days=(2 - first_day.weekday()) % 7)
    third_wed = first_wed + timedelta(weeks=2)

    if trade_date >= third_wed:
        # Use next month
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1

    return f"{y:04d}{m:02d}"


def load_1m_data() -> pd.DataFrame:
    """Load full day-session 1-min OHLCV and compute EstRange."""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ORDER BY timestamp
        """).df()

    df = df.set_index("timestamp")
    df.columns = ["Open", "High", "Low", "Close", "Volume"]

    # Compute EstRange on full history (needs 20-day warmup)
    df = compute_vol_estimated_range(df, lookback=20, use_ema=True)

    return df


def lookup_option_price(
    conn: duckdb.DuckDBPyConnection,
    trade_date: date,
    contract: str,
    strike: int,
    put_call: str,
    after_time: time,
    before_time: time,
) -> float | None:
    """Find the first trade price for the given option after a specific time."""
    row = conn.execute(
        """
        SELECT price FROM ticks_options
        WHERE trade_date = ? AND contract = ? AND strike = ?
          AND put_call = ? AND trade_time >= ? AND trade_time <= ?
        ORDER BY trade_time
        LIMIT 1
        """,
        [trade_date, contract, strike, put_call, after_time, before_time],
    ).fetchone()
    return float(row[0]) if row else None


def lookup_price_at_time(
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


def check_strike_touched(
    conn: duckdb.DuckDBPyConnection,
    trade_date: date,
    strike: int,
    after_time: time,
    before_time: time,
) -> bool:
    """Check if TX futures price touched or breached the given strike level."""
    row = conn.execute(
        """
        SELECT 1 FROM ohlcv_1m
        WHERE symbol = 'TX'
          AND CAST(timestamp AS DATE) = ?
          AND CAST(timestamp AS TIME) BETWEEN ? AND ?
          AND (low <= ? AND high >= ?)
        LIMIT 1
        """,
        [trade_date, after_time, before_time, strike, strike],
    ).fetchone()
    return row is not None


def run_backtest(
    start: str = "2026-01-01",
    end: str = "2026-12-31",
    fraction: float = 0.70,
    spread_pct: float = 0.50,
    exit_time_str: str = "12:30",
    skip_wed: bool = True,
) -> pd.DataFrame:
    exit_time = time(int(exit_time_str.split(":")[0]), int(exit_time_str.split(":")[1]))
    entry_start = time(9, 30)

    # Load 1-min data with EstRange
    print("Loading 1-min data and computing EstRange...")
    df = load_1m_data()
    print(f"  Total bars: {len(df):,}")

    # Get unique trading dates in range
    dates = sorted(df.index.normalize().unique())
    dates = [d for d in dates if pd.Timestamp(start) <= d <= pd.Timestamp(end)]
    print(f"  Trading days in range: {len(dates)}")

    trades = []

    with duckdb.connect(DB_PATH, read_only=True) as conn:
        for dt in dates:
            td = dt.date()
            weekday = td.weekday()  # 0=Mon, 2=Wed

            # Skip Wednesday
            if skip_wed and weekday == 2:
                continue

            # Get day's 1-min bars
            day_mask = df.index.normalize() == dt
            day_df = df[day_mask]

            # Get EstRange at 09:30 (first bar with valid EstRange at or after 09:30)
            bars_930 = day_df[day_df.index.time >= entry_start]
            if bars_930.empty:
                continue
            est_range = bars_930["EstRange"].dropna()
            if est_range.empty:
                continue
            er = float(est_range.iloc[0])
            if er <= 0 or np.isnan(er):
                continue

            # Session extremes up to 09:30
            bars_pre = day_df[day_df.index.time < entry_start]
            if bars_pre.empty:
                continue
            session_high = float(bars_pre["High"].max())
            session_low = float(bars_pre["Low"].min())

            # Compute levels
            est_high = session_low + er * fraction
            est_low = session_high - er * fraction

            # Scan bars from 09:30 to exit_time for first touch
            scan_bars = day_df[
                (day_df.index.time >= entry_start) & (day_df.index.time <= exit_time)
            ]

            touched_side = None
            touch_time = None
            for idx, row in scan_bars.iterrows():
                h, l = float(row["High"]), float(row["Low"])
                if h >= est_high and touched_side is None:
                    touched_side = "high"
                    touch_time = idx.time()
                    break
                if l <= est_low and touched_side is None:
                    touched_side = "low"
                    touch_time = idx.time()
                    break

            if touched_side is None:
                continue

            # Determine trade
            contract = get_monthly_contract(td)
            spread_width = max(round_to_100(er * spread_pct), 100)

            if touched_side == "high":
                # Sell Put Spread: sell put at est_low strike, buy put spread_width below
                sell_strike = round_to_100(est_low)
                buy_strike = sell_strike - spread_width
                put_call = "P"
                side = "Sell Put Spread"
            else:
                # Sell Call Spread: sell call at est_high strike, buy call spread_width above
                sell_strike = round_to_100(est_high)
                buy_strike = sell_strike + spread_width
                put_call = "C"
                side = "Sell Call Spread"

            # Look up actual premiums (within 5 min after touch)
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
                # Try wider time window (15 min)
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
            if credit <= 0:
                continue

            max_loss = spread_width - credit

            # Check if sell_strike is touched between touch_time and exit_time
            struck = check_strike_touched(conn, td, sell_strike, touch_time, exit_time)

            if struck:
                # Check exit price at exit_time for partial loss assessment
                # Conservative: assume full loss
                pnl = -max_loss
                result = "Loss"
            else:
                pnl = credit
                result = "Win"

            trades.append({
                "date": td,
                "weekday": ["Mon", "Tue", "Wed", "Thu", "Fri"][weekday],
                "side": side,
                "est_range": round(er, 1),
                "est_high": round(est_high, 1),
                "est_low": round(est_low, 1),
                "sell_strike": sell_strike,
                "buy_strike": buy_strike,
                "contract": contract,
                "touch_time": touch_time.strftime("%H:%M"),
                "sell_premium": sell_premium,
                "buy_premium": buy_premium,
                "credit": round(credit, 1),
                "spread_width": spread_width,
                "max_loss": round(max_loss, 1),
                "pnl": round(pnl, 1),
                "result": result,
                "cr_pct": round(credit / spread_width * 100, 1),
            })

    return pd.DataFrame(trades)


def print_summary(df_trades: pd.DataFrame) -> None:
    if df_trades.empty:
        print("No trades.")
        return

    n = len(df_trades)
    wins = df_trades[df_trades["result"] == "Win"]
    losses = df_trades[df_trades["result"] == "Loss"]
    total_pnl = df_trades["pnl"].sum()
    win_sum = wins["pnl"].sum()
    loss_sum = abs(losses["pnl"].sum())
    pf = win_sum / loss_sum if loss_sum > 0 else float("inf")

    # Max consecutive losses
    max_consec = cur = 0
    for r in df_trades["result"]:
        cur = cur + 1 if r == "Loss" else 0
        max_consec = max(max_consec, cur)

    print(f"\n{'='*60}")
    print(f"  EstRange Credit Spread Backtest")
    print(f"{'='*60}")
    print(f"  期間          {df_trades['date'].min()} ~ {df_trades['date'].max()}")
    print(f"  筆數          {n}")
    print(f"  勝率          {len(wins)/n*100:.1f}% ({len(wins)}/{n})")
    print(f"  PF            {pf:.2f}")
    print(f"  Total PnL     {total_pnl:+,.1f} pts (NT${total_pnl*50:+,.0f})")
    print(f"  Avg/trade     {df_trades['pnl'].mean():+.1f} pts")
    print(f"  Avg Credit    {df_trades['credit'].mean():.1f} pts (CR% {df_trades['cr_pct'].mean():.1f}%)")
    print(f"  Max consec L  {max_consec}")
    print(f"{'='*60}")

    # By month
    df_trades["month"] = df_trades["date"].apply(lambda d: d.strftime("%Y-%m"))
    monthly = df_trades.groupby("month").agg(
        n=("pnl", "count"),
        wins=("result", lambda x: (x == "Win").sum()),
        pnl=("pnl", "sum"),
    )
    monthly["wr"] = (monthly["wins"] / monthly["n"] * 100).round(1)
    print(f"\n{'--- By Month ---':^60}")
    print(f"  {'Month':<10} {'n':>4} {'Win':>4} {'WR%':>6} {'PnL':>10} {'NT$':>12}")
    for m, row in monthly.iterrows():
        print(
            f"  {m:<10} {row['n']:>4} {row['wins']:>4} "
            f"{row['wr']:>5.1f}% {row['pnl']:>+10.1f} {row['pnl']*50:>+12,.0f}"
        )

    # By weekday
    print(f"\n{'--- By Weekday ---':^60}")
    print(f"  {'Day':<5} {'n':>4} {'WR%':>6} {'PnL':>10}")
    for day in ["Mon", "Tue", "Thu", "Fri"]:
        sub = df_trades[df_trades["weekday"] == day]
        if sub.empty:
            continue
        wr = (sub["result"] == "Win").sum() / len(sub) * 100
        print(f"  {day:<5} {len(sub):>4} {wr:>5.1f}% {sub['pnl'].sum():>+10.1f}")

    # By side
    print(f"\n{'--- By Side ---':^60}")
    print(f"  {'Side':<20} {'n':>4} {'WR%':>6} {'PnL':>10}")
    for side in ["Sell Put Spread", "Sell Call Spread"]:
        sub = df_trades[df_trades["side"] == side]
        if sub.empty:
            continue
        wr = (sub["result"] == "Win").sum() / len(sub) * 100
        print(f"  {side:<20} {len(sub):>4} {wr:>5.1f}% {sub['pnl'].sum():>+10.1f}")


def main():
    parser = argparse.ArgumentParser(description="EstRange Credit Spread Options Backtest")
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument("--end", default="2026-03-18")
    parser.add_argument("--fraction", type=float, default=0.70)
    parser.add_argument("--spread-pct", type=float, default=0.50)
    parser.add_argument("--exit-time", default="12:30")
    parser.add_argument("--no-skip-wed", action="store_true")
    parser.add_argument("--output", default=None, help="Save trades CSV")
    args = parser.parse_args()

    df_trades = run_backtest(
        start=args.start,
        end=args.end,
        fraction=args.fraction,
        spread_pct=args.spread_pct,
        exit_time_str=args.exit_time,
        skip_wed=not args.no_skip_wed,
    )

    print_summary(df_trades)

    if args.output:
        df_trades.to_csv(args.output, index=False)
        print(f"\nTrades saved → {args.output}")
    elif not df_trades.empty:
        out = f"output/estrange_options_{args.start}_{args.end}.csv"
        df_trades.to_csv(out, index=False)
        print(f"\nTrades saved → {out}")


if __name__ == "__main__":
    main()
