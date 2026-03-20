"""
EstRange Credit Spread Options Backtest

Strategy (from specs/strategies/2026-03-17-estrange-options.md):
  - At 09:30, compute EstRange; Est High = session_low + ER*fraction,
    Est Low = session_high - ER*fraction
  - 09:30~exit_time: first touch of Est High → sell Put Spread (strike near Est Low),
    first touch of Est Low → sell Call Spread (strike near Est High)
  - Spread width = ER * spread_pct, rounded to nearest 100, min 100
  - Skip settlement Wednesdays
  - Select nearest-expiring contract (most liquid)
  - Max 1 trade per day
  - Loss = strike touched before exit → lose (spread_width - credit)
  - Win = exit without touching sell strike → keep full credit
"""

import argparse
import math
import re
from datetime import date, time, timedelta

import duckdb
import numpy as np
import pandas as pd

from src.backtest.estimate_hl import compute_vol_estimated_range

DB_PATH = "data/futures.duckdb"


def round_to_100(x: float) -> int:
    return int(round(x / 100.0)) * 100


def get_expiry_date(contract: str) -> date | None:
    """Calculate expiry date for a TXO contract.

    Monthly YYYYMM   → 3rd Wednesday
    Weekly  YYYYMMWn  → nth Wednesday of that month
    Friday  YYYYMMFn  → nth Friday of that month
    """
    m = re.match(r"^(\d{4})(\d{2})(?:(W|F)(\d))?$", contract)
    if not m:
        return None
    y, mo = int(m.group(1)), int(m.group(2))
    typ = m.group(3)  # None, 'W', or 'F'
    num = int(m.group(4)) if m.group(4) else 3  # monthly = 3rd Wed

    first_day = date(y, mo, 1)
    if typ == "F":
        # nth Friday (weekday=4)
        first_fri = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
        return first_fri + timedelta(weeks=num - 1)
    else:
        # Wednesday (monthly=3rd, Wn=nth)
        first_wed = first_day + timedelta(days=(2 - first_day.weekday()) % 7)
        if typ is None:
            return first_wed + timedelta(weeks=2)  # 3rd Wednesday
        else:
            return first_wed + timedelta(weeks=num - 1)


def get_monthly_contract(trade_date: date) -> str:
    """Return the monthly contract code for the given trade date."""
    y, m = trade_date.year, trade_date.month
    first_day = date(y, m, 1)
    first_wed = first_day + timedelta(days=(2 - first_day.weekday()) % 7)
    third_wed = first_wed + timedelta(weeks=2)
    if trade_date > third_wed:
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return f"{y:04d}{m:02d}"


def preload_daily_contracts(
    conn: duckdb.DuckDBPyConnection, start: str, end: str
) -> dict[date, list[tuple[str, int, date | None]]]:
    """Pre-load (contract, volume, expiry) per trading day.

    Returns {trade_date: [(contract, volume, expiry_date), ...] sorted by volume DESC}.
    """
    df = conn.execute(
        """
        SELECT trade_date, contract, SUM(volume) AS vol
        FROM ticks_options
        WHERE symbol = 'TXO'
          AND trade_date BETWEEN ? AND ?
        GROUP BY trade_date, contract
        """,
        [start, end],
    ).df()

    result: dict[date, list[tuple[str, int, date | None]]] = {}
    for td, grp in df.groupby("trade_date"):
        td_date = td.date() if hasattr(td, "date") else td
        rows = []
        for _, r in grp.iterrows():
            contract = r["contract"]
            vol = int(r["vol"])
            exp = get_expiry_date(contract)
            rows.append((contract, vol, exp))
        rows.sort(key=lambda x: x[1], reverse=True)  # volume DESC
        result[td_date] = rows
    return result


def select_contract(
    trade_date: date,
    daily_contracts: dict[date, list[tuple[str, int, date | None]]],
    monthly_only: bool = False,
    min_dte: int = 2,
    max_dte: int | None = None,
    w_only: bool = False,
    f_only: bool = False,
) -> tuple[str | None, str | None]:
    """Select contract for a trading day.

    Returns (selected_contract, reason) where reason describes the selection.
    If monthly_only, falls back to the old get_monthly_contract logic.
    min_dte: minimum days to expiry (default 2, skips DTE=0/1).
    max_dte: maximum days to expiry (default None = no limit).
    w_only: only pick W (Wednesday expiry) or Monthly contracts, skip F contracts.
    f_only: only pick F (Friday expiry) contracts.
    """
    if monthly_only:
        return get_monthly_contract(trade_date), "monthly"

    candidates = daily_contracts.get(trade_date, [])
    if not candidates:
        return None, "no_data"

    # Filter: must have min_dte <= DTE <= max_dte
    valid = []
    for c, vol, exp in candidates:
        if exp is None:
            continue
        if w_only and "F" in c:
            continue
        if f_only and "F" not in c:
            continue
        dte = (exp - trade_date).days
        if dte >= min_dte and (max_dte is None or dte <= max_dte):
            valid.append((c, vol, exp, dte))
    if not valid:
        return None, "no_valid_expiry"

    # Pick nearest expiry
    valid.sort(key=lambda x: x[2])  # sort by expiry_date ASC
    nearest = valid[0]
    return nearest[0], f"exp={nearest[2]}_dte={nearest[3]}"


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
    direction: str,
    after_time: time,
    before_time: time,
) -> time | None:
    """Check if TX futures price touched or breached the given strike level.

    Parameters
    ----------
    direction : str
        "down" for sell put (price drops to strike → low <= strike),
        "up" for sell call (price rises to strike → high >= strike).

    Returns the time of the first 1-min bar where the strike was breached,
    or None if never breached.
    """
    if direction == "down":
        condition = "low <= ?"
    else:
        condition = "high >= ?"
    row = conn.execute(
        f"""
        SELECT CAST(timestamp AS TIME) FROM ohlcv_1m
        WHERE symbol = 'TX'
          AND CAST(timestamp AS DATE) = ?
          AND CAST(timestamp AS TIME) BETWEEN ? AND ?
          AND ({condition})
        ORDER BY timestamp
        LIMIT 1
        """,
        [trade_date, after_time, before_time, strike],
    ).fetchone()
    return row[0] if row else None


