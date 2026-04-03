"""
H057 探索 v3：領先指標 Bottom + 週 MACD 金叉進場 + 月 KD 跌破 80 出場

邏輯：
1. 領先指標出現 bottom 拐點 → 「待命」狀態
2. 等週 MACD 金叉（MACD 上穿 Signal）→ 進場做多
3. 月 KD(9,3,3) 跌破 80 → 出場
4. 如果金叉遲遲不來（或月 KD 已跌破 80），取消待命
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

# Monthly OHLC
monthly = conn.execute("""
    SELECT
        date_trunc('month', timestamp) as month,
        FIRST(open) as open,
        MAX(high) as high,
        MIN(low) as low,
        LAST(close) as close
    FROM ohlcv_1m
    WHERE symbol = 'TX'
        AND EXTRACT(hour FROM timestamp) >= 8
        AND EXTRACT(hour FROM timestamp) < 14
    GROUP BY 1
    ORDER BY 1
""").fetchdf()

# Weekly OHLC
weekly = conn.execute("""
    SELECT
        date_trunc('week', timestamp) as week,
        FIRST(open) as open,
        MAX(high) as high,
        MIN(low) as low,
        LAST(close) as close
    FROM ohlcv_1m
    WHERE symbol = 'TX'
        AND EXTRACT(hour FROM timestamp) >= 8
        AND EXTRACT(hour FROM timestamp) < 14
    GROUP BY 1
    ORDER BY 1
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

# Golden cross: MACD crosses above Signal
weekly["prev_macd"] = weekly["macd"].shift(1)
weekly["prev_signal"] = weekly["signal"].shift(1)
weekly["golden_cross"] = (weekly["prev_macd"] <= weekly["prev_signal"]) & (weekly["macd"] > weekly["signal"])

gc_weeks = weekly[weekly["golden_cross"]]
print(f"\nWeekly MACD golden crosses: {len(gc_weeks)}")


# ── 4. Leading Indicator ────────────────────────────────────────────────

li = pd.read_csv(BASE / "data" / "leading_indicator.csv")
li["date"] = pd.to_datetime(li["date"], format="%Y/%m")
li["pub_date"] = pd.to_datetime(li["last_working_day"], format="%Y/%m/%d")
li = li.sort_values("date").reset_index(drop=True)

li["direction"] = np.sign(li["leading_index"].diff())
li["prev_direction"] = li["direction"].shift(1)
li["is_bottom"] = (li["direction"] > 0) & (li["prev_direction"] < 0)

