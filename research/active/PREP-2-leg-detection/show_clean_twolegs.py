"""語意定義的『乾淨兩腳』日：leg1≥0.5A 衝勢 + 回撤∈[0.3,0.9]×leg1 + leg2 同向。
標示 leg2 是否突破 P1（成功 vs 失敗腳）。抓最近 N 個給視覺驗證。"""
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
LEG1_MIN = 0.5      # leg1 至少 0.5 ATR（真衝勢，跳過震盪開盤 twitch）
RETR_LO, RETR_HI = 0.3, 0.9   # 真回撤band
N_SHOW = 8

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
hhmm = lambda i: f"{(525 + i)//60:02d}:{(525 + i) % 60:02d}"


def first_clean_twoleg(pr, a):
    """找第一組符合語意的 (P0..P3) 兩腳；回傳 (pivots4, leg1,retr,leg2, success) 或 None。"""
    legs = legs_from_pivots(detect_legs(pr, theta=K * a))
    for j in range(len(legs) - 1):
        l1, rt = legs[j], legs[j + 1]
        if j + 2 >= len(legs):
            break
        l2 = legs[j + 2]
        if l1["adp"] < LEG1_MIN * a:
            continue
        r = rt["adp"] / l1["adp"]
        if not (RETR_LO <= r <= RETR_HI):
            continue
        # leg2 同向 leg1（ZigZag 必然），成功=突破 P1
        success = (l2["p1"] > l1["p1"]) if l1["dir"] > 0 else (l2["p1"] < l1["p1"])
        return (l1["i0"], l1["i1"], rt["i1"], l2["i1"]), l1, rt, l2, success, r
    return None


picked = []
for d in sorted(days.keys(), reverse=True):
    a = atr.get(d, np.nan)
    if not np.isfinite(a):
        continue
    res = first_clean_twoleg(days[d]["close"].to_numpy(), a)
    if res:
        picked.append((d, a, res))
    if len(picked) >= N_SHOW:
        break
picked = picked[::-1]

# 統計：全期符合比例
nmatch = sum(1 for d in days if np.isfinite(atr.get(d, np.nan))
             and first_clean_twoleg(days[d]["close"].to_numpy(), atr[d]))
nvalid = sum(1 for d in days if np.isfinite(atr.get(d, np.nan)))
print(f"=== 語意乾淨兩腳：全期 {nmatch}/{nvalid} 日 ({nmatch/nvalid:.0%}) 含至少一組 ===")
print(f"   條件：leg1≥{LEG1_MIN}A、回撤∈[{RETR_LO},{RETR_HI}]×leg1、leg2同向\n")
for d, a, (idx4, l1, rt, l2, suc, r) in picked:
    p = days[d].set_index("mins")["close"]
    seq = " → ".join(f"{hhmm(i)}@{p[i]:.0f}" for i in idx4)
    print(f"  {d.date()} (ATR={a:.0f})  {seq}")
    print(f"      leg1={l1['adp']/a:.2f}A({'升' if l1['dir']>0 else '跌'})  回撤={r:.2f}×leg1  "
          f"leg2={l2['adp']/a:.2f}A  等幅 leg2/leg1={l2['adp']/l1['adp']:.2f}  "
          f"→ {'✅突破P1(成功腳)' if suc else '❌未過P1(失敗腳)'}")

fig, axes = plt.subplots(2, 4, figsize=(19, 8))
for ax, (d, a, (idx4, l1, rt, l2, suc, r)) in zip(axes.flat, picked):
    g = days[d]
    ax.plot(g["mins"], g["close"], color="#ccc", lw=.8, zorder=1)
    ys = [days[d].set_index("mins")["close"][i] for i in idx4]
    ax.plot(idx4, ys, "-o", color=("#c0392b" if suc else "#e67e22"), lw=2, ms=5, zorder=3)
    labs = ["P0", "P1", "P2", "P3"]
    for i, lb, yy in zip(idx4, labs, ys):
        ax.annotate(lb, (i, yy), fontsize=8, color="#2980b9", fontweight="bold",
                    xytext=(0, 7), textcoords="offset points")
    ax.set_title(f"{d.date()}  leg1={l1['adp']/a:.1f}A 回撤{r:.0%} {'成功' if suc else '失敗'}", fontsize=9)
    ax.set_xlabel("分(0=08:45)", fontsize=7); ax.tick_params(labelsize=6)
plt.tight_layout()
out = HERE / "results" / "prep2_clean_twolegs.png"
plt.savefig(out, dpi=110)
print(f"\nsaved {out}")
