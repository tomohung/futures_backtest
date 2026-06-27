"""
H132 Phase 1：電子/金融 leadership 方向 → forward TAIEX 報酬（directional risk-on/off）。

聚焦三個晉升門檻：
  1. 基礎效應重現（非重疊 OLS）
  2. 穩定性：逐年 + pre/post 2019 + regime 分層（realized-vol / VIX）符號是否一致為正、無反號
  3. 增量：控制 TAIEX 動能 + realized vol(+VIX 2016+) 後 dir 是否仍顯著
  4. 多空對稱性：spread 分解 + 剔除 2025 高波尾段

方法論（[[feedback_excursion_needs_forward_tautology_guard]]）：顯著性一律非重疊 stride=K。
資料：results/sector_index.csv（H131 驗證沿用）。VIX 僅 2016-11 起 → VIX 控制用子樣本。

用法：uv run python research/active/H132-elec-fin-direction/explore.py
"""
from __future__ import annotations
from pathlib import Path
import duckdb, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

HERE = Path(__file__).parent; RES = HERE / "results"
DB = HERE.parent.parent.parent / "data" / "futures.duckdb"
WS = [10, 20]; KS = [5, 10, 20]
plt.rcParams["font.sans-serif"] = ["Heiti TC", "Arial Unicode MS", "PingFang TC"]
plt.rcParams["axes.unicode_minus"] = False

lines = []
def out(s=""):
    print(s); lines.append(s)

def z(x):
    x = np.asarray(x, float); return (x - np.nanmean(x)) / np.nanstd(x)

def ols(y, X):
    """OLS，回傳 beta, t（同方差）, R², N。X 不含常數。"""
    X = np.atleast_2d(X);  X = X if X.shape[0] == len(y) else X.T
    m = np.all(np.isfinite(X), 1) & np.isfinite(y)
    y = y[m]; X = X[m]
    X1 = np.column_stack([np.ones(len(y)), X])
    b, *_ = np.linalg.lstsq(X1, y, rcond=None)
    res = y - X1 @ b; n, k = X1.shape
    se = np.sqrt(np.diag((res @ res) / (n - k) * np.linalg.inv(X1.T @ X1)))
    r2 = 1 - (res @ res) / ((y - y.mean()) ** 2).sum()
    return b, b / se, r2, n

