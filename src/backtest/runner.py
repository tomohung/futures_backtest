import argparse
from pathlib import Path

import duckdb
import numpy as np
from backtesting import Backtest

from src.strategies.orb import ORBStrategy

DB_PATH = "data/futures.duckdb"
OUTPUT_DIR = Path("output")


def build_output_path(start, end, params: dict) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    date_part = start or "all"
    if end:
        date_part += f"_{end}"
    param_part = (
        f"re{params['range_end_minute']}"
        f"_ee{params['entry_end_minute']}"
        f"_sl{int(params['sl_pct']*1000)}"
        f"_tp{params['tp_multiplier']}"
        f"_ta{params['trail_activate_minute']}"
    )
    return OUTPUT_DIR / f"orb_{param_part}_{date_part}.csv"


def print_summary(stats):
    trades = stats["_trades"].copy()
    if trades.empty:
        print("沒有交易記錄")
        return

    pnl = trades["PnL"]
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    # Max consecutive losses
    max_consec = cur = 0
    for v in (pnl <= 0).tolist():
        cur = cur + 1 if v else 0
        max_consec = max(max_consec, cur)

    # Max drawdown from equity curve
    eq = stats["_equity_curve"]["Equity"]
    max_dd_pct = (eq / eq.cummax() - 1).min() * 100

    rows = [
        ("總交易次數",           f"{len(trades)} 筆"),
        ("做多次數",             f"{(trades['Size'] > 0).sum()} 筆"),
        ("做空次數",             f"{(trades['Size'] < 0).sum()} 筆"),
        ("勝率",                f"{len(wins)/len(trades)*100:.1f}%"),
        ("平均獲利",             f"+{wins.mean():.0f} 點  (NT${wins.mean()*200:,.0f})" if len(wins) else "—"),
        ("平均虧損",             f"{losses.mean():.0f} 點  (NT${losses.mean()*200:,.0f})" if len(losses) else "—"),
        ("獲利因子 (PF)",        f"{wins.sum() / abs(losses.sum()):.2f}" if len(losses) else "∞"),
        ("最大連續虧損次數",      f"{max_consec} 筆"),
        ("最大回撤",             f"{max_dd_pct:.2f}%"),
        ("期望值 (每筆平均損益)", f"{pnl.mean():.1f} 點  (NT${pnl.mean()*200:,.0f})"),
    ]

    col_w = max(len(r[0]) for r in rows)
    print()
    print("=" * 42)
    for label, value in rows:
        print(f"  {label:<{col_w}}  {value}")
    print("=" * 42)


def load_data(start=None, end=None):
    import pandas as pd

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

    if start:
        df = df[df.index >= start]
    if end:
        df = df[df.index <= end]

    return df


def _wilder_smooth(arr: "np.ndarray", period: int) -> "np.ndarray":
    import numpy as np
    out = np.full(len(arr), np.nan)
    for i in range(period - 1, len(arr)):
        window = arr[i - period + 1: i + 1]
        if not np.any(np.isnan(window)):
            out[i] = window.mean()
            break
    start_idx = 0
    for i, v in enumerate(out):
        if not np.isnan(v):
            start_idx = i
            break
    for i in range(start_idx + 1, len(arr)):
        if not np.isnan(arr[i]) and not np.isnan(out[i - 1]):
            out[i] = out[i - 1] * (period - 1) / period + arr[i] / period
    return out


def _compute_daily_adx(df_day: "pd.DataFrame", period: int = 14) -> "pd.Series":
    """Compute ADX(period) on daily OHLCV and return a Series indexed by trade_date."""
    import numpy as np
    import pandas as pd

    high  = df_day["High"].values
    low   = df_day["Low"].values
    close = df_day["Close"].values
    n = len(df_day)

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

    atr_s = _wilder_smooth(tr,   period)
    dmp_s = _wilder_smooth(dm_p, period)
    dmm_s = _wilder_smooth(dm_m, period)
    di_p  = 100 * dmp_s / (atr_s + 1e-10)
    di_m  = 100 * dmm_s / (atr_s + 1e-10)
    dx    = 100 * np.abs(di_p - di_m) / (di_p + di_m + 1e-10)
    adx   = _wilder_smooth(dx, period)
    return pd.Series(adx, index=df_day.index)


