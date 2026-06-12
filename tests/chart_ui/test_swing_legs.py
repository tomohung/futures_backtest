from src.chart_ui.services.swing_legs import zigzag_legs


def test_single_up_leg():
    # 從 100 一路漲到 150，threshold=30：一段 up，start=低點、end=高點
    bars = [(525, 100, 100), (526, 110, 105), (527, 130, 120), (528, 150, 140)]
    legs = zigzag_legs(bars, threshold=30)
    assert len(legs) == 1
    leg = legs[0]
    assert leg["dir"] == "up"
    assert leg["start_min"] == 525
    assert leg["start_price"] == 100
    assert leg["end_min"] == 528
    assert leg["end_price"] == 150


def test_up_then_down_two_legs():
    # 漲到 150 再跌到 110：兩段（up 100->150, down 150->110），threshold=30
    bars = [
        (525, 100, 100), (526, 130, 120), (527, 150, 140),
        (528, 145, 135), (529, 130, 120), (530, 115, 110),
    ]
    legs = zigzag_legs(bars, threshold=30)
    assert [lg["dir"] for lg in legs] == ["up", "down"]
    assert legs[0]["start_price"] == 100 and legs[0]["end_price"] == 150
    assert legs[1]["start_price"] == 150 and legs[1]["end_price"] == 110


def test_small_wiggle_below_threshold_is_one_leg():
    # 漲到 150（中途小回 5 點 < threshold）→ 仍合併為單一 up 段
    bars = [
        (525, 100, 100), (526, 120, 115), (527, 118, 113),  # 小回 5
        (528, 140, 130), (529, 150, 145),
    ]
    legs = zigzag_legs(bars, threshold=30)
    assert len(legs) == 1
    assert legs[0]["dir"] == "up"
    assert legs[0]["end_price"] == 150
