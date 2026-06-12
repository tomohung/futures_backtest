# Chart-UI 主圖「L3 波段」指標 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 chart-ui 主圖新增一個可開關的「L3 波段」指標，自動用斜線標出當日「起點在 11:30 前、幅度 ≥ L3」的所有單向 swing 波段，複盤理想最大行情。

**Architecture:** 後端新增獨立 service（純函式 ZigZag 波段偵測 + DB 整合層）與 route `/api/swing-legs`；L3 距離重用 `daystats.py` 既有的 EMA20 振幅函式。前端新增一個指標 toggle 與一個 lightweight-charts Primitive，在主圖 canvas 上自繪斜線與幅度標註，沿用既有 `touchLinesPrimitive` 模式。

**Tech Stack:** Python 3.14 / DuckDB / FastAPI / pytest（後端）；vanilla JS + lightweight-charts v5（前端）。

---

## File Structure

| 檔案 | 動作 | 職責 |
|---|---|---|
| `src/chart_ui/services/swing_legs.py` | 建立 | 純函式 ZigZag 波段偵測 + DB 整合（讀日盤 K、算 L3、篩選） |
| `src/chart_ui/routes/swing_legs.py` | 建立 | `GET /api/swing-legs?date=` route |
| `src/chart_ui/app.py` | 修改 | 註冊新 router |
| `tests/chart_ui/test_swing_legs.py` | 建立 | 純函式單元測試 + 整合測試 |
| `tests/chart_ui/test_swing_legs_route.py` | 建立 | route 參數驗證 smoke test |
| `src/chart_ui/static/app.js` | 修改 | state toggle、Primitive、載入與繪製、legend、事件綁定 |

ZigZag 核心抽成不依賴 DB 的純函式 `zigzag_legs()`，讓波段邏輯能完整 TDD；DB 與篩選包在 `compute_swing_legs()`。

---

## 演算法定義（ZigZag，反轉門檻 = L3 距離）

純函式 `zigzag_legs(bars, threshold)`：

- **輸入**：`bars` = `[(minute:int, high:float, low:float), ...]`，已按時間昇冪排序；`threshold:float`（= L3 距離）。`minute` = 當日分鐘數（08:45 = 525）。
- **輸出**：`legs` = `[{"start_min", "start_price", "end_min", "end_price", "dir"}]`，`dir ∈ {"up","down"}`。

狀態機：
- `trend = None` 時，同時追蹤起點以來的 running low（`up_ref`，上漲基準）與 running high（`dn_ref`，下跌基準）。當 `high - up_ref ≥ threshold` 先成立 → 確立 `up`，第一個 pivot = 那個 low；否則 `dn_ref - low ≥ threshold` 成立 → 確立 `down`，第一個 pivot = 那個 high。
- `trend == "up"`：續創高就更新極值 `ext`；當 `ext - low ≥ threshold`（從高點回落門檻）→ 把 `ext` 記為 H pivot，轉 `down`。
- `trend == "down"`：對稱處理。
- **收尾**：把最後的 `ext` 當一個暫定 pivot（未確認反轉），讓最後一段也能輸出。

相鄰 pivot 組成 leg；`L→H` 為 up、`H→L` 為 down。`amplitude = abs(end_price - start_price)`。

`compute_swing_legs()` 的**篩選**：保留 `start_min < 690`（11:30 前起點）**且** `amplitude ≥ threshold` 的 leg。後者會自然濾掉收尾那段不足 L3 的暫定波段（對應 spec「淨幅 < L3 不標」），也濾掉中間偶發的小鋸齒段。

---

## Task 1: ZigZag 純函式 — 單一上漲波段

**Files:**
- Create: `src/chart_ui/services/swing_legs.py`
- Test: `tests/chart_ui/test_swing_legs.py`

- [ ] **Step 1: 寫 failing test**

```python
# tests/chart_ui/test_swing_legs.py
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/chart_ui/test_swing_legs.py::test_single_up_leg -v`
Expected: FAIL（`ModuleNotFoundError` 或 `ImportError: cannot import name 'zigzag_legs'`）

