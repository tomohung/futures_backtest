import numpy as np
import pandas as pd


def cumulative_candle_delta(
    open_: pd.Series,
    close: pd.Series,
    volume: pd.Series,
) -> pd.Series:
    """
    Cumulative Candle Delta (CCD)

    Assigns signed volume based on candle body direction:
      - Bullish candle (close > open): +volume
      - Bearish candle (close < open): -volume
      - Doji (close == open):           0

    Then accumulates the signed values into a running total.

    Parameters
    ----------
    open_ : pd.Series  (trailing underscore to avoid shadowing builtin)
    close : pd.Series
    volume : pd.Series

    Returns
    -------
    pd.Series  (same index as inputs, dtype float)
    """
    direction = np.sign(close - open_)   # +1, -1, or 0
    signed_vol = volume * direction
    return signed_vol.cumsum()
