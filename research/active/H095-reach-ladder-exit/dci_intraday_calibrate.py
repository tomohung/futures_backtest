"""DCI-intraday 多日 τ/β 校準（Phase-1 探索；對齊 dci_intraday_spec.md §2/§3/§6）。

把單日目視版（dci_intraday_20260529.py）升級成多日統計校準：對每個交易日重建
09:30 的 thrust / breadth / confirm，標記當日 TX 是否達 open-anchor L3 / L4，再用
point-biserial 相關 + 十分位命中率（多空分開）找 τ（thrust 門檻）、β（confirm 門檻）。

公式（dci_intraday_spec §2–§3，**非單日那支的 OC-only 投票版**）：
  m_i     = tanh((price@930_i − open_i) / range_i)          每檔權值股開盤錨動能
  range_i = 該股 causal EMA20(日 high−low)                  跨年自我標準化、與 reach 同尺
  thrust  = Σ w_i·m_i / Σ w_i   (i∈權值前21；w_i=前一日成交值，causal 權重近似)
  breadth = (up930 − dn930) / active   全 TWSE 上市 09:30 running（vs 昨收）
  confirm = breadth · sign(thrust)
  regime  : |thrust|≥τ & confirm≥β → TREND；|thrust|≥τ & confirm<β → NARROW；else CHOP

reach 標記（TX open-anchor 擺幅 vs c×EMA20，c: L3=0.711 L4=0.977；對齊 daystats/單日版）：
  up_swing(t)=max_{s≤t}(high−run_low)、dn_swing(t)=max_{s≤t}(run_high−low)
  - full  ：全日(08:45–13:45)最大擺幅是否達階（spec §6.2 原定）
  - fwd   ：09:30 當下尚未達階、但 09:30 之後才達（防自證套套邏輯；memory 鐵律）

限制（務必記住）：
  * stock_min 為 **TWSE 上市-only**（下載 --market TWSE），故 breadth 是上市-only，
    與 spec 想要的全市場 breadth 有 TPEX 參與度差；τ/β 待補 TPEX 盤中後複驗。
  * w_i 權重用前一日成交值近似（無官方比重表，spec §1/§7 允許）。
  * 樣本只含已載入的 2025-06 ~ 2026-02（~181 日），跨年穩定性僅能 2025 vs 2026 粗分。

用法：
  uv run python research/active/H095-reach-ladder-exit/dci_intraday_calibrate.py
  STOCK_MIN_DB=path 可指向快照副本（回補背景跑寫鎖時）。
"""
from __future__ import annotations

import os
from datetime import date, time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

DB = os.environ.get(
    "STOCK_MIN_DB",
    str(Path(__file__).resolve().parents[3] / "data" / "futures.duckdb"),
)
SNAP = time(9, 30)              # 09:30 盤中快照
START, END = date(2025, 6, 1), date(2026, 2, 28)

TOP_WEIGHT_SYMBOLS = [
    "2330", "2317", "2454", "2308", "2881", "2382", "2891", "2882", "2412",
    "2303", "3711", "2886", "1216", "2884", "2885", "2357", "2892", "2880",
    "3008", "2002", "2207",
]
# reach 階：c×EMA20（L3 名目 50%、L4 名目 25%）。校準聚焦 L3/L4（出場決策關鍵階）。
LVL = {"L3": 0.711, "L4": 0.977}


# ───────────────────────── 資料載入 ─────────────────────────
def trading_days(c) -> list:
    # 統一回 pandas Timestamp，與各 .df() 的 trade_date（Timestamp）對齊
    return [pd.Timestamp(r[0]) for r in c.execute(
        "SELECT DISTINCT trade_date FROM stock_min "
        "WHERE trade_date BETWEEN ? AND ? ORDER BY 1", [START, END]
    ).fetchall()]


