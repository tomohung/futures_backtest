# Chart-UI 覆盤出場資訊 + 主圖關卡標示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** chart-ui 選交易日覆盤時，右欄顯示當日 DCI(事後)+regime+建議出場法，主圖標示多空 L1–L4 關卡線、各階觸及 marker、09:30/10:45 時間線。

**Architecture:** 後端新增 `dci_daily.py`（純函式算當日收盤 DCI）+ `daystats.py` 擴充 payload（dci/touches/exit_advice，含純函式 `_exit_advice`、`_collect_touches`）；前端 `app.js` 新增 `renderDci`（右欄）與 `drawReviewOverlay`（主圖，沿用 markerState/priceLines，與回測清單 `drawTradeMarkers` 並存）。

**Tech Stack:** Python 3.14 + DuckDB + pytest（後端）；vanilla JS + lightweight-charts v5（前端，目視驗證）。

---

## File Structure

- Create `src/chart_ui/services/dci_daily.py` — 當日 DCI 計算（W 固定權值清單 / H 成交值前20 / B 漲跌家數）
- Create `tests/chart_ui/test_dci_daily.py` — dci_daily 單元測試（自帶 inline DuckDB）
- Create `tests/chart_ui/test_exit_advice.py` — `_exit_advice` 純函式測試
- Modify `src/chart_ui/services/daystats.py` — `_collect_touches`(到 L3)、`_exit_advice`、payload 串接
- Modify `src/chart_ui/static/app.js` — `renderDci`、`drawReviewOverlay`、`renderDayStats` 串接
- Modify `src/chart_ui/static/app.css` — DCI 區塊樣式

測試策略：`compute_daily_dci`、`_exit_advice`、`_collect_touches` 走 TDD（前兩者自帶 inline DB / 純函式，第三者用既有 ohlcv_1m fixture）。daystats 串接與前端走 `uv run chart-ui` 對真實 `data/futures.duckdb` 目視驗證（daystats 因查 vixtwn/market_breadth 未防呆，無法跑 fixture DB，與既有情況一致）。

---

### Task 1: dci_daily 模組

**Files:**
- Create: `src/chart_ui/services/dci_daily.py`
- Test: `tests/chart_ui/test_dci_daily.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/chart_ui/test_dci_daily.py
from datetime import date
import duckdb
import pytest
from src.chart_ui.services.dci_daily import compute_daily_dci, TOP_WEIGHT_SYMBOLS


def _db(tmp_path):
    p = tmp_path / "dci.duckdb"
    con = duckdb.connect(str(p))
    con.execute("CREATE TABLE market_breadth (trade_date DATE, market VARCHAR, "
                "listed_count INT, up_count INT, down_count INT, total_value BIGINT)")
    con.execute("CREATE TABLE stock_day (trade_date DATE, market VARCHAR, symbol VARCHAR, "
                "change DECIMAL(10,2), value BIGINT)")
    con.execute("INSERT INTO market_breadth VALUES "
                "(DATE '2026-05-21','TWSE',1000,700,200,1000000)")
    # 權值股全漲、熱門股全漲 → W,H 接近 +1；家數 (700-200)/1000=+0.5
    rows = []
    for s in TOP_WEIGHT_SYMBOLS[:5]:
        rows.append(f"(DATE '2026-05-21','TWSE','{s}',10.0,9000000000)")
    # 幾檔非權值熱門股（成交值更大）也全漲
    for i in range(20):
        rows.append(f"(DATE '2026-05-21','TWSE','H{i:03d}',5.0,99000000000)")
    con.execute("INSERT INTO stock_day VALUES " + ",".join(rows))
    con.close()
    return p


def test_dci_strong_bull_day(tmp_path):
    con = duckdb.connect(str(_db(tmp_path)), read_only=True)
    r = compute_daily_dci(con, date(2026, 5, 21))
    con.close()
    assert r is not None
    assert r["B"] == pytest.approx(0.5)
    assert r["W"] == pytest.approx(1.0)        # 權值股全漲
    assert r["H"] == pytest.approx(1.0)        # 熱門前20全漲
    assert r["dci_long"] == pytest.approx(0.40 * 1.0 + 0.35 * 1.0 + 0.25 * 0.5)
    assert r["regime_long"] == "strong"


def test_dci_none_when_no_breadth(tmp_path):
    p = tmp_path / "empty.duckdb"
    con = duckdb.connect(str(p))
    con.execute("CREATE TABLE market_breadth (trade_date DATE, market VARCHAR, "
                "listed_count INT, up_count INT, down_count INT, total_value BIGINT)")
    con.execute("CREATE TABLE stock_day (trade_date DATE, market VARCHAR, symbol VARCHAR, "
                "change DECIMAL(10,2), value BIGINT)")
    con.close()
    con = duckdb.connect(str(p), read_only=True)
    assert compute_daily_dci(con, date(2026, 5, 21)) is None
    con.close()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/chart_ui/test_dci_daily.py -v`
