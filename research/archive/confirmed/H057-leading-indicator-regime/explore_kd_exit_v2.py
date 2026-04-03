"""
H057 探索 v2：底部進場 + KD 跌破 80 出場（正確版）

修正：
- KD 使用實際月 OHLC（從 DB），參數 (9,3,3)
- 領先指標用 CSV（涵蓋 2018/8~2026/2）
- 兩者合併後取交集時間範圍
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


# ── 1. Load Monthly OHLC from DB ────────────────────────────────────────

conn = duckdb.connect(str(DB_PATH), read_only=True)
ohlc = conn.execute("""
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
conn.close()

ohlc["month"] = pd.to_datetime(ohlc["month"])
print(f"DB monthly OHLC: {ohlc['month'].min():%Y/%m} ~ {ohlc['month'].max():%Y/%m} ({len(ohlc)} months)")


# ── 2. Calculate KD (9,3,3) with actual H/L/C ───────────────────────────

k_period, smooth_k, d_period = 9, 3, 3

low_min = ohlc["low"].rolling(k_period).min()
high_max = ohlc["high"].rolling(k_period).max()
rsv = (ohlc["close"] - low_min) / (high_max - low_min) * 100
ohlc["K"] = rsv.rolling(smooth_k).mean()
ohlc["D"] = ohlc["K"].rolling(d_period).mean()


# ── 3. Load Leading Indicator ────────────────────────────────────────────

li = pd.read_csv(BASE / "data" / "leading_indicator.csv")
li["date"] = pd.to_datetime(li["date"], format="%Y/%m")
li["pub_date"] = pd.to_datetime(li["last_working_day"], format="%Y/%m/%d")
li = li.sort_values("date").reset_index(drop=True)

# Turning points
li["direction"] = np.sign(li["leading_index"].diff())
li["prev_direction"] = li["direction"].shift(1)
li["is_bottom"] = (li["direction"] > 0) & (li["prev_direction"] < 0)

print(f"Leading Indicator: {li['date'].min():%Y/%m} ~ {li['date'].max():%Y/%m} ({len(li)} months)")


# ── 4. Merge on month ───────────────────────────────────────────────────

# Leading indicator date = the month it describes
# OHLC month = the month of the candle
# They should match: e.g., 2024/01 leading indicator → 2024/01 OHLC candle
# But the publication is T+1 month delayed

df = pd.merge(li, ohlc[["month", "open", "high", "low", "close", "K", "D"]],
              left_on="date", right_on="month", how="inner", suffixes=("_li", "_ohlc"))

# Use OHLC close as the actual TAIEX price (more accurate than publication date)
# But for trading: we can only act AFTER publication (T+1 month)
# So entry price should be the OHLC close of the publication month

print(f"Merged range: {df['date'].min():%Y/%m} ~ {df['date'].max():%Y/%m} ({len(df)} months)")
print()

# KD exit signal
df["above_80"] = df["K"] > 80
df["prev_above_80"] = df["above_80"].shift(1).fillna(False).astype(bool)
df["kd_exit"] = df["prev_above_80"] & (~df["above_80"])

# Show KD values
print("=== Monthly KD (9,3,3) with actual H/L/C ===")
print(f"{'Month':>8s}  {'Close':>8s}  {'K':>6s}  {'D':>6s}  {'LI':>6s}  {'Dir':>4s}  Signals")
print("-" * 70)
for _, row in df.iterrows():
    signals = []
    if row["is_bottom"]:
        signals.append("BOTTOM")
    if row["kd_exit"]:
        signals.append("KD_EXIT")
    if row["above_80"]:
        signals.append("K>80")
    sig_str = ", ".join(signals)
    print(f"{row['date']:%Y/%m}  {row['close']:8.0f}  {row['K']:6.1f}  {row['D']:6.1f}  "
          f"{row['leading_index']:6.2f}  {row['direction']:+4.0f}  {sig_str}")
print()


# ── 5. Strategy Simulation ──────────────────────────────────────────────

