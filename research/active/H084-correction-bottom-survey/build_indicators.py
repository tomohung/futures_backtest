"""
H084 Step 0.3：建置可立即建的指標 → results/indicators.parquet

指標清單：
  - econ_score             : 景氣對策信號綜合分數（月→日 forward-fill, point-in-time）
  - econ_signal_color      : 燈號（紅/黃紅/綠/黃藍/藍）
  - econ_blue_streak       : 連續藍燈或黃藍燈月數
  - econ_published_at      : 這筆 econ 變成可用的日期（point-in-time）
  - taiex_dist_250ma_pct   : (close - MA250) / MA250 × 100
  - taiex_dist_125ma_z     : 距 125MA 的 z-score（1 年滾動標準化）
  - vix                    : 台指 VIX（vixtwn，2016-11+）
  - vix_pct                : VIX 的 1 年滾動百分位排名（NULL when window short）
  - volume_5m_60m          : TAIEX volume 5MA / 60MA（量能萎縮指標）
  - margin_amt             : 融資餘額（仟元）
  - margin_drop_60d_pct    : 融資餘額從 60 日高點減幅 %（負值表示減少）
  - margin_amt_pct_1y      : 融資餘額 1 年滾動百分位

待補（後續批次）：
  - pc_ratio_5d（put/call ratio）
  - breadth_*、new_lows_52w（等 stock_day / market_breadth ETL）

Point-in-time 處理：
  景氣對策信號月報，月 M 的資料約於 M+1 月 25 日由國發會公告。
  本腳本以 M+1 月 25 日為 publication_date，先簡化（之後若要嚴謹可改用實際公告日）。

用法：
  uv run python research/active/H084-correction-bottom-survey/build_indicators.py
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"
RESULTS_DIR = Path(__file__).parent / "results"

WEAK_COLORS = {"藍", "黃藍"}
PUB_DELAY_DAYS = 25  # 月 M 的景氣資料約 M+1 月 25 日公告


def _publication_date(report_month: date) -> date:
    """月份 M 的景氣資料公告日 ≈ M+1 月 25 日"""
    if report_month.month == 12:
        return date(report_month.year + 1, 1, PUB_DELAY_DAYS)
    return date(report_month.year, report_month.month + 1, PUB_DELAY_DAYS)


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """從 DuckDB 載入 TAIEX、VIX、景氣信號、融資餘額"""
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        taiex = conn.execute("""
            SELECT trade_date, close, volume
            FROM taiex_day
            ORDER BY trade_date
        """).fetchdf()
        vix = conn.execute("""
            SELECT date AS trade_date, vix
            FROM vixtwn
            ORDER BY date
        """).fetchdf()
        econ = conn.execute("""
            SELECT report_month, score, signal_color
            FROM econ_signal
            WHERE score IS NOT NULL
            ORDER BY report_month
        """).fetchdf()
        margin = conn.execute("""
            SELECT trade_date, fin_amt_curr_bal
            FROM margin_balance
            ORDER BY trade_date
        """).fetchdf()
    taiex["close"] = taiex["close"].astype(float)
    taiex["volume"] = taiex["volume"].astype(float)
    taiex["trade_date"] = pd.to_datetime(taiex["trade_date"]).dt.date
    vix["trade_date"] = pd.to_datetime(vix["trade_date"]).dt.date
    econ["report_month"] = pd.to_datetime(econ["report_month"]).dt.date
    margin["trade_date"] = pd.to_datetime(margin["trade_date"]).dt.date
    margin["fin_amt_curr_bal"] = margin["fin_amt_curr_bal"].astype(float)
    return taiex, vix, econ, margin


def compute_econ_streak(econ: pd.DataFrame) -> pd.DataFrame:
    """Add econ_blue_streak (連續藍/黃藍燈月數) + econ_published_at 欄位"""
    econ = econ.copy().sort_values("report_month").reset_index(drop=True)
    econ["is_weak"] = econ["signal_color"].isin(WEAK_COLORS)
    streaks = []
    s = 0
    for w in econ["is_weak"]:
        s = s + 1 if w else 0
        streaks.append(s)
    econ["econ_blue_streak"] = streaks
    econ["econ_published_at"] = econ["report_month"].apply(_publication_date)
    return econ


def merge_econ_to_daily(daily: pd.DataFrame, econ: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time forward-fill：每個 trade_date 取最新 econ_published_at <= trade_date 的 row"""
    e = econ[["econ_published_at", "score", "signal_color", "econ_blue_streak"]].rename(
        columns={"econ_published_at": "trade_date", "score": "econ_score",
                 "signal_color": "econ_signal_color"}
    )
    daily_sorted = daily.sort_values("trade_date").reset_index(drop=True)
    e_sorted = e.sort_values("trade_date").reset_index(drop=True)
    # 用 datetime 做 merge_asof 比較穩
    daily_sorted["_dt"] = pd.to_datetime(daily_sorted["trade_date"])
    e_sorted["_dt"] = pd.to_datetime(e_sorted["trade_date"])
    merged = pd.merge_asof(
        daily_sorted.sort_values("_dt"),
        e_sorted.drop(columns=["trade_date"]).sort_values("_dt"),
        on="_dt",
        direction="backward",
    )
    return merged.drop(columns=["_dt"])


