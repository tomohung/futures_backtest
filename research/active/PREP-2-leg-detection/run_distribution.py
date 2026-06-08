"""
PREP-2 leg 定義驗證 + k 校準（零策略，跨所有交易日）

跑 detect_legs 於每日（θ=k×ATR10），報：
 - 一天幾隻腳的分佈（校準 k）
 - 有 ≥3 腳日：回撤深度(P1→P2/leg1)、leg2/leg1 等幅比、leg2/leg1 時間比、leg2 失敗率(未過 P1)
驗證「第二隻腳」定義是否合理，並挑一個產出 2–4 腳/日的 k。
"""
import sys
import duckdb
import numpy as np
import pandas as pd
import datetime as dt
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from prep2_legs import detect_legs, legs_from_pivots

OUT = HERE / "results"
OUT.mkdir(exist_ok=True)

con = duckdb.connect(str(ROOT / "data" / "futures.duckdb"), read_only=True)
df = con.sql("""SELECT timestamp, close, high, low FROM ohlcv_1m
               WHERE symbol='TX' AND timestamp::time BETWEEN TIME '08:45' AND TIME '13:45'
               ORDER BY timestamp""").df()
con.close()
df["date"] = df["timestamp"].dt.normalize()
df["mins"] = (df["timestamp"].dt.hour * 60 + df["timestamp"].dt.minute) - 525

# ATR10（前10日日盤range均, shift）
rng = df.groupby("date").apply(lambda x: x["high"].max() - x["low"].min(), include_groups=False)
atr = rng.rolling(10).mean().shift(1)

days = {d: g.sort_values("mins")["close"].to_numpy() for d, g in df.groupby("date")}
print(f"=== N={len(days)} 交易日 ===")

KS = [0.2, 0.3, 0.4, 0.5]
print("\n###### k 校準：一天腳數分佈（θ=k×ATR10）######")
print("  k     腳數中位  腳數均  P(≥3腳)  P(=1腳)  P(≥5腳)")
legcount = {}
for k in KS:
    counts = []
    for d, pr in days.items():
        a = atr.get(d, np.nan)
        if not np.isfinite(a):
            continue
        piv = detect_legs(pr, theta=k * a)
        counts.append(len(piv) - 1)
    counts = np.array(counts)
    legcount[k] = counts
    print(f"  {k:<5} {np.median(counts):>6.0f}  {counts.mean():>5.1f}  {(counts>=3).mean():>6.0%}  "
          f"{(counts==1).mean():>6.0%}  {(counts>=5).mean():>6.0%}")

# 用 k=0.3 看腳結構分佈（之後可調）
def analyze_k(k):
    retr, mag, timr, fail, n3 = [], [], [], [], 0
    for d, pr in days.items():
        a = atr.get(d, np.nan)
        if not np.isfinite(a):
            continue
        legs = legs_from_pivots(detect_legs(pr, theta=k * a))
        if len(legs) >= 3:
            n3 += 1
            l1, rt, l2 = legs[0], legs[1], legs[2]
            retr.append(rt["adp"] / l1["adp"])
            mag.append(l2["adp"] / l1["adp"])
            timr.append(l2["dt"] / l1["dt"] if l1["dt"] > 0 else np.nan)
            # 失敗：leg2 未過 leg1 極值(P1)
            if l1["dir"] > 0:
                fail.append(l2["p1"] <= l1["p1"])
            else:
                fail.append(l2["p1"] >= l1["p1"])
    return np.array(retr), np.array(mag), np.array(timr, dtype=float), np.array(fail), n3

print("\n###### 腳結構分佈（有 ≥3 腳日）######")
for k in KS:
    retr, mag, timr, fail, n3 = analyze_k(k)
    if n3 < 20:
        print(f"  k={k}: ≥3腳日僅 {n3}，樣本不足"); continue
    tm = timr[np.isfinite(timr)]
    print(f"\n  --- k={k}  ≥3腳日 N={n3} ---")
    print(f"    回撤深度 P1→P2/leg1：中位={np.median(retr):.2f}  IQR[{np.percentile(retr,25):.2f},{np.percentile(retr,75):.2f}]")
    print(f"    leg2/leg1 等幅比：  中位={np.median(mag):.2f}  IQR[{np.percentile(mag,25):.2f},{np.percentile(mag,75):.2f}]  P(0.7~1.3=近等幅)={((mag>=0.7)&(mag<=1.3)).mean():.0%}")
    print(f"    leg2/leg1 時間比：  中位={np.median(tm):.2f}  IQR[{np.percentile(tm,25):.2f},{np.percentile(tm,75):.2f}]")
    print(f"    leg2 失敗率(未過P1)：{fail.mean():.0%}")

# plot：k=0.3 的腳數分佈 + 等幅比/回撤分佈
k0 = 0.3
retr, mag, timr, fail, n3 = analyze_k(k0)
fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
axes[0].hist(legcount[k0], bins=range(1, 12), align="left", color="#7f8c8d", rwidth=.85)
axes[0].set_title(f"一天腳數分佈 (k={k0})"); axes[0].set_xlabel("腳數"); axes[0].set_ylabel("日數")
axes[1].hist(retr[retr < 2], bins=30, color="#2980b9"); axes[1].axvline(0.618, color="r", ls="--", label="0.618")
axes[1].set_title("回撤深度 P1→P2 / leg1"); axes[1].set_xlabel("比例"); axes[1].legend(fontsize=8)
axes[2].hist(mag[mag < 3], bins=30, color="#c0392b"); axes[2].axvline(1.0, color="k", ls="--", label="等幅=1.0")
axes[2].set_title("leg2/leg1 等幅比"); axes[2].set_xlabel("比例"); axes[2].legend(fontsize=8)
plt.tight_layout(); plt.savefig(OUT / "prep2_legs_distribution.png", dpi=110)
print(f"\nsaved {OUT/'prep2_legs_distribution.png'}")
