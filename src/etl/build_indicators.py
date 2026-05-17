#!/usr/bin/env python3
"""
更新 fg-composite indicators.csv(S004 / H084 用)。

策略:
    - 既有 CSV (research/archive/confirmed/H084-.../results/indicators.csv) 為歷史 raw data 來源
    - DB 表(taiex_day / vixtwn / margin_balance / econ_signal)為新資料來源
    - 兩者 merge — DB 為最新優先,CSV 補齊 DB 沒有的歷史
    - 重算 rolling indicators(taiex_dist_125ma_z / vix_pct / margin_drop_60d_pct / margin_amt_pct_1y)
    - 寫回原 CSV 路徑

冪等:每次重跑會用最新 DB + 既有 CSV 重產整份 CSV。

使用:
    uv run python src/etl/build_indicators.py
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"
CSV_PATH = (PROJECT_ROOT / "research" / "archive" / "confirmed"
            / "H084-correction-bottom-survey" / "results" / "indicators.csv")

WEAK_COLORS = {"藍", "黃藍"}
PUB_DELAY_DAYS = 25


def _publication_date(report_month: date) -> date:
    if report_month.month == 12:
        return date(report_month.year + 1, 1, PUB_DELAY_DAYS)
    return date(report_month.year, report_month.month + 1, PUB_DELAY_DAYS)


def load_db_data() -> dict:
    """從 DB 載入四個 raw data tables(可能有缺,後續用 CSV 補齊)"""
    out = {"taiex": None, "vix": None, "econ": None, "margin": None}
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        try:
            out["taiex"] = conn.execute("""
                SELECT trade_date, close, volume
                FROM taiex_day ORDER BY trade_date
            """).fetchdf()
        except Exception as e:
            print(f"  [WARN] taiex_day: {e}")
        try:
            out["vix"] = conn.execute("""
                SELECT date AS trade_date, vix
                FROM vixtwn ORDER BY date
            """).fetchdf()
        except Exception as e:
            print(f"  [WARN] vixtwn: {e}")
        try:
            out["econ"] = conn.execute("""
                SELECT report_month, score, signal_color
                FROM econ_signal WHERE score IS NOT NULL
                ORDER BY report_month
            """).fetchdf()
        except Exception as e:
            print(f"  [WARN] econ_signal: {e}")
        try:
            out["margin"] = conn.execute("""
                SELECT trade_date, fin_amt_curr_bal AS margin_amt
                FROM margin_balance ORDER BY trade_date
            """).fetchdf()
        except Exception as e:
            print(f"  [WARN] margin_balance: {e}")
    return out


def load_csv() -> pd.DataFrame:
    if not CSV_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(CSV_PATH, parse_dates=["trade_date"])
    df["trade_date"] = df["trade_date"].dt.date
    return df


def merge_raw_with_csv(db_raw: pd.DataFrame | None, csv_df: pd.DataFrame,
                       value_col: str, db_value_col: str | None = None) -> pd.DataFrame:
    """合併 DB raw 與 CSV raw,DB 為最新優先;DB 缺的日期用 CSV 補。

    Returns DataFrame with columns ['trade_date', value_col].
    """
    db_value_col = db_value_col or value_col
    parts = []
    if db_raw is not None and len(db_raw) > 0:
        db_part = db_raw[["trade_date", db_value_col]].rename(columns={db_value_col: value_col}).copy()
        if not pd.api.types.is_datetime64_any_dtype(db_part["trade_date"]):
            db_part["trade_date"] = pd.to_datetime(db_part["trade_date"]).dt.date
        parts.append(db_part)
        db_dates = set(db_part["trade_date"])
    else:
        db_dates = set()
    if value_col in csv_df.columns:
        csv_part = csv_df[["trade_date", value_col]].copy()
        # DB 有的日期不用 CSV
        csv_part = csv_part[~csv_part["trade_date"].isin(db_dates)]
        parts.append(csv_part)
    if not parts:
        return pd.DataFrame(columns=["trade_date", value_col])
    out = pd.concat(parts, ignore_index=True).sort_values("trade_date").reset_index(drop=True)
    # remove duplicates keeping first (DB rows came first)
    out = out.drop_duplicates(subset=["trade_date"], keep="first")
    return out


def compute_taiex_indicators(taiex: pd.DataFrame) -> pd.DataFrame:
    df = taiex.copy().sort_values("trade_date").reset_index(drop=True)
    df["ma_250"] = df["close"].rolling(window=250, min_periods=200).mean()
    df["ma_125"] = df["close"].rolling(window=125, min_periods=100).mean()
    df["taiex_dist_250ma_pct"] = (df["close"] - df["ma_250"]) / df["ma_250"] * 100
    diff_125 = df["close"] - df["ma_125"]
    rolling_std_diff_125 = diff_125.rolling(window=250, min_periods=200).std()
    df["taiex_dist_125ma_z"] = diff_125 / rolling_std_diff_125
    vol5 = df["volume"].rolling(window=5, min_periods=5).mean()
    vol60 = df["volume"].rolling(window=60, min_periods=40).mean()
    df["volume_5m_60m"] = vol5 / vol60
    return df[["trade_date", "close", "volume",
               "taiex_dist_250ma_pct", "taiex_dist_125ma_z", "volume_5m_60m"]]


def compute_vix_indicators(vix: pd.DataFrame) -> pd.DataFrame:
    df = vix.copy().sort_values("trade_date").reset_index(drop=True)
    df["vix_pct"] = df["vix"].rolling(window=250, min_periods=200).apply(
        lambda x: x.rank(pct=True).iloc[-1] * 100, raw=False
    )
    return df


def compute_margin_indicators(margin: pd.DataFrame) -> pd.DataFrame:
    df = margin.copy().sort_values("trade_date").reset_index(drop=True)
    rolling_60d_max = df["margin_amt"].rolling(window=60, min_periods=40).max()
    df["margin_drop_60d_pct"] = (df["margin_amt"] - rolling_60d_max) / rolling_60d_max * 100
    df["margin_amt_pct_1y"] = df["margin_amt"].rolling(window=250, min_periods=200).apply(
        lambda x: x.rank(pct=True).iloc[-1] * 100, raw=False
    )
    return df


def compute_econ_streak(econ: pd.DataFrame) -> pd.DataFrame:
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
    e = econ[["econ_published_at", "score", "signal_color", "econ_blue_streak"]].rename(
        columns={"econ_published_at": "trade_date", "score": "econ_score",
                 "signal_color": "econ_signal_color"}
    )
    daily_sorted = daily.copy()
    daily_sorted["_dt"] = pd.to_datetime(daily_sorted["trade_date"])
    e_sorted = e.copy()
    e_sorted["_dt"] = pd.to_datetime(e_sorted["trade_date"])
    merged = pd.merge_asof(
        daily_sorted.sort_values("_dt"),
        e_sorted.drop(columns=["trade_date"]).sort_values("_dt"),
        on="_dt", direction="backward",
    )
    return merged.drop(columns=["_dt"])


def main() -> None:
    print(f"=== fg-composite indicators builder ===")
    csv_df = load_csv()
    print(f"  CSV: {len(csv_df)} rows  ({csv_df['trade_date'].min()} ~ {csv_df['trade_date'].max()})"
          if len(csv_df) else "  CSV: empty")

    db = load_db_data()
    for k, v in db.items():
        if v is not None and len(v) > 0:
            print(f"  DB {k}: {len(v)} rows  ({v['trade_date'].min()} ~ {v['trade_date'].max()})"
                  if "trade_date" in v.columns
                  else f"  DB {k}: {len(v)} rows")

    # TAIEX: merge DB + CSV (DB 為最新優先)
    if db["taiex"] is not None:
        db_taiex = db["taiex"].copy()
        db_taiex["trade_date"] = pd.to_datetime(db_taiex["trade_date"]).dt.date
    else:
        db_taiex = None
    taiex_close = merge_raw_with_csv(db_taiex, csv_df, "close")
    taiex_vol = merge_raw_with_csv(db_taiex, csv_df, "volume")
    taiex = taiex_close.merge(taiex_vol, on="trade_date", how="outer").sort_values("trade_date")

    # VIX: 同樣 merge
    if db["vix"] is not None:
        db_vix = db["vix"].copy()
        db_vix["trade_date"] = pd.to_datetime(db_vix["trade_date"]).dt.date
    else:
        db_vix = None
    vix = merge_raw_with_csv(db_vix, csv_df, "vix")

    # Margin: 同樣 merge
    if db["margin"] is not None:
        db_margin = db["margin"].copy()
        db_margin["trade_date"] = pd.to_datetime(db_margin["trade_date"]).dt.date
    else:
        db_margin = None
    margin = merge_raw_with_csv(db_margin, csv_df, "margin_amt")

    # Econ: 只用 DB(若 DB 有的話),否則用 CSV
    if db["econ"] is not None and len(db["econ"]) > 0:
        econ = db["econ"].copy()
        econ["report_month"] = pd.to_datetime(econ["report_month"]).dt.date
    else:
        # 從 CSV 反推 econ(忽略,因 daily CSV 沒月份對應)
        raise RuntimeError("Econ data missing in DB — please run download_econ + parse_econ")

    print(f"\n  After merge:")
    print(f"  taiex: {len(taiex)} rows  ({taiex['trade_date'].min()} ~ {taiex['trade_date'].max()})")
    print(f"  vix:   {len(vix)} rows  ({vix['trade_date'].min()} ~ {vix['trade_date'].max()})")
    print(f"  margin: {len(margin)} rows  ({margin['trade_date'].min()} ~ {margin['trade_date'].max()})")
    print(f"  econ:   {len(econ)} rows  ({econ['report_month'].min()} ~ {econ['report_month'].max()})")

    # Compute rolling indicators
    taiex_ind = compute_taiex_indicators(taiex)
    vix_ind = compute_vix_indicators(vix)
    margin_ind = compute_margin_indicators(margin)
    econ_processed = compute_econ_streak(econ)

    # Merge to daily (基於 TAIEX 日期)
    daily = taiex_ind.merge(
        vix_ind[["trade_date", "vix", "vix_pct"]], on="trade_date", how="left",
    ).merge(
        margin_ind[["trade_date", "margin_amt", "margin_drop_60d_pct", "margin_amt_pct_1y"]],
        on="trade_date", how="left",
    )
    daily = merge_econ_to_daily(daily, econ_processed)

    cols = ["trade_date", "close", "volume",
            "taiex_dist_250ma_pct", "taiex_dist_125ma_z", "volume_5m_60m",
            "vix", "vix_pct",
            "margin_amt", "margin_drop_60d_pct", "margin_amt_pct_1y",
            "econ_score", "econ_signal_color", "econ_blue_streak"]
    daily = daily[cols]

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    daily.to_csv(CSV_PATH, index=False)
    print(f"\n  Output → {CSV_PATH}")
    print(f"  Shape: {daily.shape}, range {daily['trade_date'].min()} ~ {daily['trade_date'].max()}")
    print(f"  Non-null vix_pct in last 10 rows:")
    print("  " + daily.tail(10)[["trade_date","close","vix","vix_pct","margin_amt","margin_drop_60d_pct"]].to_string(index=False).replace("\n", "\n  "))


if __name__ == "__main__":
    main()
