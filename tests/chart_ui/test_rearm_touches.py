"""純函式 _rearm_touches：每個 ≥L2 反轉波段重新上膛 L1–L5（方案 B）。"""

from src.chart_ui.services.daystats import _rearm_touches

LEVELS = [("L1", 10.0), ("L2", 20.0), ("L3", 30.0)]
L2_DIST = 20.0

# W 形日：上(100→140) / 下(140→90) / 上(90→145)。各段反轉 ≥ L2(20)。
W_BARS = [
    (0, 100, 100),
    (1, 110, 100),
    (2, 125, 105),
    (3, 140, 120),   # 波段高 140
    (4, 135, 115),
    (5, 120, 100),
    (6, 105, 90),    # 波段低 90
    (7, 115, 95),
    (8, 130, 110),
    (9, 145, 125),   # 波段高 145
]


def test_rearm_redraws_same_level_per_swing():
    out = _rearm_touches(W_BARS, LEVELS, L2_DIST)
    bull = out["bull"]
    # 兩段上攻（錨 100、錨 90）各點亮一組 L1–L3 → 同階各兩筆
    assert [t["level"] for t in bull].count("L1") == 2
    assert [t["level"] for t in bull].count("L2") == 2
    assert [t["level"] for t in bull].count("L3") == 2
    # L1 兩筆錨價不同：100+10 與 90+10
    l1_prices = sorted(t["price"] for t in bull if t["level"] == "L1")
    assert l1_prices == [100, 110]
    # 中間下行段點亮空方 L1–L3（錨 140）
    bear_levels = [t["level"] for t in out["bear"]]
    assert bear_levels.count("L1") == 1
    assert bear_levels.count("L3") == 1
    assert sorted(t["price"] for t in out["bear"] if t["level"] == "L1") == [130]  # 140-10
    # 仍按時間昇冪
    assert [t["minute"] for t in bull] == sorted(t["minute"] for t in bull)


def test_fallback_single_anchor_when_no_swing():
    # 無任何 ≥L2 反轉的小波動日 → 退回單一 running 錨點，L1 仍畫
    bars = [(0, 100, 100), (1, 105, 100), (2, 112, 104)]   # 最大上行 12，僅達 L1
    out = _rearm_touches(bars, LEVELS, L2_DIST)
    assert [t["level"] for t in out["bull"]] == ["L1"]
    assert out["bull"][0]["price"] == 110   # run_lo 100 + 10
    assert out["bear"] == []


def test_empty_bars():
    assert _rearm_touches([], LEVELS, L2_DIST) == {"bull": [], "bear": []}
