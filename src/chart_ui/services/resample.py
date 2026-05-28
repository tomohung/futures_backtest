"""把 1 分 K DataFrame 聚合成 N 分鐘 OHLCV。

以視窗第一根為 origin（'start'）對齊 bucket。日盤每日 300 分鐘、相鄰交易日
間隔 24h（=1440 分），皆為 5/15/30/60 的整數倍，故每日 bucket 會自動對齊
到 08:45 開盤。空 bucket（夜間/午休/換日缺口）以 dropna 移除。
"""

import pandas as pd

_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def resample_intraday(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """df：DatetimeIndex、欄位 open/high/low/close/volume。回傳聚合後 DataFrame。"""
    if minutes <= 1 or df.empty:
        return df
    out = df.resample(f"{minutes}min", origin="start").agg(_AGG).dropna(subset=["open"])
    return out
