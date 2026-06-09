"""H110 Phase 1 — 檢查點掃描 × 五分位強度 × 方向命中（分佈探索）。

層 A（純訊號品質，全 181 日 2025-06~2026-02）：
  檢查點 t∈{09:05,09:10,09:15,09:20,09:25,09:30}，dci_long(t)=W-20 thrust@t
  （動態 20日均值大型股，value-weighted tanh）。依 |dci_long(t)| 五分位（逐 t 各自定界），
  看 sign(dci_long) 對「TX 當日擺更遠的一邊」(up_full vs dn_full) 命中率的強度單調性與 t 成熟度。
層 B（reversal 特定，因果）：
  對窗內 reversal 進場（output/reversal_2025_trades.csv，覆蓋 2025-06~2025-12），每個 t 取進場≥t 子集，
  base(=trade Direction，5m120MA 斜率) vs dci(t) 歧異率、歧異日分五分位「誰對」（對應 TX 擺更遠的一邊）。
因果代價表：各 t 可用 reversal 筆數(進場≥t) vs 訊號強度。

限制：上市-only、窗內小樣本、偏多頭；層 B 缺 2026-01/02（CSV 只到 2025）。全部附 N。
用法：uv run python research/active/H110-reversal-dci-direction/explore.py
"""
from __future__ import annotations

import os
import sys
from datetime import date, time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
H095 = HERE.parents[0] / "H095-reach-ladder-exit"
sys.path.insert(0, str(H095))
from dci_universe_sweep import stock_features, wmean_tanh   # noqa: E402

DB = os.environ.get("STOCK_MIN_DB", str(HERE.parents[2] / "data" / "futures.duckdb"))
LO, HI = date(2025, 6, 1), date(2026, 2, 28)
CKPTS = ["09:05:00", "09:10:00", "09:15:00", "09:20:00", "09:25:00", "09:30:00"]
KEYS = [s[:5] for s in CKPTS]
REV_CSV = HERE.parents[2] / "output" / "reversal_2025_trades.csv"


def snap_prices(c):
    filt = ", ".join(
        f"arg_max(close, minute) FILTER (WHERE minute <= TIME '{s}') AS \"p_{s[:5]}\"" for s in CKPTS)
    return c.execute(
        f"SELECT trade_date, stock_id, {filt} FROM stock_min "
        f"WHERE trade_date BETWEEN ? AND ? AND minute <= TIME '{CKPTS[-1]}' "
        f"GROUP BY trade_date, stock_id", [LO, HI]).df()


