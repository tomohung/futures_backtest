"""
H057 補充探索：月 KD 進入 80 後跌破 80 作為出場訊號

假設：月 KD 進入 80 以上 = 強勢攻擊期，跌破 80 = 攻擊結束，出場等下一次機會
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

# ── Load Data ────────────────────────────────────────────────────────────

df = pd.read_csv(BASE / "data" / "leading_indicator.csv")
df["date"] = pd.to_datetime(df["date"], format="%Y/%m")
df["pub_date"] = pd.to_datetime(df["last_working_day"], format="%Y/%m/%d")
df = df.sort_values("date").reset_index(drop=True)


# ── Calculate Monthly KD ────────────────────────────────────────────────
# 用 TAIEX 月收盤計算 Stochastic (9,3,3)

def calc_kd(close, k_period=9, d_period=3, smooth_k=3):
    """Calculate Stochastic KD from monthly close prices."""
    low_min = close.rolling(k_period).min()
    high_max = close.rolling(k_period).max()
    rsv = (close - low_min) / (high_max - low_min) * 100
    rsv = rsv.fillna(50)
    # Smooth K = SMA of RSV
    k = rsv.rolling(smooth_k).mean()
    # D = SMA of K
    d = k.rolling(d_period).mean()
    return k, d

df["K"], df["D"] = calc_kd(df["taiex"])

print("=== Monthly KD Overview ===")
print(f"Data range: {df['date'].min():%Y/%m} ~ {df['date'].max():%Y/%m}")
print(f"K range: {df['K'].min():.1f} ~ {df['K'].max():.1f}")
print(f"Months with K > 80: {(df['K'] > 80).sum()}")
print(f"Months with K < 20: {(df['K'] < 20).sum()}")
print()

# ── Identify KD Phases ──────────────────────────────────────────────────
# 進入 80 區間 → 強勢攻擊
# 跌破 80 → 出場訊號

df["above_80"] = df["K"] > 80
df["prev_above_80"] = df["above_80"].shift(1).fillna(False).astype(bool)

# 進入 80：前月 K <= 80, 本月 K > 80
df["enter_80"] = (~df["prev_above_80"]) & df["above_80"]
# 跌破 80：前月 K > 80, 本月 K <= 80
df["exit_80"] = df["prev_above_80"] & (~df["above_80"])

print("=== KD > 80 Entry/Exit Events ===")
print()

entries = df[df["enter_80"] == True].copy()
exits = df[df["exit_80"] == True].copy()

print(f"進入 80 次數: {len(entries)}")
print(f"跌破 80 次數: {len(exits)}")
print()

# ── Analyze: Hold during K>80, Exit when K drops below 80 ───────────────

print("=== 策略模擬：K 進入 80 時做多，跌破 80 時出場 ===")
print()

trades = []
in_position = False
entry_price = None
entry_date = None

for i, row in df.iterrows():
    if row["enter_80"] and not in_position:
        in_position = True
        entry_price = row["taiex"]
        entry_date = row["date"]
    elif row["exit_80"] and in_position:
        exit_price = row["taiex"]
        exit_date = row["date"]
        ret_pct = (exit_price - entry_price) / entry_price * 100
        trades.append({
            "entry_date": entry_date,
            "exit_date": exit_date,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "return_pct": ret_pct,
            "hold_months": (exit_date.year - entry_date.year) * 12 + exit_date.month - entry_date.month,
        })
        in_position = False

# If still in position at end
if in_position:
    last = df.iloc[-1]
    ret_pct = (last["taiex"] - entry_price) / entry_price * 100
    trades.append({
        "entry_date": entry_date,
        "exit_date": last["date"],
        "entry_price": entry_price,
        "exit_price": last["taiex"],
        "return_pct": ret_pct,
        "hold_months": (last["date"].year - entry_date.year) * 12 + last["date"].month - entry_date.month,
        "note": "still open",
    })

trades_df = pd.DataFrame(trades)

print(f"{'Entry':>8s}  {'Exit':>8s}  {'EntryP':>8s}  {'ExitP':>8s}  {'Ret%':>7s}  {'Months':>6s}  Note")
print("-" * 70)
for _, t in trades_df.iterrows():
    note = t.get("note", "") if "note" in t else ""
    print(f"{t['entry_date']:%Y/%m}  {t['exit_date']:%Y/%m}  "
          f"{t['entry_price']:8.0f}  {t['exit_price']:8.0f}  "
          f"{t['return_pct']:+6.1f}%  {t['hold_months']:5d}M  {note}")

print()
print(f"總交易次數: {len(trades_df)}")
print(f"勝率: {(trades_df['return_pct'] > 0).mean()*100:.0f}%")
print(f"平均報酬: {trades_df['return_pct'].mean():+.2f}%")
print(f"平均持有月數: {trades_df['hold_months'].mean():.1f}M")
print(f"最大獲利: {trades_df['return_pct'].max():+.1f}%")
print(f"最大虧損: {trades_df['return_pct'].min():+.1f}%")


# ── Compare: KD exit vs. Buy-and-Hold ───────────────────────────────────

print()
print("=== 跌破 80 後的走勢（驗證出場是否正確）===")
print("跌破 80 後 1/3/6 個月的 TAIEX 報酬：")
print()

for _, row in exits.iterrows():
    idx = df.index.get_loc(row.name)
    base = row["taiex"]
    rets = {}
    for n in [1, 3, 6]:
        if idx + n < len(df):
            fwd = df.iloc[idx + n]["taiex"]
            rets[n] = (fwd - base) / base * 100
        else:
            rets[n] = None
    r1 = f"{rets[1]:+.1f}%" if rets[1] is not None else "N/A"
    r3 = f"{rets[3]:+.1f}%" if rets[3] is not None else "N/A"
    r6 = f"{rets[6]:+.1f}%" if rets[6] is not None else "N/A"
    print(f"  {row['date']:%Y/%m}  K={row['K']:.1f}  TAIEX={base:.0f}  "
          f"+1M={r1}  +3M={r3}  +6M={r6}")

# Stats for exits
print()
print("--- 跌破 80 後報酬統計 ---")
for n in [1, 3, 6]:
    rets = []
    for _, row in exits.iterrows():
        idx = df.index.get_loc(row.name)
        if idx + n < len(df):
            fwd = df.iloc[idx + n]["taiex"]
            rets.append((fwd - row["taiex"]) / row["taiex"] * 100)
    if rets:
        rets = np.array(rets)
        print(f"  +{n}M: mean={np.mean(rets):+.2f}%  median={np.median(rets):+.2f}%  "
              f"N={len(rets)}  hit(neg)={np.mean(rets < 0)*100:.0f}%")


# ── Also test: K enters 20 zone (oversold) as entry ────────────────────

print()
print("=== 補充：K < 20 超賣區進場 ===")

df["below_20"] = df["K"] < 20
df["prev_below_20"] = df["below_20"].shift(1).fillna(False).astype(bool)
df["exit_20"] = df["prev_below_20"] & (~df["below_20"])  # 離開 20 區間

for _, row in df[df["exit_20"] == True].iterrows():
    idx = df.index.get_loc(row.name)
    base = row["taiex"]
    rets = {}
    for n in [1, 3, 6]:
        if idx + n < len(df):
            fwd = df.iloc[idx + n]["taiex"]
            rets[n] = (fwd - base) / base * 100
        else:
            rets[n] = None
    r1 = f"{rets[1]:+.1f}%" if rets[1] is not None else "N/A"
    r3 = f"{rets[3]:+.1f}%" if rets[3] is not None else "N/A"
    r6 = f"{rets[6]:+.1f}%" if rets[6] is not None else "N/A"
    print(f"  {row['date']:%Y/%m}  K={row['K']:.1f}  TAIEX={base:.0f}  "
          f"+1M={r1}  +3M={r3}  +6M={r6}")


# ── Combined: Leading Indicator bottom + KD confirmation ────────────────

print()
print("=== 組合策略：領先指標 bottom 拐點 + 月 KD 確認 ===")
print()

# Load turning points from main explore
li_df = df.copy()
li_df["direction"] = np.sign(li_df["leading_index"].diff())
li_df["prev_direction"] = li_df["direction"].shift(1)
li_df["is_bottom"] = (li_df["direction"] > 0) & (li_df["prev_direction"] < 0)

print("領先指標 bottom + K < 50（低位啟動）：")
for _, row in li_df[li_df["is_bottom"]].iterrows():
    k_val = row["K"]
    idx = df.index.get_loc(row.name)
    marker = " <-- K<50" if k_val < 50 else ""
    rets_3m = ""
    if idx + 3 < len(df):
        fwd = df.iloc[idx + 3]["taiex"]
        ret = (fwd - row["taiex"]) / row["taiex"] * 100
        rets_3m = f"+3M={ret:+.1f}%"
    print(f"  {row['date']:%Y/%m}  K={k_val:.1f}  TAIEX={row['taiex']:.0f}  {rets_3m}{marker}")

print()
print("=== 完整策略構想 ===")
print("進場：領先指標 bottom 拐點（N=3 確認）+ K 從低位回升")
print("持有：K > 80 進入強勢攻擊期")
print("出場：K 跌破 80 → 攻擊結束，退出等待")
print("不做空：top 拐點僅作為警示，不建立空頭部位")


# ── Visualization ───────────────────────────────────────────────────────

fig, axes = plt.subplots(3, 1, figsize=(14, 10))

# Panel 1: TAIEX with KD>80 shading
ax1 = axes[0]
ax1.plot(df["date"], df["taiex"], "k-", linewidth=1.5)

# Shade KD>80 periods
in_zone = False
zone_start = None
for _, row in df.iterrows():
    if row["above_80"] and not in_zone:
        zone_start = row["date"]
        in_zone = True
    elif not row["above_80"] and in_zone:
        ax1.axvspan(zone_start, row["date"], alpha=0.2, color="red", label="K>80" if zone_start == df[df["above_80"]].iloc[0]["date"] else "")
        in_zone = False
if in_zone:
    ax1.axvspan(zone_start, df["date"].iloc[-1], alpha=0.2, color="red")

# Mark exit signals
for _, row in exits.iterrows():
    ax1.axvline(row["date"], color="blue", alpha=0.5, linestyle="--")

ax1.set_ylabel("TAIEX")
ax1.set_title("H057: TAIEX with Monthly KD > 80 Zones (red) & Exit Signals (blue)")
ax1.grid(True, alpha=0.3)

# Panel 2: KD
ax2 = axes[1]
ax2.plot(df["date"], df["K"], "b-", linewidth=1.5, label="K")
ax2.plot(df["date"], df["D"], "r--", linewidth=1, label="D")
ax2.axhline(80, color="gray", linestyle="--", alpha=0.5)
ax2.axhline(20, color="gray", linestyle="--", alpha=0.5)
ax2.fill_between(df["date"], 80, 100, alpha=0.1, color="red")
ax2.fill_between(df["date"], 0, 20, alpha=0.1, color="green")
ax2.set_ylabel("KD")
ax2.set_ylim(0, 100)
ax2.legend(loc="upper left")
ax2.grid(True, alpha=0.3)

# Panel 3: Leading Index
ax3 = axes[2]
ax3.plot(df["date"], df["leading_index"], "g-", linewidth=1.5, label="Leading Index")
ax3.set_ylabel("Leading Index")
ax3.set_xlabel("Date")
ax3.legend(loc="upper left")
ax3.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(OUTPUT / "h057_kd_analysis.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"\nSaved: {OUTPUT / 'h057_kd_analysis.png'}")