- [ ] **Step 3: 寫最小實作**

```python
# src/chart_ui/services/swing_legs.py
"""主圖「L3 波段」：當日 11:30 前起點、幅度 ≥ L3 的單向 swing 波段偵測。

zigzag_legs 為不依賴 DB 的純函式（反轉門檻 = L3 距離）；compute_swing_legs 包 DB
整合（讀日盤 1 分 K、重用 daystats 的 EMA20 振幅算 L3、篩選起點 < 11:30 且幅度 ≥ L3）。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

from src.chart_ui import paths
from src.chart_ui.services.daystats import LVL_QUANTILES, SYMBOL, _ema20_range

NOON_MIN = 690          # 11:30（起點時間閘）
L3_COEF = LVL_QUANTILES[2][2]  # 0.711 × EMA20


def zigzag_legs(bars, threshold):
    """ZigZag 波段偵測，反轉門檻 = threshold。

    bars: [(minute, high, low), ...] 已按時間昇冪。threshold: 反轉/幅度門檻。
    回傳 [{start_min, start_price, end_min, end_price, dir}]，dir ∈ {'up','down'}。
    收尾會把最後未確認反轉的極值當暫定 pivot 輸出（幅度篩選由呼叫端負責）。
    """
    if len(bars) < 2:
        return []
    first_min, first_h, first_l = bars[0]
    up_ref_min, up_ref = first_min, first_l   # 上漲基準（running low）
    dn_ref_min, dn_ref = first_min, first_h   # 下跌基準（running high）
    trend = None
    ext_min = ext = None
    pivots = []  # (minute, price, kind) kind ∈ {'L','H'}
    for m, h, l in bars:
        if trend is None:
            if l < up_ref:
                up_ref_min, up_ref = m, l
            if h > dn_ref:
                dn_ref_min, dn_ref = m, h
            if h - up_ref >= threshold:
                trend = "up"
                pivots.append((up_ref_min, up_ref, "L"))
                ext_min, ext = m, h
            elif dn_ref - l >= threshold:
                trend = "down"
                pivots.append((dn_ref_min, dn_ref, "H"))
                ext_min, ext = m, l
        elif trend == "up":
            if h > ext:
                ext_min, ext = m, h
            elif ext - l >= threshold:
                pivots.append((ext_min, ext, "H"))
                trend = "down"
                ext_min, ext = m, l
        else:  # down
            if l < ext:
                ext_min, ext = m, l
            elif h - ext >= threshold:
                pivots.append((ext_min, ext, "L"))
                trend = "up"
                ext_min, ext = m, h
    if trend is not None:
        pivots.append((ext_min, ext, "H" if trend == "up" else "L"))

    legs = []
    for (sm, sp, _sk), (em, ep, _ek) in zip(pivots, pivots[1:]):
        legs.append({
            "start_min": sm, "start_price": sp,
            "end_min": em, "end_price": ep,
            "dir": "up" if ep >= sp else "down",
        })
    return legs
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/chart_ui/test_swing_legs.py::test_single_up_leg -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chart_ui/services/swing_legs.py tests/chart_ui/test_swing_legs.py
git commit -m "feat(chart-ui): add zigzag_legs pure function for L3 swing detection"
```

---

## Task 2: ZigZag 純函式 — 雙向多段與鋸齒過濾

**Files:**
- Modify: `src/chart_ui/services/swing_legs.py`（必要時微調，預期不需改）
- Test: `tests/chart_ui/test_swing_legs.py`

- [ ] **Step 1: 寫 failing tests**

```python
# tests/chart_ui/test_swing_legs.py（append）
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
```

- [ ] **Step 2: 跑測試確認失敗或通過**

Run: `uv run pytest tests/chart_ui/test_swing_legs.py -v`
Expected: 兩個新測試 PASS（Task 1 實作已涵蓋；若 FAIL 則修 `zigzag_legs` 直到通過，勿改測試的預期值）

- [ ] **Step 3: 若有需要才修實作**

僅在 Step 2 失敗時調整 `zigzag_legs`。預期不需改動。

- [ ] **Step 4: 跑全檔測試**

