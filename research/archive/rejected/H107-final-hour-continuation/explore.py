"""
H107 尾盤趨勢延續 — Phase 1 分佈探索（零策略，早盤 vs 尾盤對比）

(A) 30 分區塊動能矩陣：定位日內續行最強落在哪段
(B) 方向動能續行：錨點 t 的 corr(進場前走勢, t→收盤剩餘走勢) + 同向率，早盤錨 vs 尾盤錨
(C) 突破續行：t 破前 30 分區間 → 收盤延伸率(續行) vs 回補，對比 baseline 漂移
全部以 ATR 正規化 / 對比無條件 baseline，核心是「尾盤是否顯著 > 早盤」。
"""
import duckdb
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from scipy.stats import spearmanr

OUT = Path(__file__).parent / "results"
OUT.mkdir(exist_ok=True)
ATR_N = 10

con = duckdb.connect("data/futures.duckdb", read_only=True)
df = con.sql("""
    SELECT timestamp, high, low, close
    FROM ohlcv_1m
    WHERE symbol='TX' AND timestamp::time BETWEEN TIME '08:45' AND TIME '13:45'
    ORDER BY timestamp
""").df()
con.close()
df["date"] = df["timestamp"].dt.normalize()
df["mins"] = (df["timestamp"].dt.hour * 60 + df["timestamp"].dt.minute) - (8 * 60 + 45)

# pivot date × minute（close / high / low），minute 0..300
C = df.pivot_table(index="date", columns="mins", values="close").sort_index()
H = df.pivot_table(index="date", columns="mins", values="high").sort_index()
L = df.pivot_table(index="date", columns="mins", values="low").sort_index()
C = C.ffill(axis=1).bfill(axis=1)
H = H.ffill(axis=1).bfill(axis=1)
L = L.ffill(axis=1).bfill(axis=1)
day_range = (H.max(axis=1) - L.min(axis=1))
atr = day_range.rolling(ATR_N).mean().shift(1)
valid = atr.notna()
C, H, L, atr = C[valid], H[valid], L[valid], atr[valid]
opn, cls = C[0], C[300]
N = len(C)
print(f"=== SAMPLE === N={N} 交易日  {C.index.min().date()} → {C.index.max().date()}")

# ---------------------------------------------------------------- (A) 30 分區塊動能矩陣
print("\n###### (A) 區塊動能：corr(進場前走勢 open→t, 後續 t→t+30)  [續行>0 / fade<0] ######")
bnds = list(range(0, 301, 30))
print("  錨點t(分)  時刻    corr(prev,next30)  corr(prev,t→收)  同向率(t→收)  N")
contA = {}
for t in bnds[1:-1]:
    prev = (C[t] - opn) / atr
    nxt30 = (C[min(t + 30, 300)] - C[t]) / atr
    fwd = (cls - C[t]) / atr
    r_next = spearmanr(prev, nxt30)[0]
    r_fwd = spearmanr(prev, fwd)[0]
    sign_agree = (np.sign(cls - C[t]) == np.sign(C[t] - opn)).mean()
    hhmm = f"{8 + (525 + t)//60 - ((525+t)//60>0)*0:02d}".replace("","")  # placeholder
    hh = (525 + t) // 60; mm = (525 + t) % 60
    print(f"  {t:>6}    {hh:02d}:{mm:02d}      {r_next:+.3f}            {r_fwd:+.3f}          {sign_agree:.0%}        {N}")
    contA[t] = (r_fwd, sign_agree)

# ---------------------------------------------------------------- (B) 方向動能續行：早盤錨 vs 尾盤錨
print("\n###### (B) 方向動能續行（corr 進場前 × 剩餘, 同向率） ######")
print("  baseline: 無條件 P(close>open)=%.0f%%  P(close>price_t) 隨 t 漂移" % (cls > opn).mean())
anchors = {"早盤09:15": 30, "早盤09:45": 60, "早盤10:15": 90, "午盤11:45": 180,
           "尾盤12:45(last60)": 240, "尾盤13:00(last45)": 255, "尾盤13:15(last30)": 270}
rowsB = []
for name, t in anchors.items():
    prev = (C[t] - opn) / atr
    fwd = (cls - C[t]) / atr
    r = spearmanr(prev, fwd)[0]
    sign_agree = (np.sign(cls - C[t]) == np.sign(C[t] - opn)).mean()
    base_up = (cls > C[t]).mean()
    print(f"  {name:<18} corr(prev,剩餘)={r:+.3f}  同向續行率={sign_agree:.0%}  "
          f"(baseline P(close>price_t)={base_up:.0%})  剩餘ATR均={fwd.abs().mean():.2f}")
    rowsB.append(dict(name=name, t=t, corr=r, sign_agree=sign_agree))

# ---------------------------------------------------------------- (C) 突破續行：延伸率 vs baseline
print("\n###### (C) 突破前30分區間 → 收盤延伸率(續行) vs 回補；對比 baseline 漂移 ######")
print("  錨點         破上沿N 上破續漲率 | 破下沿N 下破續跌率 | baseline同向 | 淨續行(延伸−baseline)")
rowsC = []
for name, t in anchors.items():
    if t < 30:
        continue
    win_h = H.loc[:, t - 30:t - 1].max(axis=1)
    win_l = L.loc[:, t - 30:t - 1].min(axis=1)
    up = C[t] > win_h          # 向上突破
    dn = C[t] < win_l          # 向下突破
    ext_up = (cls > C[t])[up].mean() if up.sum() else np.nan      # 續漲
    ext_dn = (cls < C[t])[dn].mean() if dn.sum() else np.nan      # 續跌
    base_up = (cls > C[t]).mean()
    base_dn = (cls < C[t]).mean()
    net = np.nanmean([ext_up - base_up, ext_dn - base_dn])        # 超額續行
    print(f"  {name:<18} {int(up.sum()):>4} {ext_up:>8.0%}  | {int(dn.sum()):>4} {ext_dn:>8.0%}  | "
          f"{base_up:.0%}/{base_dn:.0%}    | {net:+.1%}")
    rowsC.append(dict(name=name, t=t, ext_up=ext_up, ext_dn=ext_dn, net=net))

# ---------------------------------------------------------------- plots
dfB = pd.DataFrame(rowsB); dfC = pd.DataFrame(rowsC)
fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
ts = sorted(contA.keys())
axes[0].plot(ts, [contA[t][0] for t in ts], "o-", color="#c0392b", label="corr(進場前,剩餘) 續行")
axes[0].axhline(0, color="k", lw=.6)
axes[0].axvspan(240, 300, color="#f9e79f", alpha=.5, label="尾盤(last60)")
axes[0].set_title("(A/B) 方向動能續行 vs 錨點時刻"); axes[0].set_xlabel("錨點 t(分, 0=08:45)")
axes[0].set_ylabel("續行 corr"); axes[0].legend(fontsize=8)
axes[1].plot(dfC.t, dfC.net, "s-", color="#2980b9", label="淨超額續行 (延伸−baseline)")
axes[1].axhline(0, color="k", lw=.6); axes[1].axvspan(240, 300, color="#f9e79f", alpha=.5)
axes[1].set_title("(C) 突破淨超額續行 vs 錨點"); axes[1].set_xlabel("錨點 t(分)")
axes[1].set_ylabel("延伸率 − baseline"); axes[1].legend(fontsize=8)
plt.tight_layout()
plt.savefig(OUT / "h107_distribution.png", dpi=110)
print(f"\nsaved {OUT/'h107_distribution.png'}")
