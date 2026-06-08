"""
H109 EstHL 殘留靜日濾網 — Phase 1（盤前預測子 vs 殘留靜日，增量於 NVF）

核心問題（gate 關鍵）：
 (Q1) 盤前可知預測子能否預測「當日 |day move|」，且夜盤(night_norm)以外有增量資訊？
 (Q2) 在 EstHL 實際進場日(N=170, 已過 NVF)，哪個盤前預測子能事前分出虧損的殘留靜日？
 (Q3) 增量於 night_norm？濾掉的日子是否誤殺 Q3 大贏家？

盤前預測子（皆 08:58 進場前可知）：
  night_norm（既有 NVF）、前1/3日日盤range%、OR寬度%(08:45–08:57)、|gap|%、前一日VIX
標的：當日 |day move|%（label，盤後）；EstHL ReturnPct%（實際交易結果）
"""
import duckdb
import numpy as np
import pandas as pd
import datetime as dt
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import spearmanr

OUT = Path(__file__).parent / "results"
OUT.mkdir(exist_ok=True)

con = duckdb.connect("data/futures.duckdb", read_only=True)
df = con.sql("""SELECT timestamp, open, high, low, close FROM ohlcv_1m
               WHERE symbol='TX' ORDER BY timestamp""").df()
vix = con.sql("SELECT date, vix FROM vixtwn ORDER BY date").df()
con.close()
df["t"] = df["timestamp"].dt.time
df["date"] = df["timestamp"].dt.normalize()

# ---- day session per day ----
day = df[(df.t >= dt.time(8, 45)) & (df.t <= dt.time(13, 45))]
g = day.groupby("date")
D = pd.DataFrame({
    "open": g.apply(lambda x: x.loc[x.t == dt.time(8, 45), "open"].iloc[0], include_groups=False),
    "close": g.apply(lambda x: x.loc[x.t == dt.time(13, 45), "close"].iloc[-1], include_groups=False),
    "dhigh": g["high"].max(), "dlow": g["low"].min(),
    "or_h": g.apply(lambda x: x.loc[x.t <= dt.time(8, 57), "high"].max(), include_groups=False),
    "or_l": g.apply(lambda x: x.loc[x.t <= dt.time(8, 57), "low"].min(), include_groups=False),
}).sort_index()
D["daymove"] = (D["close"] - D["open"]).abs() / D["open"] * 100      # 當日 |move|% (label)
D["dayrange"] = (D["dhigh"] - D["dlow"]) / D["open"] * 100
D["or_w"] = (D["or_h"] - D["or_l"]) / D["open"] * 100                # OR 寬度% (盤前可知)
D["pdr1"] = D["dayrange"].shift(1)                                   # 前一日日盤range%
D["pdr3"] = D["dayrange"].rolling(3).mean().shift(1)                # 前3日均
D["gap"] = (D["open"] - D["close"].shift(1)).abs() / D["open"] * 100  # |gap|%

# ---- night range → night_norm (既有 NVF) ----
night = df[(df.t >= dt.time(15, 0)) | (df.t <= dt.time(5, 0))].copy()
tdays = D.index.to_numpy()
open_dt = (D.index + pd.Timedelta(hours=8, minutes=45)).to_numpy()
idx = np.searchsorted(open_dt, night["timestamp"].to_numpy(), side="left")
night = night[idx < len(tdays)].copy()
night["own"] = tdays[idx[idx < len(tdays)]]
ng = night.groupby("own")
nrange = (ng["high"].max() - ng["low"].min())
D["night_range"] = nrange
D["night_ema20"] = D["night_range"].ewm(span=20, adjust=False).mean().shift(1)
D["night_norm"] = D["night_range"] / D["night_ema20"]                # 既有 NVF metric

# ---- prior-day VIX ----
vix["date"] = pd.to_datetime(vix["date"]).dt.normalize()
D = D.merge(vix.set_index("date")["vix"].rename("vix_prev").shift(1), left_index=True, right_index=True, how="left")
# 注意：vix shift 在 vix 自己的序列；改用 merge_asof 對齊前一交易日
vixs = vix.set_index("date")["vix"]
D["vix_prev"] = [vixs[vixs.index < d].iloc[-1] if (vixs.index < d).any() else np.nan for d in D.index]

