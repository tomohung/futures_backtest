"""盤中『延伸力 / EXT』逐分鐘序列（多/空），供 chart-ui 副圖。

與 legacy DCI（services/dci_daily.py，收盤 W/H/B、±0.2）**不同物**：
這是 H095/H111/H112 的盤中重設計版——open-anchor、預測「當天往某方向延伸到關卡的程度」。
  ext_long(t)  = value-weighted tanh((p@≤t − open)/range_i) 於前 10 大型股（動態 20日均成交值）
                 → 早盤上行延伸偏向（H111/H114 OOS：W10 窄 universe 解釋力 OOS 零衰退，W50 崩）
  ext_short(t) = z(s_thr) + z(s_B)，固定 z 尺度（全窗 250 日 @09:30 校準）
                 s_thr=−thrust(W-100 寬權值)、s_B=−(漲−跌家數)/active（全 TWSE）
                 → 連續下行壓力表（H112 OOS：連續 corr 穩 +0.31~0.36，但離散關卡地圖已否證）

只對有 stock_min 的日子（2025-06~2026-06）有值；其餘回 None。
強門檻參考線：ext_long ≥ +0.12、ext_short(z-sum) ≥ +1.33（全窗 top~20%，看盤用）。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import duckdb
import numpy as np
import pandas as pd

from src.chart_ui import paths

# 固定 z 尺度（H112 short_reach_panel @09:30，全窗 250 日 2025-06~2026-06 重校）
_THR_MU, _THR_SD = 0.01590, 0.15487
_B_MU, _B_SD = -0.04558, 0.39559

STRONG_LONG = 0.16        # ext_long(W10) 強門檻（全窗 @09:30 top~20%；W10 OOS 解釋力零衰退，優於 W50）
STRONG_SHORT = 1.33       # ext_short(z-sum) 強門檻（全窗 top~20%；OOS：連續壓力表，離散關卡地圖已否證 H112）


def _features(conn, sel: date) -> pd.DataFrame | None:
    """當日每檔 open/prev/range_i(EMA20日振幅)/trail_val(20日均值)；causal。"""
    start = sel - timedelta(days=100)
    df = conn.execute(
        "SELECT trade_date, symbol, open, high, low, close, change, value "
        "FROM stock_day WHERE market='TWSE' AND trade_date BETWEEN ? AND ? "
        "ORDER BY symbol, trade_date", [start, sel]).df()
    if df.empty:
        return None
    for col in ("open", "high", "low", "close", "change", "value"):
        df[col] = df[col].astype(float)
    rng = df["high"] - df["low"]
    df["range_i"] = rng.groupby(df["symbol"]).transform(
        lambda s: s.shift(1).ewm(span=20, adjust=False).mean())
    df["trail_val"] = df.groupby("symbol")["value"].transform(
        lambda s: s.shift(1).rolling(20, min_periods=10).mean())
    df["prev"] = df["close"] - df["change"]
    sub = df[df["trade_date"] == pd.Timestamp(sel)]
    return sub[["symbol", "open", "prev", "range_i", "trail_val"]].dropna(subset=["open"])


def compute_extension_series(conn, sel: date) -> dict | None:
    """回傳 {'bars':[{'time':'YYYY-MM-DD HH:MM:SS','ext_long':..,'ext_short':..}, ...],
              'strong_long':0.10,'strong_short':1.2} 或 None（無 stock_min）。"""
    feat = _features(conn, sel)
    if feat is None or feat.empty:
        return None
    mn = conn.execute(
        "SELECT minute, stock_id, close FROM stock_min WHERE trade_date = ? ORDER BY minute",
        [sel]).df()
    if mn.empty:
        return None
    mn["minute"] = mn["minute"].astype(str)
    panel = mn.pivot_table(index="minute", columns="stock_id", values="close", aggfunc="last")
    panel = panel.sort_index().ffill()

    feat = feat[feat["symbol"].isin(panel.columns)].set_index("symbol")
    syms = [s for s in panel.columns if s in feat.index]
    panel = panel[syms]
    opn = feat["open"].reindex(syms).to_numpy(float)
    prev = feat["prev"].reindex(syms).to_numpy(float)
    rng = feat["range_i"].reindex(syms).to_numpy(float)
    tval = feat["trail_val"].reindex(syms).to_numpy(float)
    P_real = panel.to_numpy(float)                      # ffill 後、未成交股仍 NaN（家數用）
    P_thr = np.where(np.isnan(P_real), opn[None, :], P_real)   # thrust 未成交→開盤(m=0 中性)

    with np.errstate(invalid="ignore", divide="ignore"):
        m = np.tanh((P_thr - opn[None, :]) / rng[None, :])      # [T,N]，rng 無效→nan

    order = np.argsort(-np.nan_to_num(tval, nan=-1.0))
    w10, w100 = order[:10], order[:100]   # ext_long 用 W10（OOS：窄勝寬，W50 解釋力 OOS 崩）；ext_short 家數仍需 W100 廣尾

    def wthrust(idx):
        mi = m[:, idx]; wi = tval[idx]
        ok = np.isfinite(mi) & (np.isfinite(wi) & (wi > 0))[None, :]
        num = np.where(ok, mi * wi[None, :], 0.0).sum(1)
        den = np.where(ok, wi[None, :], 0.0).sum(1)
        return np.divide(num, den, out=np.zeros_like(num), where=den > 0)

    ext_long = wthrust(w10)
    s_thr = -wthrust(w100)
    # 家數：只算「真的成交過」的股票（P_real 非 NaN），未成交不投票
    traded = np.isfinite(P_real) & np.isfinite(prev)[None, :]
    up = (traded & (P_real > prev[None, :])).sum(1)
    dn = (traded & (P_real < prev[None, :])).sum(1)
    active = traded.sum(1)
    s_B = -np.divide(up - dn, active, out=np.zeros(P_real.shape[0]), where=active > 0)
    ext_short = (s_thr - _THR_MU) / _THR_SD + (s_B - _B_MU) / _B_SD

    def _epoch(mstr: str) -> int:
        h, mi, s = (int(x) for x in mstr.split(":"))
        return int(datetime(sel.year, sel.month, sel.day, h, mi, s,
                            tzinfo=timezone.utc).timestamp())   # naive→UTC，對齊 kline_loader

    bars = [{"time": _epoch(mins), "ext_long": round(float(el), 4),
             "ext_short": round(float(es), 4)}
            for mins, el, es in zip(panel.index, ext_long, ext_short)]
    return {"bars": bars, "strong_long": STRONG_LONG, "strong_short": STRONG_SHORT}


_cache: dict[str, dict | None] = {}


def get_extension(date_str: str) -> dict | None:
    """route 用：開唯讀連線算當日延伸力序列；逐日結果靜態 → 記憶體快取。"""
    if date_str in _cache:
        return _cache[date_str]
    sel = date.fromisoformat(date_str)
    with duckdb.connect(str(paths.DUCKDB_PATH), read_only=True) as conn:
        res = compute_extension_series(conn, sel)
    _cache[date_str] = res
    return res