def _third_wednesday(y: int, m: int) -> date:
    """Return the 3rd Wednesday of the given year/month."""
    first_day = date(y, m, 1)
    first_wed = first_day + timedelta(days=(2 - first_day.weekday()) % 7)
    return first_wed + timedelta(weeks=2)


def run_backtest(
    start: str = "2026-01-01",
    end: str = "2026-12-31",
    fraction: float = 0.70,
    spread_pct: float = 0.50,
    exit_time_str: str = "12:30",
    skip_wed: bool = False,
    skip_settlement: bool = True,
    max_spread: int | None = None,
    min_gap: int = 50,
    monthly_only: bool = False,
    min_dte: int = 2,
    max_dte: int | None = None,
    w_only: bool = False,
    f_only: bool = False,
    weekdays: list[str] | None = None,
    min_credit: float = 0,
    min_hold: int = 0,
    no_sl: bool = False,
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

    # Pre-compute settlement dates
    settlement_dates: set[date] = set()
    if skip_settlement:
        for y in range(int(start[:4]), int(end[:4]) + 1):
            for m in range(1, 13):
                settlement_dates.add(_third_wednesday(y, m))

    trades = []

    with duckdb.connect(DB_PATH, read_only=True) as conn:
        # Pre-load contract volumes per day
        print("  Pre-loading contract data...")
        daily_contracts = preload_daily_contracts(conn, start, end)

        for dt in dates:
            td = dt.date()
            weekday = td.weekday()  # 0=Mon, 2=Wed

            # Filter by weekday
            weekday_name = ["Mon", "Tue", "Wed", "Thu", "Fri"][weekday]
            if weekdays and weekday_name not in weekdays:
                continue

            # Skip Wednesday
            if skip_wed and weekday == 2:
                continue

            # Skip settlement day (3rd Wednesday)
            if skip_settlement and td in settlement_dates:
                continue

            # Get day's 1-min bars
            day_mask = df.index.normalize() == dt
            day_df = df[day_mask]

            # Build running session high/low and EstRange from all bars
            # (dynamically updated, matching TradingView behavior)
            session_high = -np.inf
            session_low = np.inf
            er = np.nan

            # Update session extremes from all bars up to entry_start
            for idx, row in day_df.iterrows():
                if idx.time() >= entry_start:
                    break
                session_high = max(session_high, float(row["High"]))
                session_low = min(session_low, float(row["Low"]))

            if session_high == -np.inf:
                continue

            # Scan bars from 09:30 to exit_time, dynamically updating levels
            scan_bars = day_df[
                (day_df.index.time >= entry_start) & (day_df.index.time <= exit_time)
            ]

            touched_side = None
            touch_time = None
            touch_er = np.nan
            touch_est_high = np.nan
            touch_est_low = np.nan

            for idx, row in scan_bars.iterrows():
                h, l = float(row["High"]), float(row["Low"])

                # Update session extremes BEFORE computing levels
                # (matches TradingView: sess_high/low updated first, then est levels)
                session_high = max(session_high, h)
                session_low = min(session_low, l)

                # Update EstRange (use latest available)
                bar_er = row.get("EstRange")
                if pd.notna(bar_er) and bar_er > 0:
                    er = float(bar_er)

                if np.isnan(er):
                    continue

                # Compute dynamic levels with current session extremes
                est_high = session_low + er * fraction
                est_low = session_high - er * fraction

                if h >= est_high:
                    touched_side = "high"
                    touch_time = idx.time()
                    touch_er = er
                    touch_est_high = est_high
                    touch_est_low = est_low
                    break
                if l <= est_low:
                    touched_side = "low"
                    touch_time = idx.time()
                    touch_er = er
                    touch_est_high = est_high
                    touch_est_low = est_low
                    break

            if touched_side is None:
                continue

            # Min holding time filter
            if min_hold > 0:
                from datetime import datetime as _dt
                hold_minutes = (_dt.combine(td, exit_time) - _dt.combine(td, touch_time)).total_seconds() / 60
                if hold_minutes < min_hold:
                    continue

            er = touch_er
            est_high = touch_est_high
            est_low = touch_est_low

            # Skip if Est High and Est Low are too close (large session range)
            if est_high - est_low < min_gap:
                continue

            # Determine trade
            contract, contract_reason = select_contract(td, daily_contracts, monthly_only, min_dte, max_dte, w_only, f_only)
            if contract is None:
                continue
            spread_width = max(round_to_100(er * spread_pct), 100)
            if max_spread is not None:
                spread_width = min(spread_width, max_spread)

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
            if credit <= 0 or credit < min_credit:
                continue

            max_loss = spread_width - credit

            # Check if sell_strike is touched between touch_time and exit_time
            # Sell put → price drops to strike ("down"); Sell call → price rises to strike ("up")
            sl_direction = "down" if touched_side == "high" else "up"
            struck_time = check_strike_touched(conn, td, sell_strike, sl_direction, touch_time, exit_time)

            if struck_time and not no_sl:
                # Stop-loss: close spread at actual option prices when strike touched
                close_time = struck_time
                result = "Loss"
            else:
                # No stop-loss triggered (or disabled): close at exit_time
                close_time = exit_time
                result = "Win" if not struck_time else "Win(SL-skip)"

            # Close spread at actual option prices
            close_window_end = time(
                min(close_time.hour + (close_time.minute + 5) // 60, 13),
                (close_time.minute + 5) % 60,
            )
            close_sell = lookup_option_price(
                conn, td, contract, sell_strike, put_call, close_time, close_window_end,
            )
            close_buy = lookup_option_price(
                conn, td, contract, buy_strike, put_call, close_time, close_window_end,
            )
            if close_sell is not None and close_buy is not None:
                close_debit = close_sell - close_buy
                pnl = credit - close_debit
            elif result == "Loss":
                pnl = -max_loss
            else:
                # Win but no exit prices: use last known prices before exit
                close_sell2 = lookup_price_at_time(
                    conn, td, contract, sell_strike, put_call, close_time,
                )
                close_buy2 = lookup_price_at_time(
                    conn, td, contract, buy_strike, put_call, close_time,
                )
                if close_sell2 is not None and close_buy2 is not None:
                    close_debit = close_sell2 - close_buy2
                    pnl = credit - close_debit
                else:
                    pnl = credit  # fallback: no exit prices available

            exit_at = close_time.strftime("%H:%M")

            trades.append({
                "date": td,
                "weekday": weekday_name,
                "side": side,
                "est_range": round(er, 1),
                "est_high": round(est_high, 1),
                "est_low": round(est_low, 1),
                "sell_strike": sell_strike,
                "buy_strike": buy_strike,
                "contract": contract,
                "touch_time": touch_time.strftime("%H:%M"),
                "exit_time": exit_at,
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
    for day in ["Mon", "Tue", "Wed", "Thu", "Fri"]:
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
    parser.add_argument("--skip-wed", action="store_true", help="Skip all Wednesdays")
    parser.add_argument("--no-skip-settlement", action="store_true", help="Include settlement days")
    parser.add_argument("--max-spread", type=int, default=None, help="Max spread width (pts)")
    parser.add_argument("--min-gap", type=int, default=50, help="Min est_high - est_low gap (pts, default 50)")
    parser.add_argument("--monthly-only", action="store_true", help="Use monthly contracts only (old behavior)")
    parser.add_argument("--min-dte", type=int, default=2, help="Minimum days to expiry (default 2)")
    parser.add_argument("--max-dte", type=int, default=None, help="Maximum days to expiry (default: no limit)")
    parser.add_argument("--w-only", action="store_true", help="Only use W (Wednesday) contracts, skip F (Friday)")
    parser.add_argument("--f-only", action="store_true", help="Only use F (Friday) contracts, skip W (Wednesday)")
    parser.add_argument("--weekdays", default=None, help="Only trade on specified weekdays (e.g. Mon,Tue,Fri)")
    parser.add_argument("--min-credit", type=float, default=0, help="Minimum credit to enter trade (pts, default 0)")
    parser.add_argument("--min-hold", type=int, default=0, help="Minimum holding time in minutes (skip if touch too close to exit)")
    parser.add_argument("--no-sl", action="store_true", help="Disable stop-loss (hold to exit_time regardless)")
    parser.add_argument("--output", default=None, help="Save trades CSV")
    args = parser.parse_args()

    weekday_filter = [w.strip() for w in args.weekdays.split(",")] if args.weekdays else None

    df_trades = run_backtest(
        start=args.start,
        end=args.end,
        fraction=args.fraction,
        spread_pct=args.spread_pct,
        exit_time_str=args.exit_time,
        skip_wed=args.skip_wed,
        skip_settlement=not args.no_skip_settlement,
        max_spread=args.max_spread,
        min_gap=args.min_gap,
        monthly_only=args.monthly_only,
        min_dte=args.min_dte,
        max_dte=args.max_dte,
        w_only=args.w_only,
        f_only=args.f_only,
        weekdays=weekday_filter,
        min_credit=args.min_credit,
        min_hold=args.min_hold,
        no_sl=args.no_sl,
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
