"""
H049 Phase 1 Explore: EstHL Costline — VWAP 突破進場
分析 21 筆實盤 costline 交易的早盤走勢與 intraday VWAP 關係
"""

import pandas as pd
import numpy as np
import duckdb
from datetime import time

DB_PATH = "data/futures.duckdb"

# ── 21 筆 costline 交易 ──────────────────────────────────────────────
COSTLINE_TRADES = [
    # (date, direction, entry_time, entry_price, pnl)
    ("2024-11-06", "B", "09:10", 23164, -38),
    ("2024-11-07", "B", "09:00", 23160, 178),
    ("2024-11-26", "S", "09:05", 22728, -61),
    ("2024-11-28", "S", "09:04", 22323, 88),
    ("2024-12-17", "B", "09:06", 23135, 21),
    ("2024-12-23", "B", "09:25", 22990, 176),
    ("2024-12-31", "S", "09:04", 22996, -29),
    ("2025-01-13", "S", "09:03", 22924, 372),
    ("2025-01-16", "B", "09:07", 23045, 113),
    ("2025-01-22", "B", "09:33", 23621, 33),
    ("2025-02-06", "B", "09:12", 23344, -43),
    ("2025-02-10", "S", "09:02", 23311, 54),
    ("2025-02-20", "S", "09:02", 23516, 125),
    ("2025-02-25", "S", "09:07", 23230, -11),
    ("2025-02-26", "S", "09:06", 23127, -50),
    ("2025-05-19", "S", "09:10", 21691, 1),
    ("2025-05-28", "S", "09:07", 21459, 143),
    ("2025-07-10", "B", "09:07", 22412, 130),
    ("2025-10-03", "B", "09:04", 26511, 178),
    ("2025-11-27", "B", "09:28", 27552, 58),
    ("2025-12-15", "B", "09:14", 27867, 45),
]


def load_day_1m(conn, date_str):
    """載入某天的日盤 1 分 K 資料"""
    df = conn.execute("""
        SELECT timestamp, open, high, low, close, volume
        FROM ohlcv_1m
        WHERE symbol = 'TX'
          AND CAST(timestamp AS DATE) = ?
          AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
        ORDER BY timestamp
    """, [date_str]).df()
    return df


