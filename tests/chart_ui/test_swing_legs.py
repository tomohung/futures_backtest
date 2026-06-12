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
