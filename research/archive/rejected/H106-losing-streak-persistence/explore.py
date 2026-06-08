"""
H106 連虧後收手 — Phase 1 分佈探索（日度版，條件期望 vs IID 虛無）

用 EstHL/Reversal 全期 trade log（1 筆/日），測：連續 k 個虧損交易日後，下一筆條件期望/勝率
是否顯著低於無條件基準。核心防呆＝IID 洗牌：把損益序列隨機打散 N 次重算同一條件統計，
看真實值是否落在虛無分佈之外（真正正自相關），否則「連虧收手」只是賭徒謬誤。

trade log：output/s001_esthl_2021-01-01.csv、output/s002_reversal_2021-01-01.csv（重跑回測產生）
"""
import numpy as np
import pandas as pd
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).parent / "results"
OUT.mkdir(exist_ok=True)
RNG = np.random.default_rng(42)
N_SHUF = 5000
KS = [1, 2, 3, 4]

STRATS = {
    "EstHL": "output/s001_esthl_2021-01-01.csv",
    "Reversal": "output/s002_reversal_2021-01-01.csv",
}


def load_seq(path):
    d = pd.read_csv(path, parse_dates=["EntryTime"]).sort_values("EntryTime")
    r = (d["ReturnPct"].to_numpy() * 100.0)   # 損益%
    return r


def cond_after_k_losses(r, k):
    """回傳 (下一筆損益% array) 給『前 k 筆皆虧』的位置。"""
    w = r > 0
    idx = []
    for i in range(k, len(r)):
        if not w[i - k:i].any():   # 前 k 筆全非贏（虧或平）
            idx.append(i)
    return r[idx] if idx else np.array([])


def cond_after_k_wins(r, k):
    w = r > 0
    idx = [i for i in range(k, len(r)) if w[i - k:i].all()]
    return r[idx] if idx else np.array([])


def shuffle_null(r, k, stat="mean", n=N_SHUF):
    """IID 虛無：打散 r，重算『連虧 k 後下一筆』統計分佈。"""
    out = np.empty(n)
    for j in range(n):
        rp = RNG.permutation(r)
        nxt = cond_after_k_losses(rp, k)
        out[j] = (nxt.mean() if stat == "mean" else (nxt > 0).mean()) if len(nxt) else np.nan
    return out[~np.isnan(out)]


def runs_test_z(w):
    """win/loss 二元序列 runs test z（<0 = 比隨機更聚集/正自相關）。"""
    n1, n0 = int(w.sum()), int((~w).sum())
    n = n1 + n0
    runs = 1 + int((w[1:] != w[:-1]).sum())
    mu = 1 + 2 * n1 * n0 / n
    var = 2 * n1 * n0 * (2 * n1 * n0 - n) / (n * n * (n - 1))
    return (runs - mu) / np.sqrt(var) if var > 0 else np.nan


def lag1_autocorr(x):
    x = x - x.mean()
    return float((x[1:] * x[:-1]).sum() / (x * x).sum())


print("=" * 96)
print(f"  H106 連虧後收手  IID 洗牌 N={N_SHUF}")
print("=" * 96)
results = {}
for name, path in STRATS.items():
    r = load_seq(path)
    w = r > 0
    base_mean, base_win = r.mean(), w.mean()
    print(f"\n###### {name}  N={len(r)}  無條件 E[損益%]={base_mean:+.3f}%  勝率={base_win:.0%} ######")
    print(f"  序列結構：lag-1 自相關(損益)={lag1_autocorr(r):+.3f}  "
          f"lag-1 自相關(勝負)={lag1_autocorr(w.astype(float)):+.3f}  "
          f"runs-test z={runs_test_z(w):+.2f}（<0=聚集）")
    print(f"  {'連虧k':<6}{'N':>5}{'下一筆E%':>10}{'下一筆勝率':>10}{'IID虛無均E%':>12}{'p(真≤虛無)':>11}  判定")
    rows = []
    for k in KS:
        nxt = cond_after_k_losses(r, k)
        if len(nxt) == 0:
            continue
        null = shuffle_null(r, k, "mean")
        p_lo = float((null <= nxt.mean()).mean())   # 真實值在虛無分佈的左尾機率
        flag = "顯著偏低✔" if (p_lo < 0.05 and len(nxt) >= 10) else ("樣本薄" if len(nxt) < 10 else "—")
        print(f"  {k:<6}{len(nxt):>5}{nxt.mean():>+10.3f}{(nxt>0).mean():>10.0%}"
              f"{null.mean():>+12.3f}{p_lo:>11.2f}  {flag}")
        rows.append(dict(k=k, N=len(nxt), mean=nxt.mean(), win=(nxt > 0).mean(),
                         null_mean=null.mean(), null_lo=np.percentile(null, 5),
                         null_hi=np.percentile(null, 95), p_lo=p_lo))
    # 對稱：連贏後
    print("  -- 對稱對照：連贏 k 後下一筆 --")
    for k in KS:
        nx = cond_after_k_wins(r, k)
        if len(nx) >= 10:
            print(f"  連贏{k}  N={len(nx):>3}  下一筆E%={nx.mean():+.3f}  勝率={(nx>0).mean():.0%}")
    results[name] = pd.DataFrame(rows)

# pooled（合併池，依時間排序）
print("\n###### Pooled（EstHL+Reversal 合併、依 EntryTime 排序） ######")
allr = []
for path in STRATS.values():
    d = pd.read_csv(path, parse_dates=["EntryTime"])[["EntryTime", "ReturnPct"]]
    allr.append(d)
pool = pd.concat(allr).sort_values("EntryTime")
rp = pool["ReturnPct"].to_numpy() * 100
print(f"  N={len(rp)}  無條件 E={rp.mean():+.3f}%  勝率={(rp>0).mean():.0%}  lag1(勝負)={lag1_autocorr((rp>0).astype(float)):+.3f}")
for k in KS:
    nxt = cond_after_k_losses(rp, k)
    if len(nxt) >= 10:
        null = shuffle_null(rp, k, "mean")
        print(f"  連虧{k}  N={len(nxt):>3}  E%={nxt.mean():+.3f}  勝率={(nxt>0).mean():.0%}  "
              f"IID虛無均={null.mean():+.3f}  p(真≤虛無)={float((null<=nxt.mean()).mean()):.2f}")

# ---- plot ----
fig, axes = plt.subplots(1, len(STRATS), figsize=(6 * len(STRATS), 4.5))
for ax, (name, df) in zip(np.atleast_1d(axes), results.items()):
    r = load_seq(STRATS[name]); base = r.mean()
    if len(df):
        ax.plot(df.k, df["mean"], "o-", color="#c0392b", label="連虧後 下一筆 E%")
        ax.fill_between(df.k, df["null_lo"], df["null_hi"], color="#bbb", alpha=.5, label="IID 虛無 5–95%")
        ax.plot(df.k, df["null_mean"], "--", color="#555", lw=.8)
    ax.axhline(base, color="#2980b9", lw=1, label=f"無條件基準 {base:+.2f}%")
    ax.axhline(0, color="k", lw=.5)
    ax.set_title(f"{name}：連虧 k 後下一筆期望 vs IID")
    ax.set_xlabel("連虧次數 k"); ax.set_ylabel("下一筆 E[損益%]"); ax.legend(fontsize=8)
plt.tight_layout()
plt.savefig(OUT / "h106_distribution.png", dpi=110)
print(f"\nsaved {OUT/'h106_distribution.png'}")
