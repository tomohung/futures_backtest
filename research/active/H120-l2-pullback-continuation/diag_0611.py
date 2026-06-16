"""Diagnostic: trace H120 detect_day for 2026-06-11, focus on ~09:11.
Instruments the per-leg state machine to show WHY a setup did/didn't fire.
Read-only. Run: uv run python research/active/H120-l2-pullback-continuation/diag_0611.py
"""
from datetime import date
import duckdb
from src.chart_ui import paths
from src.chart_ui.services.daystats import SYMBOL, _ema20_range
from src.chart_ui.services.swing_legs import zigzag_legs
from src.chart_ui.services.l2_pullback import COEF, PB_FLOOR_FRAC, EMA5, _sma, _min_to_hhmm

SEL = date(2026, 6, 11)


def m2h(m):
    return _min_to_hhmm(m)


with duckdb.connect(str(paths.DUCKDB_PATH), read_only=True) as conn:
    ema20 = _ema20_range(conn, SEL)
    rows = conn.execute(
        "SELECT CAST(timestamp AS TIME) t, open, high, low, close FROM ohlcv_1m "
        "WHERE symbol = ? AND CAST(timestamp AS DATE) = ? "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "ORDER BY timestamp", [SYMBOL, SEL]).fetchall()
bars = [(t.hour * 60 + t.minute, float(o), float(h), float(l), float(c))
        for t, o, h, l, c in rows]

dist = {k: COEF[k] * ema20 for k in COEF}
L2d, L3d = dist["L2"], dist["L3"]
pb_floor = PB_FLOOR_FRAC * ema20
print(f"ema20={ema20:.2f}  L2d={L2d:.1f}  L3d={L3d:.1f}  pb_floor={pb_floor:.1f}")
print(f"bars: {m2h(bars[0][0])}..{m2h(bars[-1][0])} n={len(bars)}")

# show price action around 09:00-09:30
print("\n--- price 08:45-09:40 ---")
for m, o, h, l, c in bars:
    if 525 <= m <= 580:  # 08:45=525 ... 09:40=580
        print(f"  {m2h(m)} O{o:.0f} H{h:.0f} L{l:.0f} C{c:.0f}")

closes = [b[4] for b in bars]
s5 = _sma(closes, EMA5)
legs = zigzag_legs([(m, h, l) for m, _, h, l, _ in bars], threshold=L2d)

print(f"\n--- zigzag legs (threshold=L2d={L2d:.1f}) ---")
for lg in legs:
    print(f"  {lg['dir']:4s} {m2h(lg['start_min'])}@{lg['start_price']:.0f} -> "
          f"{m2h(lg['end_min'])}@{lg['end_price']:.0f}  "
          f"move={abs(lg['end_price']-lg['start_price']):.1f}")