def calc_intraday_vwap(df):
    """計算 intraday VWAP（累積 typical_price * volume / 累積 volume）"""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    cum_tpv = (tp * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum()
    df["vwap"] = cum_tpv / cum_vol
    return df


def load_prev_day_vwap(conn, date_str):
    """載入前一日的 VWAP（成本線）"""
    result = conn.execute("""
        WITH day_data AS (
            SELECT open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND CAST(timestamp AS DATE) = (
                  SELECT MAX(CAST(timestamp AS DATE))
                  FROM ohlcv_1m
                  WHERE symbol = 'TX'
                    AND CAST(timestamp AS DATE) < ?
                    AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
              )
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
        )
        SELECT SUM((high + low + close) / 3 * volume) / SUM(volume) AS vwap
        FROM day_data
    """, [date_str]).fetchone()
    return result[0] if result else None


def analyze_trade(conn, date_str, direction, entry_time_str, entry_price, pnl):
    """分析單筆交易當日的早盤走勢"""
    df = load_day_1m(conn, date_str)
    if df.empty:
        return None

    df = calc_intraday_vwap(df)
    prev_vwap = load_prev_day_vwap(conn, date_str)

    # 開盤價與 prev_day VWAP 的位置
    open_price = df.iloc[0]["open"]
    if prev_vwap is None:
        return None

    open_vs_pvwap = "above" if open_price > prev_vwap else "below"

    # 進場時間（解析 HH:MM）
    entry_h, entry_m = map(int, entry_time_str.split(":"))
    entry_ts = pd.Timestamp(f"{date_str} {entry_h:02d}:{entry_m:02d}:00")

    # 進場前的走勢：08:45 到 entry_time
    pre_entry = df[df["timestamp"] <= entry_ts]
    if pre_entry.empty:
        return None

    # 進場前的高低點
    pre_high = pre_entry["high"].max()
    pre_low = pre_entry["low"].min()
    pre_range = pre_high - pre_low

    # 進場價 vs VWAP
    # 用進場前最後一根的 intraday VWAP
    last_vwap_at_entry = pre_entry.iloc[-1]["vwap"]
    entry_vs_vwap = "above" if entry_price > last_vwap_at_entry else "below"

    # 進場價 vs prev_day VWAP
    entry_vs_pvwap = "above" if entry_price > prev_vwap else "below"

    # VWAP 交叉偵測：進場前有無從 below → above 或 above → below
    close_vs_pvwap = (pre_entry["close"] > prev_vwap).astype(int)
    crossings = close_vs_pvwap.diff().abs().sum()

    # 開盤區間（前 15 分鐘 08:45~09:00）
    or_bars = df[df["timestamp"] < pd.Timestamp(f"{date_str} 09:00:00")]
    if not or_bars.empty:
        or_high = or_bars["high"].max()
        or_low = or_bars["low"].min()
    else:
        or_high = or_low = open_price

    # 進場價 vs OR
    if direction == "B":
        entry_vs_or = "above_or_high" if entry_price > or_high else (
            "within_or" if entry_price >= or_low else "below_or_low"
        )
    else:
        entry_vs_or = "below_or_low" if entry_price < or_low else (
            "within_or" if entry_price <= or_high else "above_or_high"
        )

    # 整理時間：從開盤到進場的分鐘數
    consolidation_min = (entry_ts - df.iloc[0]["timestamp"]).total_seconds() / 60

    # 日盤全日報酬
    day_close = df.iloc[-1]["close"]
    day_return = day_close - open_price

    return {
        "date": date_str,
        "direction": direction,
        "entry_time": entry_time_str,
        "entry_price": entry_price,
        "pnl": pnl,
        "open_price": open_price,
        "prev_vwap": round(prev_vwap, 1),
        "open_vs_pvwap": open_vs_pvwap,
        "entry_vs_pvwap": entry_vs_pvwap,
        "entry_vs_intraday_vwap": entry_vs_vwap,
        "intraday_vwap_at_entry": round(last_vwap_at_entry, 1),
        "pvwap_crossings": int(crossings),
        "pre_entry_range": round(pre_range, 1),
        "or_high": round(or_high, 1),
        "or_low": round(or_low, 1),
        "entry_vs_or": entry_vs_or,
        "consolidation_min": round(consolidation_min, 1),
        "day_return": round(day_return, 1),
    }


def main():
    conn = duckdb.connect(DB_PATH, read_only=True)

    results = []
    for date_str, direction, entry_time, entry_price, pnl in COSTLINE_TRADES:
        r = analyze_trade(conn, date_str, direction, entry_time, entry_price, pnl)
        if r:
            results.append(r)

    conn.close()

    df = pd.DataFrame(results)

    print("=" * 80)
    print("H049 Phase 1: EstHL Costline — VWAP 突破進場分析")
    print("=" * 80)
    print(f"\n分析成功: {len(df)}/{len(COSTLINE_TRADES)} 筆")

    # ── 1. 開盤 vs 前日 VWAP 位置 ──────────────────────────────
    print("\n\n### 1. 開盤 vs 前日 VWAP")
    for pos in ["above", "below"]:
        sub = df[df["open_vs_pvwap"] == pos]
        if len(sub) > 0:
            print(f"  開盤在 VWAP {pos}: {len(sub)} 筆")
            print(f"    做多: {len(sub[sub['direction']=='B'])} | 做空: {len(sub[sub['direction']=='S'])}")

    # ── 2. 進場 vs 前日 VWAP 位置 ──────────────────────────────
    print("\n### 2. 進場 vs 前日 VWAP")
    for pos in ["above", "below"]:
        sub = df[df["entry_vs_pvwap"] == pos]
        if len(sub) > 0:
            b_sub = sub[sub["direction"] == "B"]
            s_sub = sub[sub["direction"] == "S"]
            print(f"  進場在 VWAP {pos}: {len(sub)} 筆")
            if len(b_sub) > 0:
                print(f"    做多 {len(b_sub)} 筆: 勝率 {(b_sub['pnl']>0).sum()}/{len(b_sub)}, avg PnL {b_sub['pnl'].mean():.0f}")
            if len(s_sub) > 0:
                print(f"    做空 {len(s_sub)} 筆: 勝率 {(s_sub['pnl']>0).sum()}/{len(s_sub)}, avg PnL {s_sub['pnl'].mean():.0f}")

    # ── 3. 進場 vs 開盤區間 ────────────────────────────────────
    print("\n### 3. 進場 vs 開盤區間 (OR)")
    print(df["entry_vs_or"].value_counts().to_string())

    # ── 4. 進場方向 vs VWAP 位置的一致性 ──────────────────────────
    print("\n### 4. 方向 vs VWAP 位置一致性")
    # 做多且在 VWAP 上方 = 一致，做空且在 VWAP 下方 = 一致
    df["direction_consistent"] = (
        ((df["direction"] == "B") & (df["entry_vs_pvwap"] == "above")) |
        ((df["direction"] == "S") & (df["entry_vs_pvwap"] == "below"))
    )
    consistent = df[df["direction_consistent"]]
    inconsistent = df[~df["direction_consistent"]]
    print(f"  方向一致（做多在VWAP上/做空在VWAP下）: {len(consistent)} 筆")
    if len(consistent) > 0:
        print(f"    勝率: {(consistent['pnl']>0).sum()}/{len(consistent)} = {(consistent['pnl']>0).mean()*100:.0f}%")
        print(f"    avg PnL: {consistent['pnl'].mean():.0f}")
    print(f"  方向反轉（做多在VWAP下/做空在VWAP上）: {len(inconsistent)} 筆")
    if len(inconsistent) > 0:
        print(f"    勝率: {(inconsistent['pnl']>0).sum()}/{len(inconsistent)} = {(inconsistent['pnl']>0).mean()*100:.0f}%")
        print(f"    avg PnL: {inconsistent['pnl'].mean():.0f}")

    # ── 5. VWAP 交叉次數 ──────────────────────────────────────
    print("\n### 5. 進場前 VWAP 交叉次數")
    print(df["pvwap_crossings"].value_counts().sort_index().to_string())

    # ── 6. 整理時間（開盤到進場） ──────────────────────────────
    print("\n### 6. 整理時間（開盤到進場）")
    print(f"  平均: {df['consolidation_min'].mean():.0f} 分鐘")
    print(f"  中位: {df['consolidation_min'].median():.0f} 分鐘")
    print(f"  範圍: {df['consolidation_min'].min():.0f} ~ {df['consolidation_min'].max():.0f} 分鐘")

    # ── 7. 進場前波動幅度 ──────────────────────────────────────
    print("\n### 7. 進場前波動幅度")
    print(f"  平均: {df['pre_entry_range'].mean():.0f} 點")
    print(f"  中位: {df['pre_entry_range'].median():.0f} 點")

    # ── 8. 每筆交易詳細表 ──────────────────────────────────────
    print("\n\n### 詳細分析表")
    print(f"{'日期':<12} {'方向':>2} {'進場':>5} {'進場價':>7} {'PnL':>5} | "
          f"{'開盤':>7} {'前VWAP':>7} {'開盤vs':>6} {'進場vs':>6} | "
          f"{'交叉':>2} {'整理min':>5} {'進場vsOR':>12}")
    print("-" * 110)
    for _, r in df.iterrows():
        print(f"{r['date']:<12} {r['direction']:>2} {r['entry_time']:>5} {r['entry_price']:>7.0f} {r['pnl']:>+5.0f} | "
              f"{r['open_price']:>7.0f} {r['prev_vwap']:>7.0f} {r['open_vs_pvwap']:>6} {r['entry_vs_pvwap']:>6} | "
              f"{r['pvwap_crossings']:>2} {r['consolidation_min']:>5.0f} {r['entry_vs_or']:>12}")

    # ── 9. 交叉型態分類初探 ──────────────────────────────────────
    print("\n\n### 9. 交叉型態初步分類")
    # Type A: 開盤在 VWAP 同側，進場也在同側（順勢突破）
    # Type B: 開盤在 VWAP 反側，穿越 VWAP 後進場（反轉突破）
    df["trade_type"] = "unknown"
    for idx, r in df.iterrows():
        if r["direction"] == "B":
            if r["open_vs_pvwap"] == "above" and r["entry_vs_pvwap"] == "above":
                df.at[idx, "trade_type"] = "A_trend"  # 開盤已在VWAP上，順勢做多
            elif r["open_vs_pvwap"] == "below" and r["entry_vs_pvwap"] == "above":
                df.at[idx, "trade_type"] = "B_cross_up"  # 穿越VWAP向上做多
            elif r["open_vs_pvwap"] == "below" and r["entry_vs_pvwap"] == "below":
                df.at[idx, "trade_type"] = "C_counter"  # 在VWAP下方做多（反轉前）
            else:
                df.at[idx, "trade_type"] = "D_other"
        else:  # S
            if r["open_vs_pvwap"] == "below" and r["entry_vs_pvwap"] == "below":
                df.at[idx, "trade_type"] = "A_trend"  # 開盤已在VWAP下，順勢做空
            elif r["open_vs_pvwap"] == "above" and r["entry_vs_pvwap"] == "below":
                df.at[idx, "trade_type"] = "B_cross_down"  # 穿越VWAP向下做空
            elif r["open_vs_pvwap"] == "above" and r["entry_vs_pvwap"] == "above":
                df.at[idx, "trade_type"] = "C_counter"  # 在VWAP上方做空（反轉前）
            else:
                df.at[idx, "trade_type"] = "D_other"

    for ttype in sorted(df["trade_type"].unique()):
        sub = df[df["trade_type"] == ttype]
        wins = (sub["pnl"] > 0).sum()
        print(f"\n  {ttype}: {len(sub)} 筆")
        print(f"    勝率: {wins}/{len(sub)} = {wins/len(sub)*100:.0f}%")
        print(f"    avg PnL: {sub['pnl'].mean():.0f}")
        print(f"    total PnL: {sub['pnl'].sum():.0f}")
        for _, r in sub.iterrows():
            print(f"      {r['date']} {r['direction']} entry={r['entry_time']} pnl={r['pnl']:+.0f}")


if __name__ == "__main__":
    main()