Expected: FAIL（`ModuleNotFoundError: dci_daily`）

- [ ] **Step 3: 實作 dci_daily.py**

```python
"""當日 DCI（方向共識指標）— 收盤/事後值。詳見
research/active/H095-reach-ladder-exit/dci_spec.md。

W 用固定權值清單(無真實市值,以成交值近似權重)、H 用當日成交值前20、B 用漲跌家數。
盤中即時版需另接盤中三序列；此處僅供 chart-ui 覆盤標「事後」。
"""
from __future__ import annotations

from datetime import date

# 台股權值前 ~20 大（截至 2026-05，需偶爾更新）
TOP_WEIGHT_SYMBOLS = [
    "2330", "2317", "2454", "2308", "2881", "2382", "2891", "2882", "2412",
    "2303", "3711", "2886", "1216", "2884", "2885", "2357", "2892", "2880",
    "3008", "2002", "2207",
]
_WL = (0.40, 0.35, 0.25)   # long: W,H,B
_WS = (0.30, 0.30, 0.40)   # short


def _band_long(c: float) -> str:
    return "strong" if c >= 0.30 else "weak" if c <= -0.10 else "mid"


def _band_short(c: float) -> str:
    return "strong" if c <= -0.20 else "weak" if c >= 0.10 else "mid"


def compute_daily_dci(conn, sel: date) -> dict | None:
    """回傳 {W,H,B,dci_long,dci_short,regime_long,regime_short} 或 None（資料不足）。"""
    b = conn.execute(
        "SELECT up_count, down_count, listed_count FROM market_breadth "
        "WHERE market='TWSE' AND trade_date = ?", [sel]
    ).fetchone()
    if not b or not b[2]:
        return None
    B = (b[0] - b[1]) / b[2]

    ph = ",".join(["?"] * len(TOP_WEIGHT_SYMBOLS))
    w = conn.execute(
        f"SELECT SUM(SIGN(change)*value)/NULLIF(SUM(value),0) FROM stock_day "
        f"WHERE market='TWSE' AND trade_date = ? AND symbol IN ({ph}) "
        f"AND change IS NOT NULL AND value IS NOT NULL",
        [sel, *TOP_WEIGHT_SYMBOLS],
    ).fetchone()
    h = conn.execute(
        "SELECT SUM(SIGN(change)*value)/NULLIF(SUM(value),0) FROM ("
        "  SELECT change, value FROM stock_day WHERE market='TWSE' AND trade_date = ? "
        "  AND change IS NOT NULL AND value IS NOT NULL ORDER BY value DESC LIMIT 20)",
        [sel],
    ).fetchone()
    if w is None or w[0] is None or h is None or h[0] is None:
        return None
    W, H = float(w[0]), float(h[0])

    dl = _WL[0] * W + _WL[1] * H + _WL[2] * B
    ds = _WS[0] * W + _WS[1] * H + _WS[2] * B
    return {
        "W": round(W, 3), "H": round(H, 3), "B": round(B, 3),
        "dci_long": round(dl, 3), "dci_short": round(ds, 3),
        "regime_long": _band_long(dl), "regime_short": _band_short(ds),
    }
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/chart_ui/test_dci_daily.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add src/chart_ui/services/dci_daily.py tests/chart_ui/test_dci_daily.py
git commit -m "feat(chart-ui): dci_daily 當日 DCI 計算(收盤/事後)"
```

---

### Task 2: `_exit_advice` 建議出場法（純函式）

