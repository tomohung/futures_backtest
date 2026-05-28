import pandas as pd

from src.chart_ui.services.resample import resample_intraday


def _df(rows):
    idx = pd.to_datetime([r[0] for r in rows])
    return pd.DataFrame(
        {
            "open": [r[1] for r in rows],
            "high": [r[2] for r in rows],
            "low": [r[3] for r in rows],
            "close": [r[4] for r in rows],
            "volume": [r[5] for r in rows],
        },
        index=idx,
    )


def test_resample_5m_buckets_ohlcv():
    # 6 根 1m bar，08:45~08:50 → 5m 應聚成 2 根（08:45 含 5 根、08:50 含 1 根）
    rows = [
        ("2025-06-16 08:45:00", 100, 105, 99, 102, 10),
        ("2025-06-16 08:46:00", 102, 108, 101, 107, 12),
        ("2025-06-16 08:47:00", 107, 110, 106, 109, 8),
        ("2025-06-16 08:48:00", 109, 111, 104, 105, 5),
        ("2025-06-16 08:49:00", 105, 106, 100, 101, 7),
        ("2025-06-16 08:50:00", 101, 103, 100, 102, 4),
    ]
    out = resample_intraday(_df(rows), 5)
    assert len(out) == 2
    first = out.iloc[0]
    assert first["open"] == 100      # 第一根 open
    assert first["high"] == 111      # 5 根最高
    assert first["low"] == 99        # 5 根最低
    assert first["close"] == 101     # 第 5 根 close
    assert first["volume"] == 42     # 10+12+8+5+7
    assert out.iloc[1]["open"] == 101


def test_resample_drops_empty_buckets():
    # 跨越午休/換日的缺口不應產生空 bar
    rows = [
        ("2025-06-16 13:44:00", 100, 101, 99, 100, 3),
        ("2025-06-17 08:45:00", 200, 201, 199, 200, 4),
    ]
    out = resample_intraday(_df(rows), 15)
    assert len(out) == 2  # 只有兩個有資料的 bucket，中間空檔被丟掉
