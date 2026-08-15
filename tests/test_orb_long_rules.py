"""④ ORBLongStrategy 進出場規則測試。

透過真實的 backtesting.py 引擎跑合成日 K，斷言在**產出的交易紀錄**上，
不去戳 next() 的內部狀態。這樣測到的是「策略實際會怎麼做」，
而不是「我以為 next() 怎麼寫」，且完全不需要動 production code。

合成資料的慣例（見 tests/synthetic.py）：
  * 每根 bar Open = Close，High = Close+1，Low = Close−1
  * 所以開盤區間高點 = max(OR 期間 close) + 1
  * 第一個交易日是 backtesting.py 的 indicator 暖身期，不會有交易；
    每個測試都放一天平盤暖身日，斷言只看第二天之後

成交價語意：訊號在收盤價成立的那根 bar 發出，**成交在下一根的 Open**。
因為 Open = Close，所以成交價 = 下一根的 close 值。
"""
from datetime import date, time

import numpy as np
import pytest
from backtesting import Backtest

from src.strategies.orb import ORBLongStrategy
from tests.synthetic import DAY_SESSION_BARS, minute_of, multi_day_frame

WARMUP = date(2026, 1, 5)      # 暖身日，永遠平盤不觸發
D1 = date(2026, 1, 6)          # 受測日
D2 = date(2026, 1, 7)

FLAT = 20000.0
CASH = 1_000_000


def _flat_day(price=FLAT):
    return np.full(DAY_SESSION_BARS, price)


def _at(closes, t: time, value):
    """把 t 之後（含）的所有 close 設為 value。"""
    closes[minute_of(t):] = value
    return closes


def _run(days, strategy=ORBLongStrategy, **params):
    df = multi_day_frame({WARMUP: _flat_day(), **days})
    stats = Backtest(df, strategy, cash=CASH, finalize_trades=True).run(**params)
    return stats["_trades"]


def _trades_on(trades, d: date):
    if trades.empty:
        return trades
    return trades[trades["EntryTime"].dt.date == d]


# ══════════════════════════════════════════════════════════════════
# 暖身與開盤區間
# ══════════════════════════════════════════════════════════════════

def test_first_trading_day_is_warmup_and_never_trades():
    """回測的第一個交易日不會有交易 —— OR 高低線 indicator 在 09:30 前是 NaN，
    backtesting.py 跳過那段前導 bar，開盤區間根本沒被累計。

    這不是策略規則，是引擎的暖身行為，但它會讓「回測區間第一天」永遠缺一筆。
    跑短區間（例如只回測 5 天）時，等於少掉 20% 的樣本。
    """
    breakout = _at(_flat_day(), time(9, 35), 20050.0)
    trades = _run({WARMUP: breakout, D1: breakout.copy()})

    assert _trades_on(trades, WARMUP).empty
    assert len(_trades_on(trades, D1)) == 1


def test_no_entry_before_opening_range_closes():
    """09:30（含）之前只累計開盤區間，不進場 —— 即使價格一路衝高。"""
    rising = np.linspace(20000, 20300, DAY_SESSION_BARS)
    trades = _run({D1: rising})

    entries = _trades_on(trades, D1)
    assert len(entries) == 1
    assert entries.iloc[0]["EntryTime"].time() > time(9, 30)


def test_entry_on_breakout_above_opening_range():
    """收盤突破 OR 高點 → 次根成交做多。"""
    trades = _run({D1: _at(_flat_day(), time(9, 35), 20050.0)})

    entries = _trades_on(trades, D1)
    assert len(entries) == 1
    row = entries.iloc[0]
    assert row["Size"] == 1
    assert row["EntryTime"].time() == time(9, 36)     # 09:35 訊號 → 09:36 成交
    assert row["EntryPrice"] == pytest.approx(20050.0)


def test_no_entry_without_breakout():
    """價格始終在 OR 區間內 → 不進場。

    OR 高點 = 20000 + wick 1 = 20001，收盤 20000.5 未突破。
    """
    trades = _run({D1: _at(_flat_day(), time(9, 35), 20000.5)})

    assert _trades_on(trades, D1).empty


def test_no_entry_after_entry_window_closes():
    """進場窗口為 09:30–11:00（entry_end_minute=120）；11:00 後突破不進場。"""
    trades = _run({D1: _at(_flat_day(), time(11, 5), 20050.0)})

    assert _trades_on(trades, D1).empty