def compute_taiex_indicators(taiex: pd.DataFrame) -> pd.DataFrame:
    """TAIEX 衍生指標：距 250MA、125MA z-score、量能萎縮"""
    df = taiex.copy()
    df["ma_250"] = df["close"].rolling(window=250, min_periods=200).mean()
    df["ma_125"] = df["close"].rolling(window=125, min_periods=100).mean()
    df["taiex_dist_250ma_pct"] = (df["close"] - df["ma_250"]) / df["ma_250"] * 100

    # z-score: 距 125MA 用 1 年（250 日）滾動 std 標準化
    diff_125 = df["close"] - df["ma_125"]
    rolling_std_diff_125 = diff_125.rolling(window=250, min_periods=200).std()
    df["taiex_dist_125ma_z"] = diff_125 / rolling_std_diff_125

    # 量能萎縮：5MA / 60MA
    vol5 = df["volume"].rolling(window=5, min_periods=5).mean()
    vol60 = df["volume"].rolling(window=60, min_periods=40).mean()
    df["volume_5m_60m"] = vol5 / vol60

    return df[["trade_date", "close", "volume",
               "taiex_dist_250ma_pct", "taiex_dist_125ma_z", "volume_5m_60m"]]


def compute_vix_indicators(vix: pd.DataFrame) -> pd.DataFrame:
    """VIX 與 1 年滾動百分位排名"""
    df = vix.copy().sort_values("trade_date").reset_index(drop=True)
    # 1 年滾動百分位（rank / count）
    df["vix_pct"] = df["vix"].rolling(window=250, min_periods=200).apply(
        lambda x: (x.rank(pct=True).iloc[-1]) * 100, raw=False
    )
    return df


def compute_margin_indicators(margin: pd.DataFrame) -> pd.DataFrame:
    """融資餘額衍生指標"""
    df = margin.copy().sort_values("trade_date").reset_index(drop=True)
    df = df.rename(columns={"fin_amt_curr_bal": "margin_amt"})

    # 60 日高點減幅 %（負值表示減少）
    rolling_60d_max = df["margin_amt"].rolling(window=60, min_periods=40).max()
    df["margin_drop_60d_pct"] = (df["margin_amt"] - rolling_60d_max) / rolling_60d_max * 100

    # 1 年滾動百分位
    df["margin_amt_pct_1y"] = df["margin_amt"].rolling(window=250, min_periods=200).apply(
        lambda x: (x.rank(pct=True).iloc[-1]) * 100, raw=False
    )
    return df