def tx_dir(c):
    bars = c.execute(
        "SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, high, low FROM ohlcv_1m "
        "WHERE symbol='TX' AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "AND CAST(timestamp AS DATE) BETWEEN ? AND ? ORDER BY d,t", [LO, HI]).df()
    bars["high"] = bars["high"].astype(float); bars["low"] = bars["low"].astype(float)
    rows = []
    for d, g in bars.groupby("d"):
        hi, lo = g["high"].values, g["low"].values
        up = np.maximum.accumulate(hi - np.minimum.accumulate(lo))[-1]
        dn = np.maximum.accumulate(np.maximum.accumulate(hi) - lo)[-1]
        rows.append({"d": pd.Timestamp(d).date(), "dir_full": 1 if up >= dn else -1,
                     "up_full": up, "dn_full": dn})
    return pd.DataFrame(rows).set_index("d")


def build_dci(c):
    feat = stock_features(c); px = snap_prices(c)
    g = px.merge(feat, on=["trade_date", "stock_id"], how="inner")
    g = g[g["range_i"] > 0]
    rows = []
    for d, gd in g.groupby("trade_date"):
        gv = gd.dropna(subset=["trail_val"]).nlargest(20, "trail_val")
        rec = {"d": pd.Timestamp(d).date()}
        for k in KEYS:
            rec[f"th_{k}"] = wmean_tanh(gv, f"p_{k}", "trail_val")
        rows.append(rec)
    return pd.DataFrame(rows).set_index("d")


def quintile(x):
    """回傳每點所屬五分位 (0..4)，依 x 的分位；NaN→-1。"""
    s = pd.Series(x)
    try:
        return pd.qcut(s, 5, labels=False, duplicates="drop").fillna(-1).astype(int).values
    except ValueError:
        return np.full(len(s), -1)


def main():
    with duckdb.connect(DB, read_only=True) as c:
        dci = build_dci(c)
        tx = tx_dir(c)
    df = dci.join(tx, how="inner")
    N = len(df)

    L = ["=" * 88,
         f"H110 Phase 1 — 檢查點掃描 × 五分位 × 方向命中  N={N} 日（{df.index.min()}~{df.index.max()}）",
         "層 A：sign(dci_long) 對『TX 擺更遠的一邊』命中率；|dci_long| 五分位（逐檢查點定界）"]

    # ── 層 A：各 t × 五分位 命中率 ──
    L.append("\n" + "─" * 88)
    L.append("層 A) 命中率 by 檢查點 × |thrust| 五分位（Q1弱→Q5強）  + 全體命中 + 強度corr")
    L.append(f"{'t':>6} | {'Q1':>6}{'Q2':>6}{'Q3':>6}{'Q4':>6}{'Q5':>6} | {'全體':>6} | {'r(|th|,命中)':>11}")
    baseline = max((df["dir_full"] == 1).mean(), (df["dir_full"] == -1).mean())
    layerA = {}
    for k in KEYS:
        th = df[f"th_{k}"]
        pred = np.sign(th)
        hit = (pred == df["dir_full"]).astype(float)
        q = quintile(th.abs())
        cells = []
        for qi in range(5):
            m = q == qi
            cells.append(f"{hit[m].mean():.0%}" if m.sum() else "  -  ")
        allhit = hit[pred != 0].mean()
        rstrength = np.corrcoef(th.abs(), hit)[0, 1] if hit.std() else np.nan
        layerA[k] = {"q": [hit[q == qi].mean() if (q == qi).sum() else np.nan for qi in range(5)],
                     "all": allhit}
        L.append(f"{k:>6} | " + "".join(f"{x:>6}" for x in cells) +
                 f" | {allhit:>6.0%} | {rstrength:>+11.3f}")
    L.append(f"  （多數類基準={baseline:.0%}；Q5=最強分位，期望命中最高且 Q1<Q5 單調）")

    # ── 層 B：reversal 特定 ──
    L.append("\n" + "─" * 88)
    if REV_CSV.exists():
        rv = pd.read_csv(REV_CSV)
        rv["d"] = pd.to_datetime(rv["Date"]).dt.date
        rv = rv[rv["d"] >= date(2025, 6, 2)].copy()
        et = pd.to_datetime(rv["EntryTime"].astype(str).str.slice(0, 19), errors="coerce")
        rv["emin"] = (et.dt.hour * 60 + et.dt.minute).values
        rv["base_dir"] = np.where(rv["Direction"].str.lower().str.startswith("l"), 1, -1)
        rv = rv.merge(df.reset_index(), on="d", how="inner")   # 帶 dci + dir_full
        L.append(f"層 B) reversal 特定（CSV 覆蓋 {rv['d'].min()}~{rv['d'].max()}，N={len(rv)}；缺 2026-01/02）")
        L.append(f"{'t':>6} | {'可用筆數':>8}{'歧異率':>7} | {'歧異日:base命中':>14}{'dci命中':>9} | {'強分位(Q4-5)dci命中':>18}")
        for k in KEYS:
            tmin = int(k[:2]) * 60 + int(k[3:5])
            sub = rv[rv["emin"] >= tmin].copy()
            if len(sub) == 0:
                L.append(f"{k:>6} | {'0':>8}"); continue
            sub["dci_dir"] = np.sign(sub[f"th_{k}"])
            disag = sub[sub["dci_dir"] != sub["base_dir"]]
            drate = len(disag) / len(sub)
            # 誰對：對應 dir_full
            if len(disag):
                base_hit = (disag["base_dir"] == disag["dir_full"]).mean()
                dci_hit = (disag["dci_dir"] == disag["dir_full"]).mean()
                # 強分位（用該 t 的 181 日 |th| 分位，取 Q4-5＝前 40%）
                cut = df[f"th_{k}"].abs().quantile(0.6)
                strong = disag[disag[f"th_{k}"].abs() >= cut]
                sdci = (strong["dci_dir"] == strong["dir_full"]).mean() if len(strong) else np.nan
                L.append(f"{k:>6} | {len(sub):>8}{drate:>7.0%} | {base_hit:>14.0%}{dci_hit:>9.0%} | "
                         f"{sdci:>14.0%}(n{len(strong)})")
            else:
                L.append(f"{k:>6} | {len(sub):>8}{drate:>7.0%} | {'無歧異':>14}")
    else:
        L.append("層 B) 找不到 reversal CSV，略過")

    # ── 因果代價表已併入層 B『可用筆數』欄 ──
    L.append("\n  ⚠ 上市-only、窗內小樣本、偏多頭；層 B 缺 2026-01/02（待實跑 reversal 補全）。")
    txt = "\n".join(L)
    print(txt)
    out = HERE / "results"; out.mkdir(exist_ok=True)
    (out / "distribution_raw.txt").write_text(txt + "\n")
    df.to_csv(out / "dci_checkpoint_panel.csv")
    print(f"\n存：{out/'distribution_raw.txt'}")


if __name__ == "__main__":
    main()