def test_only_one_entry_per_day():
    """每日只進場一次（long_entered 旗標）—— 停損出場後再突破也不再進。"""
    closes = _flat_day()
    _at(closes, time(9, 35), 20050.0)     # 突破 → 進場
    _at(closes, time(9, 38), 19900.0)     # 跌破停損 → 出場
    _at(closes, time(9, 50), 20200.0)     # 再次突破 OR 高點

    trades = _run({D1: closes})

    assert len(_trades_on(trades, D1)) == 1


def test_daily_state_resets_across_days():
    """跨日重置：每個交易日各自累計開盤區間、各自進場一次。"""
    breakout = _at(_flat_day(), time(9, 35), 20050.0)
    trades = _run({D1: breakout.copy(), D2: breakout.copy()})

    assert len(_trades_on(trades, D1)) == 1
    assert len(_trades_on(trades, D2)) == 1


# ══════════════════════════════════════════════════════════════════
# 趨勢濾網
# ══════════════════════════════════════════════════════════════════

def _run_with_trend_ma(closes_by_day, ma_value):
    df = multi_day_frame({WARMUP: _flat_day(), **closes_by_day})
    df["TrendMA"] = ma_value
    stats = Backtest(df, ORBLongStrategy, cash=CASH, finalize_trades=True).run()
    return stats["_trades"]


def test_no_entry_when_close_below_trend_ma():
    """突破成立但收盤在趨勢均線下方 → 不做多。"""
    breakout = _at(_flat_day(), time(9, 35), 20050.0)

    trades = _run_with_trend_ma({D1: breakout}, ma_value=20500.0)

    assert _trades_on(trades, D1).empty


def test_entry_when_close_above_trend_ma():
    """同一組資料，只把均線壓到價格下方 → 進場。

    與上一條配對，證明差別確實來自趨勢濾網而非其他條件。
    """
    breakout = _at(_flat_day(), time(9, 35), 20050.0)

    trades = _run_with_trend_ma({D1: breakout}, ma_value=19500.0)

    assert len(_trades_on(trades, D1)) == 1


def test_trend_filter_skipped_when_ma_is_nan():
    """均線暖身未完成（NaN）→ 濾網放行，而不是擋掉所有交易。

    orb.py:431 的 `if not np.isnan(raw)` 決定 ma_val 是否為 None，
    None 代表「不套濾網」。若改成 NaN 一律擋，回測前段會整段沒有交易。
    """
    breakout = _at(_flat_day(), time(9, 35), 20050.0)

    trades = _run_with_trend_ma({D1: breakout}, ma_value=np.nan)

    assert len(_trades_on(trades, D1)) == 1


# ══════════════════════════════════════════════════════════════════
# 止盈：以開盤區間寬度為基準，並有下限保護
# ══════════════════════════════════════════════════════════════════

def test_take_profit_uses_or_min_width_floor_on_quiet_day():
    """安靜日（OR 寬度 2 點 < or_min_width=20）→ TP 用下限 20 計算。

    TP = 進場價 + 1.5 × max(OR寬度, 20) = 20050 + 30 = 20080。
    若沒有下限保護，TP 只會是 20050 + 1.5×2 = 20053，一開盤就被雜訊掃出場。

    價格刻意先停在 20060 —— 高於「無下限」的 20053、低於「有下限」的 20080。
    這一步是這條測試唯一能分辨兩種實作的地方：直接跳到 20080 的話，
    兩種 TP 都會在同一根成交，測試會假性通過（突變測試抓到過）。
    """
    closes = _at(_flat_day(), time(9, 35), 20050.0)
    _at(closes, time(9, 38), 20060.0)          # 越過無下限 TP(20053)，但未達 20080
    _at(closes, time(9, 40), 20080.0)          # 觸及真正的 TP（仍在 09:45 前）

    entries = _trades_on(_run({D1: closes}), D1)

    assert len(entries) == 1
    row = entries.iloc[0]
    assert row["ExitTime"].time() == time(9, 41), "在 20060 就出場 → or_min_width 下限失效"
    assert row["ExitPrice"] == pytest.approx(20080.0)