def main():
    sec = pd.read_csv(RES / "sector_index.csv"); sec["trade_date"] = pd.to_datetime(sec["trade_date"])
    with duckdb.connect(str(DB), read_only=True) as c:
        tx = c.execute("select trade_date, close from taiex_day order by trade_date").df()
        vix = c.execute("select date as trade_date, vix from vixtwn order by date").df()
    tx["trade_date"] = pd.to_datetime(tx["trade_date"]); vix["trade_date"] = pd.to_datetime(vix["trade_date"])
    df = sec.merge(tx, on="trade_date").merge(vix, on="trade_date", how="left").sort_values("trade_date").reset_index(drop=True)
    df["r"] = np.log(df.tse23_close / df.tse28_close)
    df["year"] = df.trade_date.dt.year
    c_ = df.close.values
    df["ret1"] = pd.Series(c_).pct_change().values
    df["rvol20"] = pd.Series(df.ret1).rolling(20).std().values  # realized vol
    for W in WS:
        df[f"dir{W}"] = np.sign(df.r - df.r.rolling(W).mean())
        df[f"mom{W}"] = (pd.Series(c_) / pd.Series(c_).shift(W) - 1).values
    for K in KS:
        df[f"fwd{K}"] = (pd.Series(c_).shift(-K) / pd.Series(c_) - 1).values * 100

    out("# H132 Phase 1：電子/金融方向 → forward TAIEX 報酬")
    out(f"\n樣本 N={len(df)}，{df.trade_date.min().date()}~{df.trade_date.max().date()}；VIX 自 {df.dropna(subset=['vix']).trade_date.min().date()}")

    # ---------- 1. 基礎效應重現（非重疊 OLS）+ spread ----------
    out("\n" + "="*70 + "\n## 1. 基礎效應（非重疊 stride=K）")
    for W in WS:
        for K in KS:
            d = df[f"dir{W}"].values; fwd = df[f"fwd{K}"].values
            idx = np.arange(len(df)); nz = (idx % K == 0) & np.isfinite(d) & np.isfinite(fwd) & (d != 0)
            b, t, r2, n = ols(fwd[nz], z(d[nz]))
            up = fwd[nz][d[nz] > 0]; dn = fwd[nz][d[nz] < 0]
            out(f"  W={W} K={K}: dir β={b[1]:+.3f} t={t[1]:+.2f} (N={n}) | 電子領先 med={np.median(up):+.2f}% (N={len(up)}) | 金融領先 med={np.median(dn):+.2f}% (N={len(dn)}) | spread={np.median(up)-np.median(dn):+.2f}%")

    # 主視角固定 W=20, K=10
    W, K = 20, 10
    d = df[f"dir{W}"].values; fwd = df[f"fwd{K}"].values

    # ---------- 2a. 逐年穩定性（spread 符號）----------
    out("\n" + "="*70 + f"\n## 2a. 逐年穩定性（W={W},K={K}，spread=電子領先med − 金融領先med，符號一致性）")
    rows = []
    for yr, g in df.groupby("year"):
        dd = g[f"dir{W}"].values; ff = g[f"fwd{K}"].values
        m = np.isfinite(dd) & np.isfinite(ff) & (dd != 0)
        up = ff[m][dd[m] > 0]; dn = ff[m][dd[m] < 0]
        if len(up) < 5 or len(dn) < 5:
            continue
        sp = np.median(up) - np.median(dn)
        rows.append((yr, len(up), len(dn), np.median(up), np.median(dn), sp))
    pos = sum(1 for r0 in rows if r0[5] > 0)
    out(f"  {'年':>4} {'N電子':>5} {'N金融':>5} {'med電子':>8} {'med金融':>8} {'spread':>8}")
    for yr, nu, nd, mu, md, sp in rows:
        flag = "" if sp > 0 else "  ← 反號"
        out(f"  {yr:>4} {nu:>5} {nd:>5} {mu:>+8.2f} {md:>+8.2f} {sp:>+8.2f}{flag}")
    out(f"  → spread>0 的年數：{pos}/{len(rows)}")

    # ---------- 2b. pre/post 2019 改名界 ----------
    out("\n## 2b. pre/post 2019-07（改名界）")
    for label, mask in [("pre  (<2019-07)", df.trade_date < "2019-07-01"), ("post (>=2019-07)", df.trade_date >= "2019-07-01")]:
        sub = df[mask]; dd = sub[f"dir{W}"].values; ff = sub[f"fwd{K}"].values
        idx = np.arange(len(sub)); nz = (idx % K == 0) & np.isfinite(dd) & np.isfinite(ff) & (dd != 0)
        b, t, r2, n = ols(ff[nz], z(dd[nz]))
        up = ff[nz][dd[nz] > 0]; dn = ff[nz][dd[nz] < 0]
        out(f"  {label}: dir t={t[1]:+.2f} (N={n}) spread={np.median(up)-np.median(dn):+.2f}%")

    # ---------- 3a. regime 分層：realized-vol 三分位（全樣本）----------
    out("\n" + "="*70 + f"\n## 3a. regime 分層 realized-vol 三分位（W={W},K={K}，全樣本）")
    sub = df.dropna(subset=["rvol20", f"dir{W}", f"fwd{K}"]).copy()
    sub = sub[sub[f"dir{W}"] != 0]
    sub["vb"] = pd.qcut(sub.rvol20, 3, labels=["低波", "中波", "高波"])
    for vb, g in sub.groupby("vb", observed=True):
        up = g[g[f"dir{W}"] > 0][f"fwd{K}"]; dn = g[g[f"dir{W}"] < 0][f"fwd{K}"]
        out(f"  {vb}: 電子領先 med={up.median():+.2f}% | 金融領先 med={dn.median():+.2f}% | spread={up.median()-dn.median():+.2f}% (N={len(up)}/{len(dn)})")

    # ---------- 3b. VIX 三分位（2016+）----------
    out("\n## 3b. VIX 三分位（2016-11 起子樣本）")
    sub = df.dropna(subset=["vix", f"dir{W}", f"fwd{K}"]).copy(); sub = sub[sub[f"dir{W}"] != 0]
    sub["vxb"] = pd.qcut(sub.vix, 3, labels=["低VIX", "中VIX", "高VIX"])
    for vb, g in sub.groupby("vxb", observed=True):
        up = g[g[f"dir{W}"] > 0][f"fwd{K}"]; dn = g[g[f"dir{W}"] < 0][f"fwd{K}"]
        out(f"  {vb}: 電子領先 med={up.median():+.2f}% | 金融領先 med={dn.median():+.2f}% | spread={up.median()-dn.median():+.2f}% (N={len(up)}/{len(dn)})")

    # ---------- 4. 增量對照（非重疊 OLS）----------
    out("\n" + "="*70 + f"\n## 4. 增量：控制動能/波動/VIX 後 dir 是否仍顯著（W={W},K={K}，非重疊）")
    idx = np.arange(len(df)); base = (idx % K == 0) & np.isfinite(d) & np.isfinite(fwd) & (d != 0)
    mom = df[f"mom{W}"].values; rv = df.rvol20.values; vx = df.vix.values
    # 全樣本：dir + mom + rvol
    nz = base & np.isfinite(mom) & np.isfinite(rv)
    b, t, r2, n = ols(fwd[nz], np.column_stack([z(d[nz]), z(mom[nz]), z(rv[nz])]))
    out(f"  全樣本 fwd~dir+mom+rvol: dir t={t[1]:+.2f} | mom t={t[2]:+.2f} | rvol t={t[3]:+.2f} (N={n}, R²={r2:.4f})")
    # 2016+：加 VIX
    nz2 = base & np.isfinite(mom) & np.isfinite(rv) & np.isfinite(vx)
    b, t, r2, n = ols(fwd[nz2], np.column_stack([z(d[nz2]), z(mom[nz2]), z(rv[nz2]), z(vx[nz2])]))
    out(f"  2016+   fwd~dir+mom+rvol+VIX: dir t={t[1]:+.2f} | mom t={t[2]:+.2f} | rvol t={t[3]:+.2f} | VIX t={t[4]:+.2f} (N={n}, R²={r2:.4f})")

    # ---------- 5. 對稱性 + 剔除 2025 ----------
    out("\n" + "="*70 + f"\n## 5. 多空對稱性（W={W},K={K}）")
    m = np.isfinite(d) & np.isfinite(fwd) & (d != 0)
    base_med = np.median(fwd[m]); up = fwd[m][d[m] > 0]; dn = fwd[m][d[m] < 0]
    out(f"  全體 baseline med={base_med:+.2f}% | 電子領先 med={np.median(up):+.2f}%(Δ{np.median(up)-base_med:+.2f}) | 金融領先 med={np.median(dn):+.2f}%(Δ{np.median(dn)-base_med:+.2f})")
    out(f"  → edge 是 spread 還是單邊？電子側Δ={np.median(up)-base_med:+.2f}, 金融側Δ={np.median(dn)-base_med:+.2f}")
    ex = df[df.year != 2025]; dd = ex[f"dir{W}"].values; ff = ex[f"fwd{K}"].values
    idx = np.arange(len(ex)); nz = (idx % K == 0) & np.isfinite(dd) & np.isfinite(ff) & (dd != 0)
    b, t, _, n = ols(ff[nz], z(dd[nz])); up2 = ff[nz][dd[nz] > 0]; dn2 = ff[nz][dd[nz] < 0]
    out(f"  剔除 2025 後: dir t={t[1]:+.2f} (N={n}) spread={np.median(up2)-np.median(dn2):+.2f}%")

    # ---------- 視覺化 ----------
    fig, axes = plt.subplots(1, 2, figsize=(15, 5))
    yrs = [r0[0] for r0 in rows]; sps = [r0[5] for r0 in rows]
    axes[0].bar(yrs, sps, color=["#c0392b" if s > 0 else "#27ae60" for s in sps])
    axes[0].axhline(0, color="k", lw=.8); axes[0].set_title(f"逐年 spread（電子領先−金融領先 med fwdRet, W{W}K{K}）"); axes[0].set_ylabel("spread %")
    # 每日 long-short 累積：position=dir(W20), 持有 1 日
    pos_series = df[f"dir{W}"].shift(1).fillna(0).values  # 用前一日 dir 避免前視
    pnl = pos_series * df.ret1.values * 100
    cum = np.nancumsum(pnl)
    axes[1].plot(df.trade_date, cum, color="#c0392b")
    sharpe = np.nanmean(pnl) / np.nanstd(pnl) * np.sqrt(252)
    axes[1].set_title(f"每日 long-short 累積（dir{W} 持1日, Sharpe≈{sharpe:.2f}）"); axes[1].set_ylabel("累積 %")
    fig.tight_layout(); fig.savefig(RES / "h132_stability.png", dpi=110)
    out(f"\n每日 long-short（dir{W} 持1日）年化 Sharpe≈{sharpe:.2f}")
    out(f"圖：{RES/'h132_stability.png'}")
    (RES / "explore_output.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"[saved] {RES/'explore_output.txt'}")

if __name__ == "__main__":
    main()
