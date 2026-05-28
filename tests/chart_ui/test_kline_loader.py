from datetime import datetime, timezone

import duckdb
import pytest

from src.chart_ui.services.kline_loader import clear_daily_cache, load_kline


@pytest.fixture(autouse=True)
def _isolate_daily_cache():
    # daily 結果有 TTLCache（key 含 db_path），測試間先清掉避免 stale 命中。
    clear_daily_cache()
    yield
    clear_daily_cache()


def _epoch(s):  # 把本地時間字串當 UTC 算 epoch（與 loader 一致）
    return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp())


def test_trading_days_intraday_day_session(test_db_path):
    bars = load_kline(db_path=test_db_path, center="2025-06-17", tf="1m", session="day")
    times = {b["time"] for b in bars}
    # 含 2025-06-17 日盤開收
    assert _epoch("2025-06-17 08:45:00") in times
    assert _epoch("2025-06-17 13:45:00") in times
    # 不含夜盤（2025-06-16 15:00）
    assert _epoch("2025-06-16 15:00:00") not in times
    # buffer 內也含 2025-06-16 日盤
    assert _epoch("2025-06-16 08:45:00") in times


def test_full_session_includes_prev_night_excludes_prev_day(test_db_path):
    bars = load_kline(db_path=test_db_path, center="2025-06-17", tf="1m", session="full")
    times = {b["time"] for b in bars}
    # 全日盤 D=17 視窗 = [16 15:00, 17 13:45]
    assert _epoch("2025-06-16 15:00:00") in times    # 前夜
    assert _epoch("2025-06-17 09:30:00") in times    # 當日日盤
    assert _epoch("2025-06-16 08:45:00") not in times  # 16 日盤在 16 15:00 之前 → 排除


def test_intraday_ohlc_shape(test_db_path):
    bars = load_kline(db_path=test_db_path, center="2025-06-17", tf="5m", session="day")
    assert bars
    b = bars[0]
    assert set(b) == {"time", "open", "high", "low", "close", "volume"}
    assert b["high"] >= b["low"]


def test_daily_day_session(test_db_path):
    bars = load_kline(db_path=test_db_path, tf="1d", session="day")
    times = [b["time"] for b in bars]
    assert times == ["2025-06-16", "2025-06-17"]
    # 第一根 open = 該日第一根 1m 的 open（fixture base=21000）
    assert bars[0]["open"] == pytest.approx(21000.0, abs=1.0)


def test_adjust_adds_adjustment(tmp_path):
    # 自建小 db：一天日盤 3 根，adjustment=100
    db = tmp_path / "adj.duckdb"
    con = duckdb.connect(str(db))
    con.execute(
        "CREATE TABLE ohlcv_1m (timestamp TIMESTAMP, symbol VARCHAR, contract VARCHAR, "
        "open DECIMAL(10,2), high DECIMAL(10,2), low DECIMAL(10,2), close DECIMAL(10,2), "
        "volume INT, tick_count INT, is_rollover BOOLEAN, adjustment DECIMAL(10,2), adj_close DECIMAL(10,2))"
    )
    con.execute(
        "INSERT INTO ohlcv_1m VALUES "
        "('2025-06-16 08:45:00','TX','202507',100,101,99,100,5,1,false,100,200),"
        "('2025-06-16 08:46:00','TX','202507',100,102,98,101,5,1,false,100,201),"
        "('2025-06-16 13:45:00','TX','202507',101,103,100,102,5,1,false,100,202)"
    )
    con.close()
    raw = load_kline(db_path=db, center="2025-06-16", tf="1m", session="day", adjust="raw")
    adj = load_kline(db_path=db, center="2025-06-16", tf="1m", session="day", adjust="adj")
    assert raw[0]["open"] == pytest.approx(100.0)
    assert adj[0]["open"] == pytest.approx(200.0)  # +100