**Files:**
- Modify: `src/chart_ui/services/daystats.py`（新增 `_hhmm`、`_exit_advice`）
- Test: `tests/chart_ui/test_exit_advice.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/chart_ui/test_exit_advice.py
from src.chart_ui.services.daystats import _exit_advice


def test_strong_regime_early_l1_holds_l3():
    # 多, 09:25(565)碰L1, 強regime
    s = _exit_advice({"L1": 565}, "strong", "多")
    assert "碰L1" in s and "瞄L3抱BE" in s


def test_mid_regime_late_l1_collects_l2():
    # 多, 09:40(580)碰L1(晚於09:30), 中regime, 未碰L2
    s = _exit_advice({"L1": 580}, "mid", "多")
    assert "收L2" in s


def test_mid_regime_early_l2_trails():
    # 多, 碰L1 565 + 碰L2 610(早於10:45), 中regime
    s = _exit_advice({"L1": 565, "L2": 610}, "mid", "多")
    assert "碰L2" in s and "trail博L3" in s


def test_weak_regime_l2_holds():
    s = _exit_advice({"L1": 565, "L2": 610}, "weak", "多")
    assert "守L2" in s


def test_no_l1_touch():
    assert _exit_advice({}, "mid", "多") == "多(中)：未碰 L1"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/chart_ui/test_exit_advice.py -v`
Expected: FAIL（`ImportError: cannot import name '_exit_advice'`）

- [ ] **Step 3: 在 daystats.py 新增（放在 `_cont_lookup` 之後）**

```python
_GATE_0930, _GATE_1045 = 570, 645
_BAND_LABEL = {"strong": "強", "mid": "中", "weak": "弱"}


def _hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _exit_advice(touches: dict, band: str, side: str) -> str:
    """依觸及時間 + 時間閘 + EOD regime 產生建議出場字串（覆盤用，事後 regime）。"""
    bl = _BAND_LABEL.get(band, band)
    t1, t2, t3 = touches.get("L1"), touches.get("L2"), touches.get("L3")
    if t1 is None:
        return f"{side}({bl})：未碰 L1"
    parts = []
    aim1 = "瞄L3抱BE" if (band == "strong" or t1 < _GATE_0930) else "收L2(BE)"
    parts.append(f"{_hhmm(t1)}碰L1→{aim1}")
    if t2 is not None:
        if band == "strong":
            act2 = "靜態抱L3,可放L4"
        elif band == "weak":
            act2 = "守L2/快收"
        elif t2 < _GATE_1045:
            act2 = "trail博L3"
        else:
            act2 = "守L2"
        parts.append(f"{_hhmm(t2)}碰L2→{act2}")
    if t3 is not None:
        parts.append(f"{_hhmm(t3)}碰L3→" + ("寬trail博L4" if band == "strong" else "trail收割"))
    return f"{side}({bl})：" + "；".join(parts)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/chart_ui/test_exit_advice.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add src/chart_ui/services/daystats.py tests/chart_ui/test_exit_advice.py
git commit -m "feat(chart-ui): _exit_advice 依觸及+regime 產生建議出場法"
```

---

### Task 3: `_collect_touches`（到 L3）+ daystats payload 串接

**Files:**
- Modify: `src/chart_ui/services/daystats.py`
- Test: `tests/chart_ui/test_collect_touches.py`

- [ ] **Step 1: 寫失敗測試（用既有 ohlcv_1m fixture）**

```python
# tests/chart_ui/test_collect_touches.py
import duckdb
from datetime import date
from src.chart_ui.services.daystats import _collect_touches


def test_collect_touches_bull_levels(test_db_path):
    con = duckdb.connect(str(test_db_path), read_only=True)
    # fixture 有 2025-06-17 日盤；用很小的距離確保多方各階都被觸及
    out = _collect_touches(con, date(2025, 6, 17), [("L1", 1.0), ("L2", 2.0), ("L3", 3.0)])
    con.close()
    assert "bull" in out and "bear" in out
    labels = [t["level"] for t in out["bull"]]
    assert labels == ["L1", "L2", "L3"]                 # 皆觸及
    assert all("price" in t and "time" in t for t in out["bull"])
    # 時間遞增（L1 ≤ L2 ≤ L3）
    mins = [t["minute"] for t in out["bull"]]
    assert mins == sorted(mins)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/chart_ui/test_collect_touches.py -v`