def weight_ranges(c) -> pd.DataFrame:
    """權值股每日 causal EMA20(日振幅)；index=(symbol,trade_date)→range_i。
    用全史 stock_day 暖機，再裁到我們的範圍。"""
    sd = c.execute(
        "SELECT symbol, trade_date, high, low FROM stock_day "
        "WHERE symbol IN ({}) AND high IS NOT NULL AND low IS NOT NULL "
        "ORDER BY symbol, trade_date".format(",".join("?" * len(TOP_WEIGHT_SYMBOLS))),
        TOP_WEIGHT_SYMBOLS,
    ).df()
    sd["rng"] = sd["high"].astype(float) - sd["low"].astype(float)
    # causal：shift(1) 後 EMA20（不含當日）
    sd["range_i"] = (
        sd.groupby("symbol")["rng"]
        .transform(lambda s: s.shift(1).ewm(span=20, adjust=False).mean())
    )
    return sd.set_index(["symbol", "trade_date"])["range_i"]


def snapshot_930(c) -> pd.DataFrame:
    """每日每檔 09:30 價（≤09:30 最後一根 close，ffill 語意）+ stock_day open/prev/value。
    回傳 long df: trade_date, stock_id, p930, open, prev, prev_value。"""
    px = c.execute(
        "SELECT trade_date, stock_id, arg_max(close, minute) AS p930 "
        "FROM stock_min WHERE trade_date BETWEEN ? AND ? AND minute <= ? "
        "GROUP BY trade_date, stock_id", [START, END, SNAP]
    ).df()
    sd = c.execute(
        "SELECT trade_date, symbol AS stock_id, open, close, change, value "
        "FROM stock_day WHERE trade_date BETWEEN ? AND ?", [START, END]
    ).df()
    sd["open"] = sd["open"].astype(float)
    sd["prev"] = sd["close"].astype(float) - sd["change"].astype(float)
    # 前一日成交值（causal 權重）
    sd = sd.sort_values(["stock_id", "trade_date"])
    sd["prev_value"] = sd.groupby("stock_id")["value"].shift(1)
    m = px.merge(sd[["trade_date", "stock_id", "open", "prev", "prev_value"]],
                 on=["trade_date", "stock_id"], how="inner")
    m["p930"] = m["p930"].astype(float)
    return m


def tx_ladder_labels(c) -> pd.DataFrame:
    """每日 TX：EMA20(振幅) + 全日/09:30/forward 的最大 up/dn 擺幅。"""
    rng = c.execute(
        "SELECT CAST(timestamp AS DATE) d, MAX(high)-MIN(low) r FROM ohlcv_1m "
        "WHERE symbol='TX' AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "GROUP BY 1 ORDER BY 1"
    ).df()
    rng["ema20"] = rng["r"].astype(float).shift(1).ewm(span=20, adjust=False).mean()
    ema = rng.set_index("d")["ema20"]

    bars = c.execute(
        "SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, high, low FROM ohlcv_1m "
        "WHERE symbol='TX' AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "AND CAST(timestamp AS DATE) BETWEEN ? AND ? ORDER BY d, t", [START, END]
    ).df()
    bars["high"] = bars["high"].astype(float)
    bars["low"] = bars["low"].astype(float)

    rows = []
    for d, g in bars.groupby("d"):
        g = g.sort_values("t")
        hi, lo, t = g["high"].values, g["low"].values, g["t"].values
        run_lo = np.minimum.accumulate(lo)
        run_hi = np.maximum.accumulate(hi)
        up_sw = np.maximum.accumulate(hi - run_lo)
        dn_sw = np.maximum.accumulate(run_hi - lo)
        i930 = np.searchsorted([x for x in t], SNAP, side="right") - 1  # 最後一根 ≤09:30
        i930 = max(i930, 0)
        rows.append({
            "trade_date": d, "ema20": ema.get(d, np.nan),
            "up_full": up_sw[-1], "dn_full": dn_sw[-1],
            "up_930": up_sw[i930], "dn_930": dn_sw[i930],
        })
    return pd.DataFrame(rows)


