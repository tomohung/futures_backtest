from src.chart_ui.services.daystats import _exit_advice


def test_strong_regime_early_l1_holds_l3():
    # 碰 L3 前守初始 SL（v4 鐵律：不移 BE）
    s = _exit_advice({"L1": 565}, "strong", "多")
    assert "碰L1" in s and "瞄L3(守初SL)" in s
    assert "BE" not in s


def test_mid_regime_late_l1_collects_l2():
    # 晚於 09:30 暫收 L2，停損仍守初始 SL
    s = _exit_advice({"L1": 580}, "mid", "多")
    assert "暫收L2(守初SL)" in s
    assert "BE" not in s


def test_mid_regime_early_l2_static_l3():
    # 碰 L2 早於 10:45（中）：靜態瞄 L3，不移停損（不再用 trail）
    s = _exit_advice({"L1": 565, "L2": 610}, "mid", "多")
    assert "碰L2" in s and "靜態瞄L3" in s
    assert "trail" not in s


def test_mid_regime_late_l2_scales_out():
    # 碰 L2 晚於 10:45（中）：半收 L2 半瞄 L3（scale-out）
    s = _exit_advice({"L1": 565, "L2": 650}, "mid", "多")
    assert "半收L2半瞄L3" in s


def test_weak_regime_l2_holds():
    s = _exit_advice({"L1": 565, "L2": 610}, "weak", "多")
    assert "守L2/快收" in s


def test_strong_l3_wide_trail():
    s = _exit_advice({"L1": 565, "L2": 610, "L3": 660}, "strong", "多")
    assert "碰L3→寬trail博L4" in s


def test_mid_l3_scales_out():
    s = _exit_advice({"L1": 565, "L2": 610, "L3": 660}, "mid", "多")
    assert "碰L3→半Dow博L4半鎖L3" in s


def test_weak_l3_static():
    # 弱不 trail，碰 L3 靜態拿
    s = _exit_advice({"L1": 565, "L2": 610, "L3": 660}, "weak", "多")
    assert "碰L3→靜態拿L3" in s
    assert "trail" not in s


def test_no_l1_touch():
    assert _exit_advice({}, "mid", "多") == "多(中)：未碰 L1"
