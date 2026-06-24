"""H130 Phase 1 探索 — L1-reset 同相位再進場。

causal 狀態機（與 6/24 概念驗證同源，重現 09:01+10:13）：
  相位確立(ext−anchor≥L2d) → extend → pullback(dip≥pb_floor) → 收盤站回/破 5MA = 進場
  → needL1(待 retrace 回 L1 線 high≥anchor−L1d / low≤anchor+L1d = reset)
  → touchL2(待重新同向碰 L2 線) → extend …循環。相位由 ≥L2 反向 swing 結束。
每筆標 reentry_idx（同相位第幾次：1=首次, ≥2=L1-reset 再進場）+ entry_min。
零策略 forward excursion（碰 L3/L4/L5、MFE/MAE，自 phase anchor 計，與 H126 同法）。
含虛無對照（時間配對）+ overfit 檢查（leave-6/24-out、單日集中度）。

用法：uv run python research/active/H130-l1-reset-reentry/explore.py
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.chart_ui import paths
from src.chart_ui.services.daystats import SYMBOL, _ema20_range
from src.chart_ui.services.l2_pullback import COEF

RESULTS = Path(__file__).parent / "results"
SESSION = "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'"
C1 = 0.385
PB_FLOOR_FRAC = 0.05


def _sma(seq, n):
    out, s = [], 0.0
    for i, v in enumerate(seq):
        s += v
        if i >= n:
            s -= seq[i - n]
        out.append(s / n if i >= n - 1 else None)
    return out


def detect_l1reset(bars, ema):
    """回傳每筆進場 dict：entry_i, entry_min, side, entry, anchor, reentry_idx。"""
    L1d, L2d = C1 * ema, COEF["L2"] * ema
    L5d = COEF["L5"] * ema
    pb_floor = PB_FLOOR_FRAC * ema
    closes = [b[4] for b in bars]
    s5 = _sma(closes, 5)
    out = []
    trend, ext, anchor = 0, None, None
    up_ref, dn_ref = bars[0][3], bars[0][2]
    sub, peak, pbext = None, None, None
    ridx = 0                                  # 本相位已進場次數
    for i in range(len(bars)):
        m, o, h, l, c = bars[i]
        if trend != 0 and anchor is not None:
            up = trend == 1
            ext = max(ext, h) if up else min(ext, l)
            if sub == "needL1":
                if (l <= anchor + L1d) if up else (h >= anchor - L1d):
                    sub = "touchL2"
            elif sub == "touchL2":
                if (h >= anchor + L2d) if up else (l <= anchor - L2d):
                    sub, peak, pbext = "extend", (h if up else l), None
            elif sub == "extend":
                peak = max(peak, h) if up else min(peak, l)
                dip = (peak - l) if up else (h - peak)
                if dip >= pb_floor:
                    sub, pbext = "pullback", (l if up else h)
            elif sub == "pullback":
                pbext = min(pbext, l) if up else max(pbext, h)
                if i > 0 and s5[i] is not None and s5[i - 1] is not None:
                    recl = (closes[i - 1] < s5[i - 1] and c > s5[i]) if up \
                        else (closes[i - 1] > s5[i - 1] and c < s5[i])
                    over = (c >= anchor + L5d) if up else (c <= anchor - L5d)
                    if recl and not over:
                        ridx += 1
                        out.append({"entry_i": i, "entry_min": m, "side": "long" if up else "short",
                                    "entry": round(c, 1), "anchor": round(anchor, 1), "reentry_idx": ridx})
                        sub = "needL1"
        # zigzag
        if trend == 0:
            up_ref, dn_ref = min(up_ref, l), max(dn_ref, h)
            if h - up_ref >= L2d:
                trend, ext, anchor, sub, peak, pbext, ridx = 1, h, up_ref, "extend", h, None, 0
            elif dn_ref - l >= L2d:
                trend, ext, anchor, sub, peak, pbext, ridx = -1, l, dn_ref, "extend", l, None, 0
        elif trend == 1:
            if h > ext:
                ext = h
            elif ext - l >= L2d:
                trend, anchor, ext, sub, peak, pbext, ridx = -1, ext, l, "extend", l, None, 0
        else:
            if l < ext:
                ext = l
            elif h - ext >= L2d:
                trend, anchor, ext, sub, peak, pbext, ridx = 1, ext, h, "extend", h, None, 0
    return out


def forward(entry_i, side, anchor, ema, bars):
    up = side == "long"
    entry_px = bars[entry_i][4]
    L3d, L4d, L5d = COEF["L3"] * ema, COEF["L4"] * ema, COEF["L5"] * ema
    reach = {"L3": 0, "L4": 0, "L5": 0}
    mfe = run_adv = 0.0
    for (_m, _o, h, l, _c) in bars[entry_i + 1:]:
        run_adv = max(run_adv, (h - entry_px) if not up else (entry_px - l))
        fpx = l if not up else h
        for lv, dd in (("L3", L3d), ("L4", L4d), ("L5", L5d)):
            if not reach[lv] and ((fpx <= anchor - dd) if not up else (fpx >= anchor + dd)):
                reach[lv] = 1
        mfe = max(mfe, (entry_px - l) if not up else (h - entry_px))
    return mfe / ema, run_adv / ema, reach


def _day_bars(conn, d):
    rows = conn.execute(
        f"SELECT CAST(timestamp AS TIME) t, open, high, low, close FROM ohlcv_1m "
        f"WHERE symbol=? AND CAST(timestamp AS DATE)=? {SESSION} ORDER BY timestamp",
        [SYMBOL, d]).fetchall()
    return [(t.hour * 60 + t.minute, float(o), float(h), float(l), float(c)) for t, o, h, l, c in rows]


def collect():
    rows = []
    with duckdb.connect(str(paths.DUCKDB_PATH), read_only=True) as conn:
        days = [r[0] for r in conn.execute(
            f"SELECT DISTINCT CAST(timestamp AS DATE) d FROM ohlcv_1m WHERE symbol=? {SESSION} ORDER BY d",
            [SYMBOL]).fetchall()]
        for d in days:
            ema = _ema20_range(conn, d)
            if not ema:
                continue
            bars = _day_bars(conn, d)
            if len(bars) < 5:
                continue
            ents = detect_l1reset(bars, ema)
            # 標記本日各 side 是否有 re-entry（給 selection 對照）
            phase_has_re = defaultdict(bool)   # (date,side)→是否出現 reentry_idx≥2
            for e in ents:
                if e["reentry_idx"] >= 2:
                    phase_has_re[e["side"]] = True
            for e in ents:
                mfe, mae, reach = forward(e["entry_i"], e["side"], e["anchor"], ema, bars)
                is_re = e["reentry_idx"] >= 2
                grp = ("C_reset" if is_re else
                       ("B_first_multi" if phase_has_re[e["side"]] else "A_first_single"))
                rows.append({
                    "date": str(d), "side": e["side"], "reentry_idx": e["reentry_idx"],
                    "is_reset": int(is_re), "group": grp, "entry_min": e["entry_min"],
                    "entry": e["entry"], "ema": round(ema, 1),
                    "mfe_L": round(mfe, 3), "mae_L": round(mae, 3),
                    "reach_L3": reach["L3"], "reach_L4": reach["L4"], "reach_L5": reach["L5"],
                })
    return rows


def _agg(rows):
    n = len(rows)
    if not n:
        return None
    def rate(k):
        return sum(r[k] for r in rows) / n
    import statistics as st
    return {"n": n, "rL3": rate("reach_L3"), "rL4": rate("reach_L4"), "rL5": rate("reach_L5"),
            "mfe_med": st.median(r["mfe_L"] for r in rows), "mfe_mean": st.mean(r["mfe_L"] for r in rows),
            "mae_med": st.median(r["mae_L"] for r in rows),
            "emin_med": int(st.median(r["entry_min"] for r in rows))}


def _line(label, a):
    if not a:
        print(f"  {label:22s} N=0")
        return
    print(f"  {label:22s} N={a['n']:4d} | L3/L4/L5={a['rL3']*100:5.1f}/{a['rL4']*100:5.1f}/{a['rL5']*100:5.1f}% "
          f"| MFE med/mean={a['mfe_med']:.2f}/{a['mfe_mean']:.2f} | MAE med={a['mae_med']:.2f} | emin={a['emin_med']}")


def main():
    RESULTS.mkdir(exist_ok=True)
    rows = collect()
    with open(RESULTS / "entries.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print("=" * 100)
    print("H130 Phase 1 — L1-reset 同相位再進場｜分佈探索")
    print("=" * 100)
    days = {r["date"] for r in rows}
    re_rows = [r for r in rows if r["is_reset"]]
    print(f"\n總進場 N={len(rows)}｜涵蓋交易日={len(days)}｜L1-reset 再進場 N={len(re_rows)}")
    print(f"時間範圍 {min(days)} ~ {max(days)}")

    # 再進場次數分佈
    print("\n[每相位再進場次數分佈 + 多空]")
    for side in ("short", "long"):
        sr = [r for r in rows if r["side"] == side]
        by_k = defaultdict(int)
        for r in sr:
            by_k[min(r["reentry_idx"], 3)] += 1
        re_days = len({r["date"] for r in sr if r["is_reset"]})
        dist = "  ".join(f"{k}{'+' if k==3 else ''}={by_k[k]}" for k in sorted(by_k))
        print(f"  {side:6s}: 總 N={len(sr)} | {dist} | 具 L1-reset 的日={re_days}")

    # 對照組（pooled）
    print("\n[對照組 — pooled]")
    for g in ("A_first_single", "B_first_multi", "C_reset"):
        _line(g, _agg([r for r in rows if r["group"] == g]))
    print("  ▶ C vs B（同為有 reset 的相位，再進場 vs 首次）= 真正 reset 效應")
    print("  ▶ B vs A = selection（會出現 reset 的相位 vs 不會的）")

    # 時間配對
    print("\n[時間配對 — 09:30/10:30/11:30 閘，首次 vs reset]")
    for lo, hi, nm in ((525, 570, "<09:30"), (570, 630, "09:30-10:30"),
                       (630, 690, "10:30-11:30"), (690, 826, ">=11:30")):
        f1 = [r for r in rows if not r["is_reset"] and lo <= r["entry_min"] < hi]
        f2 = [r for r in rows if r["is_reset"] and lo <= r["entry_min"] < hi]
        print(f"  {nm}")
        _line("  首次", _agg(f1))
        _line("  reset", _agg(f2))

    # overfit 檢查：leave-6/24-out + 單日集中度
    print("\n[overfit 檢查]")
    re_no624 = [r for r in re_rows if r["date"] != "2026-06-24"]
    _line("reset 全部", _agg(re_rows))
    _line("reset 去掉6/24", _agg(re_no624))
    by_day_re = defaultdict(int)
    for r in re_rows:
        by_day_re[r["date"]] += 1
    top = sorted(by_day_re.items(), key=lambda x: -x[1])[:5]
    print(f"  L1-reset 再進場分佈於 {len(by_day_re)} 個交易日；單日最多前5：{top}")
    reach5 = [r["date"] for r in re_rows if r["reach_L5"]]
    print(f"  reset 碰 L5 的 {sum(r['reach_L5'] for r in re_rows)} 筆來自 {len(set(reach5))} 個不同日")

    figures(rows)
    print(f"\n[saved] {RESULTS/'entries.csv'} (N={len(rows)})")


def figures(rows):
    buckets = [(525, 570, "<9:30"), (570, 630, "9:30-\n10:30"), (630, 690, "10:30-\n11:30"), (690, 826, ">=11:30")]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    xs = range(len(buckets))
    for lv, col in (("rL4", "#ff7f0e"), ("rL5", "#d62728")):
        for isre, ls, mk in ((0, "--", "o"), (1, "-", "s")):
            ys = []
            for lo, hi, _ in buckets:
                a = _agg([r for r in rows if r["is_reset"] == isre and lo <= r["entry_min"] < hi])
                ys.append(a[lv] * 100 if a else 0)
            axes[0].plot(xs, ys, ls + mk, color=col, alpha=0.6 if not isre else 1.0,
                         label=f"{lv[1:]} {'reset' if isre else 'first'}")
    axes[0].set_xticks(list(xs))
    axes[0].set_xticklabels([b[2] for b in buckets])
    axes[0].set_ylabel("reach rate (%)")
    axes[0].set_title("time-matched: reset(solid) vs first(dashed) deep-target reach")
    axes[0].legend(fontsize=8)
    axes[0].grid(alpha=0.3)
    g3 = ("A_first_single", "B_first_multi", "C_reset")
    aggs = [_agg([r for r in rows if r["group"] == g]) for g in g3]
    w = 0.27
    for i, (lv, col) in enumerate((("rL3", "#1f77b4"), ("rL4", "#ff7f0e"), ("rL5", "#d62728"))):
        axes[1].bar([v + (i - 1) * w for v in range(3)], [a[lv] * 100 if a else 0 for a in aggs], w, label=lv[1:], color=col)
    axes[1].set_xticks(range(3))
    axes[1].set_xticklabels(["A:first\nsingle", "B:first\nmulti", "C:reset"])
    axes[1].set_ylabel("reach rate (%)")
    axes[1].set_title("C vs B = pure reset effect")
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(RESULTS / "reset_excursion.png", dpi=110)
    print(f"[saved] {RESULTS/'reset_excursion.png'}")


if __name__ == "__main__":
    main()