Run: `uv run pytest tests/chart_ui/test_swing_legs.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add tests/chart_ui/test_swing_legs.py src/chart_ui/services/swing_legs.py
git commit -m "test(chart-ui): cover bidirectional legs and sub-threshold wiggle merge"
```

---

## Task 3: compute_swing_legs — DB 整合與篩選

**Files:**
- Modify: `src/chart_ui/services/swing_legs.py`
- Test: `tests/chart_ui/test_swing_legs.py`

- [ ] **Step 1: 寫 failing test（純函式層級的篩選 + 終點欄位）**

先加一個對「篩選與輸出欄位」可單測的純函式 `_filter_and_format`，避免依賴真實 DB。

```python
# tests/chart_ui/test_swing_legs.py（append）
from src.chart_ui.services.swing_legs import _filter_and_format


def test_filter_drops_late_start_and_short_amp():
    raw = [
        {"start_min": 600, "start_price": 100, "end_min": 700, "end_price": 180, "dir": "up"},   # 保留
        {"start_min": 700, "start_price": 180, "end_min": 720, "end_price": 100, "dir": "down"},  # 起點 700>=690 → 丟
        {"start_min": 650, "start_price": 100, "end_min": 660, "end_price": 130, "dir": "up"},    # 幅度 30<50 → 丟
    ]
    out = _filter_and_format(raw, threshold=50)
    assert len(out) == 1
    lg = out[0]
    assert lg["start_time"] == "10:00"   # 600 分（當日絕對分鐘）→ 10:00
    assert lg["end_time"] == "11:40"     # 700 分 → 11:40
    assert lg["dir"] == "up"
    assert lg["amp"] == 80               # 帶方向：up 為正
    assert lg["l3_mult"] == 1.6          # 80/50


def test_filter_amp_negative_for_down():
    raw = [{"start_min": 600, "start_price": 200, "end_min": 680, "end_price": 110, "dir": "down"}]
    out = _filter_and_format(raw, threshold=50)
    assert out[0]["amp"] == -90          # down 為負
    assert out[0]["l3_mult"] == 1.8
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/chart_ui/test_swing_legs.py::test_filter_drops_late_start_and_short_amp -v`
Expected: FAIL（`ImportError: cannot import name '_filter_and_format'`）

- [ ] **Step 3: 實作 `_filter_and_format` 與 `compute_swing_legs`**

在 `swing_legs.py` append：

```python
def _min_to_hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _filter_and_format(raw_legs, threshold):
    """篩選 start_min < 11:30 且 abs(amp) ≥ threshold，並格式化輸出。

    amp 帶方向（up 正 / down 負）；l3_mult = round(abs(amp)/threshold, 1)。
    """
    out = []
    for lg in raw_legs:
        if lg["start_min"] >= NOON_MIN:
            continue
        amp_abs = abs(lg["end_price"] - lg["start_price"])
        if amp_abs < threshold:
            continue
        amp = round(lg["end_price"] - lg["start_price"])
        out.append({
            "start_time": _min_to_hhmm(lg["start_min"]),
            "start_price": round(lg["start_price"]),
            "end_time": _min_to_hhmm(lg["end_min"]),
            "end_price": round(lg["end_price"]),
            "dir": lg["dir"],
            "amp": amp,
            "l3_mult": round(amp_abs / threshold, 1),
        })
    return out


def _day_bars(conn, sel: date):
    """當日日盤 1 分 K：[(minute, high, low)]，08:45–13:45，昇冪。"""
    rows = conn.execute(
        "SELECT CAST(timestamp AS TIME) t, high, low FROM ohlcv_1m "
        "WHERE symbol = ? AND CAST(timestamp AS DATE) = ? "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "ORDER BY timestamp",
        [SYMBOL, sel],
    ).fetchall()
    return [(t.hour * 60 + t.minute, float(h), float(l)) for t, h, l in rows]


def compute_swing_legs(*, date_str: str, db_path: Path | None = None) -> dict:
    """回傳 {legs:[...], l3_dist, ema20}。ema20 不足 20 日時 legs 為空。"""
    db_path = Path(db_path) if db_path else paths.DUCKDB_PATH
    sel = date.fromisoformat(date_str)
    with duckdb.connect(str(db_path), read_only=True) as conn:
        ema20 = _ema20_range(conn, sel)
        if not ema20:
            return {"legs": [], "l3_dist": None, "ema20": None}
        l3_dist = L3_COEF * ema20
        bars = _day_bars(conn, sel)
    raw = zigzag_legs(bars, threshold=l3_dist)
    return {
        "legs": _filter_and_format(raw, threshold=l3_dist),
        "l3_dist": round(l3_dist, 1),
        "ema20": round(ema20, 1),
    }
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/chart_ui/test_swing_legs.py -v`
Expected: 全 PASS

