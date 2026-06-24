"""H126 — detect_day 同向序數 ordinal + is_h126 / h126_variant 純函式測試。"""
from src.chart_ui.services.l2_pullback import (
    COEF,
    H126_TARGET,
    detect_day,
    h126_variant,
    is_h126,
)


def _synthetic_bars():
    """合成一日：long#1 → short#1 → long#2（同向 long 出現兩次），ema20=100。"""
    def seg(p0, p1, n):
        return [p0 + (p1 - p0) * i / n for i in range(1, n + 1)]
    legs = [(10000, 10060, 10), (10060, 10052, 6), (10052, 10064, 8),
            (10064, 10005, 12), (10005, 10014, 6), (10014, 10006, 8),
            (10006, 10066, 12), (10066, 10058, 6), (10058, 10070, 8)]
    pts = [10000]
    for a, b, n in legs:
        pts += seg(a, b, n)
    return [(525 + i, (pts[i - 1] if i else c), max((pts[i - 1] if i else c), c) + 2,
             min((pts[i - 1] if i else c), c) - 2, c) for i, c in enumerate(pts)]


def test_detect_day_assigns_sequential_ordinal_per_side():
    entries, _ = detect_day(_synthetic_bars(), 100.0)
    # 每個 side 的 ordinal 依時間序為 1,2,...
    seen: dict[str, int] = {}
    for e in entries:
        seen[e["side"]] = seen.get(e["side"], 0) + 1
        assert e["ordinal"] == seen[e["side"]]
    # 本合成日確有同向 long 兩次（ordinal 2 出現）
    longs = [e["ordinal"] for e in entries if e["side"] == "long"]
    assert longs == [1, 2]
    assert [e["ordinal"] for e in entries if e["side"] == "short"] == [1]


def test_is_h126_window_and_ordinal():
    base = {"ordinal": 2, "entry_min": 600, "side": "long"}
    assert is_h126(base) is True                      # 2nd+ 且 09:30–11:30
    assert is_h126({**base, "ordinal": 1}) is False   # 第一次不算
    assert is_h126({**base, "entry_min": 560}) is False  # <09:30
    assert is_h126({**base, "entry_min": 690}) is False  # ≥11:30（右開）
    assert is_h126({**base, "entry_min": 689}) is True


def test_h126_variant_uses_anchor_stop_and_L4_target():
    dist = {k: COEF[k] * 100.0 for k in COEF}
    long_e = {"side": "long", "entry": 10060.0, "anchor": 10000.0, "ordinal": 2, "entry_min": 600}
    v = h126_variant(long_e, dist)
    assert v["stop"] == 10000.0                                   # alpha=1.0 → 停損=錨點
    assert v["target"] == round(10000.0 + dist[H126_TARGET], 1)   # 目標=錨+L4d
    assert v["risk"] == round(10060.0 - 10000.0)
    short_e = {"side": "short", "entry": 9940.0, "anchor": 10000.0, "ordinal": 2, "entry_min": 600}
    vs = h126_variant(short_e, dist)
    assert vs["stop"] == 10000.0
    assert vs["target"] == round(10000.0 - dist[H126_TARGET], 1)
    # 純函式不改原 dict
    assert "is_h126" not in long_e and long_e["entry"] == 10060.0