# Bottom signals with N-month confirmation
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
            # Signal available at pub_date of confirmation month
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
    1. Leading indicator bottom confirmed → armed (waiting for MACD golden cross)
    2. Weekly MACD golden cross after signal_date → entry
    3. Monthly KD drops below 80 → exit
    """
    bottoms = get_confirmed_bottoms(li, n_confirm)
    trades = []
    armed = False
    armed_date = None
    in_position = False
    entry_price = None
    entry_date = None
    entry_reason = None

    # Build monthly KD exit dates
    kd_exit_months = set(monthly[monthly["kd_exit"]]["month"].values)

    # Timeline: iterate through weeks
    for wi, wrow in weekly.iterrows():
        week_date = wrow["week"]

        # Check if we should arm (new bottom signal available)
        if not in_position and not armed:
            for _, b in bottoms.iterrows():
                if b["signal_date"] <= week_date and (armed_date is None or b["signal_date"] > armed_date):
                    # Check this signal hasn't been used already
                    already_used = False
                    for t in trades:
                        if t["bottom_date"] == b["turn_date"]:
                            already_used = True
                            break
                    if not already_used:
                        armed = True
                        armed_date = b["signal_date"]
                        armed_bottom = b["turn_date"]
                        break

        # Check for entry: armed + golden cross
        if armed and not in_position and wrow["golden_cross"]:
            # Check if we've waited too long
            weeks_waited = (week_date - pd.Timestamp(armed_date)).days / 7
            if weeks_waited <= max_wait_weeks:
                in_position = True
                entry_price = wrow["close"]
                entry_date = week_date
                entry_reason = f"Bottom {armed_bottom:%Y/%m} + GC {week_date:%Y/%m/%d}"
                entry_bottom = armed_bottom
                armed = False

        # Check timeout for armed state
        if armed and not in_position:
            weeks_waited = (week_date - pd.Timestamp(armed_date)).days / 7
            if weeks_waited > max_wait_weeks:
                armed = False

        # Check for exit: monthly KD < 80
        if in_position:
            # Find the month this week belongs to
            week_month = pd.Timestamp(week_date.year, week_date.month, 1)
            if week_month in kd_exit_months:
                # Exit at end of month (use last week of that month)
                next_month = week_month + pd.DateOffset(months=1)
                if week_date >= week_month and (wi == len(weekly) - 1 or weekly.iloc[wi + 1]["week"] >= next_month):
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


# Simpler approach: just find golden crosses after each bottom signal
print()
print("=" * 80)
print("策略：領先指標 Bottom + 週 MACD 金叉進場 + 月 KD(9,3,3) 跌破 80 出場")
print("=" * 80)

# First, show the golden crosses around each bottom for reference
print("\n=== 每次 Bottom 後的週 MACD 金叉 ===")
for n in [1]:
    bottoms = get_confirmed_bottoms(li, n_confirm=n)
    for _, b in bottoms.iterrows():
        sig_date = b["signal_date"]
        # Find first golden cross within 6 months after signal
        gc_after = weekly[(weekly["week"] >= sig_date) &
                         (weekly["week"] <= sig_date + pd.DateOffset(months=6)) &
                         (weekly["golden_cross"])]
        if len(gc_after) > 0:
            first_gc = gc_after.iloc[0]
            wait_days = (first_gc["week"] - sig_date).days
            print(f"  Bottom {b['turn_date']:%Y/%m}  signal={sig_date:%Y/%m/%d}  "
                  f"→ 首次金叉 {first_gc['week']:%Y/%m/%d} (等{wait_days}天)  "
                  f"close={first_gc['close']:.0f}")
        else:
            print(f"  Bottom {b['turn_date']:%Y/%m}  signal={sig_date:%Y/%m/%d}  "
                  f"→ 6個月內無金叉")

print()

for n in [1, 2, 3]:
    trades_df = simulate(li, monthly, weekly, n_confirm=n)
    print(f"\n--- N={n} 確認 ---")

    if len(trades_df) == 0:
        print("  No trades")
        continue

    print(f"{'Entry':>12s}  {'Exit':>12s}  {'EntryP':>8s}  {'ExitP':>8s}  "
          f"{'Ret%':>7s}  {'Weeks':>5s}  Reason")
    print("-" * 95)

    for _, t in trades_df.iterrows():
        note = t.get("note", "") if "note" in t and pd.notna(t.get("note", "")) else ""
        suffix = f"  [{note}]" if note else ""
        print(f"{t['entry_date']:%Y/%m/%d}  {t['exit_date']:%Y/%m/%d}  "
              f"{t['entry_price']:8.0f}  {t['exit_price']:8.0f}  "
              f"{t['return_pct']:+6.1f}%  {t['hold_weeks']:5.0f}w  "
              f"{t['reason']}{suffix}")

    closed = trades_df[~trades_df.get("note", pd.Series("")).fillna("").str.contains("open")]
    print()
    print(f"  交易次數: {len(trades_df)} (已平倉: {len(closed)})")
    if len(closed) > 0:
        print(f"  勝率: {(closed['return_pct'] > 0).mean()*100:.0f}%")
        print(f"  平均報酬: {closed['return_pct'].mean():+.2f}%")
        print(f"  中位數報酬: {closed['return_pct'].median():+.2f}%")
        print(f"  平均持有: {closed['hold_weeks'].mean():.0f} weeks")
        print(f"  最大獲利: {closed['return_pct'].max():+.1f}%")
        print(f"  最大虧損: {closed['return_pct'].min():+.1f}%")
        total_ret = (1 + closed["return_pct"] / 100).prod() - 1
        print(f"  累計報酬: {total_ret*100:+.1f}%")


# ── 6. Compare: v2 (no MACD) vs v3 (with MACD) for 2025 case ───────────

print()
print("=" * 80)
print("2025 案例比較")
print("=" * 80)
print()
print("v2 (無 MACD 確認):")
print("  2025/02 進場 @ 23196 → 接著跌到 20149 (-13.1%)")
print()

# Find what happened with MACD confirmation for 2025
bottoms_n1 = get_confirmed_bottoms(li, n_confirm=1)
b2025 = bottoms_n1[bottoms_n1["turn_date"] == pd.Timestamp("2025-01-01")]
if len(b2025) > 0:
    sig = b2025.iloc[0]["signal_date"]
    gc_after = weekly[(weekly["week"] >= sig) &
                     (weekly["golden_cross"])]
    if len(gc_after) > 0:
        first_gc = gc_after.iloc[0]
        print(f"v3 (週 MACD 金叉確認):")
        print(f"  Bottom signal: {sig:%Y/%m/%d}")
        print(f"  首次金叉: {first_gc['week']:%Y/%m/%d}  close={first_gc['close']:.0f}")
        print(f"  避開了 2025/03~2025/05 的下跌")


# ── 7. Visualization ────────────────────────────────────────────────────

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
ax1.set_title("H057 v3: Bottom + Weekly MACD Golden Cross Entry + Monthly KD Exit")
ax1.grid(True, alpha=0.3)

# Panel 2: Weekly MACD
ax2 = axes[1]
ax2.plot(weekly["week"], weekly["macd"], "b-", linewidth=1, label="MACD")
ax2.plot(weekly["week"], weekly["signal"], "r-", linewidth=1, label="Signal")
colors = ["red" if h > 0 else "green" for h in weekly["hist"]]
ax2.bar(weekly["week"], weekly["hist"], color=colors, alpha=0.4, width=5)
ax2.axhline(0, color="gray", linewidth=0.5)

# Mark golden crosses
gc = weekly[weekly["golden_cross"]]
ax2.scatter(gc["week"], gc["macd"], c="gold", marker="*", s=80, zorder=5, label="Golden Cross")
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
plt.savefig(OUTPUT / "h057_bottom_macd_kd_v3.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"\nSaved: {OUTPUT / 'h057_bottom_macd_kd_v3.png'}")
