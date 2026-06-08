"""
H108 利潤集中度 — Phase 1 分佈診斷

A. 策略自身報酬集中度：top-K 佔 gross profit、剔每年 top-N 後淨利、Gini、最大贏家/均贏；EstHL vs Reversal
B. 對市場大動日依賴：策略 PnL vs 市場|日漲跌幅|、剔市場大動日後 edge
benchmark：對稱常態模擬（同 N/mean/std）的 top-K share + 市場 buy-hold 自身集中度（防「剔贏家必降」機械廢話）

trade log：output/s001_esthl_2021-01-01.csv、output/s002_reversal_2021-01-01.csv
"""
import duckdb
import numpy as np
import pandas as pd
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).parent / "results"
OUT.mkdir(exist_ok=True)
RNG = np.random.default_rng(7)
STRATS = {"EstHL": "output/s001_esthl_2021-01-01.csv",
          "Reversal": "output/s002_reversal_2021-01-01.csv"}


def gini_gross(pnl):
    """正報酬(gross profit)的 Gini，衡量贏家集中度。"""
    w = np.sort(pnl[pnl > 0])
    n = len(w)
    if n == 0:
        return np.nan
    cum = np.cumsum(w)
    return (n + 1 - 2 * np.sum(cum) / cum[-1]) / n


def topk_gross_share(pnl, k):
    w = pnl[pnl > 0]
    if w.sum() == 0:
        return np.nan
    return np.sort(w)[::-1][:k].sum() / w.sum()


def remove_topn_per_year(d, n):
    """每年剔 top-n 獲利交易後的全期淨利%（與年度）。"""
    kept = []
    for yr, g in d.groupby("yr"):
        g2 = g.sort_values("pct", ascending=False).iloc[n:]   # 去掉前 n 大
        kept.append(g2)
    k = pd.concat(kept) if kept else d.iloc[0:0]
    return k["pct"].sum()


# ---------------------------------------------------------------- market daily return
con = duckdb.connect("data/futures.duckdb", read_only=True)
mkt = con.sql("""
    WITH d AS (
      SELECT timestamp::date dt,
             first(close ORDER BY timestamp) FILTER (WHERE timestamp::time>=TIME '08:45') o,
             last(close ORDER BY timestamp)  FILTER (WHERE timestamp::time<=TIME '13:45') c
      FROM ohlcv_1m WHERE symbol='TX' AND timestamp::time BETWEEN TIME '08:45' AND TIME '13:45'
      GROUP BY dt)
    SELECT dt, (c-o)/o*100 AS mret FROM d
""").df()
con.close()
mkt["dt"] = pd.to_datetime(mkt["dt"])
mkt["absmove"] = mkt["mret"].abs()
mkt["yr"] = mkt["dt"].dt.year

print("=" * 96)
print("  H108 利潤集中度診斷")
print("=" * 96)

data = {}
for name, path in STRATS.items():
    d = pd.read_csv(path, parse_dates=["EntryTime"]).sort_values("EntryTime")
    d["pct"] = d["ReturnPct"] * 100
    d["pts"] = d["PnL"]
    d["dt"] = d["EntryTime"].dt.normalize()
    d["yr"] = d["EntryTime"].dt.year
    data[name] = d
    pnl = d["pct"].to_numpy()
    tot = pnl.sum()
    print(f"\n###### {name}  N={len(d)}  全期淨利%={tot:+.1f}  勝率={(pnl>0).mean():.0%} ######")
    print(f"  最大贏家={pnl.max():+.2f}%  均贏={pnl[pnl>0].mean():+.3f}%  最大/均贏={pnl.max()/pnl[pnl>0].mean():.1f}x  "
          f"skew={pd.Series(pnl).skew():.2f}  Gini(gross)={gini_gross(pnl):.3f}")
    print(f"  top-K 交易佔 gross profit： top1={topk_gross_share(pnl,1):.0%}  top5={topk_gross_share(pnl,5):.0%}  "
          f"top10={topk_gross_share(pnl,10):.0%}  top20={topk_gross_share(pnl,20):.0%}")
    # 剔每年 top-N
    print("  剔每年 top-N 獲利交易後 全期淨利%：")
    for n in (0, 1, 3, 5, 10):
        rem = remove_topn_per_year(d, n)
        print(f"    剔 top-{n:<2}/年 → {rem:+.1f}%  ({rem/tot*100 if tot else 0:.0f}% of 原淨利)"
              + ("  ← 轉負" if rem < 0 <= tot else ""))
    # benchmark：同 N/mean/std 常態模擬 top5 gross share
    sims = []
    mu, sd = pnl.mean(), pnl.std()
    for _ in range(2000):
        s = RNG.normal(mu, sd, len(pnl))
        sims.append(topk_gross_share(s, 5))
    sims = np.array(sims)
    real5 = topk_gross_share(pnl, 5)
    print(f"  benchmark(常態模擬 同N/μ/σ) top5 gross share: 模擬中位={np.nanmedian(sims):.0%}  "
          f"真實={real5:.0%}  p(真≥模擬)={ (sims<=real5).mean():.2f} → "
          + ("集中度超機械效應✔" if (sims<=real5).mean()>0.95 else "未超 benchmark"))

