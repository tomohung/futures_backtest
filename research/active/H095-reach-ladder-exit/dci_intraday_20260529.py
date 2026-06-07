"""盤中 DCI 序列 × 台指走勢 × ladder 進程（單日：2026-05-29，首批分 k 驗證）。

目的：用首批下載的全市場分 k（stock_min）算出盤中逐分鐘 DCI，疊台指期 TX 走勢
與 reach ladder（L1–L5）進程，目視盤中 DCI 與台指方向/階梯達成的關係。

定義（盤中版，對齊 dci_daily.compute_daily_dci 的「等權兩票」收盤定義）：
  每檔每分鐘兩票：sign(price_t − 昨收) + sign(price_t − 當日開盤)
    - 昨收 = stock_day(當日).close − change；開盤 = stock_day(當日).open
    - price_t = stock_min 該檔 ≤ t 的最後一根 close（forward-fill；首根前用開盤）
  W = 權值前~21（TWSE，固定清單）兩票平均
  H = 當日成交值前 20（全市場 TWSE+TPEX，依 stock_day.value 取，整日固定集合）兩票平均
  B = (現價>昨收家數 − 現價<昨收家數) / 上市總家數（market_breadth listed_count, 全市場）
  dci_long = .40W+.35H+.25B；dci_short = .30W+.30H+.40B（多空不對稱，dci_spec §5）

ladder（TX-only，對齊 daystats）：
  EMA20 = 前 20 日盤(08:45–13:45)振幅的 causal ewm(span=20)；Ld = c×EMA20，
  c = 0.385/0.497/0.711/0.977/1.225（L1–L5；名目達到率 90/75/50/25/12.5%）。
  盤中達第幾階 = running 方向擺動：
    up_swing(t)=max_{s≤t}(high_s − run_low_s)、dn_swing(t)=max_{s≤t}(run_high_s − low_s)。

注意：W 用固定權值清單以成交值近似權重（無官方比重表，dci_spec §1 允許）；
H 集合用整日成交值前20（非逐分鐘重選），為單日覆盤的簡化。盤中即時版另議。
"""
from __future__ import annotations

from datetime import date, time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

DB = str(Path(__file__).resolve().parents[3] / "data" / "futures.duckdb")
SEL = date(2026, 5, 29)

TOP_WEIGHT_SYMBOLS = [
    "2330", "2317", "2454", "2308", "2881", "2382", "2891", "2882", "2412",
    "2303", "3711", "2886", "1216", "2884", "2885", "2357", "2892", "2880",
    "3008", "2002", "2207",
]
_WL = (0.40, 0.35, 0.25)
_WS = (0.30, 0.30, 0.40)
LVL = [("L1", 0.385), ("L2", 0.497), ("L3", 0.711), ("L4", 0.977), ("L5", 1.225)]


def _sign_df(x: pd.DataFrame) -> pd.DataFrame:
    return np.sign(x)


def load_stock_panel(c: duckdb.DuckDBPyConnection):
    """回傳 price[minute×stock] (ffill), 以及每檔 prev_close/open/value/market。"""
    sd = c.execute(
        "SELECT symbol, market, open, close, change, value FROM stock_day "
        "WHERE trade_date = ? AND close IS NOT NULL",
        [SEL],
    ).df()
    sd["prev"] = sd["close"].astype(float) - sd["change"].astype(float)
    sd["open"] = sd["open"].astype(float)
    sd = sd.set_index("symbol")

    mn = c.execute(
        "SELECT minute, stock_id, close FROM stock_min WHERE trade_date = ? ORDER BY minute",
        [SEL],
    ).df()
    mn["minute"] = mn["minute"].astype(str)
    panel = mn.pivot_table(index="minute", columns="stock_id", values="close", aggfunc="last")
    panel = panel.sort_index().ffill()
    # 首根前的 NaN → 用開盤填
    opens = sd["open"].reindex(panel.columns)
    panel = panel.fillna(pd.DataFrame(
        np.tile(opens.values, (len(panel), 1)), index=panel.index, columns=panel.columns))
    return panel, sd


