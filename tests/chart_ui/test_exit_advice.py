from src.chart_ui.services.daystats import _exit_advice


def _by_level(res, level):
    """從結構化回傳取出某 level 的 step（沒有則 None）。"""
    for s in res["steps"]:
        if s["level"] == level:
            return s
    return None


def test_strong_regime_early_l1_holds_l3():
    # 碰 L3 前守初始 SL（v4 鐵律：不移 BE）
    res = _exit_advice({"L1": 565}, "strong", "多")
    assert res["band_label"] == "強"
    l1 = _by_level(res, "L1")
    assert l1["action"] == "瞄 L3（守初SL）"
    assert "BE" not in l1["action"]


def test_mid_regime_late_l1_collects_l2():
    # 晚於 09:30（570）暫收 L2，停損仍守初始 SL
    res = _exit_advice({"L1": 580}, "mid", "多")
    l1 = _by_level(res, "L1")
    assert l1["action"] == "暫收 L2（守初SL）"
    assert "BE" not in l1["action"]


def test_mid_regime_early_l2_static_l3():
    # 碰 L2 早於 10:30（630，中）：靜態瞄 L3，不移停損（不再用 trail）
    res = _exit_advice({"L1": 565, "L2": 610}, "mid", "多")
    l2 = _by_level(res, "L2")
    assert l2["action"] == "靜態瞄 L3"
    assert "trail" not in l2["action"]


def test_mid_regime_late_l2_scales_out():
    # 碰 L2 晚於 10:30（中）：半收 L2 半瞄 L3（scale-out）
    res = _exit_advice({"L1": 565, "L2": 650}, "mid", "多")
    l2 = _by_level(res, "L2")
    assert l2["action"] == "半收 L2、半瞄 L3"


def test_weak_regime_l2_holds():
    res = _exit_advice({"L1": 565, "L2": 610}, "weak", "多")
    l2 = _by_level(res, "L2")
    assert l2["action"] == "守 L2／快收"


def test_strong_l2_static_and_hunt_l4():
    # 強 band L2：靜態瞄 L3、標記獵 L4；晚碰（>=630）附上限旁註
    res = _exit_advice({"L1": 565, "L2": 650}, "strong", "多")
    l2 = _by_level(res, "L2")
    assert l2["action"] == "靜態瞄 L3、標記獵 L4"
    assert l2["note"] == "晚碰上限 ~11:00–11:30"


def test_l3_long_dci_branches():
    # 新版 L3 不再依 band 分歧：統一「依 DCI 拆」，多方走 0.2/0.4 拆分支
    res = _exit_advice({"L1": 565, "L2": 610, "L3": 660}, "mid", "多")
    l3 = _by_level(res, "L3")
    assert l3["action"] == "依 DCI 拆"
    assert any("0.2" in b for b in l3["branches"])
    # L3=660 介於 09:30 與 11:30 之間，無時間旁註
    assert l3["note"] is None


def test_l3_band_independent():
    # 強/中/弱在 L3 給出相同的多方 DCI 分支（band 只影響 L1/L2 目標積極度）
    base = {"L1": 565, "L2": 610, "L3": 660}
    branches = {b: _by_level(_exit_advice(base, b, "多"), "L3")["branches"]
                for b in ("strong", "mid", "weak")}
    assert branches["strong"] == branches["mid"] == branches["weak"]


def test_l3_short_asymmetric():
    # 空方 L3 分支與多方不對稱：以 −0.2 切 Dow 為界
    res = _exit_advice({"L1": 565, "L2": 610, "L3": 660}, "mid", "空")
    l3 = _by_level(res, "L3")
    assert any("−0.2" in b for b in l3["branches"])


def test_l3_early_gap_and_go_note():
    # 早碰 L3（< 09:30=570）：gap-and-go 旁註
    res = _exit_advice({"L1": 540, "L2": 555, "L3": 565}, "mid", "多")
    l3 = _by_level(res, "L3")
    assert l3["note"] is not None and "gap-and-go" in l3["note"]


def test_l4_l5_steps_present():
    # 碰到 L4／L5 會各補一個 step
    res = _exit_advice({"L1": 565, "L2": 610, "L3": 660, "L4": 700, "L5": 740}, "mid", "多")
    assert _by_level(res, "L4") is not None
    assert _by_level(res, "L5") is not None


def test_no_l1_touch():
    res = _exit_advice({}, "mid", "多")
    assert res == {"band_label": "中", "steps": [], "note": "未碰 L1"}
