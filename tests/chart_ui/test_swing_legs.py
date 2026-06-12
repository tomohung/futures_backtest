from src.chart_ui.services.swing_legs import zigzag_legs, _filter_and_format, compute_swing_legs


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


def test_filter_drops_late_start_and_short_amp():
    raw = [
        {"start_min": 600, "start_price": 100, "end_min": 700, "end_price": 180, "dir": "up"},   # 保留
        {"start_min": 700, "start_price": 180, "end_min": 720, "end_price": 100, "dir": "down"},  # 起點 700>=690 → 丟
        {"start_min": 650, "start_price": 100, "end_min": 660, "end_price": 130, "dir": "up"},    # 幅度 30<50 → 丟
    ]
    out = _filter_and_format(raw, threshold=50)
    assert len(out) == 1
    lg = out[0]
    assert lg["start_time"] == "10:00"   # 600 分 → 10:00
    assert lg["end_time"] == "11:40"     # 700 分 → 11:40
    assert lg["dir"] == "up"
    assert lg["amp"] == 80               # 帶方向：up 為正
    assert lg["l3_mult"] == 1.6          # 80/50


def test_filter_amp_negative_for_down():
    raw = [{"start_min": 600, "start_price": 200, "end_min": 680, "end_price": 110, "dir": "down"}]
    out = _filter_and_format(raw, threshold=50)
    assert out[0]["amp"] == -90          # down 為負
    assert out[0]["l3_mult"] == 1.8


def test_compute_swing_legs_insufficient_history(test_db_path):
    out = compute_swing_legs(date_str="2025-06-17", db_path=test_db_path)
    assert out["legs"] == []
    assert out["ema20"] is None
    assert out["l3_dist"] is None