def intraday_dci(c) -> pd.DataFrame:
    panel, sd = load_stock_panel(c)
    cols = panel.columns
    prev = sd["prev"].reindex(cols).values.astype(float)
    opn = sd["open"].reindex(cols).values.astype(float)

    # listed_count（全市場上市總家數，與 daily B 同尺度）
    listed = c.execute(
        "SELECT sum(listed_count) FROM market_breadth WHERE trade_date = ?", [SEL]
    ).fetchone()[0]

    # H 集合：整日成交值前 20（全市場）
    h_set = c.execute(
        "SELECT symbol FROM stock_day WHERE trade_date = ? AND value IS NOT NULL "
        "ORDER BY value DESC LIMIT 20", [SEL]
    ).df()["symbol"].tolist()
    w_set = [s for s in TOP_WEIGHT_SYMBOLS if s in cols]
    h_set = [s for s in h_set if s in cols]
    w_idx = [cols.get_loc(s) for s in w_set]
    h_idx = [cols.get_loc(s) for s in h_set]

    P = panel.values.astype(float)               # [T × N]
    sp = np.sign(P - prev[None, :])              # vs 昨收
    so = np.sign(P - opn[None, :])               # vs 開盤

    def strength(idx):
        a, b = sp[:, idx], so[:, idx]
        return (a.sum(1) + b.sum(1)) / (2 * len(idx))

    W = strength(w_idx)
    H = strength(h_idx)
    up = (sp > 0).sum(1)
    dn = (sp < 0).sum(1)
    B = (up - dn) / listed

    out = pd.DataFrame({
        "minute": panel.index, "W": W, "H": H, "B": B,
        "dci_long": _WL[0] * W + _WL[1] * H + _WL[2] * B,
        "dci_short": _WS[0] * W + _WS[1] * H + _WS[2] * B,
    })
    return out


def tx_ladder(c) -> pd.DataFrame:
    """TX 05-29 分K + running 方向擺動 + EMA20 + 各階距離 + 盤中到第幾階。"""
    # 前 20 日盤振幅 → causal EMA20
    rng = c.execute(
        "SELECT CAST(timestamp AS DATE) d, MAX(high)-MIN(low) r FROM ohlcv_1m "
        "WHERE symbol='TX' AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "AND CAST(timestamp AS DATE) <= ? GROUP BY 1 ORDER BY 1", [SEL]
    ).df()
    ema20 = rng["r"].astype(float).shift(1).ewm(span=20, adjust=False).mean().iloc[-1]

    bars = c.execute(
        "SELECT CAST(timestamp AS TIME) t, open, high, low, close FROM ohlcv_1m "
        "WHERE symbol='TX' AND CAST(timestamp AS DATE) = ? "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' ORDER BY t", [SEL]
    ).df()
    for col in ("open", "high", "low", "close"):
        bars[col] = bars[col].astype(float)
    hi, lo = bars["high"].values, bars["low"].values
    run_lo = np.minimum.accumulate(lo)
    run_hi = np.maximum.accumulate(hi)
    up_swing = np.maximum.accumulate(hi - run_lo)
    dn_swing = np.maximum.accumulate(run_hi - lo)
    bars["minute"] = bars["t"].astype(str)
    bars["up_swing"] = up_swing
    bars["dn_swing"] = dn_swing
    bars["ema20"] = ema20
    for name, co in LVL:
        bars[f"d_{name}"] = co * ema20

    def lvl_reached(swing):
        out = np.zeros(len(swing), int)
        for i, (name, co) in enumerate(LVL, 1):
            out[swing >= co * ema20] = i
        return out
    bars["up_lvl"] = lvl_reached(up_swing)
    bars["dn_lvl"] = lvl_reached(dn_swing)
    return bars, ema20