PRED = ["night_norm", "pdr1", "pdr3", "or_w", "gap", "vix_prev"]
A = D.dropna(subset=["daymove", "night_norm", "pdr1", "vix_prev"]).copy()
print(f"=== ALL trading days N={len(A)}  {A.index.min().date()}→{A.index.max().date()} ===")

# ---- (Q1) 盤前預測子 vs 當日 |move|，增量於 night_norm ----
print("\n###### (Q1) 盤前預測子對『當日|move|』的預測力 + 增量於 night_norm ######")
# 先 regress daymove ~ night_norm 取殘差
from numpy.polynomial import polynomial as P
nn = A["night_norm"].to_numpy(); dm = A["daymove"].to_numpy()
b1, b0 = np.polyfit(nn, dm, 1)
resid = dm - (b0 + b1 * nn)
print(f"  {'預測子':<12}{'corr(pred,|move|)':>18}{'增量 corr(pred,殘差)':>22}")
for p in PRED:
    x = A[p].to_numpy()
    r_raw = spearmanr(x, dm)[0]
    r_inc = spearmanr(x, resid)[0] if p != "night_norm" else 0.0
    print(f"  {p:<12}{r_raw:>+18.3f}{r_inc:>+22.3f}")

# ---- (Q2) EstHL 進場日：盤前預測子能否分出虧損靜日 ----
est = pd.read_csv("output/s001_esthl_2021-01-01.csv", parse_dates=["EntryTime"])
est["date"] = est["EntryTime"].dt.normalize()
est["pct"] = est["ReturnPct"] * 100
E = est.merge(D[PRED + ["daymove"]], left_on="date", right_index=True, how="left").dropna(subset=PRED)
print(f"\n###### (Q2) EstHL 進場日 N={len(E)}（已過 NVF=殘留母體）盤前預測子分桶 × 期望 ######")
print(f"  baseline: EstHL 均PnL={E.pct.mean():+.3f}%  勝率={(E.pct>0).mean():.0%}")
for p in PRED:
    E["q"] = pd.qcut(E[p], 4, labels=False, duplicates="drop")
    means = E.groupby("q")["pct"].mean()
    wins = E.groupby("q")["pct"].apply(lambda s: (s > 0).mean())
    ns = E.groupby("q").size()
    rho = spearmanr(E[p], E["pct"])[0]
    seg = "  ".join(f"Q{q}:{means[q]:+.2f}%/{wins[q]:.0%}(n{ns[q]})" for q in means.index)
    print(f"  {p:<11} spear(pred,PnL)={rho:+.3f} | {seg}")

# ---- (Q3) 最佳預測子的低桶：誤殺 Q3 贏家? + 增量於 night_norm ----
print("\n###### (Q3) 增量檢定：控制 night_norm 後，最佳盤前預測子是否仍分離 EstHL PnL ######")
nnE = E["night_norm"].to_numpy(); pnlE = E["pct"].to_numpy()
bb1, bb0 = np.polyfit(nnE, pnlE, 1)
residE = pnlE - (bb0 + bb1 * nnE)
for p in [q for q in PRED if q != "night_norm"]:
    print(f"  {p:<11} 增量 spear(pred, EstHL_PnL殘差去night)={spearmanr(E[p], residE)[0]:+.3f}")

# plot
fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
for p in PRED:
    E["q"] = pd.qcut(E[p], 4, labels=False, duplicates="drop")
    axes[0].plot(range(4), E.groupby("q")["pct"].mean().values, "o-", label=p)
axes[0].axhline(0, color="k", lw=.5); axes[0].axhline(E.pct.mean(), color="gray", ls="--", lw=.7, label="baseline")
axes[0].set_title("EstHL 均PnL% vs 盤前預測子四分位"); axes[0].set_xlabel("預測子四分位(低→高)")
axes[0].set_ylabel("EstHL 均PnL%"); axes[0].legend(fontsize=7)
axes[1].scatter(A["night_norm"], A["daymove"], s=5, alpha=.25)
axes[1].set_title("夜盤 night_norm vs 當日|move|%（夜≠日的散度）")
axes[1].set_xlabel("night_norm"); axes[1].set_ylabel("當日|move|%"); axes[1].set_xlim(0, 3)
plt.tight_layout()
plt.savefig(OUT / "h109_distribution.png", dpi=110)
print(f"\nsaved {OUT/'h109_distribution.png'}")