print("\n--- per-leg state machine trace ---")
for lg in legs:
    move = abs(lg["end_price"] - lg["start_price"])
    tag = f"{lg['dir']} {m2h(lg['start_min'])}@{lg['start_price']:.0f}->{m2h(lg['end_min'])}@{lg['end_price']:.0f}"
    if move < L2d:
        print(f"[SKIP move<{L2d:.0f}] {tag}")
        continue
    up = lg["dir"] == "up"
    sm, em, anchor = lg["start_min"], lg["end_min"], lg["start_price"]
    seg_idx = [i for i, b in enumerate(bars) if sm <= b[0] <= em]
    if len(seg_idx) < 3:
        print(f"[SKIP seg<3] {tag}")
        continue
    est_i = None
    ext = 0.0
    for i in seg_idx:
        _, _, h, l, _ = bars[i]
        ext = max(ext, (h - anchor) if up else (anchor - l))
        if ext >= L2d:
            est_i = i
            break
    if est_i is None:
        print(f"[SKIP no-L2-est] {tag}")
        continue
    print(f"[LEG] {tag}  L2 confirmed @ {m2h(bars[est_i][0])}")
    state = "extend"
    peak = None
    pb_ext = None
    fired = False
    for i in seg_idx:
        if i < est_i:
            continue
        m, o, h, l, c = bars[i]
        if peak is None:
            peak = h if up else l
            continue
        if state == "extend":
            if (h > peak) if up else (l < peak):
                peak = h if up else l
            if abs(peak - anchor) >= L3d:
                print(f"    {m2h(m)} -> MATURED (peak {peak:.0f} hit L3 {anchor + (L3d if up else -L3d):.0f}); no trade")
                break
            dip = (peak - l) if up else (h - peak)
            if dip >= pb_floor:
                state = "pullback"
                pb_ext = l if up else h
                print(f"    {m2h(m)} pullback START (peak={peak:.0f} dip={dip:.1f}>={pb_floor:.1f}) pb_ext={pb_ext:.0f}")
        else:
            pb_ext = min(pb_ext, l) if up else max(pb_ext, h)
            cs, ps = s5[i], s5[i - 1]
            pc = bars[i - 1][4]
            if cs is None or ps is None:
                continue
            reclaim = (pc < ps and c > cs) if up else (pc > ps and c < cs)
            overshoot = (c >= anchor + L3d) if up else (c <= anchor - L3d)
            if reclaim:
                depth = (peak - pb_ext) if up else (pb_ext - peak)
                dfrac = depth / L2d
                if overshoot:
                    print(f"    {m2h(m)} reclaim but OVERSHOOT (c={c:.0f}); no trade")
                    break
                print(f"    {m2h(m)} *** ENTRY {('long' if up else 'short')} c={c:.0f} "
                      f"depth_frac={dfrac:.2f} (need>=0.25)  pb_ext={pb_ext:.0f}")
                fired = True
                break
    if not fired and state == "pullback":
        print(f"    (pullback never reclaimed 5MA before leg end)")


print("\n--- WHAT-IF: allow multiple pullback-entries per leg (no break) ---")
for lg in legs:
    move = abs(lg["end_price"] - lg["start_price"])
    if move < L2d:
        continue
    up = lg["dir"] == "up"
    sm, em, anchor = lg["start_min"], lg["end_min"], lg["start_price"]
    seg_idx = [i for i, b in enumerate(bars) if sm <= b[0] <= em]
    if len(seg_idx) < 3:
        continue
    est_i = None
    ext = 0.0
    for i in seg_idx:
        _, _, h, l, _ = bars[i]
        ext = max(ext, (h - anchor) if up else (anchor - l))
        if ext >= L2d:
            est_i = i
            break
    if est_i is None:
        continue
    state = "extend"
    peak = None
    pb_ext = None
    tag = f"{lg['dir']} {m2h(lg['start_min'])}->{m2h(lg['end_min'])}"
    for i in seg_idx:
        if i < est_i:
            continue
        m, o, h, l, c = bars[i]
        if peak is None:
            peak = h if up else l
            continue
        if state == "extend":
            if (h > peak) if up else (l < peak):
                peak = h if up else l
            if abs(peak - anchor) >= L3d:
                break
            dip = (peak - l) if up else (h - peak)
            if dip >= pb_floor:
                state = "pullback"
                pb_ext = l if up else h
        else:
            pb_ext = min(pb_ext, l) if up else max(pb_ext, h)
            cs, ps = s5[i], s5[i - 1]
            pc = bars[i - 1][4]
            if cs is None or ps is None:
                continue
            reclaim = (pc < ps and c > cs) if up else (pc > ps and c < cs)
            overshoot = (c >= anchor + L3d) if up else (c <= anchor - L3d)
            if reclaim and not overshoot:
                depth = (peak - pb_ext) if up else (pb_ext - peak)
                dfrac = depth / L2d
                kept = "KEEP" if dfrac >= 0.25 else "filtered(shallow)"
                print(f"  [{tag}] {m2h(m)} reclaim entry c={c:.0f} depth_frac={dfrac:.2f} -> {kept}")
                # reset to look for the next pullback within the same leg
                state = "extend"
                peak = h if up else l
