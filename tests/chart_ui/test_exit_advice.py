from src.chart_ui.services.daystats import _exit_advice


def test_strong_regime_early_l1_holds_l3():
    s = _exit_advice({"L1": 565}, "strong", "多")
    assert "碰L1" in s and "瞄L3抱BE" in s


def test_mid_regime_late_l1_collects_l2():
    s = _exit_advice({"L1": 580}, "mid", "多")
    assert "收L2" in s


def test_mid_regime_early_l2_trails():
    s = _exit_advice({"L1": 565, "L2": 610}, "mid", "多")
    assert "碰L2" in s and "trail博L3" in s


def test_weak_regime_l2_holds():
    s = _exit_advice({"L1": 565, "L2": 610}, "weak", "多")
    assert "守L2" in s


def test_no_l1_touch():
    assert _exit_advice({}, "mid", "多") == "多(中)：未碰 L1"
