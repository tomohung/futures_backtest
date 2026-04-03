"""
H057 補充探索：底部進場 + KD 跌破 80 出場

策略邏輯：
- 進場：領先指標 bottom 拐點（可選 N=1/2/3 確認）
- 出場：月 K 從 80 以上跌破 80（強勢攻擊結束）
- 如果進場時 K 已經 > 80，等跌破 80 後再等下一次底部訊號
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

plt.rcParams["font.family"] = ["Arial Unicode MS", "Heiti TC", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

BASE = Path(__file__).parent
OUTPUT = BASE / "results"
OUTPUT.mkdir(exist_ok=True)

# ── Load & Prepare ──────────────────────────────────────────────────────

df = pd.read_csv(BASE / "data" / "leading_indicator.csv")
df["date"] = pd.to_datetime(df["date"], format="%Y/%m")
df["pub_date"] = pd.to_datetime(df["last_working_day"], format="%Y/%m/%d")
df = df.sort_values("date").reset_index(drop=True)

# Monthly KD (9,3,3)
def calc_kd(close, k_period=9, d_period=3, smooth_k=3):
    low_min = close.rolling(k_period).min()
    high_max = close.rolling(k_period).max()
    rsv = (close - low_min) / (high_max - low_min) * 100
    rsv = rsv.fillna(50)
    k = rsv.rolling(smooth_k).mean()
    d = k.rolling(d_period).mean()
    return k, d

df["K"], df["D"] = calc_kd(df["taiex"])

# Leading indicator turning points
df["direction"] = np.sign(df["leading_index"].diff())
df["prev_direction"] = df["direction"].shift(1)
df["is_bottom"] = (df["direction"] > 0) & (df["prev_direction"] < 0)

# KD exit signal: K was > 80 last month, now <= 80
df["above_80"] = df["K"] > 80
df["prev_above_80"] = df["above_80"].shift(1).fillna(False).astype(bool)
df["kd_exit"] = df["prev_above_80"] & (~df["above_80"])


# ── Simulate: Bottom entry + KD<80 exit ─────────────────────────────────

def simulate(df, n_confirm=1):
    """
    Entry: Leading indicator bottom turn, confirmed by N consecutive months.
           Signal available at confirmation month's publication date.
    Exit:  Monthly K drops below 80 (was above 80 last month).
    """
    trades = []
    in_position = False
    entry_price = None
    entry_date = None
    entry_k = None

    # Find confirmed bottoms
    confirmed_bottoms = set()
    for idx in range(1, len(df) - n_confirm):
        row = df.iloc[idx]
        if not row["is_bottom"]:
            continue
        direction = row["direction"]
        persist = True
        for k in range(1, n_confirm + 1):
            if idx + k >= len(df):
                persist = False
                break
            if df.iloc[idx + k]["direction"] != direction:
                persist = False
                break
        if persist:
            # Signal available at confirmation month
            signal_idx = idx + n_confirm
            if signal_idx < len(df):
                confirmed_bottoms.add(signal_idx)

    for i in range(len(df)):
        row = df.iloc[i]

        if not in_position:
            if i in confirmed_bottoms:
                in_position = True
                entry_price = row["taiex"]
                entry_date = row["date"]
                entry_k = row["K"]
        else:
            if row["kd_exit"]:
                exit_price = row["taiex"]
                exit_date = row["date"]
                ret_pct = (exit_price - entry_price) / entry_price * 100
                hold_months = (exit_date.year - entry_date.year) * 12 + exit_date.month - entry_date.month
                trades.append({
                    "entry_date": entry_date,
                    "exit_date": exit_date,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "entry_k": entry_k,
                    "exit_k": row["K"],
                    "return_pct": ret_pct,
                    "hold_months": hold_months,
                })
                in_position = False

    # Still open position
    if in_position:
        last = df.iloc[-1]
        ret_pct = (last["taiex"] - entry_price) / entry_price * 100
        hold_months = (last["date"].year - entry_date.year) * 12 + last["date"].month - entry_date.month
        trades.append({
            "entry_date": entry_date,
            "exit_date": last["date"],
            "entry_price": entry_price,
            "exit_price": last["taiex"],
            "entry_k": entry_k,
            "exit_k": last["K"],
            "return_pct": ret_pct,
            "hold_months": hold_months,
            "note": "still open",
        })

    return pd.DataFrame(trades)


print("=" * 80)
print("策略：領先指標 Bottom 進場 + 月 KD 跌破 80 出場")
print("=" * 80)

for n in [1, 2, 3]:
    trades_df = simulate(df, n_confirm=n)
    print(f"\n--- N={n} 確認 ---")

    if len(trades_df) == 0:
        print("  No trades")
        continue

    print(f"{'Entry':>8s}  {'Exit':>8s}  {'EntryP':>8s}  {'ExitP':>8s}  "
          f"{'EntK':>5s}  {'ExtK':>5s}  {'Ret%':>7s}  {'Hold':>5s}  Note")
    print("-" * 85)

    for _, t in trades_df.iterrows():
        note = t.get("note", "") if "note" in t and pd.notna(t.get("note", "")) else ""
        print(f"{t['entry_date']:%Y/%m}  {t['exit_date']:%Y/%m}  "
              f"{t['entry_price']:8.0f}  {t['exit_price']:8.0f}  "
              f"{t['entry_k']:5.1f}  {t['exit_k']:5.1f}  "
              f"{t['return_pct']:+6.1f}%  {t['hold_months']:4.0f}M  {note}")

    closed = trades_df[~trades_df.get("note", pd.Series("")).fillna("").str.contains("open")]
    print()
    print(f"  交易次數: {len(trades_df)} (已平倉: {len(closed)})")
    if len(closed) > 0:
        print(f"  勝率: {(closed['return_pct'] > 0).mean()*100:.0f}%")
        print(f"  平均報酬: {closed['return_pct'].mean():+.2f}%")
        print(f"  中位數報酬: {closed['return_pct'].median():+.2f}%")
        print(f"  平均持有: {closed['hold_months'].mean():.1f}M")
        print(f"  最大獲利: {closed['return_pct'].max():+.1f}%")
        print(f"  最大虧損: {closed['return_pct'].min():+.1f}%")
        total_ret = (1 + closed["return_pct"] / 100).prod() - 1
        print(f"  累計報酬: {total_ret*100:+.1f}%")


# ── Compare with: Bottom entry + no exit rule (hold 6M) ─────────────────

print()
print("=" * 80)
print("比較基準：Bottom 進場 + 固定持有 6 個月出場")
print("=" * 80)

for n in [1, 2, 3]:
    confirmed_bottoms = []
    for idx in range(1, len(df) - n):
        row = df.iloc[idx]
        if not row["is_bottom"]:
            continue
        persist = True
        for k in range(1, n + 1):
            if idx + k >= len(df):
                persist = False
                break
            if df.iloc[idx + k]["direction"] != row["direction"]:
                persist = False
                break
        if persist:
            signal_idx = idx + n
            if signal_idx + 6 < len(df):
                entry = df.iloc[signal_idx]
                exit_row = df.iloc[signal_idx + 6]
                ret = (exit_row["taiex"] - entry["taiex"]) / entry["taiex"] * 100
                confirmed_bottoms.append({
                    "entry_date": entry["date"],
                    "exit_date": exit_row["date"],
                    "return_pct": ret,
                })

    if confirmed_bottoms:
        cb_df = pd.DataFrame(confirmed_bottoms)
        print(f"\n  N={n}: {len(cb_df)} trades  "
              f"mean={cb_df['return_pct'].mean():+.2f}%  "
              f"win={((cb_df['return_pct']>0).mean()*100):.0f}%  "
              f"median={cb_df['return_pct'].median():+.2f}%")


# ── Visualization ───────────────────────────────────────────────────────

# Use N=1 for visualization (most trades)
trades_n1 = simulate(df, n_confirm=1)

fig, axes = plt.subplots(3, 1, figsize=(14, 10))

# Panel 1: TAIEX with trade markers
ax1 = axes[0]
ax1.plot(df["date"], df["taiex"], "k-", linewidth=1.2)

for _, t in trades_n1.iterrows():
    ax1.axvspan(t["entry_date"], t["exit_date"], alpha=0.15, color="blue")
    ax1.scatter(t["entry_date"], t["entry_price"], c="red", marker="^", s=120, zorder=5)
    note = t.get("note", "")
    if pd.isna(note) or "open" not in str(note):
        ax1.scatter(t["exit_date"], t["exit_price"], c="green", marker="v", s=120, zorder=5)

ax1.set_ylabel("TAIEX")
ax1.set_title("H057: Bottom Entry (N=1) + KD Exit (<80)")
ax1.legend(["TAIEX", "Entry", "Exit"], loc="upper left")
ax1.grid(True, alpha=0.3)

# Panel 2: KD with 80 line
ax2 = axes[1]
ax2.plot(df["date"], df["K"], "b-", linewidth=1.5, label="K")
ax2.plot(df["date"], df["D"], "r--", linewidth=1, alpha=0.7, label="D")
ax2.axhline(80, color="gray", linestyle="--", alpha=0.5)
ax2.axhline(20, color="gray", linestyle="--", alpha=0.5)
ax2.fill_between(df["date"], 80, 100, alpha=0.1, color="red")
ax2.set_ylabel("Monthly KD")
ax2.set_ylim(0, 100)
ax2.legend(loc="upper left")
ax2.grid(True, alpha=0.3)

# Panel 3: Leading Index with bottom markers
ax3 = axes[2]
ax3.plot(df["date"], df["leading_index"], "g-", linewidth=1.5)
bottoms = df[df["is_bottom"]]
ax3.scatter(bottoms["date"], bottoms["leading_index"], c="red", marker="^", s=80, zorder=5)
ax3.set_ylabel("Leading Index")
ax3.set_xlabel("Date")
ax3.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(OUTPUT / "h057_bottom_kd_exit.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"\nSaved: {OUTPUT / 'h057_bottom_kd_exit.png'}")
