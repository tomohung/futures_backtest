"""③ 資料管線不變量測試 — load_data_with_night_ma 的隱含契約。

這些性質目前只靠註解與呼叫順序維持，沒有任何機制保證。它們一旦被破壞，
回測不會報錯，只會安靜地算出不同的數字：

  * EstRange 必須在**日期篩選前**用完整歷史計算（runner.py 的註解自己寫的）
  * 結算日量校正必須在 EstRange **之前**跑，否則 SatZone 會偏窄
  * 暖身期必須是 NaN 而非 0 —— 策略靠 isnan 判斷「還不能用」，填 0 會讓濾網靜默通過
  * 欄位是**位置對應**改名的（df_day.columns = [...]），SQL 欄位順序一動就全錯
"""
from datetime import date, datetime, time

import numpy as np
import pandas as pd
import pytest

from src.backtest import runner
from src.backtest.runner import _SETTLEMENT_VOL_MULTIPLIER
from tests.synthetic import weekdays, write_ohlcv_db

# EstRange 的 EMA(20) 需要 20 個交易日暖身，另留幾天觀察區間
TRADING_DAYS = weekdays(date(2026, 1, 5), 28)
LATE_START = TRADING_DAYS[24].isoformat()


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("invariants") / "ohlcv.duckdb"
    write_ohlcv_db(path, TRADING_DAYS)
    return path


def _load(db, monkeypatch, **kwargs):
    monkeypatch.setattr(runner, "DB_PATH", str(db))
    return runner.load_data_with_night_ma(**kwargs)


# ══════════════════════════════════════════════════════════════════
# 不變量 1：EstRange 必須用完整歷史計算，日期篩選只能在最後做
# ══════════════════════════════════════════════════════════════════

EST_COLUMNS = ["EmaVol", "EmaHL", "EstHL", "SatZoneUpper", "SatZoneLower",
               "EstHighLevel", "EstLowLevel"]


@pytest.mark.parametrize("column", EST_COLUMNS)
def test_estimate_hl_unaffected_by_start_filter(db, monkeypatch, column):
    """同一天的 EstRange，帶不帶 start 都必須算出一樣的值。

    runner.py 的註解寫著「Estimated H-L zones (must run on full history
    BEFORE date filtering)」—— 這條測試就是把那句註解變成可執行的保證。
    若哪天有人把 `if start:` 搬到 compute_estimate_hl_zones 之前，
    EMA(20) 會從被截斷的歷史重新暖身，SatZone 靜默改變、回測結果不可重現。
    """
    full = _load(db, monkeypatch, trend_ma_days=1, estimate_hl=True)
    sliced = _load(db, monkeypatch, trend_ma_days=1, estimate_hl=True, start=LATE_START)

    overlap = sliced.index
    assert len(overlap) > 0, "測試資料未涵蓋 LATE_START 之後的日期"

    pd.testing.assert_series_equal(
        full.loc[overlap, column], sliced[column], check_names=False,
    )


def test_estimate_hl_columns_are_present(db, monkeypatch):
    """estimate_hl=True 必須補齊全部 7 個欄位，缺一個策略就會 KeyError。"""
    df = _load(db, monkeypatch, trend_ma_days=1, estimate_hl=True)

    assert set(EST_COLUMNS) <= set(df.columns)


def test_estimate_hl_not_computed_when_disabled(db, monkeypatch):
    """estimate_hl=False 時不應留下半成品欄位（避免策略誤用到未校正的值）。"""
    df = _load(db, monkeypatch, trend_ma_days=1, estimate_hl=False)

    assert not (set(EST_COLUMNS) & set(df.columns))


# ══════════════════════════════════════════════════════════════════
# 不變量 2：結算日量校正必須先於 EstRange
# ══════════════════════════════════════════════════════════════════

def test_settlement_volume_is_adjusted_before_estimate_hl(db, monkeypatch):
    """estimate_hl=True 時，回傳的 Volume 在結算日必須已經是校正後的值。

    ohlcv_1m 只存主力合約的量，結算日的量會被拆到新舊兩個合約上，
    因此要先 ×1.9 再算 EstRange。這裡用「回傳的 Volume 已被改寫」
    間接證明 adjust_settlement_volume 確實在 compute_estimate_hl_zones 之前跑過。
    """
    raw_volume = 100      # synthetic.write_ohlcv_db 固定寫入的量
    settlement = date(2026, 1, 21)     # 2026-01 第三個星期三
    assert settlement in TRADING_DAYS

    df = _load(db, monkeypatch, trend_ma_days=1, estimate_hl=True)
    on_settle = df.loc[settlement.isoformat(), "Volume"]

    assert (on_settle == round(raw_volume * _SETTLEMENT_VOL_MULTIPLIER)).all()