def load_data_with_night_ma(start=None, end=None, trend_ma_days=10, rolling_or_window=0,
                             adx_period=0, estimate_hl=False):
    """Load day-session OHLCV with TrendMA computed on continuous day+night 1-min bars.

    The MA is computed on the full price series (including night session) so that
    overnight price action is reflected. The returned DataFrame contains a 'TrendMA'
    column aligned to day-session timestamps; ORBStrategy will use it automatically.

    rolling_or_window : int
        If > 0, also compute a N-day rolling average of the OR width (08:45~09:30)
        and add it as a 'RollingOR' column. Used by the regime filter in Phase 5.
    """
    import pandas as pd

    with duckdb.connect(DB_PATH, read_only=True) as conn:
        # All bars (day + night) for MA computation — no date filter, need full warmup
        df_all = conn.execute("""
            SELECT timestamp, close FROM ohlcv_1m
            WHERE symbol = 'TX'
            ORDER BY timestamp
        """).df().set_index("timestamp")

        # Day session only for backtesting
        df_day = conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ORDER BY timestamp
        """).df().set_index("timestamp")

        if rolling_or_window > 0:
            df_or = conn.execute("""
                SELECT CAST(timestamp AS DATE) as trade_date,
                       MAX(high) - MIN(low)   as or_width
                FROM ohlcv_1m
                WHERE symbol = 'TX'
                  AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '09:30:00'
                GROUP BY 1
                ORDER BY 1
            """).df()

    df_day.columns = ["Open", "High", "Low", "Close", "Volume"]

    # Rolling MA on continuous series, then align to day-session index
    n_bars = trend_ma_days * 301
    ma = df_all["close"].rolling(n_bars, min_periods=n_bars).mean()
    df_day["TrendMA"] = ma.reindex(df_day.index)

    # Rolling OR average (regime filter)
    if rolling_or_window > 0:
        df_or["trade_date"] = pd.to_datetime(df_or["trade_date"])
        df_or = df_or.set_index("trade_date")
        df_or["rolling_or"] = df_or["or_width"].rolling(rolling_or_window,
                                                         min_periods=rolling_or_window).mean()
        day_dates = pd.DatetimeIndex(df_day.index).normalize()
        df_day["RollingOR"] = df_or["rolling_or"].reindex(day_dates).values

    # Daily ADX filter (for long-only strategy)
    if adx_period > 0:
        # Synthesise daily OHLCV from day-session 1-min bars
        df_daily = df_day.groupby(df_day.index.normalize()).agg(
            Open=("Open",  "first"),
            High=("High",  "max"),
            Low=("Low",    "min"),
            Close=("Close","last"),
        )
        adx_series = _compute_daily_adx(df_daily, period=adx_period)
        day_dates = pd.DatetimeIndex(df_day.index).normalize()
        df_day["DailyADX"] = adx_series.reindex(day_dates).values

    # Estimated H-L zones (must run on full history BEFORE date filtering)
    if estimate_hl:
        from src.backtest.estimate_hl import compute_estimate_hl_zones
        df_day = compute_estimate_hl_zones(df_day)

    if start:
        df_day = df_day[df_day.index >= start]
    if end:
        df_day = df_day[df_day.index <= end]

    return df_day


def load_data_for_orb_est_hl(start=None, end=None):
    """Load day-session data with Estimate H-L zones, 30m 20MA, and BigCost columns.

    Columns added:
        EmaHL, SatZoneUpper, SatZoneLower, EstHL, EstHighLevel, EstLowLevel, EmaVol
            — from compute_estimate_hl_zones()
        MA30_20  — 20-period MA of 30m closes (continuous day+night), 1-slot delayed
        Close30  — last 30m close, 1-slot delayed (for direction comparison)
        BigCost  — yesterday's institutional cost (heavy-volume VWAP)
    """
    import pandas as pd

    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df_all = conn.execute("""
            SELECT timestamp, close FROM ohlcv_1m
            WHERE symbol = 'TX'
            ORDER BY timestamp
        """).df().set_index("timestamp")

        df_day = conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ORDER BY timestamp
        """).df().set_index("timestamp")

        df_bigcost = conn.execute("""
            WITH vol_ma AS (
                SELECT timestamp::DATE AS date, timestamp, close, volume,
                       AVG(volume) OVER (
                           PARTITION BY timestamp::DATE
                           ORDER BY timestamp
                           ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                       ) AS vol_20ma
                FROM ohlcv_1m
                WHERE symbol = 'TX'
                  AND timestamp::TIME BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ),
            filtered AS (
                SELECT date, close, volume FROM vol_ma WHERE volume >= vol_20ma
            )
            SELECT date, ROUND(SUM(close * volume) / SUM(volume))::INT AS big_cost
            FROM filtered GROUP BY date ORDER BY date
        """).df()

    df_day.columns = ["Open", "High", "Low", "Close", "Volume"]

    # Estimate H-L zones (must run on full history before date filtering)
    from src.backtest.estimate_hl import compute_estimate_hl_zones
    df_day = compute_estimate_hl_zones(df_day)

    # 30m 20MA from continuous series (day + night)
    # Default 30min grid: 8:00, 8:30, 9:00, ... so 8:30–8:59 bar labeled 8:30
    s30 = df_all["close"].resample("30min").last()
    ma30_20 = s30.rolling(20, min_periods=20).mean()
    # shift(1): value at label T reflects the closed bar ending at T-30min (no lookahead)
    ma30_20_shifted = ma30_20.shift(1)
    close30_shifted = s30.shift(1)
    df_day["MA30_20"] = ma30_20_shifted.reindex(df_day.index, method="ffill")
    df_day["Close30"] = close30_shifted.reindex(df_day.index, method="ffill")

    # Gap: today's first bar open minus yesterday's day-session last close
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df_gap = conn.execute("""
            SELECT
                timestamp::DATE AS date,
                FIRST(open ORDER BY timestamp) AS day_open,
                LAST(close  ORDER BY timestamp) AS day_close
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            GROUP BY 1 ORDER BY 1
        """).df()
    df_gap["date"] = pd.to_datetime(df_gap["date"])
    df_gap = df_gap.set_index("date")
    df_gap["GapSize"] = df_gap["day_open"] - df_gap["day_close"].shift(1)
    day_dates = pd.DatetimeIndex(df_day.index).normalize()
    df_day["GapSize"] = df_gap["GapSize"].reindex(day_dates).values

    # Night session direction: prev-day close vs prev-day night open (15:00 bar)
    # night_return > 0 → overnight bullish; < 0 → bearish
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df_night = conn.execute("""
            SELECT
                timestamp::DATE AS date,
                FIRST(close ORDER BY timestamp) AS night_open,
                LAST(close  ORDER BY timestamp) AS night_close
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME >= TIME '15:00:00'
            GROUP BY 1 ORDER BY 1
        """).df()
    df_night["date"] = pd.to_datetime(df_night["date"])
    df_night = df_night.set_index("date")
    # night_return for date D = close of night session that STARTS on D
    # available the NEXT trading day (shift 1)
    df_night["NightReturn"] = (df_night["night_close"] - df_night["night_open"]).shift(1)
    day_dates = pd.DatetimeIndex(df_day.index).normalize()
    df_day["NightReturn"] = df_night["NightReturn"].reindex(day_dates).values

    # OR width (8:45–8:57) and 20-day rolling average
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df_or = conn.execute("""
            SELECT timestamp::DATE AS date,
                   MAX(high) - MIN(low) AS or_width
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME BETWEEN TIME '08:45:00' AND TIME '08:57:00'
            GROUP BY 1 ORDER BY 1
        """).df()
    df_or["date"] = pd.to_datetime(df_or["date"])
    df_or = df_or.set_index("date")
    df_or["RollingOR"] = df_or["or_width"].rolling(20, min_periods=20).mean()
    day_dates = pd.DatetimeIndex(df_day.index).normalize()
    df_day["ORWidth"]   = df_or["or_width"].reindex(day_dates).values
    df_day["RollingOR"] = df_or["RollingOR"].reindex(day_dates).values

    # Daily ADX(14) — synthesise daily OHLCV from day-session bars
    df_daily = df_day.groupby(df_day.index.normalize()).agg(
        Open=("Open", "first"), High=("High", "max"),
        Low=("Low", "min"),   Close=("Close", "last"),
    )
    adx_series = _compute_daily_adx(df_daily, period=14)
    day_dates = pd.DatetimeIndex(df_day.index).normalize()
    df_day["DailyADX"] = adx_series.reindex(day_dates).values

    # BigCost: yesterday (shift 1) and day-before-yesterday (shift 2)
    df_bigcost["date"] = pd.to_datetime(df_bigcost["date"])
    df_bigcost = df_bigcost.set_index("date")
    for i in range(1, 6):
        df_bigcost[f"BigCost{i}"] = df_bigcost["big_cost"].shift(i)
    day_dates = pd.DatetimeIndex(df_day.index).normalize()
    for i in range(1, 6):
        df_day[f"BigCost{i}"] = df_bigcost[f"BigCost{i}"].reindex(day_dates).values

    if start:
        df_day = df_day[df_day.index >= start]
    if end:
        df_day = df_day[df_day.index <= end]

    return df_day


