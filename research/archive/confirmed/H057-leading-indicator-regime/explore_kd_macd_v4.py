"""
H057 探索 v4：領先指標 Bottom + 週 MACD 多頭確認進場 + 月 KD 跌破 80 出場

進場條件（放寬版）：
1. 領先指標 bottom 拐點確認
2. 週 MACD 已在 Signal 上方（已經金叉過）→ 直接進場
   或等待新的金叉 → 金叉時進場
3. 月 KD(9,3,3) 跌破 80 → 出場
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import duckdb
from pathlib import Path

plt.rcParams["font.family"] = ["Arial Unicode MS", "Heiti TC", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

BASE = Path(__file__).parent
OUTPUT = BASE / "results"
OUTPUT.mkdir(exist_ok=True)
DB_PATH = BASE.parent.parent.parent / "data" / "futures.duckdb"


# ── 1. Load Data ────────────────────────────────────────────────────────

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

print(f"Monthly: {monthly['month'].min():%Y/%m} ~ {monthly['month'].max():%Y/%m} ({len(monthly)} months)")
print(f"Weekly:  {weekly['week'].min():%Y/%m/%d} ~ {weekly['week'].max():%Y/%m/%d} ({len(weekly)} weeks)")


# ── 2. Monthly KD (9,3,3) ───────────────────────────────────────────────

k_period, smooth_k, d_period = 9, 3, 3
low_min = monthly["low"].rolling(k_period).min()
high_max = monthly["high"].rolling(k_period).max()
rsv = (monthly["close"] - low_min) / (high_max - low_min) * 100
monthly["K"] = rsv.rolling(smooth_k).mean()
monthly["D"] = monthly["K"].rolling(d_period).mean()
monthly["above_80"] = monthly["K"] > 80
monthly["prev_above_80"] = monthly["above_80"].shift(1).fillna(False).astype(bool)
monthly["kd_exit"] = monthly["prev_above_80"] & (~monthly["above_80"])


# ── 3. Weekly MACD (12,26,9) ────────────────────────────────────────────

ema12 = weekly["close"].ewm(span=12, adjust=False).mean()
ema26 = weekly["close"].ewm(span=26, adjust=False).mean()
weekly["macd"] = ema12 - ema26
weekly["signal"] = weekly["macd"].ewm(span=9, adjust=False).mean()
weekly["hist"] = weekly["macd"] - weekly["signal"]
weekly["macd_bullish"] = weekly["macd"] > weekly["signal"]  # 已在多頭狀態
weekly["golden_cross"] = (~weekly["macd_bullish"].shift(1).fillna(False)) & weekly["macd_bullish"]


# ── 4. Leading Indicator ────────────────────────────────────────────────

li = pd.read_csv(BASE / "data" / "leading_indicator.csv")
li["date"] = pd.to_datetime(li["date"], format="%Y/%m")
li["pub_date"] = pd.to_datetime(li["last_working_day"], format="%Y/%m/%d")
li = li.sort_values("date").reset_index(drop=True)
li["direction"] = np.sign(li["leading_index"].diff())
li["prev_direction"] = li["direction"].shift(1)
li["is_bottom"] = (li["direction"] > 0) & (li["prev_direction"] < 0)


def get_confirmed_bottoms(li, n_confirm=1):
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
                    "signal_month": li.iloc[confirm_idx]["date"],
                })
    return pd.DataFrame(bottoms)


# ── 5. Strategy Simulation ──────────────────────────────────────────────

def simulate(li, monthly, weekly, n_confirm=1, max_wait_weeks=26):
    """
    Entry:
      1. Leading indicator bottom confirmed → signal_date
      2. On signal_date, check weekly MACD:
         - If MACD > Signal (already bullish) → enter immediately (that week's close)
         - If MACD <= Signal → wait for golden cross within max_wait_weeks
    Exit:
      Monthly KD(9,3,3) drops below 80
    """
    bottoms = get_confirmed_bottoms(li, n_confirm)
    trades = []
    in_position = False
    entry_price = None
    entry_date = None
    entry_bottom = None
    armed = False
    armed_date = None
    armed_bottom_date = None
    used_bottoms = set()

    # Build monthly KD exit dates
    kd_exit_months = set(monthly[monthly["kd_exit"]]["month"].values)

    for wi in range(len(weekly)):
        wrow = weekly.iloc[wi]
        week_date = wrow["week"]

        # Check for new bottom signals
        if not in_position and not armed:
            for _, b in bottoms.iterrows():
                if b["turn_date"] in used_bottoms:
                    continue
                if pd.Timestamp(b["signal_date"]) <= week_date:
                    armed = True
                    armed_date = pd.Timestamp(b["signal_date"])
                    armed_bottom_date = b["turn_date"]
                    used_bottoms.add(b["turn_date"])

                    # Check: is MACD already bullish on signal week?
                    # Find the week closest to signal_date
                    signal_week_mask = weekly["week"] <= week_date
                    if signal_week_mask.any():
                        signal_week = weekly[signal_week_mask].iloc[-1]
                        if signal_week["macd_bullish"]:
                            # Already bullish → enter immediately
                            in_position = True
                            entry_price = wrow["close"]
                            entry_date = week_date
                            entry_bottom = armed_bottom_date
                            entry_reason = f"Bottom {armed_bottom_date:%Y/%m} + MACD already bullish"
                            armed = False
                    break

        # If armed but not entered, wait for golden cross
        if armed and not in_position:
            weeks_waited = (week_date - armed_date).days / 7
            if weeks_waited > max_wait_weeks:
                armed = False  # timeout
            elif wrow["golden_cross"]:
                in_position = True
                entry_price = wrow["close"]
                entry_date = week_date
                entry_bottom = armed_bottom_date
                entry_reason = f"Bottom {armed_bottom_date:%Y/%m} + GC {week_date:%Y/%m/%d}"
                armed = False

        # Check for exit
        if in_position:
            week_month = pd.Timestamp(week_date.year, week_date.month, 1)
            if week_month in kd_exit_months:
                next_month = week_month + pd.DateOffset(months=1)
                next_week_date = weekly.iloc[wi + 1]["week"] if wi + 1 < len(weekly) else pd.Timestamp("2099-01-01")
                if next_week_date >= next_month or wi == len(weekly) - 1:
                    exit_price = wrow["close"]
                    exit_date = week_date
                    ret_pct = (exit_price - entry_price) / entry_price * 100
                    hold_weeks = (exit_date - entry_date).days / 7
                    trades.append({
                        "bottom_date": entry_bottom,
                        "entry_date": entry_date,
                        "exit_date": exit_date,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "return_pct": ret_pct,
                        "hold_weeks": hold_weeks,
                        "reason": entry_reason,
                    })
                    in_position = False

    # Still open
    if in_position:
        last = weekly.iloc[-1]
        ret_pct = (last["close"] - entry_price) / entry_price * 100
        hold_weeks = (last["week"] - entry_date).days / 7
        trades.append({
            "bottom_date": entry_bottom,
            "entry_date": entry_date,
            "exit_date": last["week"],
            "entry_price": entry_price,
            "exit_price": last["close"],
            "return_pct": ret_pct,
            "hold_weeks": hold_weeks,
            "reason": entry_reason,
            "note": "still open",
        })

    return pd.DataFrame(trades)


# ── 6. Show MACD state at each bottom signal ────────────────────────────

print()
print("=" * 90)
print("每次 Bottom signal 時的週 MACD 狀態")
print("=" * 90)

for n in [1]:
    bottoms = get_confirmed_bottoms(li, n_confirm=n)
    for _, b in bottoms.iterrows():
        sig_date = pd.Timestamp(b["signal_date"])
        # Find the week on or before signal_date
        mask = weekly["week"] <= sig_date
        if not mask.any():
            continue
        sw = weekly[mask].iloc[-1]
        state = "BULLISH (MACD > Signal) → 直接進場" if sw["macd_bullish"] else "BEARISH → 等金叉"

        # If bearish, find next golden cross
        gc_info = ""
        if not sw["macd_bullish"]:
            gc_after = weekly[(weekly["week"] > sig_date) &
                             (weekly["week"] <= sig_date + pd.DateOffset(weeks=26)) &
                             (weekly["golden_cross"])]
            if len(gc_after) > 0:
                gc = gc_after.iloc[0]
                wait = (gc["week"] - sig_date).days
                gc_info = f" → 金叉 {gc['week']:%Y/%m/%d} (等{wait}天)"
            else:
                gc_info = " → 26週內無金叉"

        print(f"  Bottom {b['turn_date']:%Y/%m}  signal={sig_date:%Y/%m/%d}  "
              f"MACD={sw['macd']:.0f} Signal={sw['signal']:.0f}  {state}{gc_info}")

print()


# ── 7. Run Simulation ───────────────────────────────────────────────────

print("=" * 90)
print("策略 v4：Bottom + 週 MACD 多頭確認（已金叉 or 等金叉）+ 月 KD 跌破 80 出場")
print("=" * 90)

for n in [1, 2, 3]:
    trades_df = simulate(li, monthly, weekly, n_confirm=n)
    print(f"\n--- N={n} 確認 ---")

    if len(trades_df) == 0:
        print("  No trades")
        continue

    print(f"{'Entry':>12s}  {'Exit':>12s}  {'EntryP':>8s}  {'ExitP':>8s}  "
          f"{'Ret%':>7s}  {'Weeks':>5s}  Reason")
    print("-" * 100)

    for _, t in trades_df.iterrows():
        note = t.get("note", "") if "note" in t and pd.notna(t.get("note", "")) else ""
        suffix = f"  [{note}]" if note else ""
        print(f"{t['entry_date']:%Y/%m/%d}  {t['exit_date']:%Y/%m/%d}  "
              f"{t['entry_price']:8.0f}  {t['exit_price']:8.0f}  "
              f"{t['return_pct']:+6.1f}%  {t['hold_weeks']:5.0f}w  "
              f"{t['reason']}{suffix}")

    closed = trades_df[~trades_df.get("note", pd.Series("")).fillna("").str.contains("open")]
    all_trades = trades_df
    print()
    print(f"  交易次數: {len(all_trades)} (已平倉: {len(closed)})")
    if len(closed) > 0:
        print(f"  勝率: {(closed['return_pct'] > 0).mean()*100:.0f}%")
        print(f"  平均報酬: {closed['return_pct'].mean():+.2f}%")
        print(f"  中位數報酬: {closed['return_pct'].median():+.2f}%")
        print(f"  平均持有: {closed['hold_weeks'].mean():.0f} weeks")
        print(f"  最大獲利: {closed['return_pct'].max():+.1f}%")
        print(f"  最大虧損: {closed['return_pct'].min():+.1f}%")
        total_ret = (1 + closed["return_pct"] / 100).prod() - 1
        print(f"  累計報酬: {total_ret*100:+.1f}%")

    # Include open position in total
    if len(all_trades) > 0:
        total_all = (1 + all_trades["return_pct"] / 100).prod() - 1
        print(f"  累計報酬(含未平倉): {total_all*100:+.1f}%")


# ── 8. Visualization ────────────────────────────────────────────────────

trades_n1 = simulate(li, monthly, weekly, n_confirm=1)

fig, axes = plt.subplots(4, 1, figsize=(14, 13))

# Panel 1: TAIEX with trade markers
ax1 = axes[0]
ax1.plot(weekly["week"], weekly["close"], "k-", linewidth=0.8, alpha=0.7)

for _, t in trades_n1.iterrows():
    ax1.axvspan(t["entry_date"], t["exit_date"], alpha=0.15, color="blue")
    ax1.scatter(t["entry_date"], t["entry_price"], c="red", marker="^", s=120, zorder=5)
    note = t.get("note", "")
    if pd.isna(note) or "open" not in str(note):
        ax1.scatter(t["exit_date"], t["exit_price"], c="green", marker="v", s=120, zorder=5)

ax1.set_ylabel("TX Close (Weekly)")
ax1.set_title("H057 v4: Bottom + MACD Bullish Confirm + Monthly KD Exit")
ax1.grid(True, alpha=0.3)

# Panel 2: Weekly MACD
ax2 = axes[1]
ax2.plot(weekly["week"], weekly["macd"], "b-", linewidth=1, label="MACD")
ax2.plot(weekly["week"], weekly["signal"], "r-", linewidth=1, label="Signal")
colors = ["red" if h > 0 else "green" for h in weekly["hist"]]
ax2.bar(weekly["week"], weekly["hist"], color=colors, alpha=0.4, width=5)
ax2.axhline(0, color="gray", linewidth=0.5)
ax2.set_ylabel("Weekly MACD")
ax2.legend(loc="upper left", fontsize=8)
ax2.grid(True, alpha=0.3)

# Panel 3: Monthly KD
ax3 = axes[2]
ax3.plot(monthly["month"], monthly["K"], "b-", linewidth=1.5, label="K")
ax3.plot(monthly["month"], monthly["D"], "r--", linewidth=1, alpha=0.7, label="D")
ax3.axhline(80, color="gray", linestyle="--", alpha=0.5)
ax3.fill_between(monthly["month"], 80, 100, alpha=0.1, color="red")
ax3.set_ylabel("Monthly KD (9,3,3)")
ax3.set_ylim(0, 100)
ax3.legend(loc="upper left")
ax3.grid(True, alpha=0.3)

# Panel 4: Leading Index
ax4 = axes[3]
ax4.plot(li["date"], li["leading_index"], "g-", linewidth=1.5)
bottoms_pts = li[li["is_bottom"]]
ax4.scatter(bottoms_pts["date"], bottoms_pts["leading_index"], c="red", marker="^", s=80, zorder=5)
ax4.set_ylabel("Leading Index")
ax4.set_xlabel("Date")
ax4.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(OUTPUT / "h057_v4_macd_bullish.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"\nSaved: {OUTPUT / 'h057_v4_macd_bullish.png'}")