Expected: FAIL（`ImportError: _collect_touches`）

- [ ] **Step 3: 在 daystats.py 新增 `_collect_touches`**

```python
def _collect_touches(conn, sel, levels: list[tuple[str, float]]) -> dict:
    """各階(label, 距離) 多/空首次觸及。回傳 {bull:[{level,price,time,minute}], bear:[...]}。

    多方(上擺)從盤中低點往上、空方(下擺)從盤中高點往下，距離達到即記首觸（與 _level1_signals 同義）。
    price = 多方 base_low+距離 / 空方 base_high−距離（投射價）。
    """
    rows = conn.execute(
        "SELECT CAST(timestamp AS TIME) t, high, low FROM ohlcv_1m "
        "WHERE symbol = ? AND CAST(timestamp AS DATE) = ? "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' ORDER BY timestamp",
        [SYMBOL, sel],
    ).fetchall()
    out = {"bull": [], "bear": []}
    if not rows:
        return out
    run_lo, run_hi = float("inf"), float("-inf")
    up_max = dn_max = 0.0
    base_lo = float(rows[0][2])
    base_hi = float(rows[0][1])
    done_b, done_s = set(), set()
    for t, h, l in rows:
        h, l = float(h), float(l)
        run_lo, run_hi = min(run_lo, l), max(run_hi, h)
        up_max, dn_max = max(up_max, h - run_lo), max(dn_max, run_hi - l)
        m = t.hour * 60 + t.minute
        for label, dist in levels:
            if label not in done_b and up_max >= dist:
                done_b.add(label)
                out["bull"].append({"level": label, "price": round(run_lo + dist),
                                    "time": t.strftime("%H:%M"), "minute": m})
            if label not in done_s and dn_max >= dist:
                done_s.add(label)
                out["bear"].append({"level": label, "price": round(run_hi - dist),
                                    "time": t.strftime("%H:%M"), "minute": m})
    out["bull"].sort(key=lambda x: x["minute"])
    out["bear"].sort(key=lambda x: x["minute"])
    return out
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/chart_ui/test_collect_touches.py -v`
Expected: PASS（1 passed）

- [ ] **Step 5: 串接 payload — 修改 `compute_daystats`**

在 `compute_daystats` 內、`with duckdb.connect(...)` 區塊（算完 `ema20`、`level1` 後）加：

```python
            # 觸及（到 L3）+ DCI(收盤/事後) + 建議出場法
            touches = {"bull": [], "bear": []}
            dci = None
            exit_advice = None
            if ema20:
                lv = [(s, c * ema20) for s, _, c in LVL_QUANTILES[:3]]  # L1/L2/L3 距離
                lv = [("L1", lv[0][1]), ("L2", lv[1][1]), ("L3", lv[2][1])]
                touches = _collect_touches(conn, sel, lv)
                from src.chart_ui.services.dci_daily import compute_daily_dci
                dci = compute_daily_dci(conn, sel)
                if dci:
                    dci["hindsight"] = True
                    dci["w_proxy"] = True
                bmin = {t["level"]: t["minute"] for t in touches["bull"]}
                smin = {t["level"]: t["minute"] for t in touches["bear"]}
                bl = dci["regime_long"] if dci else "mid"
                bs = dci["regime_short"] if dci else "mid"
                exit_advice = {"bull": _exit_advice(bmin, bl, "多"),
                               "bear": _exit_advice(smin, bs, "空")}
```

注意：`LVL_QUANTILES` 元素為 `(序號, 達到率, 係數)`，序號是 `"1"/"2"/"3"`，故上方用 `("L1"...)` 重新標籤。

在 `return { ... }` 內新增三鍵：

```python
        "touches": touches,
        "dci": dci,
        "exit_advice": exit_advice,
```

- [ ] **Step 6: 對真實 DB 煙霧驗證 payload**

Run:
```bash
uv run python -c "from src.chart_ui.services.daystats import compute_daystats; import json; r=compute_daystats(date_str='2026-05-21'); print('dci', r['dci']); print('advice', r['exit_advice']); print('touches bull', r['touches']['bull'])"
```
Expected: `dci` 為含 regime 的 dict（非 None）、`exit_advice` 多/空各一字串、`touches` 有 L1/L2/L3 條目（視當日行情）。