def simulate(df, n_confirm=1):
    """
    Entry: Leading indicator bottom turn with N-month confirmation.
           Enter at the close of the confirmation month.
           (In practice: act on publication date, which is ~T+1 month)
    Exit:  Monthly K drops below 80.
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
            signal_idx = idx + n_confirm
            if signal_idx < len(df):
                confirmed_bottoms.add(signal_idx)

    for i in range(len(df)):
        row = df.iloc[i]

        if not in_position:
            if i in confirmed_bottoms:
                in_position = True
                entry_price = row["close"]
                entry_date = row["date"]
                entry_k = row["K"]
        else:
            if row["kd_exit"]:
                exit_price = row["close"]
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

    # Still open
    if in_position:
        last = df.iloc[-1]
        ret_pct = (last["close"] - entry_price) / entry_price * 100
        hold_months = (last["date"].year - entry_date.year) * 12 + last["date"].month - entry_date.month
        trades.append({
            "entry_date": entry_date,
            "exit_date": last["date"],
            "entry_price": entry_price,
            "exit_price": last["close"],
            "entry_k": entry_k,
            "exit_k": last["K"],
            "return_pct": ret_pct,
            "hold_months": hold_months,
            "note": "still open",
        })

    return pd.DataFrame(trades)


print("=" * 80)
print("策略：領先指標 Bottom 進場 + 月 KD(9,3,3) 跌破 80 出場")
print("KD 使用實際月 K 線 OHLC 計算")
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


# ── 6. KD Exit Aftermath ────────────────────────────────────────────────

print()
print("=" * 80)
print("跌破 80 後走勢驗證（出場是否正確？）")
print("=" * 80)

exits = df[df["kd_exit"]].copy()
print(f"\n跌破 80 事件數: {len(exits)}")
print()

for _, row in exits.iterrows():
    idx = df.index.get_loc(row.name)
    base = row["close"]
    rets = {}
    for n_fwd in [1, 3, 6]:
        if idx + n_fwd < len(df):
            fwd = df.iloc[idx + n_fwd]["close"]
            rets[n_fwd] = (fwd - base) / base * 100
        else:
            rets[n_fwd] = None
    r1 = f"{rets[1]:+.1f}%" if rets[1] is not None else "N/A"
    r3 = f"{rets[3]:+.1f}%" if rets[3] is not None else "N/A"
    r6 = f"{rets[6]:+.1f}%" if rets[6] is not None else "N/A"
    print(f"  {row['date']:%Y/%m}  K={row['K']:.1f}  Close={base:.0f}  "
          f"+1M={r1}  +3M={r3}  +6M={r6}")

print()
print("--- 跌破 80 後報酬統計 ---")
for n_fwd in [1, 3, 6]:
    rets = []
    for _, row in exits.iterrows():
        idx = df.index.get_loc(row.name)
        if idx + n_fwd < len(df):
            fwd = df.iloc[idx + n_fwd]["close"]
            rets.append((fwd - row["close"]) / row["close"] * 100)
    if rets:
        rets = np.array(rets)
        print(f"  +{n_fwd}M: mean={np.mean(rets):+.2f}%  median={np.median(rets):+.2f}%  "
              f"N={len(rets)}  hit(neg)={np.mean(rets < 0)*100:.0f}%")


# ── 7. Visualization ────────────────────────────────────────────────────

trades_n1 = simulate(df, n_confirm=1)

fig, axes = plt.subplots(3, 1, figsize=(14, 10))

# Panel 1: TAIEX with trade markers
ax1 = axes[0]
ax1.plot(df["date"], df["close"], "k-", linewidth=1.2)

for _, t in trades_n1.iterrows():
    ax1.axvspan(t["entry_date"], t["exit_date"], alpha=0.15, color="blue")
    ax1.scatter(t["entry_date"], t["entry_price"], c="red", marker="^", s=120, zorder=5)
    note = t.get("note", "")
    if pd.isna(note) or "open" not in str(note):
        ax1.scatter(t["exit_date"], t["exit_price"], c="green", marker="v", s=120, zorder=5)

ax1.set_ylabel("TAIEX (TX Close)")
ax1.set_title("H057 v2: Bottom Entry (N=1) + KD(9,3,3) Exit (<80) — Correct OHLC")
ax1.grid(True, alpha=0.3)

# Panel 2: KD
ax2 = axes[1]
ax2.plot(df["date"], df["K"], "b-", linewidth=1.5, label="K")
ax2.plot(df["date"], df["D"], "r--", linewidth=1, alpha=0.7, label="D")
ax2.axhline(80, color="gray", linestyle="--", alpha=0.5)
ax2.axhline(20, color="gray", linestyle="--", alpha=0.5)
ax2.fill_between(df["date"], 80, 100, alpha=0.1, color="red")
ax2.set_ylabel("Monthly KD (9,3,3)")
ax2.set_ylim(0, 100)
ax2.legend(loc="upper left")
ax2.grid(True, alpha=0.3)

# Panel 3: Leading Index
ax3 = axes[2]
ax3.plot(df["date"], df["leading_index"], "g-", linewidth=1.5)
bottoms = df[df["is_bottom"]]
ax3.scatter(bottoms["date"], bottoms["leading_index"], c="red", marker="^", s=80, zorder=5)
ax3.set_ylabel("Leading Index")
ax3.set_xlabel("Date")
ax3.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(OUTPUT / "h057_bottom_kd_exit_v2.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"\nSaved: {OUTPUT / 'h057_bottom_kd_exit_v2.png'}")