def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    taiex, vix, econ, margin = load_data()
    print(f"Loaded TAIEX={len(taiex)}, VIX={len(vix)}, econ_signal={len(econ)}, margin={len(margin)}")

    # 計算 TAIEX 衍生指標
    taiex_ind = compute_taiex_indicators(taiex)
    print(f"  TAIEX indicators ready: {taiex_ind.shape}")

    # 計算 VIX 衍生指標
    vix_ind = compute_vix_indicators(vix)
    print(f"  VIX indicators ready: {vix_ind.shape} ({vix_ind['trade_date'].min()} ~ {vix_ind['trade_date'].max()})")

    # 處理景氣信號
    econ_processed = compute_econ_streak(econ)
    print(f"  Econ processed: {econ_processed.shape}")

    # 計算 margin 衍生指標
    margin_ind = compute_margin_indicators(margin)
    print(f"  Margin indicators ready: {margin_ind.shape} ({margin_ind['trade_date'].min()} ~ {margin_ind['trade_date'].max()})")

    # 以 TAIEX 日期為基準合併
    daily = taiex_ind.copy()
    # Merge VIX
    daily = daily.merge(vix_ind[["trade_date", "vix", "vix_pct"]],
                        on="trade_date", how="left")
    # Merge margin
    daily = daily.merge(margin_ind[["trade_date", "margin_amt",
                                     "margin_drop_60d_pct", "margin_amt_pct_1y"]],
                        on="trade_date", how="left")
    # Merge econ (point-in-time)
    daily = merge_econ_to_daily(daily, econ_processed)

    # 整理欄位順序
    cols = ["trade_date", "close", "volume",
            "taiex_dist_250ma_pct", "taiex_dist_125ma_z", "volume_5m_60m",
            "vix", "vix_pct",
            "margin_amt", "margin_drop_60d_pct", "margin_amt_pct_1y",
            "econ_score", "econ_signal_color", "econ_blue_streak"]
    daily = daily[cols]

    # 輸出
    out_csv = RESULTS_DIR / "indicators.csv"
    daily.to_csv(out_csv, index=False)
    print(f"\nOutput → {out_csv}")
    print(f"Shape: {daily.shape}, range {daily['trade_date'].min()} ~ {daily['trade_date'].max()}")

    # Summary
    print("\n=== Indicator coverage (non-null counts) ===")
    print(daily[cols[3:]].notna().sum().to_string())

    print("\n=== Recent 5 days ===")
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    print(daily.tail(5).to_string(index=False))

    print("\n=== Sample at known troughs ===")
    sample_dates = [date(2008, 11, 20), date(2020, 3, 19), date(2022, 10, 25),
                    date(2024, 8, 5), date(2025, 4, 9), date(2026, 3, 31)]
    for d in sample_dates:
        row = daily[daily["trade_date"] == d]
        if row.empty:
            print(f"  {d}: not found")
            continue
        r = row.iloc[0]
        vix_str = f"{r['vix']:.1f}" if pd.notna(r["vix"]) else "—"
        vix_pct_str = f"{r['vix_pct']:.0f}" if pd.notna(r["vix_pct"]) else "—"
        z125_str = f"{r['taiex_dist_125ma_z']:.2f}" if pd.notna(r["taiex_dist_125ma_z"]) else "—"
        mrg_str = f"{r['margin_drop_60d_pct']:.1f}%" if pd.notna(r["margin_drop_60d_pct"]) else "—"
        print(f"  {d}: dist250={r['taiex_dist_250ma_pct']:.1f}%, "
              f"z125={z125_str}, "
              f"vol5/60={r['volume_5m_60m']:.2f}, "
              f"VIX={vix_str}, VIX_pct={vix_pct_str}, "
              f"margin60d={mrg_str}, "
              f"econ={r['econ_score']}/{r['econ_signal_color']}/streak={r['econ_blue_streak']}")


if __name__ == "__main__":
    main()
