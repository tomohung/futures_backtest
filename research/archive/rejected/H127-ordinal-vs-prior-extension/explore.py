"""H127 Phase 1 探索 — 序數 vs 前置延伸：L2 拉回續攻 edge 的真正 driver。

重用 services/l2_pullback.detect_day（causal）逐日掃 L2 拉回進場，對每筆新增 causal 前置延伸特徵，
再用「分層對照 + 輕量 logistic horse race」把『序數(1st/2nd+)』與『進場時已實現的同向延伸』拆開：

  prior_swing_L  = 進場前(< i)同向最大「已實現擺動」/ EMA20（anchor-free，最faithful 於趨勢成熟度）
                   long  = max_{j<i}( high[j] − min(low[0..j]) ) / ema20
                   short = max_{j<i}( max(high[0..j]) − low[j] ) / ema20
  prior_run_open = open-anchored 同向已走幅度 / EMA20（proposal 備援定義）
  ext_lvl        = prior_swing_L 換算成關卡（>=L3 / >=L2 / <L2），離散前置延伸代理

決定性 cell：prior_swing≥L3（已延伸）內 1st vs 2nd+；2nd+ 內 prior 高 vs 低。
edge 窗：entry∈[09:30,11:30]（H126 結論）。

用法：uv run python research/active/H127-ordinal-vs-prior-extension/explore.py
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

import duckdb
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.optimize import minimize

from src.chart_ui import paths
from src.chart_ui.services.daystats import SYMBOL, _ema20_range
from src.chart_ui.services.l2_pullback import COEF, detect_day

RESULTS = Path(__file__).parent / "results"
SESSION = "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'"
WIN_LO, WIN_HI = 570, 690     # 09:30–11:30（H126 edge 窗）
L2C, L3C = COEF["L2"], COEF["L3"]


def day_bars(conn, sel: date):
    rows = conn.execute(
        f"SELECT CAST(timestamp AS TIME) t, open, high, low, close FROM ohlcv_1m "
        f"WHERE symbol=? AND CAST(timestamp AS DATE)=? {SESSION} ORDER BY timestamp",
        [SYMBOL, sel]).fetchall()
    return [(t.hour * 60 + t.minute, float(o), float(h), float(l), float(c))
            for t, o, h, l, c in rows]


def prior_features(entry_i, side, bars, ema20, sess_open):
    """進場前(< entry_i)的 causal 前置同向延伸。回傳 (prior_swing_L, prior_run_open_L)。"""
    up = side == "long"
    if entry_i <= 0:
        return 0.0, 0.0
    run_ext = 0.0
    if up:
        lo = bars[0][3]
        hi_open = bars[0][2]
        for (_m, _o, h, l, _c) in bars[:entry_i]:
            lo = min(lo, l)
            run_ext = max(run_ext, h - lo)        # 從先前低點的最大上行擺動
            hi_open = max(hi_open, h)
        run_open = hi_open - sess_open
    else:
        hi = bars[0][2]
        lo_open = bars[0][3]
        for (_m, _o, h, l, _c) in bars[:entry_i]:
            hi = max(hi, h)
            run_ext = max(run_ext, hi - l)        # 從先前高點的最大下行擺動
            lo_open = min(lo_open, l)
        run_open = sess_open - lo_open
    return run_ext / ema20, run_open / ema20


def forward(entry_i, side, anchor, dist, bars):
    up = side == "long"
    entry_px = bars[entry_i][4]
    L3d, L4d, L5d = dist["L3"], dist["L4"], dist["L5"]
    reach = {"L3": 0, "L4": 0, "L5": 0}
    mfe = 0.0
    for (_m, _o, h, l, _c) in bars[entry_i + 1:]:
        fpx = l if not up else h
        for lv, d in (("L3", L3d), ("L4", L4d), ("L5", L5d)):
            if not reach[lv] and ((fpx <= anchor - d) if not up else (fpx >= anchor + d)):
                reach[lv] = 1
        mfe = max(mfe, (entry_px - l) if not up else (h - entry_px))
    return reach, mfe / dist["L2"] * L2C  # mfe in EMA20 units (=mfe/ema20)


def ext_lvl(sw):
    return ">=L3" if sw >= L3C else ">=L2" if sw >= L2C else "<L2"


def collect():
    rows = []
    with duckdb.connect(str(paths.DUCKDB_PATH), read_only=True) as conn:
        days = [r[0] for r in conn.execute(
            f"SELECT DISTINCT CAST(timestamp AS DATE) d FROM ohlcv_1m WHERE symbol=? {SESSION} "
            "ORDER BY d", [SYMBOL]).fetchall()]
        for d in days:
            ema20 = _ema20_range(conn, d)
            if not ema20:
                continue
            bars = day_bars(conn, d)
            if len(bars) < 5:
                continue
            entries, dist = detect_day(bars, ema20)
            if not entries:
                continue
            sess_open = bars[0][1]
            side_count = defaultdict(int)
            side_total = defaultdict(int)
            for e in entries:
                side_total[e["side"]] += 1
            for e in entries:
                side_count[e["side"]] += 1
                sw, ro = prior_features(e["entry_i"], e["side"], bars, ema20, sess_open)
                reach, mfe = forward(e["entry_i"], e["side"], e["anchor"], dist, bars)
                rows.append({
                    "date": str(d), "side": e["side"], "ordinal": side_count[e["side"]],
                    "is_2nd": int(side_count[e["side"]] >= 2),
                    "entry_min": e["entry_min"],
                    "prior_swing_L": round(sw, 3), "prior_run_open_L": round(ro, 3),
                    "ext_lvl": ext_lvl(sw),
                    "mfe_L": round(mfe, 3),
                    "reach_L3": reach["L3"], "reach_L4": reach["L4"], "reach_L5": reach["L5"],
                })
    return rows


# ---------- 統計工具 ----------
def rate(sub, key):
    return (sum(r[key] for r in sub) / len(sub)) if sub else float("nan")


def line(label, sub):
    if not sub:
        print(f"  {label:22s} N=0")
        return
    print(f"  {label:22s} N={len(sub):4d} | L3/L4/L5 = "
          f"{rate(sub,'reach_L3')*100:5.1f}/{rate(sub,'reach_L4')*100:5.1f}/{rate(sub,'reach_L5')*100:5.1f}% | "
          f"prior_swing med={np.median([r['prior_swing_L'] for r in sub]):.2f} | "
          f"entry_min med={int(np.median([r['entry_min'] for r in sub]))}")


def logistic_fit(X, y):
    """標準化特徵的 L2-正則 logistic（scipy）。回傳 coef dict（標準化尺度）。"""
    Xs = (X - X.mean(0)) / X.std(0)
    Xb = np.hstack([np.ones((len(Xs), 1)), Xs])
    lam = 1e-3

    def nll(w):
        z = Xb @ w
        ll = np.sum(y * z - np.logaddexp(0, z))
        return -ll + lam * np.sum(w[1:] ** 2)

    w0 = np.zeros(Xb.shape[1])
    res = minimize(nll, w0, method="BFGS")
    return res.x


def main():
    RESULTS.mkdir(exist_ok=True)
    rows = collect()
    with open(RESULTS / "entries_prior.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print("=" * 100)
    print("H127 Phase 1 — 序數 vs 前置延伸｜driver 歸因")
    print("=" * 100)
    win = [r for r in rows if WIN_LO <= r["entry_min"] < WIN_HI]
    print(f"\n總進場 N={len(rows)}；edge 窗 09:30–11:30 N={len(win)}")
    print(f"（以下分層除特別標註外，皆限 edge 窗 09:30–11:30，避免尾盤死區稀釋）")

    # 1) 單變量：reach vs prior_swing 分桶
    print("\n[1] 單變量 — forward reach vs prior_swing_L 分桶（edge 窗）")
    bins = [(0, L2C, "<L2"), (L2C, L3C, "L2–L3"), (L3C, 1.0, "L3–L4(0.71–1.0)"), (1.0, 99, ">=1.0")]
    for lo, hi, nm in bins:
        line(f"prior_swing {nm}", [r for r in win if lo <= r["prior_swing_L"] < hi])

    # 2) 雙向分層：序數 × prior_swing（核心）
    print("\n[2] 雙向分層 — 序數 × prior_swing（edge 窗）｜看哪個在條件化後 survive")
    for nm, lo, hi in (("prior<L3", 0, L3C), ("prior>=L3", L3C, 99)):
        print(f"  -- {nm} --")
        line("    1st", [r for r in win if r["is_2nd"] == 0 and lo <= r["prior_swing_L"] < hi])
        line("    2nd+", [r for r in win if r["is_2nd"] == 1 and lo <= r["prior_swing_L"] < hi])

    # 3) 決定性 cell
    print("\n[3] 決定性對照（edge 窗）")
    print("  (a) prior>=L3 已延伸者，序數還分得開嗎？ → 見 [2] prior>=L3 的 1st vs 2nd+")
    print("  (b) 2nd+ 內，prior 高 vs 低：")
    line("    2nd+ & prior<L3", [r for r in win if r["is_2nd"] and r["prior_swing_L"] < L3C])
    line("    2nd+ & prior>=L3", [r for r in win if r["is_2nd"] and r["prior_swing_L"] >= L3C])
    print("  (c) 1st 內，prior 高 vs 低（第一次但已延伸 = 前置延伸 driver 的關鍵證據）：")
    line("    1st & prior L2–L3", [r for r in win if not r["is_2nd"] and L2C <= r["prior_swing_L"] < L3C])
    line("    1st & prior L3–1.0", [r for r in win if not r["is_2nd"] and L3C <= r["prior_swing_L"] < 1.0])
    line("    1st & prior>=1.0", [r for r in win if not r["is_2nd"] and r["prior_swing_L"] >= 1.0])
    print("  (d) 極端延伸桶 prior>=1.0 的組成與序數拆解（檢查是否另一獨立 driver）：")
    ext = [r for r in win if r["prior_swing_L"] >= 1.0]
    n2 = sum(r["is_2nd"] for r in ext)
    print(f"      prior>=1.0 共 N={len(ext)}，其中 2nd+ {n2}（{n2/len(ext)*100:.0f}%）、1st {len(ext)-n2}")
    line("    prior>=1.0 & 1st", [r for r in ext if not r["is_2nd"]])
    line("    prior>=1.0 & 2nd+", [r for r in ext if r["is_2nd"]])

    # 4) logistic horse race
    print("\n[4] logistic horse race（edge 窗）｜標準化係數（同尺度可比；越大越主導）")
    for ytag in ("reach_L4", "reach_L5"):
        X = np.array([[r["is_2nd"], r["prior_swing_L"], r["entry_min"]] for r in win], float)
        y = np.array([r[ytag] for r in win], float)
        w = logistic_fit(X, y)
        print(f"  {ytag}:  is_2nd={w[1]:+.3f}   prior_swing_L={w[2]:+.3f}   entry_min={w[3]:+.3f}   (intercept={w[0]:+.3f})")
    print("  解讀：prior_swing_L 係數 ≫ is_2nd → driver 是前置延伸；is_2nd 仍大 → 序數帶獨立資訊。")

    figures(win)
    print(f"\n[saved] {RESULTS/'entries_prior.csv'}  (N={len(rows)})")


def figures(win):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    # 左：reach_L4/L5 vs prior_swing 分桶，分 1st / 2nd+
    bins = [(0, L2C, "<L2"), (L2C, L3C, "L2-L3"), (L3C, 1.0, "L3-L4"), (1.0, 99, ">=1.0")]
    xs = range(len(bins))
    for ytag, col in (("reach_L4", "#ff7f0e"), ("reach_L5", "#d62728")):
        for is2, ls, mk in ((0, "--", "o"), (1, "-", "s")):
            ys = [rate([r for r in win if r["is_2nd"] == is2 and lo <= r["prior_swing_L"] < hi], ytag) * 100
                  for lo, hi, _ in bins]
            axes[0].plot(xs, ys, ls + mk, color=col, alpha=0.6 if is2 == 0 else 1.0,
                         label=f"{ytag[-2:]} {'2nd+' if is2 else '1st'}")
    axes[0].set_xticks(list(xs))
    axes[0].set_xticklabels([b[2] for b in bins])
    axes[0].set_xlabel("prior_swing_L (前置同向延伸)")
    axes[0].set_ylabel("reach rate (%)")
    axes[0].set_title("reach vs prior_swing: 1st(dashed) vs 2nd+(solid)  [09:30-11:30]")
    axes[0].legend(fontsize=8)
    axes[0].grid(alpha=0.3)
    # 右：prior_swing 分佈 1st vs 2nd+
    axes[1].hist([r["prior_swing_L"] for r in win if not r["is_2nd"]], bins=30, alpha=0.5,
                 label="1st", color="#1f77b4", density=True)
    axes[1].hist([r["prior_swing_L"] for r in win if r["is_2nd"]], bins=30, alpha=0.5,
                 label="2nd+", color="#d62728", density=True)
    axes[1].axvline(L2C, ls=":", c="k", lw=0.8)
    axes[1].axvline(L3C, ls=":", c="k", lw=0.8)
    axes[1].set_xlabel("prior_swing_L")
    axes[1].set_title("prior_swing 分佈：序數與前置延伸的共線程度")
    axes[1].legend()
    fig.tight_layout()
    p = RESULTS / "ordinal_vs_prior.png"
    fig.savefig(p, dpi=110)
    print(f"[saved] {p}")


if __name__ == "__main__":
    main()
