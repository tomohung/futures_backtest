"""最近 N 個『有第二腳(≥3腳)』交易日的 leg 結構視覺化 (k=0.3)。"""
import sys
import duckdb
import numpy as np
import pandas as pd
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from prep2_legs import detect_legs, legs_from_pivots

K = 0.3
N_SHOW = 10

con = duckdb.connect(str(ROOT / "data" / "futures.duckdb"), read_only=True)
df = con.sql("""SELECT timestamp, close, high, low FROM ohlcv_1m
               WHERE symbol='TX' AND timestamp::time BETWEEN TIME '08:45' AND TIME '13:45'
               ORDER BY timestamp""").df()
con.close()
df["date"] = df["timestamp"].dt.normalize()
df["mins"] = (df["timestamp"].dt.hour * 60 + df["timestamp"].dt.minute) - 525
rng = df.groupby("date").apply(lambda x: x["high"].max() - x["low"].min(), include_groups=False)
atr = rng.rolling(10).mean().shift(1)
days = {d: g.sort_values("mins") for d, g in df.groupby("date")}

# 由新到舊挑 ≥3 腳日
picked = []
for d in sorted(days.keys(), reverse=True):
    a = atr.get(d, np.nan)
    if not np.isfinite(a):
        continue
    pr = days[d]["close"].to_numpy()
    piv = detect_legs(pr, theta=K * a)
    if len(piv) - 1 >= 3:
        picked.append((d, a, piv))
    if len(picked) >= N_SHOW:
        break
picked = picked[::-1]   # 舊→新 顯示

print(f"=== 最近 {len(picked)} 個 ≥3 腳交易日 (k={K}) ===")
for d, a, piv in picked:
    legs = legs_from_pivots(piv)
    hhmm = lambda i: f"{(525 + i)//60:02d}:{(525 + i) % 60:02d}"
    seq = " → ".join(f"{hhmm(idx)}@{pr:.0f}" for idx, pr in piv)
    l1 = legs[0]["adp"]; ratios = " ".join(f"L{j+1}={l['adp']/a:.2f}A" for j, l in enumerate(legs))
    print(f"  {d.date()} (ATR={a:.0f}, {len(legs)}腳)  {seq}")
    print(f"      {ratios}  | 回撤/L1={legs[1]['adp']/l1:.2f}  L2/L1={legs[2]['adp']/l1:.2f}")

fig, axes = plt.subplots(2, 5, figsize=(20, 7.5))
for ax, (d, a, piv) in zip(axes.flat, picked):
    g = days[d]
    ax.plot(g["mins"], g["close"], color="#bbb", lw=.8, zorder=1)
    xs = [idx for idx, _ in piv]; ys = [pr for _, pr in piv]
    ax.plot(xs, ys, "-o", color="#c0392b", lw=1.6, ms=4, zorder=3)
    for j, (idx, pr) in enumerate(piv):
        ax.annotate(f"P{j}", (idx, pr), fontsize=7, color="#2980b9",
                    xytext=(0, 6 if j % 2 == 0 else -10), textcoords="offset points")
    ax.set_title(f"{d.date()}  ATR={a:.0f}  {len(piv)-1}腳", fontsize=9)
    ax.set_xlabel("分(0=08:45)", fontsize=7); ax.tick_params(labelsize=6)
plt.tight_layout()
out = HERE / "results" / "prep2_recent_days.png"
plt.savefig(out, dpi=110)
print(f"\nsaved {out}")
