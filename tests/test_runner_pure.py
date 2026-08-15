"""② runner.py 純函式測試 — 結算日推算、Wilder 平滑、結算日量校正。

這三支是回測特徵的地基：`_settlement_dates` 決定哪天要做量校正，
`adjust_settlement_volume` 影響 EstRange，`_wilder_smooth` 是 ADX 的核心。
三者都無 I/O、輸入輸出明確，是覆蓋率 CP 值最高的一塊。
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from src.backtest.runner import (
    _SETTLEMENT_VOL_MULTIPLIER,
    _settlement_dates,
    _wilder_smooth,
    adjust_settlement_volume,
)


# ══════════════════════════════════════════════════════════════════
# _settlement_dates — 台指期月結算 = 每月第三個星期三，遇休市往後滾
# ══════════════════════════════════════════════════════════════════

def _all_weekdays(start: date, end: date) -> set:
    """產生區間內所有平日，當作「沒有任何假日」的交易日集合。"""
    days = set()
    d = start
    while d <= end:
        if d.weekday() < 5:
            days.add(d)
        d += timedelta(days=1)
    return days


def test_settlement_is_third_wednesday():
    """一般月份：結算日 = 當月第三個星期三。"""
    trading = _all_weekdays(date(2026, 1, 1), date(2026, 1, 31))

    result = _settlement_dates(trading)

    assert date(2026, 1, 21) in result


def test_settlement_when_month_starts_on_wednesday():
    """月初當天就是星期三 → (2 - weekday) % 7 == 0，首週三即 1 號。

    2026-04-01 與 2026-07-01 都是星期三，是這段位移運算的邊界。
    若寫成 `(2 - weekday) % 7 or 7` 之類會整整差一週。
    """
    trading = _all_weekdays(date(2026, 4, 1), date(2026, 7, 31))

    result = _settlement_dates(trading)

    assert date(2026, 4, 15) in result   # 4/1 是首週三 → 第三週三 = 4/15
    assert date(2026, 7, 15) in result


def test_settlement_rolls_forward_when_third_wednesday_is_holiday():
    """第三個星期三休市 → 往後滾到下一個交易日。"""
    trading = _all_weekdays(date(2026, 1, 1), date(2026, 1, 31))
    trading.discard(date(2026, 1, 21))          # 週三停市
    trading.discard(date(2026, 1, 22))          # 週四也停市

    result = _settlement_dates(trading)

    assert date(2026, 1, 21) not in result
    assert date(2026, 1, 23) in result          # 滾到週五


def test_settlement_gives_up_after_10_days():
    """連續休市超過 10 天（如農曆年前後長假）→ safety break，該月不產生結算日。"""
    trading = _all_weekdays(date(2026, 1, 1), date(2026, 2, 28))
    for offset in range(12):                    # 1/21 起連停 12 天
        trading.discard(date(2026, 1, 21) + timedelta(days=offset))

    result = _settlement_dates(trading)

    jan = {d for d in result if d.year == 2026 and d.month == 1}
    assert jan == set()
    assert date(2026, 2, 18) in result          # 2 月不受影響


def test_settlement_empty_input_returns_empty():
    """沒有交易日資料 → 回空集合，不應拋例外或掃描全部年份。"""
    assert _settlement_dates(set()) == set()


def test_settlement_covers_every_month_in_range():
    """涵蓋範圍由 trading_dates 的年份決定，每個月各一個結算日。"""
    trading = _all_weekdays(date(2025, 1, 1), date(2025, 12, 31))

    result = _settlement_dates(trading)

    assert len(result) == 12
    assert {d.month for d in result} == set(range(1, 13))
    assert all(d.weekday() == 2 for d in result)   # 無假日情境下全是星期三


# ══════════════════════════════════════════════════════════════════
# _wilder_smooth — ADX 的遞迴平滑，seed = 首個完整窗口的算術平均
# ══════════════════════════════════════════════════════════════════

def test_wilder_smooth_seed_is_simple_mean():
    """第一個輸出 = 前 period 個值的算術平均，之後才進遞迴。"""
    arr = np.array([1.0, 2, 3, 4, 5])

    out = _wilder_smooth(arr, period=3)

    assert np.isnan(out[0]) and np.isnan(out[1])
    assert out[2] == pytest.approx(2.0)          # mean(1,2,3)


def test_wilder_smooth_recursion_formula():
    """遞迴式：out[i] = out[i-1] * (n-1)/n + arr[i]/n。"""
    arr = np.array([1.0, 2, 3, 4, 5])

    out = _wilder_smooth(arr, period=3)

    assert out[3] == pytest.approx(2.0 * 2 / 3 + 4 / 3)        # 2.6667
    assert out[4] == pytest.approx(out[3] * 2 / 3 + 5 / 3)     # 3.4444


def test_wilder_smooth_skips_leading_nan_window():
    """前導 NaN → seed 延後到第一個「完整無 NaN」的窗口，不會提早啟動。"""
    arr = np.array([np.nan, np.nan, 1.0, 2, 3, 4])

    out = _wilder_smooth(arr, period=3)

    assert np.all(np.isnan(out[:4]))
    assert out[4] == pytest.approx(2.0)          # mean(1,2,3)，落在 index 4
    assert out[5] == pytest.approx(2.0 * 2 / 3 + 4 / 3)


def test_wilder_smooth_all_nan_when_shorter_than_period():
    """樣本數不足 period → 全 NaN，不可回傳部分窗口的平均。"""
    out = _wilder_smooth(np.array([1.0, 2]), period=3)

    assert np.all(np.isnan(out))


def test_wilder_smooth_is_causal():
    """因果性：改動 index i 之後的值，不得影響 out[i]。"""
    arr = np.arange(1.0, 21.0)
    base = _wilder_smooth(arr, period=5)

    perturbed = arr.copy()
    perturbed[10:] = 999.0
    after = _wilder_smooth(perturbed, period=5)

    np.testing.assert_allclose(base[:10], after[:10], equal_nan=True)


# ══════════════════════════════════════════════════════════════════
# adjust_settlement_volume — 結算日成交量 ×1.9（ohlcv_1m 只存主力合約）
# ══════════════════════════════════════════════════════════════════

def _volume_frame(dates, bars_per_day=3, volume=100) -> pd.DataFrame:
    idx, vols = [], []
    for d in dates:
        for i in range(bars_per_day):
            idx.append(pd.Timestamp(d) + pd.Timedelta(hours=9, minutes=i))
            vols.append(volume)
    return pd.DataFrame({"Volume": vols}, index=pd.DatetimeIndex(idx))


def test_settlement_volume_multiplied_on_settlement_day_only():
    """只有結算日的 Volume 被放大，其餘日期不動。"""
    df = _volume_frame([date(2026, 1, 20), date(2026, 1, 21), date(2026, 1, 22)])

    adjust_settlement_volume(df)

    on_settle = df.loc["2026-01-21", "Volume"]
    assert (on_settle == round(100 * _SETTLEMENT_VOL_MULTIPLIER)).all()   # 190
    assert (df.loc["2026-01-20", "Volume"] == 100).all()
    assert (df.loc["2026-01-22", "Volume"] == 100).all()


def test_settlement_volume_mutates_in_place():
    """呼叫端（load_data_with_night_ma）沒有接回傳值，因此必須就地修改。

    若哪天改成回傳新 DataFrame 而不改原物件，EstRange 會靜默地少掉量校正——
    不會報錯，只會讓 SatZone 偏窄。這個測試就是防這件事。
    """
    df = _volume_frame([date(2026, 1, 21)])

    returned = adjust_settlement_volume(df)

    assert returned is df
    assert (df["Volume"] == 190).all()


def test_settlement_volume_preserves_dtype():
    """int64 進、int64 出：×1.9 後必須 round 回整數，不可變 float。"""
    df = _volume_frame([date(2026, 1, 21)])
    assert df["Volume"].dtype == np.int64

    adjust_settlement_volume(df)

    assert df["Volume"].dtype == np.int64


def test_settlement_volume_noop_when_no_settlement_day():
    """區間內沒有結算日 → 完全不動，且不應拋例外。"""
    df = _volume_frame([date(2026, 1, 5), date(2026, 1, 6)])

    adjust_settlement_volume(df)

    assert (df["Volume"] == 100).all()