# ───────────────────────── 指標合成 ─────────────────────────
def build_panel(c) -> pd.DataFrame:
    days = trading_days(c)
    ranges = weight_ranges(c)
    snap = snapshot_930(c)
    tx = tx_ladder_labels(c).set_index("trade_date")

    wset = set(TOP_WEIGHT_SYMBOLS)
    rows = []
    for d in days:
        day_snap = snap[snap["trade_date"] == d]
        if day_snap.empty:
            continue
        # ── breadth：全 TWSE 上市 09:30 running（vs 昨收）──
        up = int((day_snap["p930"] > day_snap["prev"]).sum())
        dn = int((day_snap["p930"] < day_snap["prev"]).sum())
        active = int(len(day_snap))
        breadth = (up - dn) / active if active else 0.0

        # ── thrust：權值前 21 的 tanh 開盤錨動能，前一日成交值加權 ──
        w = day_snap[day_snap["stock_id"].isin(wset)].copy()
        num = den = 0.0
        for _, r in w.iterrows():
            rng_i = ranges.get((r["stock_id"], d), np.nan)
            if not (rng_i and rng_i > 0):
                continue
            wt = r["prev_value"]
            if not (wt and wt > 0):
                continue
            m_i = np.tanh((r["p930"] - r["open"]) / rng_i)
            num += m_i * wt
            den += wt
        thrust = num / den if den else 0.0
        confirm = breadth * (1 if thrust > 0 else -1 if thrust < 0 else 0)

        # ── reach 標記 ──
        txr = tx.loc[d] if d in tx.index else None
        if txr is None or not (txr["ema20"] and txr["ema20"] > 0):
            continue
        ema = txr["ema20"]
        rec = {
            "trade_date": d, "n_weight": int(den > 0) and len(w),
            "thrust": thrust, "breadth": breadth, "confirm": confirm,
            "up_full": txr["up_full"], "dn_full": txr["dn_full"],
            "ema20": ema, "active": active,
        }
        for name, co in LVL.items():
            lvl = co * ema
            rec[f"up_{name}_full"] = int(txr["up_full"] >= lvl)
            rec[f"dn_{name}_full"] = int(txr["dn_full"] >= lvl)
            # forward：09:30 尚未達、之後才達（防套套邏輯）
            rec[f"up_{name}_pre"] = int(txr["up_930"] >= lvl)
            rec[f"dn_{name}_pre"] = int(txr["dn_930"] >= lvl)
            rec[f"up_{name}_fwd"] = int(txr["up_930"] < lvl <= txr["up_full"])
            rec[f"dn_{name}_fwd"] = int(txr["dn_930"] < lvl <= txr["dn_full"])
        rows.append(rec)
    return pd.DataFrame(rows)