- [ ] **Step 7: 跑既有測試確認無回歸**

Run: `uv run pytest tests/chart_ui -q`
Expected: PASS（含新測試、既有 chart_ui 測試）

- [ ] **Step 8: Commit**

```bash
git add src/chart_ui/services/daystats.py tests/chart_ui/test_collect_touches.py
git commit -m "feat(chart-ui): daystats 串接 touches(L3)/DCI/建議出場法 payload"
```

---

### Task 4: 前端右欄 DCI 區塊 + 建議出場法

**Files:**
- Modify: `src/chart_ui/static/app.js`（`renderDayStats` 內）
- Modify: `src/chart_ui/static/app.css`

- [ ] **Step 1: app.js 新增 `dciSec` 並插入右欄**

在 `renderDayStats` 內（`lvlSec` 定義之後、`el.innerHTML = ...` 之前）加：

```javascript
  // DCI 方向共識指標（收盤/事後）+ 建議出場法
  const dci = d.dci;
  const RB = { strong: ['🟥', '強'], mid: ['⬜', '中'], weak: ['🟦', '弱'] };
  let dciSec = '';
  if (dci) {
    const [li, ll] = RB[dci.regime_long] || ['', ''];
    const [si, sl] = RB[dci.regime_short] || ['', ''];
    dciSec =
      `<div class="sec"><div class="sec-title">DCI 方向共識<span class="n"> 事後·收盤</span></div>`
      + `<div class="kv"><span class="k">多 ${li}${ll}</span><span class="v">${dci.dci_long.toFixed(2)}</span></div>`
      + `<div class="kv"><span class="k">空 ${si}${sl}</span><span class="v">${dci.dci_short.toFixed(2)}</span></div>`
      + `<div class="kv"><span class="k n">W權值* / H熱門 / B家數</span>`
      + `<span class="v n">${dci.W.toFixed(2)} / ${dci.H.toFixed(2)} / ${dci.B.toFixed(2)}</span></div>`;
    if (d.exit_advice) {
      dciSec += `<div class="gap"></div>`
        + `<div class="advice">${d.exit_advice.bull}</div>`
        + `<div class="advice">${d.exit_advice.bear}</div>`;
    }
    dciSec += `</div>`;
  }
```

- [ ] **Step 2: 把 `dciSec` 接到 innerHTML**

把 `el.innerHTML = avgSec + wdSec + todaySec + nvSec + toSec + vixSec + lvlSec;`
改為：`el.innerHTML = avgSec + wdSec + todaySec + nvSec + toSec + vixSec + lvlSec + dciSec;`

- [ ] **Step 3: app.css 加樣式（檔尾）**

```css
.advice { font-size: 11px; line-height: 1.5; color: var(--fg, #ddd); padding: 1px 0; }
.sec-title .n { font-weight: normal; }
```

- [ ] **Step 4: 目視驗證**

Run: `uv run chart-ui`（瀏覽器開 http://127.0.0.1:8888/）
檢查：選一個交易日 → 右欄出現「DCI 方向共識(事後·收盤)」區塊，含多/空 DCI 值與分帶圖示、W/H/B 分項、下方多/空兩行建議出場法。`W權值*` 的星號代表近似權重。

- [ ] **Step 5: Commit**

```bash
git add src/chart_ui/static/app.js src/chart_ui/static/app.css
git commit -m "feat(chart-ui): 右欄 DCI 方向共識 + 建議出場法"
```

---

### Task 5: 主圖 `drawReviewOverlay`（關卡線 + 觸及 marker + 時間線）

**Files:**
- Modify: `src/chart_ui/static/app.js`

- [ ] **Step 1: 新增 `drawReviewOverlay(d)`（放在 `drawTradeMarkers` 之後）**

