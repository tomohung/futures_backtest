"""
H057 Phase 2 Backtest: Leading Indicator Bottom + Weekly MACD + Monthly KD Exit

策略規則：
- 進場：領先指標 bottom 拐點（N 月確認）+ 週 MACD > Signal（或等金叉）
- 出場：月 KD(9,3,3) 跌破 80
- 方向：僅做多
- 成本：每次換倉 82 點（平均）、進出滑價各 2 點
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import duckdb
from pathlib import Path
from itertools import product

plt.rcParams["font.family"] = ["Arial Unicode MS", "Heiti TC", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

BASE = Path(__file__).parent
OUTPUT = BASE / "results"
OUTPUT.mkdir(exist_ok=True)
DB_PATH = BASE.parent.parent.parent / "data" / "futures.duckdb"

# ── Constants ────────────────────────────────────────────────────────────

SLIPPAGE_PTS = 4          # 進出各 2 tick
ROLLOVER_COST_PTS = 82    # 平均每月換倉成本（點）
POINT_VALUE = 200         # TX 每點 200 TWD
MARGIN_PER_CONTRACT = 230_000  # 台指期保證金（約）


# ══════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════

def load_data():
    conn = duckdb.connect(str(DB_PATH), read_only=True)

    monthly = conn.execute("""
        SELECT
            date_trunc('month', timestamp) as month,
            FIRST(open) as open, MAX(high) as high,
            MIN(low) as low, LAST(close) as close
        FROM ohlcv_1m
        WHERE symbol = 'TX'
            AND EXTRACT(hour FROM timestamp) >= 8
            AND EXTRACT(hour FROM timestamp) < 14
        GROUP BY 1 ORDER BY 1
    """).fetchdf()

    weekly = conn.execute("""
        SELECT
            date_trunc('week', timestamp) as week,
            FIRST(open) as open, MAX(high) as high,
            MIN(low) as low, LAST(close) as close
        FROM ohlcv_1m
        WHERE symbol = 'TX'
            AND EXTRACT(hour FROM timestamp) >= 8
            AND EXTRACT(hour FROM timestamp) < 14
        GROUP BY 1 ORDER BY 1
    """).fetchdf()

    conn.close()

    monthly["month"] = pd.to_datetime(monthly["month"])
    weekly["week"] = pd.to_datetime(weekly["week"])

    li = pd.read_csv(BASE / "data" / "leading_indicator.csv")
    li["date"] = pd.to_datetime(li["date"], format="%Y/%m")
    li["pub_date"] = pd.to_datetime(li["last_working_day"], format="%Y/%m/%d")
    li = li.sort_values("date").reset_index(drop=True)

    return monthly, weekly, li


# ══════════════════════════════════════════════════════════════════════════
# INDICATOR CALCULATION
# ══════════════════════════════════════════════════════════════════════════

def calc_monthly_kd(monthly, k_period=9, smooth_k=3, d_period=3):
    low_min = monthly["low"].rolling(k_period).min()
    high_max = monthly["high"].rolling(k_period).max()
    rsv = (monthly["close"] - low_min) / (high_max - low_min) * 100
    monthly["K"] = rsv.rolling(smooth_k).mean()
    monthly["D"] = monthly["K"].rolling(d_period).mean()
    monthly["above_80"] = monthly["K"] > 80
    monthly["prev_above_80"] = monthly["above_80"].shift(1).fillna(False).astype(bool)
    monthly["kd_exit"] = monthly["prev_above_80"] & (~monthly["above_80"])
    return monthly


def calc_weekly_macd(weekly, fast=12, slow=26, signal_period=9):
    ema_fast = weekly["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = weekly["close"].ewm(span=slow, adjust=False).mean()
    weekly["macd"] = ema_fast - ema_slow
    weekly["signal"] = weekly["macd"].ewm(span=signal_period, adjust=False).mean()
    weekly["macd_bullish"] = weekly["macd"] > weekly["signal"]
    weekly["golden_cross"] = (
        (~weekly["macd_bullish"].shift(1).fillna(False)) & weekly["macd_bullish"]
    )
    return weekly


def calc_leading_indicator(li, n_confirm=1):
    li["direction"] = np.sign(li["leading_index"].diff())
    li["prev_direction"] = li["direction"].shift(1)
    li["is_bottom"] = (li["direction"] > 0) & (li["prev_direction"] < 0)

    bottoms = []
    for idx in range(1, len(li) - n_confirm):
        row = li.iloc[idx]
        if not row["is_bottom"]:
            continue
        persist = True
        for k in range(1, n_confirm + 1):
            if idx + k >= len(li):
                persist = False
                break
            if li.iloc[idx + k]["direction"] != row["direction"]:
                persist = False
                break
        if persist:
            confirm_idx = idx + n_confirm
            if confirm_idx < len(li):
                bottoms.append({
                    "turn_date": row["date"],
                    "signal_date": li.iloc[confirm_idx]["pub_date"],
                })
    return pd.DataFrame(bottoms)


# ══════════════════════════════════════════════════════════════════════════
# STRATEGY SIMULATION
# ══════════════════════════════════════════════════════════════════════════

def simulate(monthly, weekly, li, n_confirm=1, max_wait_weeks=26,
             kd_params=(9, 3, 3), macd_params=(12, 26, 9)):
    """Full strategy simulation with costs."""

    monthly = calc_monthly_kd(monthly.copy(), *kd_params)
    weekly = calc_weekly_macd(weekly.copy(), *macd_params)
    bottoms = calc_leading_indicator(li.copy(), n_confirm)

    kd_exit_months = set(monthly[monthly["kd_exit"]]["month"].values)

    trades = []
    in_position = False
    armed = False
    armed_date = None
    armed_bottom = None
    used_bottoms = set()
    entry_price = entry_date = entry_bottom = entry_reason = None

    for wi in range(len(weekly)):
        wrow = weekly.iloc[wi]
        week_date = wrow["week"]

        # Arm on new bottom signal
        if not in_position and not armed:
            for _, b in bottoms.iterrows():
                if b["turn_date"] in used_bottoms:
                    continue
                if pd.Timestamp(b["signal_date"]) <= week_date:
                    armed = True
                    armed_date = pd.Timestamp(b["signal_date"])
                    armed_bottom = b["turn_date"]
                    used_bottoms.add(b["turn_date"])

                    # Check if MACD already bullish
                    mask = weekly["week"] <= week_date
                    if mask.any() and weekly[mask].iloc[-1]["macd_bullish"]:
                        in_position = True
                        entry_price = wrow["close"]
                        entry_date = week_date
                        entry_bottom = armed_bottom
                        entry_reason = "MACD_BULLISH"
                        armed = False
                    break

        # Wait for golden cross
        if armed and not in_position:
            weeks_waited = (week_date - armed_date).days / 7
            if weeks_waited > max_wait_weeks:
                armed = False
            elif wrow["golden_cross"]:
                in_position = True
                entry_price = wrow["close"]
                entry_date = week_date
                entry_bottom = armed_bottom
                entry_reason = "GOLDEN_CROSS"
                armed = False

        # Exit check
        if in_position:
            week_month = pd.Timestamp(week_date.year, week_date.month, 1)
            if week_month in kd_exit_months:
                next_week = weekly.iloc[wi + 1]["week"] if wi + 1 < len(weekly) else pd.Timestamp("2099-01-01")
                next_month = week_month + pd.DateOffset(months=1)
                if next_week >= next_month or wi == len(weekly) - 1:
                    exit_price = wrow["close"]
                    exit_date = week_date

                    # Cost calculation
                    hold_months = max(1, round((exit_date - entry_date).days / 30))
                    rollover_cost = (hold_months - 1) * ROLLOVER_COST_PTS  # first month no rollover
                    total_cost = SLIPPAGE_PTS + rollover_cost

                    gross_pts = exit_price - entry_price
                    net_pts = gross_pts - total_cost
                    gross_pct = gross_pts / entry_price * 100
                    net_pct = net_pts / entry_price * 100

                    trades.append({
                        "bottom_date": entry_bottom,
                        "entry_date": entry_date,
                        "exit_date": exit_date,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "hold_months": hold_months,
                        "gross_pts": gross_pts,
                        "rollover_cost": rollover_cost,
                        "total_cost": total_cost,
                        "net_pts": net_pts,
                        "gross_pct": gross_pct,
                        "net_pct": net_pct,
                        "entry_reason": entry_reason,
                    })
                    in_position = False

    # Still open
    if in_position:
        last = weekly.iloc[-1]
        exit_price = last["close"]
        exit_date = last["week"]
        hold_months = max(1, round((exit_date - entry_date).days / 30))
        rollover_cost = (hold_months - 1) * ROLLOVER_COST_PTS
        total_cost = SLIPPAGE_PTS + rollover_cost
        gross_pts = exit_price - entry_price
        net_pts = gross_pts - total_cost
        gross_pct = gross_pts / entry_price * 100
        net_pct = net_pts / entry_price * 100

        trades.append({
            "bottom_date": entry_bottom,
            "entry_date": entry_date,
            "exit_date": exit_date,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "hold_months": hold_months,
            "gross_pts": gross_pts,
            "rollover_cost": rollover_cost,
            "total_cost": total_cost,
            "net_pts": net_pts,
            "gross_pct": gross_pct,
            "net_pct": net_pct,
            "entry_reason": entry_reason,
            "note": "still_open",
        })

    return pd.DataFrame(trades)


# ══════════════════════════════════════════════════════════════════════════
# EQUITY CURVE & METRICS
# ══════════════════════════════════════════════════════════════════════════

def calc_metrics(trades_df, weekly, label=""):
    """Calculate strategy metrics and build equity curve."""
    if "note" in trades_df.columns:
        closed = trades_df[trades_df["note"].isna() | ~trades_df["note"].str.contains("open")]
    else:
        closed = trades_df.copy()

    if len(closed) == 0:
        return None

    # Equity curve (multiplicative)
    equity = [1.0]
    for _, t in closed.iterrows():
        equity.append(equity[-1] * (1 + t["net_pct"] / 100))

    total_return = equity[-1] - 1

    # Time in market
    total_days = (weekly["week"].max() - weekly["week"].min()).days
    days_in_market = sum((t["exit_date"] - t["entry_date"]).days for _, t in closed.iterrows())
    exposure_pct = days_in_market / total_days * 100

    # Annualized return
    years = total_days / 365.25
    ann_return = (equity[-1]) ** (1 / years) - 1 if years > 0 else 0

    # Max drawdown from equity curve (approximate from trade-level)
    peak = equity[0]
    max_dd = 0
    for e in equity:
        if e > peak:
            peak = e
        dd = (peak - e) / peak
        if dd > max_dd:
            max_dd = dd

    # Sharpe (using net_pct per trade)
    returns = closed["net_pct"].values
    if len(returns) > 1 and returns.std() > 0:
        # Annualize: avg ~2 trades/year
        trades_per_year = len(closed) / years if years > 0 else 1
        sharpe = (returns.mean() / returns.std()) * np.sqrt(trades_per_year)
    else:
        sharpe = np.nan

    # Buy-and-hold comparison
    first_week = weekly.iloc[0]
    last_week = weekly.iloc[-1]
    bh_return = (last_week["close"] - first_week["close"]) / first_week["close"]
    bh_ann = (1 + bh_return) ** (1 / years) - 1 if years > 0 else 0

    metrics = {
        "label": label,
        "n_trades": len(closed),
        "win_rate": (closed["net_pct"] > 0).mean() * 100,
        "avg_return": closed["net_pct"].mean(),
        "median_return": closed["net_pct"].median(),
        "total_return": total_return * 100,
        "ann_return": ann_return * 100,
        "max_drawdown": max_dd * 100,
        "sharpe": sharpe,
        "avg_hold_months": closed["hold_months"].mean(),
        "exposure_pct": exposure_pct,
        "avg_cost_pts": closed["total_cost"].mean(),
        "bh_total_return": bh_return * 100,
        "bh_ann_return": bh_ann * 100,
    }
    return metrics


# ══════════════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ══════════════════════════════════════════════════════════════════════════

monthly, weekly, li = load_data()

print("=" * 90)
print("H057 Phase 2 Backtest: Leading Indicator Bottom + Weekly MACD + Monthly KD Exit")
print("=" * 90)
print(f"Data: {weekly['week'].min():%Y/%m/%d} ~ {weekly['week'].max():%Y/%m/%d}")
print(f"Costs: slippage={SLIPPAGE_PTS}pts, rollover={ROLLOVER_COST_PTS}pts/month")
print()


# ── 1. Base Strategy (N=1, default params) ───────────────────────────────

print("=" * 90)
print("1. BASE STRATEGY: N=1, KD(9,3,3), MACD(12,26,9)")
print("=" * 90)

trades = simulate(monthly, weekly, li, n_confirm=1)

print(f"\n{'Entry':>12s}  {'Exit':>12s}  {'EntryP':>7s}  {'ExitP':>7s}  "
      f"{'Gross%':>7s}  {'Cost':>5s}  {'Net%':>7s}  {'Hold':>5s}  Reason")
print("-" * 95)

for _, t in trades.iterrows():
    note = t.get("note", "") if "note" in t and pd.notna(t.get("note", "")) else ""
    suffix = f" [{note}]" if note else ""
    print(f"{t['entry_date']:%Y/%m/%d}  {t['exit_date']:%Y/%m/%d}  "
          f"{t['entry_price']:7.0f}  {t['exit_price']:7.0f}  "
          f"{t['gross_pct']:+6.1f}%  {t['total_cost']:5.0f}  "
          f"{t['net_pct']:+6.1f}%  {t['hold_months']:4.0f}M  "
          f"{t['entry_reason']}{suffix}")

m = calc_metrics(trades, weekly, "Base N=1")
if m:
    print(f"\n  Closed trades: {m['n_trades']}")
    print(f"  Win rate: {m['win_rate']:.0f}%")
    print(f"  Avg net return: {m['avg_return']:+.2f}%")
    print(f"  Total return: {m['total_return']:+.1f}%")
    print(f"  Annualized: {m['ann_return']:+.1f}%")
    print(f"  Max drawdown: {m['max_drawdown']:.1f}%")
    print(f"  Sharpe: {m['sharpe']:.2f}" if not np.isnan(m['sharpe']) else "  Sharpe: N/A")
    print(f"  Avg hold: {m['avg_hold_months']:.1f}M")
    print(f"  Time in market: {m['exposure_pct']:.0f}%")
    print(f"  Avg cost/trade: {m['avg_cost_pts']:.0f} pts")
    print(f"\n  Buy-and-hold: {m['bh_total_return']:+.1f}% ({m['bh_ann_return']:+.1f}% ann)")


# ── 2. N=1,2,3 Comparison ───────────────────────────────────────────────

print()
print("=" * 90)
print("2. N-CONFIRM COMPARISON")
print("=" * 90)

for n in [1, 2, 3]:
    t = simulate(monthly, weekly, li, n_confirm=n)
    m = calc_metrics(t, weekly, f"N={n}")
    if m:
        print(f"  N={n}: trades={m['n_trades']}  win={m['win_rate']:.0f}%  "
              f"avg={m['avg_return']:+.2f}%  total={m['total_return']:+.1f}%  "
              f"ann={m['ann_return']:+.1f}%  sharpe={m['sharpe']:.2f}" if not np.isnan(m['sharpe']) else
              f"  N={n}: trades={m['n_trades']}  win={m['win_rate']:.0f}%  "
              f"avg={m['avg_return']:+.2f}%  total={m['total_return']:+.1f}%  "
              f"ann={m['ann_return']:+.1f}%  sharpe=N/A")


# ── 3. Parameter Sensitivity ────────────────────────────────────────────

print()
print("=" * 90)
print("3. PARAMETER SENSITIVITY")
print("=" * 90)

# 3a. KD parameters
print("\n--- KD Period Sensitivity (N=1, MACD=default) ---")
print(f"{'KD Params':>12s}  {'Trades':>6s}  {'Win%':>5s}  {'AvgNet%':>8s}  {'Total%':>8s}")

for kd_k in [7, 9, 12, 14]:
    for kd_smooth in [1, 3]:
        kd_d = 3
        t = simulate(monthly, weekly, li, n_confirm=1, kd_params=(kd_k, kd_smooth, kd_d))
        m = calc_metrics(t, weekly)
        if m and m["n_trades"] > 0:
            print(f"  ({kd_k},{kd_smooth},{kd_d})  {m['n_trades']:6d}  "
                  f"{m['win_rate']:5.0f}  {m['avg_return']:+7.2f}%  {m['total_return']:+7.1f}%")

# 3b. MACD parameters
print("\n--- MACD Period Sensitivity (N=1, KD=9,3,3) ---")
print(f"{'MACD Params':>14s}  {'Trades':>6s}  {'Win%':>5s}  {'AvgNet%':>8s}  {'Total%':>8s}")

for fast, slow, sig in [(8, 17, 9), (12, 26, 9), (12, 26, 6), (19, 39, 9)]:
    t = simulate(monthly, weekly, li, n_confirm=1, macd_params=(fast, slow, sig))
    m = calc_metrics(t, weekly)
    if m and m["n_trades"] > 0:
        print(f"  ({fast},{slow},{sig})  {m['n_trades']:6d}  "
              f"{m['win_rate']:5.0f}  {m['avg_return']:+7.2f}%  {m['total_return']:+7.1f}%")

# 3c. Max wait weeks
print("\n--- Max Wait Weeks Sensitivity (N=1, default params) ---")
print(f"{'Wait':>6s}  {'Trades':>6s}  {'Win%':>5s}  {'AvgNet%':>8s}  {'Total%':>8s}")

for wait in [13, 26, 39, 52]:
    t = simulate(monthly, weekly, li, n_confirm=1, max_wait_weeks=wait)
    m = calc_metrics(t, weekly)
    if m and m["n_trades"] > 0:
        print(f"  {wait:4d}w  {m['n_trades']:6d}  "
              f"{m['win_rate']:5.0f}  {m['avg_return']:+7.2f}%  {m['total_return']:+7.1f}%")


# ── 4. Equity Curve & Drawdown Chart ────────────────────────────────────

trades_base = simulate(monthly, weekly, li, n_confirm=1)
closed_base = trades_base[~trades_base.get("note", pd.Series("")).fillna("").str.contains("open")]

# Build weekly equity curve
equity_dates = [weekly["week"].iloc[0]]
equity_values = [1.0]
bh_values = [1.0]
bh_base = weekly["close"].iloc[0]

position_open = False
current_equity = 1.0

for _, t in closed_base.iterrows():
    # Before entry: flat
    equity_dates.append(t["entry_date"])
    equity_values.append(current_equity)
    bh_values.append((weekly[weekly["week"] <= t["entry_date"]].iloc[-1]["close"]) / bh_base)

    # At exit
    equity_dates.append(t["exit_date"])
    current_equity *= (1 + t["net_pct"] / 100)
    equity_values.append(current_equity)
    bh_values.append((weekly[weekly["week"] <= t["exit_date"]].iloc[-1]["close"]) / bh_base)

# End
equity_dates.append(weekly["week"].iloc[-1])
equity_values.append(current_equity)
bh_values.append(weekly["close"].iloc[-1] / bh_base)

fig, axes = plt.subplots(2, 1, figsize=(14, 8))

# Equity curve
ax1 = axes[0]
ax1.plot(equity_dates, equity_values, "b-", linewidth=2, label="Strategy (net)")
ax1.plot(equity_dates, bh_values, "k--", linewidth=1, alpha=0.5, label="Buy & Hold")

# Shade trade periods
for _, t in closed_base.iterrows():
    ax1.axvspan(t["entry_date"], t["exit_date"], alpha=0.1, color="blue")

ax1.set_ylabel("Equity (1.0 = start)")
ax1.set_title("H057 Backtest: Equity Curve (net of costs)")
ax1.legend()
ax1.grid(True, alpha=0.3)

# Drawdown
peak = pd.Series(equity_values).cummax()
dd = (pd.Series(equity_values) - peak) / peak * 100
ax2 = axes[1]
ax2.fill_between(equity_dates, dd, 0, alpha=0.4, color="red")
ax2.set_ylabel("Drawdown (%)")
ax2.set_xlabel("Date")
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(OUTPUT / "h057_backtest_equity.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"\nSaved: {OUTPUT / 'h057_backtest_equity.png'}")


# ── 5. Summary Table ────────────────────────────────────────────────────

print()
print("=" * 90)
print("SUMMARY")
print("=" * 90)

results = []
for n in [1, 2, 3]:
    t = simulate(monthly, weekly, li, n_confirm=n)
    m = calc_metrics(t, weekly, f"N={n}")
    if m:
        results.append(m)

print(f"\n{'Config':>8s}  {'Trades':>6s}  {'Win%':>5s}  {'Avg%':>7s}  {'Total%':>8s}  "
      f"{'Ann%':>6s}  {'MDD%':>6s}  {'Sharpe':>6s}  {'Expo%':>6s}")
print("-" * 75)
for m in results:
    sharpe_str = f"{m['sharpe']:6.2f}" if not np.isnan(m['sharpe']) else "   N/A"
    print(f"{m['label']:>8s}  {m['n_trades']:6d}  {m['win_rate']:5.0f}  "
          f"{m['avg_return']:+6.2f}%  {m['total_return']:+7.1f}%  "
          f"{m['ann_return']:+5.1f}%  {m['max_drawdown']:5.1f}%  "
          f"{sharpe_str}  {m['exposure_pct']:5.0f}%")

if results:
    bh = results[0]
    print(f"\n  Buy-and-hold: total={bh['bh_total_return']:+.1f}%  ann={bh['bh_ann_return']:+.1f}%")
    print(f"  (Strategy is in market only {bh['exposure_pct']:.0f}% of time)")