- [ ] **Step 5: 加整合 smoke test（fixture DB，ema20 不足 → 空 legs）**

fixture 只有 2 天日盤，`_ema20_range` 需 20 日 → 回 None，因此 legs 為空但結構正確。

```python
# tests/chart_ui/test_swing_legs.py（append）
from datetime import date
from src.chart_ui.services.swing_legs import compute_swing_legs


def test_compute_swing_legs_insufficient_history(test_db_path):
    out = compute_swing_legs(date_str="2025-06-17", db_path=test_db_path)
    assert out["legs"] == []
    assert out["ema20"] is None
    assert out["l3_dist"] is None
```

- [ ] **Step 6: 跑測試確認通過**

Run: `uv run pytest tests/chart_ui/test_swing_legs.py -v`
Expected: 全 PASS

- [ ] **Step 7: Commit**

```bash
git add src/chart_ui/services/swing_legs.py tests/chart_ui/test_swing_legs.py
git commit -m "feat(chart-ui): compute_swing_legs DB integration with 11:30/L3 filter"
```

---

## Task 4: Route `/api/swing-legs`

**Files:**
- Create: `src/chart_ui/routes/swing_legs.py`
- Modify: `src/chart_ui/app.py:8`（import）、`src/chart_ui/app.py:39`（include_router）
- Test: `tests/chart_ui/test_swing_legs_route.py`

- [ ] **Step 1: 寫 failing test**

```python
# tests/chart_ui/test_swing_legs_route.py
from fastapi.testclient import TestClient

from src.chart_ui.app import create_app


def test_swing_legs_requires_date():
    client = TestClient(create_app())
    r = client.get("/api/swing-legs")
    assert r.status_code == 422  # 缺 required query


def test_swing_legs_bad_date():
    client = TestClient(create_app())
    r = client.get("/api/swing-legs?date=not-a-date")
    assert r.status_code == 400
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/chart_ui/test_swing_legs_route.py -v`
Expected: FAIL（route 未掛 → 422 那條可能過，但 bad date 會得 404 → FAIL）

- [ ] **Step 3: 建立 route**

```python
# src/chart_ui/routes/swing_legs.py
"""/api/swing-legs route：當日 11:30 前起點、幅度 ≥ L3 的 swing 波段。"""

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from src.chart_ui.services.swing_legs import compute_swing_legs

router = APIRouter(prefix="/api/swing-legs", tags=["swing-legs"])


@router.get("")
def get_swing_legs(d: str = Query(..., alias="date")):
    try:
        date.fromisoformat(d)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")
    return compute_swing_legs(date_str=d)
```

- [ ] **Step 4: 在 app.py 註冊 router**

`src/chart_ui/app.py` 第 8 行 import 改為（加入 `swing_legs`）：

```python
from src.chart_ui.routes import daystats, extension, kline, lists, risklevels, swing_legs
```

在第 39 行 `app.include_router(extension.router)` 之後加一行：

```python
    app.include_router(swing_legs.router)
```

- [ ] **Step 5: 跑測試確認通過**

Run: `uv run pytest tests/chart_ui/test_swing_legs_route.py -v`
Expected: 全 PASS

- [ ] **Step 6: 跑整個 chart_ui 測試確認無回歸**

Run: `uv run pytest tests/chart_ui/ -v`
Expected: 全 PASS

- [ ] **Step 7: Commit**

