"""① 前瞻偏誤與特徵語意測試 — runner.py 的特徵計算層。

回測引擎本身是 backtesting.py（第三方套件，訂單成交／停損停利／權益曲線
都是它的責任），本檔測的是**餵給引擎的特徵欄位**：

  1. 因果性 — 特徵在決策當下是否真的可得，還是偷看了未來的 bar
  2. 語意   — 特徵是否真的代表文件宣稱的東西（例：「10 日均線」是不是真的 10 日）

這兩類錯誤都不會讓回測報錯，只會讓績效變好看。

標記 xfail(strict=True) 的測試斷言的是**應有行為**，目前為已知缺陷。
修好之後測試會 XPASS，strict 模式會讓它變成失敗，提醒你回來拿掉標記。
"""
from datetime import date, datetime, time, timedelta

import duckdb
import numpy as np
import pandas as pd
import pytest

from src.backtest import runner
from tests.synthetic import (
    BARS_PER_TRADING_DAY,
    DAY_SESSION_BARS,
    weekdays,
    write_ohlcv_db,
)
from src.backtest.runner import _compute_daily_adx
from src.strategies.orb import ORBLongStrategy

# runner.py 的 RollingOR SQL 硬編碼的開盤區間結束時間
ROLLING_OR_SQL_WINDOW_END = time(9, 30)


# ══════════════════════════════════════════════════════════════════
# 測試資料由 tests/synthetic.py 產生（震盪序列，非單調斜坡）
# ══════════════════════════════════════════════════════════════════

def _load(path, monkeypatch, **kwargs):
    monkeypatch.setattr(runner, "DB_PATH", str(path))
    return runner.load_data_with_night_ma(**kwargs)


# 12 個交易日：ADX(period=3) 約需 2×period 天暖身，太短會讓 DailyADX 全是 NaN，
# 使因果性測試卡在防呆斷言上而永遠不會翻轉（曾經踩過）。
TRADING_DAYS = weekdays(date(2026, 1, 5), 12)
CUTOFF = datetime.combine(TRADING_DAYS[9], time(9, 30))   # 第 10 天 09:30 = ORBLong 開盤區間結束


# ══════════════════════════════════════════════════════════════════
# 通用因果性斷言 — 新增任何特徵欄位時都該套一次
# ══════════════════════════════════════════════════════════════════

def _assert_feature_causal(tmp_path, monkeypatch, column, **load_kwargs):
    """斷言 `column` 在 CUTOFF 當下的值，不受 CUTOFF 之後的 bar 影響。"""
    write_ohlcv_db(tmp_path / "clean.duckdb", TRADING_DAYS)
    write_ohlcv_db(tmp_path / "future.duckdb", TRADING_DAYS, perturb_after=CUTOFF)

    clean = _load(tmp_path / "clean.duckdb", monkeypatch, **load_kwargs)
    future = _load(tmp_path / "future.duckdb", monkeypatch, **load_kwargs)

    ts = pd.Timestamp(CUTOFF)
    assert ts in clean.index, "測試資料未涵蓋 CUTOFF，請檢查 _bar_times"
    assert not np.isnan(clean.loc[ts, column]), f"{column} 在 CUTOFF 仍是暖身期 NaN"

    assert clean.loc[ts, column] == pytest.approx(future.loc[ts, column]), (
        f"{column} 在 {CUTOFF} 的值會隨「之後」的 bar 改變 → 前瞻偏誤"
    )


def test_trend_ma_is_causal(tmp_path, monkeypatch):
    """TrendMA 是 trailing rolling mean，不得反映決策時點之後的價格。"""
    _assert_feature_causal(
        tmp_path, monkeypatch, "TrendMA",
        start="2026-01-06", trend_ma_days=1,
    )


def test_rolling_or_is_causal(tmp_path, monkeypatch):
    """RollingOR 含「當日」開盤區間寬度，但 OR 窗口在進場前就收完，故非前瞻。"""
    _assert_feature_causal(
        tmp_path, monkeypatch, "RollingOR",
        start="2026-01-06", trend_ma_days=1, rolling_or_window=2,
    )


