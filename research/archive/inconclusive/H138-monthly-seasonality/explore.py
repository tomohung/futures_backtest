#!/usr/bin/env python3
"""H138 月度季節性窗口 — Phase 1 分佈探索

主序列：TAIEX 日內報酬（taiex_day close/open-1），2008-2026
交叉序列：TX 日盤日內報酬（ohlcv_1m 08:45 open / 13:45 close），2021-2026

輸出：
  (1) pre-registered 複現：七月頭 10 交易日 / 八月末 7 交易日 / 組合，逐年明細 + permutation
  (2) 全月掃描：12 月每月最強連續窗口（多/空）+ Monte Carlo permutation 3000
  (3) 日曆月 vs 結算月（第三個週三）對照

報酬皆為「日內 open→close」，單位 %。窗口值 = 窗口內每日報酬之和（累積）。
"""
import duckdb
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

import matplotlib
matplotlib.rcParams["font.sans-serif"] = ["Heiti TC", "Arial Unicode MS", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

DB = Path(__file__).parents[3] / "data" / "futures.duckdb"
RESULTS = Path(__file__).parent / "results"
RESULTS.mkdir(exist_ok=True)
RNG = np.random.default_rng(42)
N_PERM = 3000


# ─────────────────────────── 資料載入 ───────────────────────────
def load_taiex():
    with duckdb.connect(str(DB), read_only=True) as c:
        df = c.execute("""
            SELECT trade_date AS d, open AS o, close AS cl
            FROM taiex_day WHERE open > 0 ORDER BY d
        """).df()
    df["ret"] = (df["cl"] / df["o"] - 1.0) * 100.0
    return df[["d", "ret"]].copy()


def load_tx():
    with duckdb.connect(str(DB), read_only=True) as c:
        df = c.execute("""
            SELECT timestamp::DATE AS d,
                   arg_min(open, timestamp)  AS o,
                   arg_max(close, timestamp) AS cl
            FROM ohlcv_1m
            WHERE symbol='TX' AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            GROUP BY d ORDER BY d
        """).df()
    df["ret"] = (df["cl"] / df["o"] - 1.0) * 100.0
    return df[["d", "ret"]].copy()


# ─────────────────────────── 月份標註 ───────────────────────────
def third_wednesday(year, month):
    d = pd.Timestamp(year, month, 1)
    # weekday(): Mon=0..Wed=2
    first_wed = d + pd.Timedelta(days=(2 - d.weekday()) % 7)
    return first_wed + pd.Timedelta(days=14)


def add_calendar_labels(df):
    """日曆月：cyc_year/cyc_month = 日曆年月；pos = 該月第幾個交易日；rpos = 倒數第幾。"""
    df = df.copy()
    df["d"] = pd.to_datetime(df["d"])
    df["cyc_year"] = df["d"].dt.year
    df["cyc_month"] = df["d"].dt.month
    g = df.groupby(["cyc_year", "cyc_month"])
    df["pos"] = g.cumcount() + 1
    df["rpos"] = g["d"].transform("size") - g.cumcount()
    return df


def add_settlement_labels(df):
    """結算月：週期 = (前一結算日, 本結算日]。cyc_month = 本結算日所在日曆月。

    每筆交易日歸屬於「第一個 >= 該日的結算日」所定義的週期。
    """
    df = df.copy().reset_index(drop=True)
    df["d"] = pd.to_datetime(df["d"])
    # 造出涵蓋資料範圍的所有結算日
    yrs = range(df["d"].dt.year.min(), df["d"].dt.year.max() + 2)
    setts = sorted(third_wednesday(y, m) for y in yrs for m in range(1, 13))
    setts = pd.DatetimeIndex(setts)
    # 每個交易日 → 第一個 >= 它的結算日
    idx = np.searchsorted(setts.values, df["d"].values, side="left")
    sett_date = setts[idx]
    df["cyc_year"] = sett_date.year
    df["cyc_month"] = sett_date.month
    g = df.groupby(["cyc_year", "cyc_month"])
    df["pos"] = g.cumcount() + 1
    df["rpos"] = g["d"].transform("size") - g.cumcount()
    return df


# ─────────────────────── pre-registered 窗口 ───────────────────────
def year_month_arrays(df, month):
    """回傳 {year: 該(結算/日曆)月的每日報酬 np.array（依日期序）}。"""
    sub = df[df["cyc_month"] == month]
    return {y: g.sort_values("d")["ret"].to_numpy()
            for y, g in sub.groupby("cyc_year")}


def prereg_head(df, month, n):
    """每年取該月前 n 個交易日之報酬和。回傳 (per_year dict, stats)。"""
    arrs = year_month_arrays(df, month)
    vals = {y: a[:n].sum() for y, a in arrs.items() if len(a) >= n}
    return vals, _stats(list(vals.values()))


def prereg_tail(df, month, n):
    arrs = year_month_arrays(df, month)
    vals = {y: a[-n:].sum() for y, a in arrs.items() if len(a) >= n}
    return vals, _stats(list(vals.values()))


def _stats(v):
    a = np.asarray(v, float)
    return {"n": len(a), "mean": a.mean(), "median": np.median(a),
            "win": (a > 0).mean() * 100, "min": a.min(), "max": a.max()}


def perm_pvalue_head(df, month, n, observed_mean, tail=False):
    """within-month shuffle null：每年月內報酬洗牌後取前/後 n 之和，跨年取平均。
    回傳 (percentile, p_one_sided)。percentile = 觀測值在 null 分佈的百分位。
    """
    arrs = [a for a in year_month_arrays(df, month).values() if len(a) >= n]
    null = np.empty(N_PERM)
    for i in range(N_PERM):
        s = 0.0
        for a in arrs:
            perm = RNG.permutation(a)
            s += perm[-n:].sum() if tail else perm[:n].sum()
        null[i] = s / len(arrs)
    pct = (null < observed_mean).mean() * 100
    p = (null >= observed_mean).mean() if observed_mean >= 0 else (null <= observed_mean).mean()
    return pct, p, null


def prereg_combined(df):
    """七月頭 10 + 八月末 7，逐年相加。"""
    jh = year_month_arrays(df, 7)
    at = year_month_arrays(df, 8)
    years = sorted(set(jh) & set(at))
    vals = {}
    for y in years:
        if len(jh[y]) >= 10 and len(at[y]) >= 7:
            vals[y] = jh[y][:10].sum() + at[y][-7:].sum()
    return vals, _stats(list(vals.values()))


def perm_combined(df, observed_mean):
    jh = [a for y, a in year_month_arrays(df, 7).items() if len(a) >= 10]
    at = [a for y, a in year_month_arrays(df, 8).items() if len(a) >= 7]
    yrs7 = {y: a for y, a in year_month_arrays(df, 7).items() if len(a) >= 10}
    yrs8 = {y: a for y, a in year_month_arrays(df, 8).items() if len(a) >= 7}
    years = sorted(set(yrs7) & set(yrs8))
    null = np.empty(N_PERM)
    for i in range(N_PERM):
        s = 0.0
        for y in years:
            s += RNG.permutation(yrs7[y])[:10].sum() + RNG.permutation(yrs8[y])[-7:].sum()
        null[i] = s / len(years)
    pct = (null < observed_mean).mean() * 100
    return pct, null


# ─────────────────────── 全月最強窗口掃描 ───────────────────────
def _scan_matrices(arrs, kmin):
    """回傳 head/tail 對齊矩陣 [Y, kmin]（head: 月初對齊；tail: 月底對齊,col0=最後一日）。"""
    H = np.vstack([a[:kmin] for a in arrs])
    T = np.vstack([a[-kmin:][::-1] for a in arrs])
    return H, T


def _best_worst(H, T, lmin=3, lmax=12):
    """對 head/tail 兩種對齊掃 L=lmin..lmax 的所有連續窗口，回傳最佳(max)/最差(min)跨年平均。"""
    best = (-1e9, None); worst = (1e9, None)
    for name, M in (("head", H), ("tail", T)):
        Y, K = M.shape
        P = np.hstack([np.zeros((Y, 1)), np.cumsum(M, axis=1)])
        for L in range(lmin, min(lmax, K) + 1):
            wins = (P[:, L:] - P[:, :K - L + 1]).mean(axis=0)  # 各 start 的跨年平均
            s = int(np.argmax(wins))
            if wins[s] > best[0]:
                best = (wins[s], (name, s, L))
            s2 = int(np.argmin(wins))
            if wins[s2] < worst[0]:
                worst = (wins[s2], (name, s2, L))
    return best, worst


def _best_worst_scalar(H, T, lmin=3, lmax=12):
    b, w = _best_worst(H, T, lmin, lmax)
    return b[0], w[0]


def scan_month(df, month, lmin=3, lmax=12):
    arrs = list(year_month_arrays(df, month).values())
    arrs = [a for a in arrs if len(a) >= lmin]
    kmin = min(len(a) for a in arrs)
    H, T = _scan_matrices(arrs, kmin)
    best, worst = _best_worst(H, T, lmin, lmax)
    # permutation：月內洗牌後重跑 max/min 選擇（selection-adjusted）
    yr_full = arrs
    nb = np.empty(N_PERM); nw = np.empty(N_PERM)
    for i in range(N_PERM):
        sh = [RNG.permutation(a) for a in yr_full]
        Hs, Ts = _scan_matrices(sh, kmin)
        nb[i], nw[i] = _best_worst_scalar(Hs, Ts, lmin, lmax)
    best_pct = (nb < best[0]).mean() * 100
    worst_pct = (nw > worst[0]).mean() * 100
    return {"n_years": len(arrs), "kmin": kmin,
            "best": best, "best_pct": best_pct,
            "worst": worst, "worst_pct": worst_pct}


def _win_label(desc, month):
    name, s, L = desc
    if name == "head":
        return f"第 {s+1}–{s+L} 個交易日"
    else:
        return f"倒數第 {s+L}–{s+1} 個交易日"


# ─────────────────────────── 熱圖 ───────────────────────────
def heatmap(df, title, path, maxpos=23):
    M = np.full((12, maxpos), np.nan)
    for m in range(1, 13):
        arrs = year_month_arrays(df, m)
        for k in range(maxpos):
            vals = [a[k] for a in arrs.values() if len(a) > k]
            if vals:
                M[m - 1, k] = np.mean(vals)
    fig, ax = plt.subplots(figsize=(15, 6))
    vmax = np.nanpercentile(np.abs(M), 95)
    im = ax.imshow(M, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_xticks(range(maxpos)); ax.set_xticklabels(range(1, maxpos + 1), fontsize=8)
    ax.set_yticks(range(12)); ax.set_yticklabels([f"{m}月" for m in range(1, 13)])
    ax.set_xlabel("月內第 k 個交易日"); ax.set_title(title)
    fig.colorbar(im, label="平均日內報酬 %")
    for m in range(12):
        for k in range(maxpos):
            if not np.isnan(M[m, k]):
                ax.text(k, m, f"{M[m,k]:+.1f}", ha="center", va="center", fontsize=5.5,
                        color="white" if abs(M[m, k]) > vmax * 0.6 else "black")
    plt.tight_layout(); plt.savefig(path, dpi=130); plt.close()
    print(f"  heatmap → {path}")


# ─────────────────────────── main ───────────────────────────
def report_series(name, df_raw, do_perm=True):
    print(f"\n{'='*70}\n### {name}\n{'='*70}")
    for split_name, labeler in (("日曆月", add_calendar_labels),
                                ("結算月", add_settlement_labels)):
        df = labeler(df_raw)
        yr0, yr1 = df["d"].dt.year.min(), df["d"].dt.year.max()
        print(f"\n── [{split_name}] {yr0}-{yr1} ──")

        # (1) pre-registered
        jh_v, jh_s = prereg_head(df, 7, 10)
        at_v, at_s = prereg_tail(df, 8, 7)
        cb_v, cb_s = prereg_combined(df)
        print(f"  七月頭10日  N={jh_s['n']:2d}  平均{jh_s['mean']:+.2f}%  勝率{jh_s['win']:.0f}%  "
              f"中位{jh_s['median']:+.2f}%  [{jh_s['min']:+.1f},{jh_s['max']:+.1f}]")
        print(f"  八月末 7日  N={at_s['n']:2d}  平均{at_s['mean']:+.2f}%  勝率{at_s['win']:.0f}%  "
              f"中位{at_s['median']:+.2f}%  [{at_s['min']:+.1f},{at_s['max']:+.1f}]")
        print(f"  組合(7頭10+8末7) N={cb_s['n']:2d}  平均{cb_s['mean']:+.2f}%  勝率{cb_s['win']:.0f}%  "
              f"最差年{cb_s['min']:+.2f}%")
        if do_perm and jh_s['n'] >= 8:
            p1, _, _ = perm_pvalue_head(df, 7, 10, jh_s['mean'], tail=False)
            p2, _, _ = perm_pvalue_head(df, 8, 7, at_s['mean'], tail=True)
            p3, _ = perm_combined(df, cb_s['mean'])
            print(f"  permutation 百分位：七月頭10={p1:.1f}th  八月末7={p2:.1f}th  組合={p3:.1f}th")
            # 逐年組合明細
            print("  組合逐年：", "  ".join(f"{y}:{v:+.1f}" for y, v in sorted(cb_v.items())))

        # (2) 全月掃描
        if do_perm:
            print(f"  [全月最強窗口掃描 + permutation {N_PERM}×]")
            print(f"  {'月':>3} {'N':>3} | {'最強多方窗口':<20} 平均%  百分位 | {'最強空方窗口':<20} 平均%  百分位")
            for m in range(1, 13):
                r = scan_month(df, m)
                bl, bd = r["best"]; wl, wd = r["worst"]
                print(f"  {m:>2}月 {r['n_years']:>3} | {_win_label(bd,m):<20} {bl:+.2f}  {r['best_pct']:5.1f}th "
                      f"| {_win_label(wd,m):<20} {wl:+.2f}  {r['worst_pct']:5.1f}th")

        # heatmap 只對日曆月/結算月各出一張（TAIEX）
        if do_perm:
            tag = "cal" if split_name == "日曆月" else "sett"
            heatmap(df, f"{name} 季節性熱圖（{split_name}，日內報酬）",
                    RESULTS / f"heatmap_{tag}.png")


if __name__ == "__main__":
    taiex = load_taiex()
    tx = load_tx()
    print(f"TAIEX N={len(taiex)}  {taiex['d'].min()}~{taiex['d'].max()}")
    print(f"TX    N={len(tx)}  {tx['d'].min()}~{tx['d'].max()}")

    report_series("TAIEX 加權指數（主）", taiex, do_perm=True)
    report_series("TX 台指期（交叉驗證，僅日曆月，無 permutation）", tx, do_perm=False)