# ---------------------------------------------------------------- B. 對市場大動日依賴
print("\n" + "=" * 96)
print("  B. 對市場大動日依賴")
for name, d in data.items():
    m = d.merge(mkt[["dt", "absmove", "mret"]], on="dt", how="left")
    m = m.dropna(subset=["absmove"])
    corr = np.corrcoef(m["absmove"], m["pct"])[0, 1]
    print(f"\n  {name}: corr(市場|move|, 策略PnL%)={corr:+.3f}")
    m["q"] = pd.qcut(m["absmove"], 4, labels=False)
    print("   市場|move|四分位  |move|中位%  策略均PnL%  策略勝率  N")
    for q, g in m.groupby("q"):
        print(f"    Q{int(q)}            {g.absmove.median():.2f}        {g.pct.mean():+.3f}     {(g.pct>0).mean():.0%}    {len(g)}")
    # 剔每年市場 |move| top-N 大動日
    tot = m["pct"].sum()
    for n in (3, 5, 10):
        kept = []
        for yr, g in m.groupby("yr"):
            big = mkt[(mkt.yr == yr)].nlargest(n, "absmove")["dt"]
            kept.append(g[~g["dt"].isin(set(big))])
        rem = pd.concat(kept)["pct"].sum()
        print(f"    剔每年市場|move| top-{n} 大動日 → 全期淨利 {rem:+.1f}% ({rem/tot*100 if tot else 0:.0f}% of 原)")

# 市場 buy-hold 自身集中度（benchmark）
print(f"\n  [benchmark] 市場 buy-hold 日報酬自身集中度：剔每年漲幅 top-5 日後 buy-hold 全期報酬")
m2 = mkt.dropna(subset=["mret"]).copy()
tot_bh = m2["mret"].sum()
kept = []
for yr, g in m2.groupby("yr"):
    kept.append(g.sort_values("mret", ascending=False).iloc[5:])
rem_bh = pd.concat(kept)["mret"].sum()
print(f"    buy-hold 全期日報酬和={tot_bh:+.1f}%；剔每年 top-5 漲日後={rem_bh:+.1f}% ({rem_bh/tot_bh*100:.0f}% of 原)")

# ---------------------------------------------------------------- plot
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
for name, d in data.items():
    pnl = np.sort(d["pct"].to_numpy())[::-1]
    cum = np.cumsum(pnl) / pnl.sum() if pnl.sum() else np.cumsum(pnl)
    axes[0].plot(np.arange(1, len(pnl) + 1) / len(pnl) * 100, cum * 100, label=name)
axes[0].plot([0, 100], [0, 100], "k--", lw=.6, label="均勻(無集中)")
axes[0].set_title("Pareto：累計淨利% vs 交易百分位(由大到小)")
axes[0].set_xlabel("交易百分位 %"); axes[0].set_ylabel("累計淨利 %"); axes[0].legend(fontsize=8)
for name, d in data.items():
    m = d.merge(mkt[["dt", "absmove"]], on="dt", how="left").dropna(subset=["absmove"])
    axes[1].scatter(m["absmove"], m["pct"], s=6, alpha=.3, label=name)
axes[1].axhline(0, color="k", lw=.5)
axes[1].set_title("策略PnL% vs 市場|日move|%"); axes[1].set_xlabel("市場|move|%"); axes[1].set_ylabel("策略PnL%")
axes[1].legend(fontsize=8)
plt.tight_layout()
plt.savefig(OUT / "h108_distribution.png", dpi=110)
print(f"\nsaved {OUT/'h108_distribution.png'}")
