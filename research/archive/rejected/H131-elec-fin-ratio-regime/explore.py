"""
H131 Phase 1：電子/金融比率趨勢強度 → TAIEX trend-vs-chop regime（forward ER）。

核心 GATE 問題：
  (B) ratioER 越高，forward TAIEX-ER 越高？（單調）
  增量：控制 TAIEX 自身 trailing ER 後，ratioER 還有沒有 partial 預測力？（最可能擋下）
  (A) 比率方向能否排序 forward TAIEX 方向報酬？
  冗餘：與 VIX 是否高度共線。

方法論注意（記憶 feedback_excursion_needs_forward_tautology_guard）：
- 虛無對照 = TAIEX 自身 trailing ER 預測 forward ER。
- forward K 日窗重疊 → autocorr 膨脹顯著性。headline 顯著性用「非重疊」(stride=K) 子樣本。

用法：uv run python research/active/H131-elec-fin-ratio-regime/explore.py
"""
from __future__ import annotations
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
RES = HERE / "results"
DB = HERE.parent.parent.parent / "data" / "futures.duckdb"
WS = [10, 20]          # trailing window
KS = [5, 10, 20]       # forward horizon
plt.rcParams["font.sans-serif"] = ["Heiti TC", "Arial Unicode MS", "PingFang TC"]
plt.rcParams["axes.unicode_minus"] = False


def efficiency_ratio(x: np.ndarray, w: int, forward: bool) -> np.ndarray:
    """ER over window w. trailing: 用過去 w；forward: 用未來 w。回傳對齊原序列(NaN 補)。"""
    n = len(x)
    out = np.full(n, np.nan)
    d = np.abs(np.diff(x))
    for t in range(n):
        if forward:
            if t + w >= n:
                continue
            net = abs(x[t + w] - x[t])
            path = d[t:t + w].sum()
        else:
            if t - w < 0:
                continue
            net = abs(x[t] - x[t - w])
            path = d[t - w:t].sum()
        out[t] = net / path if path > 0 else np.nan
    return out


def spearman(a, b):
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 10:
        return np.nan, 0
    ra = pd.Series(a[m]).rank().values
    rb = pd.Series(b[m]).rank().values
    return np.corrcoef(ra, rb)[0, 1], int(m.sum())


def ols(y, X):
    """plain OLS，回傳 beta, tstat（同方差），R²。X 不含常數，內部加。"""
    m = np.all(np.isfinite(X), axis=1) & np.isfinite(y)
    y = y[m]; X = X[m]
    X1 = np.column_stack([np.ones(len(y)), X])
    beta, *_ = np.linalg.lstsq(X1, y, rcond=None)
    resid = y - X1 @ beta
    n, k = X1.shape
    sigma2 = (resid @ resid) / (n - k)
    XtX_inv = np.linalg.inv(X1.T @ X1)
    se = np.sqrt(np.diag(sigma2 * XtX_inv))
    t = beta / se
    sst = ((y - y.mean()) ** 2).sum()
    r2 = 1 - (resid @ resid) / sst
    return beta, t, r2, int(n)


def zscore(x):
    return (x - np.nanmean(x)) / np.nanstd(x)


