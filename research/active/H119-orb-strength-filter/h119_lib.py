"""H119 共用：ORB 多突破事件建構（突破當下強度 + L3-before 排除）。

修正自第一版：
  - 強度讀「突破那一刻」CDF/NYF 延伸（非固定 09:30）。
  - 突破前已出現 L3（max high before breakout ≥ L3）→ 排除（不追延伸過的行情）。

供 explore.py / backtest.py / make_list.py 共用。
"""
from __future__ import annotations

import os
import sys

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "H118-nyf-preopen-reach"))
from explore import DB, PREOPEN_MIN_TICKS  # noqa: E402  (H118 explore，共用常數)

OR_END = "09:30:00"
ENTRY_CUTOFF = "10:00:00"
FORCE_EXIT = "13:30:00"
SL_PCT = 0.005
TP_MULT = 1.5
L3M, L4M = 0.711, 0.977


def _tx(conn):
    df = conn.execute("""
        SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, open, high, low, close
        FROM ohlcv_1m WHERE symbol='TX'
          AND CAST(timestamp AS TIME) BETWEEN TIME '08:45' AND TIME '13:45' ORDER BY d, t
    """).df()
    df["t"] = df["t"].astype(str)
    day = df.groupby("d").agg(hi=("high", "max"), lo=("low", "min")).reset_index()
    o = df[df["t"] == "08:45:00"][["d", "open"]].rename(columns={"open": "o"})
    day = day.merge(o, on="d").sort_values("d").reset_index(drop=True)
    day["ema20"] = (day["hi"] - day["lo"]).shift(1).ewm(span=20, adjust=False).mean()
    return {d: g for d, g in df.groupby("d")}, day.set_index("d")


def _sym(conn, sym):
    """SYM 每分鐘 close（date→time→close）＋ 日 open/ema20/preticks。"""
    df = conn.execute("""
        SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, open, high, low,
               close, tick_count
        FROM aux_futures_1m WHERE symbol=? ORDER BY d, t
    """, [sym]).df()
    df["t"] = df["t"].astype(str)
    day = df.groupby("d").agg(hi=("high", "max"), lo=("low", "min")).reset_index()
    o = df[df["t"] == "08:45:00"][["d", "open"]].rename(columns={"open": "o"})
    day = day.merge(o, on="d").sort_values("d").reset_index(drop=True)
    day["ema20"] = (day["hi"] - day["lo"]).shift(1).ewm(span=20, adjust=False).mean()
    pre = df[(df["t"] >= "08:45:00") & (df["t"] <= "08:59:00")]
    day = day.merge(pre.groupby("d")["tick_count"].sum().rename("preticks").reset_index(),
                    on="d", how="left")
    close_by = {d: dict(zip(g["t"], g["close"])) for d, g in df.groupby("d")}
    return close_by, day.set_index("d")


def build_events(conn, sym="CDF", or_end=OR_END, entry_cutoff=ENTRY_CUTOFF) -> pd.DataFrame:
    """每個 ORB 多突破事件一列（已排除突破前已達 L3 者）。

    or_end / entry_cutoff 可調：預設 OR 窗 08:45→09:30、突破窗 09:30→10:00；
    另可傳 08:57:00 / 09:15:00 做早窗變體。
    """
    tx_by, tx_day = _tx(conn)
    close_by, sym_day = _sym(conn, sym)
    rows = {}
    for d, g in tx_by.items():
        if d not in tx_day.index or d not in sym_day.index:
            continue
        o, ema = tx_day.loc[d, "o"], tx_day.loc[d, "ema20"]
        so, sema, pre = sym_day.loc[d, "o"], sym_day.loc[d, "ema20"], sym_day.loc[d, "preticks"]
        if not np.isfinite(ema) or ema <= 0 or not np.isfinite(sema) or sema <= 0:
            continue
        if not (pre >= PREOPEN_MIN_TICKS):
            continue
        t = g["t"].to_numpy(); hi = g["high"].to_numpy()
        lo = g["low"].to_numpy(); cl = g["close"].to_numpy()
        in_or = t <= or_end
        if in_or.sum() < 2:
            continue
        or_high = hi[in_or].max(); or_low = lo[in_or].min()
        win = (t > or_end) & (t <= entry_cutoff)
        idx = np.where(win & (hi > or_high))[0]
        if len(idx) == 0:
            continue
        i0 = idx[0]
        l3 = o + L3M * ema; l4 = o + L4M * ema
        # ── 突破前已達 L3 → 排除 ──
        if i0 > 0 and hi[:i0].max() >= l3:
            continue
        # ── 突破當下強度（SYM close @ 突破分鐘）──
        bt = t[i0]
        sc = close_by[d].get(bt)
        if sc is None:
            continue
        strength = float(np.tanh((float(sc) - so) / sema))
        # ── bracket 模擬 ──
        entry = float(or_high); sl = entry * (1 - SL_PCT); tp = entry + (entry - sl) * TP_MULT
        exit_px = None; exit_t = None
        for j in range(i0, len(t)):
            if t[j] > FORCE_EXIT:
                break
            if lo[j] <= sl:
                exit_px, exit_t = sl, t[j]; break
            if hi[j] >= tp:
                exit_px, exit_t = tp, t[j]; break
        if exit_px is None:
            le = np.where(t <= FORCE_EXIT)[0]; k = le[-1] if len(le) else len(t) - 1
            exit_px, exit_t = float(cl[k]), t[k]
        fwd_hi = hi[i0:].max(); fwd_lo = lo[i0:].min()
        rows[d] = dict(
            bo_time=bt, exit_time=exit_t, entry=entry, exit=float(exit_px),
            or_low=float(or_low), l3=round(l3, 1), l4=round(l4, 1),
            strength=round(strength, 3),
            reach_L3=float((fwd_hi - o) / ema >= L3M),
            reach_L4=float((fwd_hi - o) / ema >= L4M),
            revfail=float(fwd_lo <= or_low),
            pnl_pct=(exit_px - entry) / entry * 100,
        )
    df = pd.DataFrame(rows).T
    if not df.empty:
        df["yr"] = pd.to_datetime(df.index).year
    return df


def main():
    cfgs = [("09:30 窗", "09:30:00", "10:00:00"),
            ("08:57 早窗", "08:57:00", "09:15:00")]
    with duckdb.connect(DB, read_only=True) as conn:
        for sym in ["CDF", "NYF"]:
            for lab, oe, ec in cfgs:
                ev = build_events(conn, sym, oe, ec)
                n3 = ev["strength"].notna().sum() if not ev.empty else 0
                print(f"{sym} {lab}: 突破事件(排除L3-before後) N={len(ev)}（有強度 {n3}）")


if __name__ == "__main__":
    main()
