"""H126 Phase 1 探索 — 同向第二次 L2 拉回續攻。

重用 services/l2_pullback.detect_day（causal，無前視）逐日掃所有 L2 拉回進場，依「同方向序數」
分組，零策略量測進場後 forward excursion（碰 L3/L4/L5 比率、MFE/MAE），並用三組對照拆解
「序數效應」與「趨勢日 selection」：
  A = 單次日的 1st（該 side 當日僅 1 筆）
  B = 多次日的 1st（該 side 當日 ≥2 筆，取第 1 筆）
  C = 2nd+（多次日的第 2 筆起）
  C vs B → 真正的序數效應（同為多次日，後面 vs 第一個；非 selection tautology）
  B vs A → 趨勢日 selection 效應本身

附帶觀察欄位（僅描述、不入偵測）：VWAP flip（進場前是否曾站上成本線又跌破/反之）、EOD DCI。

用法：uv run python research/active/H126-second-l2-pullback/explore.py
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
from src.chart_ui.services.dci_daily import compute_daily_dci
from src.chart_ui.services.l2_pullback import COEF, detect_day

RESULTS = Path(__file__).parent / "results"
SESSION = "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'"

# 時間桶：對齊系統關卡時間閘（09:30=570 / 10:30=630 / 11:30=690）。半開 [lo,hi)，分鐘=h*60+m。
BUCKETS = [(525, 570, "<09:30"), (570, 630, "09:30-10:30"),
           (630, 690, "10:30-11:30"), (690, 826, ">=11:30")]


def day_bars_vol(conn, sel: date):
    """(minute,o,h,l,c,v) 昇冪，日盤。"""
    rows = conn.execute(
        f"SELECT CAST(timestamp AS TIME) t, open, high, low, close, volume FROM ohlcv_1m "
        f"WHERE symbol = ? AND CAST(timestamp AS DATE) = ? {SESSION} ORDER BY timestamp",
        [SYMBOL, sel]).fetchall()
    return [(t.hour * 60 + t.minute, float(o), float(h), float(l), float(c), int(v))
            for t, o, h, l, c, v in rows]


def vwap_series(bars6):
    """累計 VWAP（typical=(h+l+c)/3）。回傳 list 對齊 bars。"""
    out, ctp, cv = [], 0.0, 0.0
    for (_m, _o, h, l, c, v) in bars6:
        tp = (h + l + c) / 3.0
        ctp += tp * v
        cv += v
        out.append(ctp / cv if cv > 0 else c)
    return out


def vwap_flip_before(entry_i, side, bars6, vwap):
    """進場前(含 entry_i)：short=曾收在 VWAP 上方後又跌破；long=曾收在下方後又站上。"""
    above = below = False
    flip = False
    for i in range(entry_i + 1):
        c = bars6[i][4]
        if c > vwap[i]:
            above = True
            if side == "long" and below:
                flip = True
        elif c < vwap[i]:
            below = True
            if side == "short" and above:
                flip = True
    return flip


def forward(entry_i, side, anchor, dist, bars):
    """進場(收盤價)後到收盤的 forward excursion。
    回傳 (mfe_pts, mae_close_pts, reach{L3/L4/L5: mae_before_pts 或 None})。"""
    up = side == "long"
    entry_px = bars[entry_i][4]
    L3d, L4d, L5d = dist["L3"], dist["L4"], dist["L5"]
    reach = {"L3": None, "L4": None, "L5": None}
    mfe = 0.0
    run_adv = 0.0
    for (_m, _o, h, l, _c, *_r) in bars[entry_i + 1:]:
        adv = (h - entry_px) if not up else (entry_px - l)   # 逆行(虧損方向)
        run_adv = max(run_adv, adv)
        fpx = l if not up else h                              # 順行極值價
        for lv, d in (("L3", L3d), ("L4", L4d), ("L5", L5d)):
            if reach[lv] is None:
                hit = (fpx <= anchor - d) if not up else (fpx >= anchor + d)
                if hit:
                    reach[lv] = run_adv
        fav = (entry_px - l) if not up else (h - entry_px)
        mfe = max(mfe, fav)
    return mfe, run_adv, reach


def main():
    RESULTS.mkdir(exist_ok=True)
    rows = []                       # 每筆進場一列
    dci_cache: dict = {}
    with duckdb.connect(str(paths.DUCKDB_PATH), read_only=True) as conn:
        days = [r[0] for r in conn.execute(
            f"SELECT DISTINCT CAST(timestamp AS DATE) d FROM ohlcv_1m WHERE symbol=? {SESSION} "
            "ORDER BY d", [SYMBOL]).fetchall()]
        for d in days:
            ema20 = _ema20_range(conn, d)
            if not ema20:
                continue
            bars6 = day_bars_vol(conn, d)
            if len(bars6) < 5:
                continue
            bars5 = [(b[0], b[1], b[2], b[3], b[4]) for b in bars6]
            entries, dist = detect_day(bars5, ema20)
            if not entries:
                continue
            vwap = vwap_series(bars6)
            try:
                dci = dci_cache.setdefault(d, compute_daily_dci(conn, d))
            except Exception:
                dci = None
            # 同 side 計數（昇冪 = 時間序）→ 序數
            side_count = defaultdict(int)
            day_side_total = defaultdict(int)
            for e in entries:
                day_side_total[e["side"]] += 1
            for e in entries:
                side = e["side"]
                side_count[side] += 1
                k = side_count[side]
                mfe, mae, reach = forward(e["entry_i"], side, e["anchor"], dist, bars5)
                rows.append({
                    "date": str(d), "side": side, "ordinal": k,
                    "day_side_total": day_side_total[side],
                    "group": "C_2nd+" if k >= 2 else ("B_1st_multi" if day_side_total[side] >= 2 else "A_1st_single"),
                    "entry_min": e["entry_min"], "entry": e["entry"], "anchor": e["anchor"],
                    "depth_frac": round(e["depth_frac"], 3), "risk_pts": e["risk"],
                    "ema20": round(ema20, 1),
                    "mfe_pts": round(mfe, 1), "mfe_L": round(mfe / ema20, 3),
                    "mae_close_pts": round(mae, 1), "mae_close_L": round(mae / ema20, 3),
                    "reach_L3": int(reach["L3"] is not None),
                    "reach_L4": int(reach["L4"] is not None),
                    "reach_L5": int(reach["L5"] is not None),
                    "mae_before_L3": (round(reach["L3"], 1) if reach["L3"] is not None else ""),
                    "vwap_flip_before": int(vwap_flip_before(e["entry_i"], side, bars6, vwap)),
                    "dci_side": (dci["dci_short"] if dci and side == "short" else
                                 dci["dci_long"] if dci and side == "long" else ""),
                    "dci_regime": (dci["regime_short"] if dci and side == "short" else
                                   dci["regime_long"] if dci and side == "long" else ""),
                })

    # 落地 CSV
    csv_path = RESULTS / "entries.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    report(rows)
    figures(rows)
    print(f"\n[saved] {csv_path}  (N={len(rows)})")


# ---------- 報表 ----------
def _agg(rows):
    n = len(rows)
    if n == 0:
        return None
    def rate(key):
        return sum(r[key] for r in rows) / n
    mfe = sorted(r["mfe_L"] for r in rows)
    mae = sorted(r["mae_close_L"] for r in rows)
    def med(s):
        return s[len(s) // 2]
    return {
        "n": n,
        "rL3": rate("reach_L3"), "rL4": rate("reach_L4"), "rL5": rate("reach_L5"),
        "mfe_med": med(mfe), "mfe_mean": sum(mfe) / n,
        "mae_med": med(mae),
        "entry_min_med": sorted(r["entry_min"] for r in rows)[n // 2],
    }


def _line(label, a):
    if a is None:
        print(f"  {label:14s}  N=0")
        return
    print(f"  {label:14s}  N={a['n']:4d} | reach L3/L4/L5 = "
          f"{a['rL3']*100:5.1f}/{a['rL4']*100:5.1f}/{a['rL5']*100:5.1f}% | "
          f"MFE med/mean = {a['mfe_med']:.2f}/{a['mfe_mean']:.2f} L | "
          f"MAE med = {a['mae_med']:.2f} L | entry_min med = {a['entry_min_med']}")


def report(rows):
    print("=" * 100)
    print("H126 Phase 1 — 同向第二次 L2 拉回續攻｜分佈探索")
    print("=" * 100)
    days = {r["date"] for r in rows}
    print(f"\n總進場 N={len(rows)}　涵蓋交易日={len(days)}（有 ≥1 筆 L2 拉回的日）")
    print(f"時間範圍 {min(r['date'] for r in rows)} ~ {max(r['date'] for r in rows)}")

    # 序數分佈
    print("\n[同方向序數分佈]")
    for side in ("short", "long"):
        sr = [r for r in rows if r["side"] == side]
        by_k = defaultdict(int)
        for r in sr:
            by_k[min(r["ordinal"], 4)] += 1   # 4 = 4th+
        dist_str = "  ".join(f"{k}{'+' if k==4 else ''}次={by_k[k]}" for k in sorted(by_k))
        multi_days = len({r["date"] for r in sr if r["day_side_total"] >= 2})
        print(f"  {side:6s}: 總 N={len(sr)} | {dist_str} | 具≥2次同向的日={multi_days}")

    # 對照組（pooled 多空）
    print("\n[對照組 — pooled 多空]")
    for g in ("A_1st_single", "B_1st_multi", "C_2nd+"):
        _line(g, _agg([r for r in rows if r["group"] == g]))

    print("\n  ▶ C vs B（同為多次日，第二次 vs 第一次）＝真正序數效應（非 selection tautology）")
    print("  ▶ B vs A（多次日的第一次 vs 單次日的第一次）＝趨勢日 selection 效應本身")

    # 分邊對照
    for side in ("short", "long"):
        print(f"\n[對照組 — {side}]")
        for g in ("A_1st_single", "B_1st_multi", "C_2nd+"):
            _line(g, _agg([r for r in rows if r["group"] == g and r["side"] == side]))

    # 2nd+ 細分序數
    print("\n[2nd+ 再細分序數 — pooled]")
    for k in (2, 3):
        _line(f"{k}次", _agg([r for r in rows if r["ordinal"] == k]))
    _line("4次+", _agg([r for r in rows if r["ordinal"] >= 4]))

    # 時間配對對照：低 reach 是「序數差」還是「進場晚跑道短」？
    print("\n[時間配對對照 — 控制進場時間（09:30/10:30/11:30 閘），看序數是否仍有差]")
    for lo, hi, name in BUCKETS:
        b1 = [r for r in rows if r["ordinal"] == 1 and lo <= r["entry_min"] < hi]
        b2 = [r for r in rows if r["ordinal"] >= 2 and lo <= r["entry_min"] < hi]
        print(f"  {name}")
        _line("  1st", _agg(b1))
        _line("  2nd+", _agg(b2))

    # 同時段三方對照（A/B/C 同時段）：把「序數」與「趨勢日 selection」在固定時間下分開
    print("\n[同時段三方對照 — 固定時間下 A/B/C，C vs B=純序數、B vs A=純 selection]")
    for lo, hi, name in BUCKETS:
        print(f"  {name}")
        for g in ("A_1st_single", "B_1st_multi", "C_2nd+"):
            _line("  " + g, _agg([r for r in rows if r["group"] == g and lo <= r["entry_min"] < hi]))

    # VWAP 附帶欄位
    print("\n[附帶欄位 — VWAP flip（進場前曾站上成本線又跌破/反之）]")
    for g in ("A_1st_single", "B_1st_multi", "C_2nd+"):
        gr = [r for r in rows if r["group"] == g]
        if gr:
            fr = sum(r["vwap_flip_before"] for r in gr) / len(gr)
            print(f"  {g:14s}  flip 比率 = {fr*100:5.1f}%  (N={len(gr)})")

    # DCI 附帶欄位（EOD, hindsight）
    print("\n[附帶欄位 — EOD DCI（hindsight, 描述用）｜各組 dci_side 平均 + strong regime 比率]")
    for g in ("A_1st_single", "B_1st_multi", "C_2nd+"):
        gr = [r for r in rows if r["group"] == g and r["dci_side"] != ""]
        if gr:
            mean_dci = sum(float(r["dci_side"]) for r in gr) / len(gr)
            strong = sum(1 for r in gr if r["dci_regime"] == "strong") / len(gr)
            print(f"  {g:14s}  dci_side 平均 = {mean_dci:+.3f} | strong regime = {strong*100:4.1f}%  (N={len(gr)})")


# ---------- 圖 ----------
def figures(rows):
    buckets = [(lo, hi, name.replace("-", "-\n")) for lo, hi, name in BUCKETS]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    x = range(len(buckets))
    for lv, col in (("rL4", "#ff7f0e"), ("rL5", "#d62728")):
        for ordn, ls, mk in ((1, "--", "o"), (2, "-", "s")):
            ys = []
            for lo, hi, _ in buckets:
                sub = [r for r in rows if (r["ordinal"] == 1 if ordn == 1 else r["ordinal"] >= 2)
                       and lo <= r["entry_min"] < hi]
                a = _agg(sub)
                ys.append(a[lv] * 100 if a else 0)
            tag = "1st" if ordn == 1 else "2nd+"
            axes[0].plot(x, ys, ls + mk, color=col, label=f"{lv[1:]} {tag}",
                         alpha=0.6 if ordn == 1 else 1.0)
    axes[0].set_xticks(list(x))
    axes[0].set_xticklabels([b[2] for b in buckets])
    axes[0].set_ylabel("reach rate (%)")
    axes[0].set_title("time-matched: 2nd+ (solid) vs 1st (dashed) deep-target reach")
    axes[0].legend(fontsize=8)
    axes[0].grid(alpha=0.3)

    # 09:30-10:30 三方（最乾淨的 C vs B 純序數）
    g3 = ("A_1st_single", "B_1st_multi", "C_2nd+")
    aggs = [_agg([r for r in rows if r["group"] == g and 570 <= r["entry_min"] < 630]) for g in g3]
    xx = range(3)
    w = 0.27
    for i, (lv, col) in enumerate((("rL3", "#1f77b4"), ("rL4", "#ff7f0e"), ("rL5", "#d62728"))):
        axes[1].bar([v + (i - 1) * w for v in xx],
                    [a[lv] * 100 if a else 0 for a in aggs], w, label=lv[1:], color=col)
    axes[1].set_xticks(list(xx))
    axes[1].set_xticklabels(["A:1st\nsingle", "B:1st\nmulti", "C:2nd+"])
    axes[1].set_ylabel("reach rate (%)")
    axes[1].set_title("09:30-10:30 only: C vs B = pure ordinal (day-type+time fixed)")
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=0.3)

    fig.tight_layout()
    p = RESULTS / "ordinal_excursion.png"
    fig.savefig(p, dpi=110)
    print(f"[saved] {p}")


if __name__ == "__main__":
    main()