def test_take_profit_scales_with_opening_range_width():
    """OR 寬度大於下限時，TP 跟著放大 = 進場價 + 1.5 × OR 寬度。

    OR 收盤在 19950/20050 之間震盪 → or_high=20051, or_low=19949, 寬度=102。
    進場 20060 → TP = 20060 + 1.5×102 = 20213。
    """
    closes = _flat_day()
    or_end = minute_of(time(9, 30)) + 1
    closes[:or_end:2] = 20050.0
    closes[1:or_end:2] = 19950.0
    _at(closes, time(9, 35), 20060.0)          # > or_high 20051
    _at(closes, time(9, 40), 20213.0)          # 觸及 TP

    entries = _trades_on(_run({D1: closes}), D1)

    assert len(entries) == 1
    assert entries.iloc[0]["ExitPrice"] == pytest.approx(20213.0)


# ══════════════════════════════════════════════════════════════════
# 停損與移動停損
# ══════════════════════════════════════════════════════════════════

def test_stop_loss_is_pct_of_entry_before_trail_activates():
    """09:45 前用固定停損 = 進場價 × (1 − 0.4%)。

    進場 20050 → SL = 20050 × 0.996 = 19969.8，跌到 19960 觸發。
    """
    closes = _at(_flat_day(), time(9, 35), 20050.0)
    _at(closes, time(9, 40), 19960.0)

    entries = _trades_on(_run({D1: closes}), D1)

    assert len(entries) == 1
    row = entries.iloc[0]
    assert row["ExitTime"].time() < time(9, 45)
    assert row["ExitPrice"] == pytest.approx(19960.0)
    assert row["PnL"] < 0


def test_trailing_stop_exits_above_entry_after_0945():
    """09:45 後改追蹤最高收盤，回撤 0.4% 出場 —— 出場價可以**高於進場價**。

    這是移動停損與固定停損的分水嶺：固定停損只在 19969.8 觸發（虧損出場），
    而這筆在 20400 就出場並且獲利。若移動停損失效，這條會變成
    「一路抱到 13:00 強制出場」。

    OR 刻意拉寬（19700/20300，寬度 602）讓 TP = 進場價 + 903 遠離，
    避免先觸及止盈而測不到移動停損。
    """
    closes = _flat_day()
    or_end = minute_of(time(9, 30)) + 1
    closes[:or_end:2] = 20300.0
    closes[1:or_end:2] = 19700.0
    _at(closes, time(9, 31), 20300.0)          # 未突破 or_high(20301)
    _at(closes, time(9, 35), 20350.0)          # 突破 → 進場 20350
    _at(closes, time(9, 50), 20500.0)          # 09:45 後創高 → trail_peak = 20500
    _at(closes, time(9, 55), 20400.0)          # 回撤至 20500×0.996=20418 之下 → 出場

    entries = _trades_on(_run({D1: closes}), D1)

    assert len(entries) == 1
    row = entries.iloc[0]
    assert row["ExitTime"].time() == time(9, 56)
    assert row["ExitPrice"] == pytest.approx(20400.0)
    assert row["ExitPrice"] > row["EntryPrice"]      # 移動停損保住了獲利
    assert row["PnL"] > 0


def test_position_is_not_held_overnight():
    """未觸發任何停損停利 → 收在強制出場時點，絕不留倉過夜。"""
    trades = _run({D1: _at(_flat_day(), time(9, 35), 20050.0)})

    row = _trades_on(trades, D1).iloc[0]
    assert row["ExitTime"].date() == D1


def test_force_exit_is_1300_not_1330():
    """強制出場時點由 force_exit_minute=300 決定 → 08:00 + 300 分 = **13:00**。

    ⚠️ orb.py:231 的 class docstring 寫「13:30 強制平倉」，與實作不符。
    參數註解（orb.py:256）寫的 13:00 才是對的。
    這條測試釘住實際行為；若哪天真要改成 13:30，這裡會紅，
    提醒同步更新 docstring 與所有既有回測結果。
    """
    trades = _run({D1: _at(_flat_day(), time(9, 35), 20050.0)})

    row = _trades_on(trades, D1).iloc[0]
    assert row["ExitTime"].time() == time(13, 1)      # 13:00 訊號 → 13:01 成交
    assert row["ExitTime"].time() < time(13, 30)