def main():
    sec = pd.read_csv(RES / "sector_index.csv")
    sec["trade_date"] = pd.to_datetime(sec["trade_date"])
    with duckdb.connect(str(DB), read_only=True) as c:
        tx = c.execute("select trade_date, close from taiex_day order by trade_date").df()
        vix = c.execute("select date as trade_date, vix from vixtwn order by date").df()
    tx["trade_date"] = pd.to_datetime(tx["trade_date"])
    vix["trade_date"] = pd.to_datetime(vix["trade_date"])

    df = sec.merge(tx, on="trade_date", how="inner").merge(vix, on="trade_date", how="left")
    df = df.sort_values("trade_date").reset_index(drop=True)
    df["r"] = np.log(df["tse23_close"] / df["tse28_close"])
    tx_close = df["close"].values
    r = df["r"].values

    lines = []
    def out(s=""):
        print(s); lines.append(s)

    out(f"# H131 Phase 1 探索結果")
    out(f"\n樣本：{df['trade_date'].min().date()} ~ {df['trade_date'].max().date()}，N={len(df)} 交易日")
    out(f"電子/金融 log 比率 r：mean={r[~np.isnan(r)].mean():.3f} std={np.nanstd(r):.3f}")

    # forward ER targets
    for K in KS:
        df[f"fwdER{K}"] = efficiency_ratio(tx_close, K, forward=True)

    summary = {}
    for W in WS:
        ratioER = efficiency_ratio(r, W, forward=False)
        taiexER = efficiency_ratio(tx_close, W, forward=False)
        df[f"ratioER{W}"] = ratioER
        df[f"taiexER{W}"] = taiexER
        df[f"dir{W}"] = np.sign(r - pd.Series(r).rolling(W).mean().values)

        out(f"\n{'='*70}\n## W={W}（trailing 窗）")
        # 共線檢查：ratioER vs taiexER, vs VIX
        sc_rt, n1 = spearman(ratioER, taiexER)
        sc_rv, _ = spearman(ratioER, df["vix"].values)
        out(f"共線：spearman(ratioER, taiexER)={sc_rt:+.3f} | spearman(ratioER, VIX)={sc_rv:+.3f}  (N={n1})")

        for K in KS:
            fwd = df[f"fwdER{K}"].values
            # --- (B) 主關係：ratioER 五分位 → median fwdER ---
            valid = np.isfinite(ratioER) & np.isfinite(fwd)
            q = pd.qcut(ratioER[valid], 5, labels=False, duplicates="drop")
            meds = pd.Series(fwd[valid]).groupby(q).median()
            sc_main, nmain = spearman(ratioER, fwd)
            mono = "✓單調↑" if meds.is_monotonic_increasing else ("✓單調↓" if meds.is_monotonic_decreasing else "✗非單調")
            out(f"\n  K={K}: spearman(ratioER,fwdER)={sc_main:+.3f} (N={nmain})  五分位median fwdER={[round(v,3) for v in meds.values]} {mono}")

            # --- 增量（核心）：非重疊子樣本 OLS  fwdER ~ z(ratioER)+z(taiexER) ---
            idx = np.arange(len(df))
            nonoverlap = valid & np.isfinite(taiexER) & (idx % K == 0)
            zr = zscore(ratioER); zt = zscore(taiexER)
            # baseline: taiexER only
            b0, t0, r2_base, nb = ols(fwd[nonoverlap], zt[nonoverlap].reshape(-1, 1))
            # full
            bb, tt, r2_full, nf = ols(fwd[nonoverlap], np.column_stack([zr[nonoverlap], zt[nonoverlap]]))
            out(f"     非重疊(stride={K},N={nf}) OLS fwdER~z(ratioER)+z(taiexER):")
            out(f"       ratioER β={bb[1]:+.4f} t={tt[1]:+.2f} | taiexER β={bb[2]:+.4f} t={tt[2]:+.2f}")
            out(f"       R² baseline(僅taiexER)={r2_base:.4f} → full={r2_full:.4f}  ΔR²(ratioER增量)={r2_full-r2_base:+.4f}")
            summary[(W, K)] = dict(spearman=sc_main, mono=mono, ratioER_t=tt[1], dR2=r2_full - r2_base, n_nonoverlap=nf)

            # --- 雙重排序 3x3：taiexER 分箱 × ratioER 分箱 → median fwdER ---
            sub = pd.DataFrame({"f": fwd, "re": ratioER, "te": taiexER}).dropna()
            sub["tb"] = pd.qcut(sub["te"], 3, labels=["te低", "te中", "te高"])
            sub["rb"] = pd.qcut(sub["re"], 3, labels=["re低", "re中", "re高"])
            piv = sub.pivot_table("f", "tb", "rb", "median")
            out(f"     雙重排序 median fwdER（列=taiexER, 欄=ratioER）:")
            for ln in piv.round(3).to_string().split("\n"):
                out("       " + ln)

        # --- (A) 方向：forward TAIEX K 報酬 ---
        out(f"\n  (A) 方向（dir=sign(r-SMA{W})）→ forward TAIEX 報酬:")
        for K in KS:
            fwd_ret = (pd.Series(tx_close).shift(-K) / pd.Series(tx_close) - 1).values * 100
            idx = np.arange(len(df))
            nonoverlap = np.isfinite(df[f"dir{W}"].values) & np.isfinite(fwd_ret) & (idx % K == 0)
            d_ = df[f"dir{W}"].values[nonoverlap]; fr_ = fwd_ret[nonoverlap]
            up = fr_[d_ > 0]; dn = fr_[d_ < 0]
            out(f"     K={K}: 電子領先 median={np.median(up):+.2f}% (N={len(up)}) | 金融領先 median={np.median(dn):+.2f}% (N={len(dn)})")

    # 視覺化：W=20 的五分位 fwdER + 雙重排序
    W = 20
    fig, axes = plt.subplots(1, 3, figsize=(16, 4))
    for ax, K in zip(axes, KS):
        ratioER = df[f"ratioER{W}"].values; fwd = df[f"fwdER{K}"].values
        valid = np.isfinite(ratioER) & np.isfinite(fwd)
        q = pd.qcut(ratioER[valid], 5, labels=False, duplicates="drop")
        meds = pd.Series(fwd[valid]).groupby(q).median()
        ax.bar(range(len(meds)), meds.values, color="#c0392b")
        ax.set_title(f"W={W} K={K}: ratioER五分位 → median fwdER")
        ax.set_xlabel("ratioER 五分位(低→高)"); ax.set_ylabel("median forward TAIEX-ER")
    fig.tight_layout(); fig.savefig(RES / "ratioER_vs_fwdER.png", dpi=110)
    out(f"\n圖：{RES/'ratioER_vs_fwdER.png'}")

    (RES / "explore_output.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[saved] {RES/'explore_output.txt'}")


if __name__ == "__main__":
    main()