# ───────────────────────── 分析 ─────────────────────────
def point_biserial(x: np.ndarray, y: np.ndarray) -> float:
    """連續 x 與二元 y 的點二系列相關（= Pearson）。"""
    if len(x) < 5 or y.std() == 0 or x.std() == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def decile_table(df: pd.DataFrame, xcol: str, ycol: str, q: int = 5) -> pd.DataFrame:
    """把 x 切 q 分位，看每組 y 命中率與樣本數。"""
    d = df[[xcol, ycol]].dropna()
    if len(d) < q * 3:
        q = max(2, len(d) // 5)
    d = d.copy()
    try:
        d["bin"] = pd.qcut(d[xcol], q, duplicates="drop")
    except ValueError:
        return pd.DataFrame()
    g = d.groupby("bin", observed=True)[ycol].agg(["mean", "count"])
    g.columns = ["hit_rate", "n"]
    return g.reset_index()


def report_side(df: pd.DataFrame, side: str) -> list[str]:
    """side='up'(多) 或 'dn'(空)。多方用 thrust，空方用 −thrust 當力道。"""
    out = []
    sgn = "多方(up)" if side == "up" else "空方(dn)"
    force = df["thrust"] if side == "up" else -df["thrust"]
    cf = df["confirm"]  # confirm 已 = breadth·sign(thrust)，同向恆正
    out.append(f"\n{'='*70}\n【{sgn}】N={len(df)}  力道=" +
               ("thrust" if side == "up" else "−thrust"))
    for lvl in ("L3", "L4"):
        for mode in ("full", "fwd"):
            yc = f"{side}_{lvl}_{mode}"
            if yc not in df:
                continue
            sub = df.copy()
            if mode == "fwd":  # forward 僅看 09:30 尚未達階者
                sub = df[df[f"{side}_{lvl}_pre"] == 0]
            y = sub[yc].values
            base = y.mean() if len(y) else np.nan
            r_f = point_biserial(force.loc[sub.index].values, y)
            r_c = point_biserial(cf.loc[sub.index].values, y)
            tag = "全日" if mode == "full" else "fwd(09:30後)"
            out.append(
                f"  {lvl} {tag:>12}  達標率={base:5.1%} (N={len(y)})  "
                f"r(力道)={r_f:+.3f}  r(confirm)={r_c:+.3f}")
            # 力道五分位命中率（找 τ）
            sub2 = sub.assign(_force=force.loc[sub.index].values)
            dt = decile_table(sub2, "_force", yc, q=5)
            if not dt.empty:
                cells = "  ".join(
                    f"[{row['hit_rate']:.0%},n{int(row['n'])}]" for _, row in dt.iterrows())
                out.append(f"        力道分位達標率: {cells}")
    return out


def main():
    with duckdb.connect(DB, read_only=True) as c:
        panel = build_panel(c)
    if panel.empty:
        raise SystemExit("panel 為空——檢查 stock_min/stock_day 載入。")

    lines = []
    lines.append("=" * 70)
    lines.append("DCI-intraday 多日 τ/β 校準（Phase-1 探索，非 confirmed）")
    lines.append(f"範圍 {panel['trade_date'].min()} ~ {panel['trade_date'].max()}  "
                 f"N={len(panel)} 交易日  快照=09:30")
    lines.append("breadth=上市(TWSE)-only；thrust 權重=前一日成交值；reach=TX open-anchor 擺幅")
    lines.append(f"thrust 分佈: min={panel['thrust'].min():+.3f} "
                 f"p25={panel['thrust'].quantile(.25):+.3f} "
                 f"med={panel['thrust'].median():+.3f} "
                 f"p75={panel['thrust'].quantile(.75):+.3f} "
                 f"max={panel['thrust'].max():+.3f}")
    lines.append(f"breadth 分佈: min={panel['breadth'].min():+.3f} "
                 f"med={panel['breadth'].median():+.3f} "
                 f"max={panel['breadth'].max():+.3f}")

    for side in ("up", "dn"):
        lines += report_side(panel, side)

    # 跨年粗分穩定性（2025 vs 2026）
    lines.append(f"\n{'='*70}\n【跨年穩定性（2025 H2 vs 2026）】")
    panel["yr"] = pd.to_datetime(panel["trade_date"]).dt.year
    for yr, g in panel.groupby("yr"):
        for side in ("up", "dn"):
            force = g["thrust"] if side == "up" else -g["thrust"]
            r = point_biserial(force.values, g[f"{side}_L3_full"].values)
            lines.append(f"  {yr} {('多' if side=='up' else '空')}方 r(力道,L3_full)="
                         f"{r:+.3f}  L3達標率={g[f'{side}_L3_full'].mean():.1%}  N={len(g)}")

    txt = "\n".join(lines)
    print(txt)
    outdir = Path(__file__).parent / "results"
    outdir.mkdir(exist_ok=True)
    (outdir / "dci_intraday_calibrate.txt").write_text(txt + "\n")
    panel.to_csv(outdir / "dci_intraday_panel.csv", index=False)
    print(f"\n存：{outdir/'dci_intraday_calibrate.txt'}\n    {outdir/'dci_intraday_panel.csv'}")


if __name__ == "__main__":
    main()