def test_settlement_volume_untouched_when_estimate_hl_disabled(db, monkeypatch):
    """estimate_hl=False 時不做量校正 —— 校正只為 EstRange 服務。

    這條界定了副作用範圍：不跑 EstRange 的策略拿到的是原始量。
    若哪天把 adjust_settlement_volume 提到 if 外面，這裡會紅。
    """
    df = _load(db, monkeypatch, trend_ma_days=1, estimate_hl=False)

    assert (df.loc["2026-01-21", "Volume"] == 100).all()


# ══════════════════════════════════════════════════════════════════
# 不變量 3：暖身期必須是 NaN，不能是 0 或前向填補
# ══════════════════════════════════════════════════════════════════

def test_trend_ma_warmup_is_nan_not_zero(db, monkeypatch):
    """暖身不足時 TrendMA 必須是 NaN。

    orb.py:431 用 `if not np.isnan(raw)` 決定要不要套趨勢濾網。
    若這裡改成 min_periods=1 或 fillna(0)，濾網會變成
    「close > 0」—— 永遠通過，趨勢確認形同虛設，而且不會有任何錯誤訊息。
    """
    df = _load(db, monkeypatch, trend_ma_days=3)

    assert df["TrendMA"].isna().any(), "暖身期完全沒有 NaN，min_periods 可能被放寬了"
    assert np.isnan(df["TrendMA"].iloc[0])


def test_rolling_or_warmup_is_nan_not_zero(db, monkeypatch):
    """RollingOR 同理 —— orb.py:422 也是靠 isnan 判斷可用性。"""
    df = _load(db, monkeypatch, trend_ma_days=1, rolling_or_window=5)

    assert np.isnan(df["RollingOR"].iloc[0])


# ══════════════════════════════════════════════════════════════════
# 不變量 4：欄位是位置對應改名的，OHLC 語意必須成立
# ══════════════════════════════════════════════════════════════════

def test_ohlc_columns_are_not_positionally_swapped(db, monkeypatch):
    """runner.py 用 `df_day.columns = ["Open","High","Low","Close","Volume"]`
    直接依**位置**改名。SQL 的 SELECT 欄位順序一旦調整（例如有人把
    low 排到 high 前面），改名照樣成功、不會拋錯，但 High/Low 會對調。

    用 OHLC 的定義性質當守門員：High 必須是四者最大、Low 必須是最小。
    """
    df = _load(db, monkeypatch, trend_ma_days=1)

    assert (df["High"] >= df[["Open", "Close", "Low"]].max(axis=1)).all()
    assert (df["Low"] <= df[["Open", "Close", "High"]].min(axis=1)).all()
    assert (df["Volume"] > 0).all()


def test_returned_frame_matches_backtesting_contract(db, monkeypatch):
    """backtesting.py 要求 DatetimeIndex + 這五個欄位名，且索引須遞增。"""
    df = _load(db, monkeypatch, trend_ma_days=1)

    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.is_monotonic_increasing
    assert {"Open", "High", "Low", "Close", "Volume"} <= set(df.columns)


# ══════════════════════════════════════════════════════════════════
# 不變量 5：日期篩選與時段篩選
# ══════════════════════════════════════════════════════════════════

def test_start_filter_includes_boundary_day(db, monkeypatch):
    """start 是閉區間：邊界當天整天留下，前一個交易日整天排除。

    （end 的行為不對稱，見 test_end_filter_keeps_whole_last_day。）
    """
    start = TRADING_DAYS[5]

    df = _load(db, monkeypatch, trend_ma_days=1, start=start.isoformat())

    days = set(df.index.normalize().date)
    assert start in days
    assert TRADING_DAYS[4] not in days
    assert len(df.loc[start.isoformat()]) == 301   # 整個日盤都在


def test_only_day_session_bars_are_returned(db, monkeypatch):
    """回傳的必須只有日盤 08:45–13:45。

    夜盤只用來算 TrendMA，不能進回測 —— 一旦漏進來，
    ORBStrategy 的「換日重置」會在夜盤 bar 上誤觸發，開盤區間全錯。
    """
    df = _load(db, monkeypatch, trend_ma_days=1)

    times = df.index.time
    assert times.min() >= time(8, 45)
    assert times.max() <= time(13, 45)


def test_end_filter_keeps_whole_last_day(db, monkeypatch):
    """end 是日期字串（解析為當天 00:00）時的邊界行為。

    `df_day.index <= "2026-01-12"` 會被解析成 <= 2026-01-12 00:00:00，
    而日盤 bar 最早是 08:45 —— 也就是 end 當天會被整天排除。
    這條測試把這個容易誤用的現況釘住：想含當天必須寫 "2026-01-12 13:45"。
    """
    end_day = TRADING_DAYS[8]

    df = _load(db, monkeypatch, trend_ma_days=1, end=end_day.isoformat())
    assert end_day not in set(df.index.normalize().date)

    df_incl = _load(db, monkeypatch, trend_ma_days=1,
                    end=datetime.combine(end_day, time(13, 45)).isoformat())
    assert end_day in set(df_incl.index.normalize().date)