def main():
    with duckdb.connect(DB, read_only=True) as c:
        dci = intraday_dci(c)
        tx, ema20 = tx_ladder(c)

    m = pd.merge(tx[["minute", "close", "open", "up_swing", "dn_swing", "up_lvl", "dn_lvl"]],
                 dci, on="minute", how="left").sort_values("minute").reset_index(drop=True)

    tx_open = tx["open"].iloc[0]
    print(f"=== 2026-05-29 盤中 DCI × TX × ladder（EMA20={ema20:.0f} 點）===")
    print(f"TX 開盤 {tx_open:.0f}；階距 "
          + " ".join(f"{n}={co*ema20:.0f}" for n, co in LVL))
    keys = ["08:45:00", "09:00:00", "09:15:00", "09:30:00", "10:00:00", "10:30:00",
            "11:00:00", "11:30:00", "12:00:00", "13:00:00", "13:30:00", "13:45:00"]
    show = m[m["minute"].isin(keys)].copy()
    show["TXΔ"] = (show["close"] - tx_open).round(0)
    cols = ["minute", "close", "TXΔ", "up_swing", "up_lvl", "dn_swing", "dn_lvl",
            "dci_long", "dci_short"]
    fmt = show[cols].copy()
    for cc in ("up_swing", "dn_swing"):
        fmt[cc] = fmt[cc].round(0)
    for cc in ("dci_long", "dci_short", "W", "H", "B"):
        if cc in fmt:
            fmt[cc] = fmt[cc].round(3)
    fmt["dci_long"] = fmt["dci_long"].round(3)
    fmt["dci_short"] = fmt["dci_short"].round(3)
    print(fmt.to_string(index=False))

    # ---- 圖 ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from src.analysis.chart_style import setup_font
    setup_font()

    x = pd.to_datetime(m["minute"], format="%H:%M:%S")
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(13, 11), sharex=True,
                                        gridspec_kw={"height_ratios": [3, 2, 1.4]})

    # panel1: TX price + ladder lines（漲紅跌綠：收高於開=紅）
    up_color = m["close"].iloc[-1] >= tx_open
    ax1.plot(x, m["close"], color="#d62728" if up_color else "#2ca02c", lw=1.6, label="TX close")
    ax1.axhline(tx_open, color="#888", ls="-", lw=0.8, label="開盤")
    for name, co in LVL:
        ax1.axhline(tx_open + co * ema20, color="#d62728", ls="--", lw=0.7, alpha=0.6)
        ax1.axhline(tx_open - co * ema20, color="#2ca02c", ls="--", lw=0.7, alpha=0.6)
        ax1.text(x.iloc[-1], tx_open + co * ema20, f" 上{name}", color="#d62728", va="center", fontsize=8)
        ax1.text(x.iloc[-1], tx_open - co * ema20, f" 下{name}", color="#2ca02c", va="center", fontsize=8)
    ax1.set_ylabel("TX 指數")
    ax1.set_title("2026-05-29　盤中 DCI × 台指 TX × reach ladder")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(alpha=0.25)

    # panel2: DCI long/short + 帶
    ax2.axhspan(0.20, 1, color="#d62728", alpha=0.06)
    ax2.axhspan(-1, -0.20, color="#2ca02c", alpha=0.06)
    ax2.axhline(0, color="#888", lw=0.8)
    ax2.axhline(0.20, color="#d62728", ls=":", lw=0.8)
    ax2.axhline(-0.20, color="#2ca02c", ls=":", lw=0.8)
    ax2.plot(x, m["dci_long"], color="#d62728", lw=1.5, label="DCI_long")
    ax2.plot(x, m["dci_short"], color="#1f77b4", lw=1.3, label="DCI_short")
    ax2.set_ylabel("DCI")
    ax2.set_ylim(-1, 1)
    ax2.legend(loc="upper left", fontsize=8)
    ax2.grid(alpha=0.25)

    # panel3: ladder 到第幾階（上紅下綠，step）
    ax3.step(x, m["up_lvl"], color="#d62728", lw=1.4, where="post", label="上行階")
    ax3.step(x, -m["dn_lvl"], color="#2ca02c", lw=1.4, where="post", label="下行階")
    ax3.axhline(0, color="#888", lw=0.6)
    ax3.set_ylabel("ladder 階")
    ax3.set_yticks([-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5])
    ax3.set_ylim(-5.5, 5.5)
    ax3.legend(loc="upper left", fontsize=8)
    ax3.grid(alpha=0.25)
    ax3.set_xlabel("時間")

    fig.tight_layout()
    out = Path(__file__).parent / "results" / "dci_intraday_20260529.png"
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=130)
    print(f"\n圖已存：{out}")


if __name__ == "__main__":
    main()