@pytest.mark.xfail(strict=True, reason="已知缺陷：_compute_daily_adx 未 shift，D 日 ADX 用到 D 日全天 High/Low")
def test_daily_adx_is_causal(tmp_path, monkeypatch):
    """DailyADX 在 09:30 就被讀取，但它是用當日全天的 High/Low 算出來的。

    修法：`_compute_daily_adx(...).shift(1)`，讓 D 日只看得到 D-1 日為止的 ADX。
    目前 adx_period 預設為 0（濾網停用），所以沒有 live 策略被汙染；
    orb.py:322 記錄 Phase 6 結論「ADX 與勝負相關性 |r| < 0.05」——
    連偷看未來都測不出 edge，反而讓「ADX 沒用」這個結論更可信。
    """
    _assert_feature_causal(
        tmp_path, monkeypatch, "DailyADX",
        start="2026-01-06", trend_ma_days=1, adx_period=3,
    )


# ══════════════════════════════════════════════════════════════════
# ADX 的前瞻偏誤（純函式層，不碰 DB）
# ══════════════════════════════════════════════════════════════════

def _daily_frame(n=40):
    """合成日 K。刻意用震盪序列而非單調斜坡 —— 完美趨勢會讓 ADX 飽和在 100，
    當日 High/Low 的影響會被壓到小數點後十幾位而測不出來。
    """
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    t = np.arange(n)
    close = 20000 + 200 * np.sin(t / 3.0) + 8 * t
    return pd.DataFrame(
        {"High": close + 60, "Low": close - 60, "Close": close}, index=idx
    )


def test_compute_daily_adx_depends_on_same_day_range():
    """記錄現況：最後一天的高低區間一放寬，最後一天的 ADX 就變。

    這正是前瞻偏誤的來源 —— 09:30 進場時當日區間還沒走完，
    盤中每創一次新高或新低，這個「已經算好」的 ADX 就會回頭改變。

    刻意同時放寬 High 與 Low（而非單邊）：單邊擾動的影響取決於當下
    是上行段還是下行段（dm_p / dm_m 其中一邊會被歸零），會讓測試變得
    資料相依而脆弱。區間放寬則必定推高 TR。

    本測試是「現況存證」，會一直通過；真正的修復指標是
    test_daily_adx_is_causal 由 xfail 轉為 XPASS。
    """
    df = _daily_frame()
    base = _compute_daily_adx(df, period=5).iloc[-1]

    changed = df.copy()
    changed.iloc[-1, changed.columns.get_loc("High")] += 300
    changed.iloc[-1, changed.columns.get_loc("Low")] -= 300

    assert _compute_daily_adx(changed, period=5).iloc[-1] != pytest.approx(base, rel=1e-3)


def test_compute_daily_adx_does_not_depend_on_same_day_close():
    """當日 Close 不影響當日 ADX —— tr[i] 用的是 close[i-1]。

    這條界定了前瞻偏誤的**範圍**：只有 High/Low 洩漏，Close 沒有。
    修正時只需 shift 一格即可，不需要重寫 TR 公式。
    """
    df = _daily_frame()
    base = _compute_daily_adx(df, period=5).iloc[-1]

    changed = df.copy()
    changed.iloc[-1, changed.columns.get_loc("Close")] += 300

    assert _compute_daily_adx(changed, period=5).iloc[-1] == pytest.approx(base)


def test_compute_daily_adx_does_not_depend_on_earlier_days_future():
    """倒數第二天以前的 ADX 不受最後一天影響（遞迴本身是因果的）。"""
    df = _daily_frame()
    base = _compute_daily_adx(df, period=5)

    changed = df.copy()
    changed.iloc[-1] += 300

    np.testing.assert_allclose(
        base.iloc[:-1].values, _compute_daily_adx(changed, period=5).iloc[:-1].values,
        equal_nan=True,
    )


# ══════════════════════════════════════════════════════════════════
# 特徵語意：TrendMA 的「N 日」到底是幾日
# ══════════════════════════════════════════════════════════════════

def _trailing_mean_at(db_path, ts, n_bars) -> float:
    """在完整序列（日盤+夜盤）中，以 ts 為右端點往回取 n_bars 根 close 的平均。

    錨點必須是 ts 在完整序列中的位置 —— ts 是最後一根「日盤」bar，
    其後還有當晚的夜盤 bar，直接取序列尾端會錯位。
    """
    con = duckdb.connect(str(db_path), read_only=True)
    full = con.execute(
        "SELECT timestamp, close FROM ohlcv_1m WHERE symbol='TX' ORDER BY timestamp"
    ).df()
    con.close()
    pos = int(full.index[full["timestamp"] == ts][0])
    window = full["close"].iloc[pos - n_bars + 1: pos + 1].astype(float)
    assert len(window) == n_bars, "測試資料歷史長度不足，請增加 TRADING_DAYS"
    return window.mean()