def main():
    parser = argparse.ArgumentParser(
        description="Run ORB backtest on TX futures",
        epilog=(
            "Examples:\n"
            "  uv run python src/backtest/runner.py --start 2025-01-01\n"
            "  uv run python src/backtest/runner.py --start 2025-06-01 --end 2025-06-30 --resample 1min\n"
            "  uv run python src/backtest/runner.py --start 2025-01-01 --entry-end 90"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Date range
    parser.add_argument("--start", default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--end",   default=None, metavar="YYYY-MM-DD")
    # Strategy parameters
    parser.add_argument("--range-end",    type=int,   default=60,   metavar="MIN",
                        help="Opening range end (minutes from 08:00, default 60=09:00)")
    parser.add_argument("--entry-end",    type=int,   default=75,   metavar="MIN",
                        help="Entry cutoff (minutes from 08:00, default 75=09:15)")
    parser.add_argument("--sl",           type=float, default=0.005, metavar="PCT",
                        help="Stop-loss %% (default 0.005)")
    parser.add_argument("--tp",           type=float, default=2.0,  metavar="MULT",
                        help="Take-profit multiplier (default 2.0)")
    parser.add_argument("--trail-after",  type=int,   default=45,   metavar="MIN",
                        help="Trailing stop activation (minutes from 09:00, default 45=09:45)")
    # Chart
    parser.add_argument("--resample", default=None, metavar="FREQ",
                        help="Chart candle size (e.g. '1min', '1h', '1D')")
    args = parser.parse_args()

    strategy_params = {
        "range_end_minute":    args.range_end,
        "entry_end_minute":    args.entry_end,
        "sl_pct":              args.sl,
        "tp_multiplier":       args.tp,
        "trail_activate_minute": args.trail_after,
    }

    resample: str | bool | None = args.resample
    if isinstance(resample, str) and resample.lower() == "false":
        resample = False

    print(f"Loading data from {DB_PATH}...")
    df = load_data(start=args.start, end=args.end)
    print(f"Loaded {len(df):,} bars from {df.index[0]} to {df.index[-1]}")

    bt = Backtest(
        df,
        ORBStrategy,
        cash=200_000,
        commission=0.0,
        trade_on_close=True,
    )

    stats = bt.run(**strategy_params)
    print_summary(stats)

    out_path = build_output_path(args.start, args.end, strategy_params)
    stats["_trades"].to_csv(out_path, index=False)
    print(f"Trades saved → {out_path}")

    plot_kwargs = {} if resample is None else {"resample": resample}
    bt.plot(**plot_kwargs)


if __name__ == "__main__":
    main()