```bash
git add src/chart_ui/routes/swing_legs.py src/chart_ui/app.py tests/chart_ui/test_swing_legs_route.py
git commit -m "feat(chart-ui): add /api/swing-legs route"
```

---

## Task 5: 前端 — state、Primitive renderer

**Files:**
- Modify: `src/chart_ui/static/app.js`

> 前端無 JS 測試框架（專案慣例），本任務以實作 + Task 8 目視驗證把關。

- [ ] **Step 1: 加 state flag**

在 `app.js` 第 101 行 `indRisk:` 那行之後加入（預設關）：

```javascript
  indL3Legs: localStorage.getItem('cu.indL3Legs') === '1', // L3 波段斜線（理想最大行情，預設關）
```

- [ ] **Step 2: 加 Primitive 與 renderer**

在 `app.js` 第 1334 行 `touchLinesPrimitive` 區塊之後加入：

```javascript
// === L3 波段斜線（primitive；自繪斜線連 swing 低/高點 + 幅度標註）===
let l3LegReqUpdate = null;
const _l3LegRenderer = {
  draw(target) {
    if (state.tf === '1d' || !state.indL3Legs) return;
    const chart = chartState.chart;
    const series = chartState.candle;
    const legs = chartState.l3LegAnchors;
    if (!chart || !series || !legs || !legs.length) return;
    const ts = chart.timeScale();
    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      const hpr = scope.horizontalPixelRatio;
      const vpr = scope.verticalPixelRatio;
      ctx.save();
      ctx.lineWidth = Math.max(1, Math.round(2 * hpr));
      ctx.font = `${Math.round(11 * vpr)}px -apple-system, sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      for (const lg of legs) {
        const x1 = ts.timeToCoordinate(lg.startTime);
        const y1 = series.priceToCoordinate(lg.startPrice);
        const x2 = ts.timeToCoordinate(lg.endTime);
        const y2 = series.priceToCoordinate(lg.endPrice);
        if (x1 == null || y1 == null || x2 == null || y2 == null) continue;
        const color = lg.dir === 'up' ? COLORS.up : COLORS.down;
        const px1 = x1 * hpr, py1 = y1 * vpr, px2 = x2 * hpr, py2 = y2 * vpr;
        ctx.strokeStyle = color;
        ctx.beginPath();
        ctx.moveTo(px1, py1);
        ctx.lineTo(px2, py2);
        ctx.stroke();
        // 端點小圓
        for (const [cx, cy] of [[px1, py1], [px2, py2]]) {
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(cx, cy, 3 * vpr, 0, Math.PI * 2);
          ctx.fill();
        }
        // 中點標註：幅度點數 + L3 倍數（如 +182 1.4×）
        const sign = lg.amp > 0 ? '+' : '';
        const label = `${sign}${lg.amp}  ${lg.mult}×`;
        const mx = (px1 + px2) / 2, my = (py1 + py2) / 2;
        ctx.fillStyle = color;
        ctx.fillText(label, mx, my - 10 * vpr);
      }
      ctx.restore();
    });
  },
};
const _l3LegPaneView = { renderer() { return _l3LegRenderer; }, zOrder() { return 'top'; } };
const l3LegsPrimitive = {
  attached(p) { l3LegReqUpdate = p.requestUpdate; },
  detached() { l3LegReqUpdate = null; },
  updateAllViews() {},
  paneViews() { return [_l3LegPaneView]; },
};
```

- [ ] **Step 3: attach primitive**

在 `app.js` 第 647 行 `chartState.candle.attachPrimitive(touchLinesPrimitive);` 之後加入：

```javascript
  chartState.candle.attachPrimitive(l3LegsPrimitive);          // L3 波段斜線
```

- [ ] **Step 4: 啟動 app 確認無 JS 錯誤**

Run: `uv run chart-ui`（背景啟動後）開啟 `http://127.0.0.1:8888/`，開瀏覽器 console 確認無紅字錯誤，然後關閉。
Expected: 頁面正常載入，無 console error（此時尚無波段資料、不會畫東西）。

- [ ] **Step 5: Commit**