def test_trend_ma_window_is_301_bars_per_day_unit(tmp_path, monkeypatch):
    """記錄現況：n_bars = trend_ma_days × 301，套在含夜盤的序列上。

    ohlcv_1m 一個完整交易日有 1142 根 bar（日盤 301 + 夜盤 841），
    所以 trend_ma_days=N 的實際回看是 N×301/1142 ≈ 0.26N 個交易日。
    """
    db = tmp_path / "db.duckdb"
    write_ohlcv_db(db, TRADING_DAYS)
    df = _load(db, monkeypatch, trend_ma_days=2)

    ts = df.index[-1]
    expected = _trailing_mean_at(db, ts, 2 * DAY_SESSION_BARS)

    assert df.loc[ts, "TrendMA"] == pytest.approx(expected, rel=1e-6)


@pytest.mark.xfail(strict=True, reason="已知缺陷：runner.py:190 的 301 是日盤 bar 數，卻套用在含夜盤（1142 bar/日）的序列上")
def test_trend_ma_window_covers_requested_trading_days(tmp_path, monkeypatch):
    """trend_ma_days=N 應該回看 N 個交易日。

    orb.py:214 的策略說明寫「收盤價在 10 日趨勢均線上方」，
    但 runner.py:190 的 `n_bars = trend_ma_days * 301` 是**日盤** bar 數，
    而它作用的 df_all 含夜盤（1142 bar/日）→ 實際只回看約 2.6 個交易日。

    注意 orb.py:302 的 fallback 路徑用同一個 301 是**正確的**，
    因為那裡的 self.data.Close 只有日盤。同一個常數被複製到 bar 密度
    不同的序列上，是這個缺陷的成因。

    後果不是「回測結果無效」—— TrendMA 仍是 trailing，沒有前瞻
    （見 test_trend_ma_is_causal）。真正的問題是**同一個 trend_ma_days=10
    在兩條路徑下代表不同的東西**：有 TrendMA 欄位時是 ~2.6 日，
    走 fallback 時是 10 日。策略行為取決於資料怎麼載入。

    修法：改用 `trend_ma_days * BARS_PER_TRADING_DAY`，或直接以時間窗
    （`rolling('10D')`）取代 bar 數窗。

    ⚠️ 修好會改變 S001/ORBLong 的訊號，既有回測結果需重跑。
    現行「最佳參數 trend_ma_days=10」是在錯誤實作下優化出來的，
    等價於約 2.6 日均線；修正後需重新優化。
    """
    db = tmp_path / "db.duckdb"
    write_ohlcv_db(db, TRADING_DAYS)
    df = _load(db, monkeypatch, trend_ma_days=2)

    ts = df.index[-1]
    expected = _trailing_mean_at(db, ts, 2 * BARS_PER_TRADING_DAY)

    assert df.loc[ts, "TrendMA"] == pytest.approx(expected, rel=1e-6)


# ══════════════════════════════════════════════════════════════════
# 參數耦合：RollingOR 的安全性依賴時間窗的相對位置
# ══════════════════════════════════════════════════════════════════

def test_rolling_or_sql_window_closes_before_entry_is_possible():
    """RollingOR 含當日 OR 寬度，只有在 OR 窗口先於進場窗口關閉時才安全。

    runner.py 的 SQL 把開盤區間寫死成 08:45–09:30；ORBLongStrategy 則用
    range_end_minute（距 08:00 的分鐘數）決定何時開始判斷突破。
    只要有人把 range_end_minute 調小（例如 60 = 09:00）而沒同步改 SQL，
    策略就會在 09:00 讀到一個含 09:00–09:30 資訊的 RollingOR —— 靜默前瞻。
    """
    range_end = (
        datetime.combine(date(2026, 1, 1), time(8, 0))
        + timedelta(minutes=ORBLongStrategy.range_end_minute)
    ).time()

    assert range_end >= ROLLING_OR_SQL_WINDOW_END, (
        f"range_end_minute={ORBLongStrategy.range_end_minute} → {range_end}，"
        f"早於 RollingOR SQL 的 {ROLLING_OR_SQL_WINDOW_END} → RollingOR 變成前瞻特徵"
    )


def test_entry_window_opens_after_opening_range_closes():
    """進場截止必須晚於開盤區間結束，否則策略永遠不可能進場。"""
    assert ORBLongStrategy.range_end_minute < ORBLongStrategy.entry_end_minute