```javascript
// 覆盤 overlay：daystats 的關卡線 + 觸及 marker + 09:30/10:45 時間線。
// 與 drawTradeMarkers 共用 markerState.priceLines；intraday 才畫。
function drawReviewOverlay(d) {
  if (state.tf === '1d' || !chartState.candle) return;
  if (!d || (!d.bull && !d.bear)) return;
  // 關卡水平線：多紅系、空綠系（含今高/今低，已在 d.bull/d.bear 內）
  const line = (o, color) => chartState.candle.createPriceLine({
    price: +o.price, color, lineStyle: o.today ? 0 : 2, lineWidth: 1,
    axisLabelVisible: true, title: o.label || '',
  });
  for (const o of d.bull || []) markerState.priceLines.push(line(o, o.today ? '#888' : '#e0623d'));
  for (const o of d.bear || []) markerState.priceLines.push(line(o, o.today ? '#888' : '#3d9e6a'));
  // 觸及 marker
  const tm = [];
  for (const t of (d.touches && d.touches.bull) || []) tm.push({
    time: nearestBarTime(localToEpoch(`${d.date} ${t.time}:00`)), position: 'belowBar',
    shape: 'circle', color: '#e0623d', text: `多${t.level} ${t.time}`,
  });
  for (const t of (d.touches && d.touches.bear) || []) tm.push({
    time: nearestBarTime(localToEpoch(`${d.date} ${t.time}:00`)), position: 'aboveBar',
    shape: 'circle', color: '#3d9e6a', text: `空${t.level} ${t.time}`,
  });
  // 時間閘 09:30 / 10:45（以該根 K 的軸 marker 標示；垂直線 primitive 視版本另議）
  for (const hm of ['09:30', '10:45']) tm.push({
    time: nearestBarTime(localToEpoch(`${d.date} ${hm}:00`)), position: 'aboveBar',
    shape: 'arrowDown', color: '#888', text: hm,
  });
  if (tm.length) {
    tm.sort((a, b) => a.time - b.time);
    markerState.handle = markerState.handle
      ? (markerState.handle.setMarkers(tm), markerState.handle)
      : LightweightCharts.createSeriesMarkers(chartState.candle, tm);
  }
}
```

- [ ] **Step 2: 在 `renderDayStats` 末尾呼叫**

`renderDayStats(dateStr)` 取得 daystats 資料後（設好 `el.innerHTML` 之後），先清舊 overlay 再畫：

```javascript
  clearMarkers();
  drawReviewOverlay(d);
```

注意：`d` 需含 `date` 欄（payload 已有 `"date": date_str`）。若 `renderDayStats` 與 `drawTradeMarkers` 都會跑，確保覆盤 overlay 在選日期時呼叫、回測清單 marker 在選清單項時呼叫，兩者都先 `clearMarkers()`、不疊加。

- [ ] **Step 3: 目視驗證**

Run: `uv run chart-ui`
檢查：選交易日（intraday）→ 主圖出現多空 L1–L4 + 今高/今低 水平線（多紅空綠、今高低灰實線）、各階首次觸及的圓點 marker（標「多L2 10:10」）、09:30/10:45 灰色標記。切到日線(1d)不畫。切不同日期會更新、不殘留舊線。

- [ ] **Step 4: 跑全測試確認無回歸**

Run: `uv run pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chart_ui/static/app.js
git commit -m "feat(chart-ui): 主圖覆盤 overlay(關卡線/觸及marker/時間閘)"
```

---

## Self-Review

- **Spec coverage**：右欄 DCI+regime(Task1,4)、保留觸及提示(既有,未動)、建議出場法(Task2,4)、主圖關卡線/觸及marker/時間線(Task5)、dci_daily 模組(Task1)、daystats 擴充(Task3)、三個如實限制(事後標註 Task4、W 近似 Task1 常數註解+Task4 星號、時間線軸標記 fallback Task5) 皆有對應任務。
- **Placeholder scan**：無 TBD/TODO；所有 code/test step 附完整程式。
- **Type consistency**：`compute_daily_dci(conn, sel)` 回傳鍵(W/H/B/dci_long/dci_short/regime_long/regime_short) 於 Task3 串接、Task4 前端一致；`_exit_advice(touches, band, side)` 簽章 Task2 定義、Task3 呼叫一致；`_collect_touches` 回傳 `{bull,bear:[{level,price,time,minute}]}` Task3 定義、Task5 前端用 `level/price/time/today` 一致（`today` 來自 `d.bull/d.bear` 既有 ladder，非 touches）。
- **時間閘**：採軸 marker（版本安全）；spec 提的垂直線 primitive 列為未來增強，不阻塞。