```bash
git add src/chart_ui/static/app.js
git commit -m "feat(chart-ui): add L3 swing-legs primitive renderer (state + draw)"
```

---

## Task 6: 前端 — 載入波段資料與繪製函式

**Files:**
- Modify: `src/chart_ui/static/app.js`

- [ ] **Step 1: 加 `applyL3Legs` 與 `loadSwingLegs`**

在 `app.js` 第 225 行 `applyTouchMarkers` 函式（結尾 `}`）之後加入：

```javascript
// L3 波段：把 /api/swing-legs 的 legs 轉成 anchors（時間對齊 bar）並觸發重畫。
function applyL3Legs() {
  const bars = chartState.bars;
  const legs = chartState._l3LegsRaw;
  const anchors = [];
  if (state.indL3Legs && state.tf !== '1d' && legs && bars && bars.length) {
    const d = window._dayStats;
    const day = d && d.date;
    for (const lg of legs) {
      if (!day) continue;
      const st = nearestBarTime(localToEpoch(`${day} ${lg.start_time}:00`));
      const et = nearestBarTime(localToEpoch(`${day} ${lg.end_time}:00`));
      if (st == null || et == null) continue;
      anchors.push({
        startTime: st, startPrice: lg.start_price,
        endTime: et, endPrice: lg.end_price,
        dir: lg.dir, amp: lg.amp, mult: lg.l3_mult,
      });
    }
  }
  chartState.l3LegAnchors = anchors;
  if (l3LegReqUpdate) l3LegReqUpdate();
}

async function loadSwingLegs(date) {
  chartState._l3LegsRaw = null;
  if (date && state.tf !== '1d') {
    try {
      const r = await fetchJSON(`/api/swing-legs?date=${encodeURIComponent(date)}`);
      chartState._l3LegsRaw = (r && r.legs) || [];
    } catch (_) { chartState._l3LegsRaw = []; }
  }
  applyL3Legs();
}
```

- [ ] **Step 2: 在 daystats 載入後觸發**

在 `app.js` 第 1661 行 `applyTouchMarkers();` 之後加入：

```javascript
  loadSwingLegs(date);
```

- [ ] **Step 3: 啟動 app 開啟一個有足夠歷史的交易日確認斜線出現**

Run: `uv run chart-ui`，開 `http://127.0.0.1:8888/`，從『所有交易日』清單點一個近期交易日（需 ≥ 20 日歷史，例如 2026-06-11），切到 intraday（非日線）。先暫時手動把 `state.indL3Legs` 開啟驗證：瀏覽器 console 執行 `state.indL3Legs = true; applyL3Legs();`。
Expected: 主圖出現 ≥ L3 的斜線（漲紅跌綠）+ `+點數 倍數×` 標註；起點都在 11:30 前。對照右側欄 L3 距離數值合理。

- [ ] **Step 4: Commit**

```bash
git add src/chart_ui/static/app.js
git commit -m "feat(chart-ui): load /api/swing-legs and render L3 legs on day change"
```

---

## Task 7: 前端 — legend toggle 與事件綁定

**Files:**
- Modify: `src/chart_ui/static/app.js`

- [ ] **Step 1: legend 加一行 toggle**

在 `app.js` 第 1066 行（`indTouch` 的三元運算結束）之後、第 1067 行 `const maLine` 之前，加入：

```javascript
    const indL3 = state.indL3Legs
      ? `<span class="ind-toggle" data-toggle="l3legs" style="color:${COLORS.up}">L3 波段</span>`
      : `<span class="ind-toggle ma-off" data-toggle="l3legs">L3 波段</span>`;
```

並把第 1068 行的 `indLine` 結尾接上 `indL3`（在 `${indRisk}` 之後）：

```javascript
    const indLine = `${ind5}　${indMa600}<br>${indV}<br>${pvw}<br>${indBB}<br>${indPiv}<br>${indOrb}<br>${indTouch}<br>${indRisk}<br>${indL3}`;
```

- [ ] **Step 2: wireIndicatorToggles 加分支**

在 `app.js` 第 1607 行 `risk` 分支的 `}` 之後（`else if (which === 'risk') {...}` 區塊結束）加入：

```javascript
      } else if (which === 'l3legs') {
        state.indL3Legs = !state.indL3Legs;
        localStorage.setItem('cu.indL3Legs', state.indL3Legs ? '1' : '0');
        applyL3Legs();
        updateLegend(null);
```

- [ ] **Step 3: 啟動 app 點 legend toggle 驗證開關**

Run: `uv run chart-ui`，開頁面選一個近期交易日（intraday）。
Expected:
- legend 出現「L3 波段」一行，亮色=開、灰色=關。
- 點它可切換主圖斜線的顯示/隱藏。
- 重整頁面後狀態（localStorage）保留。
- 切到日線（1d）時不畫斜線。

- [ ] **Step 4: Commit**

```bash
git add src/chart_ui/static/app.js
git commit -m "feat(chart-ui): wire L3 swing-legs legend toggle"
```

---

## Task 8: 端到端目視驗證與微調

**Files:**
- Modify: `src/chart_ui/static/app.js`（僅在需要微調時）

- [ ] **Step 1: 全測試回歸**

Run: `uv run pytest tests/chart_ui/ -v`
Expected: 全 PASS

- [ ] **Step 2: 多日目視抽查**

Run: `uv run chart-ui`，抽查 3 個不同型態的交易日（單邊大趨勢日 / 雙向震盪日 / 小波動日）：
- 大趨勢日：應有 1 條很長的斜線、倍數可能 ≥ 2×。
- 雙向日：多條漲綠跌紅交錯，皆 ≥ L3。
- 小波動日：可能 0 條（全日未達 L3）→ 主圖乾淨、無報錯。
確認所有斜線起點都 < 11:30；標註方向符號正確（漲 +、跌 −）；漲紅跌綠符合台灣慣例。

- [ ] **Step 3: 微調（如有需要）**

若標註重疊難讀、線太細/太粗、端點圓點太大，調整 `_l3LegRenderer` 的 `lineWidth` / `font` / 標註 y 偏移。每次微調後重整頁面確認。

- [ ] **Step 4: Final commit**

```bash
git add src/chart_ui/static/app.js
git commit -m "polish(chart-ui): tune L3 swing-legs rendering after visual review"
```

---

## Self-Review

**Spec coverage：**
- 任意 swing 波段 / ZigZag(反轉門檻=L3) → Task 1–2（`zigzag_legs`）✓
- L3 距離 = 0.711×EMA20、重用 daystats → Task 3（`L3_COEF`、`_ema20_range`）✓
- 起點 < 11:30 篩選 → Task 3（`NOON_MIN`、`_filter_and_format`）✓
- 終點可延伸到下午 → 演算法不限制 end_min，僅篩 start_min ✓
- 邊界：最後一段未反轉畫到極值、淨幅<L3 不標 → Task 1 收尾 pivot + Task 3 `amp_abs < threshold` 篩除 ✓
- ≥L3 全畫、L4/L5 自然包含、倍數反映大小 → `l3_mult` 輸出 ✓
- 後端獨立 service + route → Task 3、4 ✓
- 前端 toggle「L3 波段」、Primitive 斜線、漲紅跌綠、點數+倍數標註、切日重抓 → Task 5–7 ✓
- 只看日盤 → `_day_bars` 限 08:45–13:45 ✓

**Placeholder scan：** 無 TBD/TODO；每個 code step 均含完整程式碼 ✓

**Type consistency：**
- service 輸出鍵：`start_time/start_price/end_time/end_price/dir/amp/l3_mult`（Task 3）= 前端 `loadSwingLegs` 讀取的鍵（Task 6）✓
- 前端 anchor 鍵：`startTime/startPrice/endTime/endPrice/dir/amp/mult`（Task 6 產生）= `_l3LegRenderer` 讀取（Task 5）✓
- `l3LegReqUpdate` 定義（Task 5）與使用（Task 5/6）一致 ✓
- toggle key `'l3legs'`（legend Task 7 / wire Task 7）一致；localStorage key `'cu.indL3Legs'`（state Task 5 / wire Task 7）一致 ✓
