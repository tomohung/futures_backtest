# Chart UI 1h K + MACD 參考圖 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 chart-ui 左側 sidebar 下方加一張唯讀的 1 小時 K + MACD 參考圖,固定含夜盤,跟著主圖日期更新。

**Architecture:** 純前端改動(`index.html` / `app.css` / `app.js`),後端 `/api/kline` 已支援 `tf=60m`、`session=full`、`from`/`to`,完全不動。mini 圖用獨立 `miniChartState`,單一 lightweight-charts 實例 + 2 panes(candle pane 0、MACD pane 1),與主圖 `chartState` 完全隔離。主圖 `loadKline()` 結尾呼叫 `loadMiniChart()` 達成日期/adjust 連動。

**Tech Stack:** Vanilla JS ES module、lightweight-charts v5(standalone)、FastAPI(後端不改)。

**測試策略說明:** 本專案前端為瀏覽器 ES module,無 JS 測試框架。純函式 MACD 數學用 `node` 直接驗證(真實自動化測試);UI 行為用 `uv run chart-ui` 啟動後的瀏覽器手動驗收(每步附明確預期)。不為此功能引入 JS 測試框架(超出需求範圍)。

**與 spec 的差異(已確認的精煉):**
- spec 寫「兩個 lightweight-charts 實例」→ 改為「單一實例 + 2 panes」,讓 K 與 MACD 共用時間軸自動對齊(沿用主圖 volume pane 的既有模式)。HTML 因此只需一個 `#mini-chart` div,不需 `#mini-macd`。
- 預設可見範圍:最近約 60 根 1h K(含夜盤 ≈ 3 個交易日)。280px 寬塞不下 spec 估的 6~8 天全日盤 1h K(一天約 19 根),故載入 14 日曆天資料但預設只顯示最近 60 根,可手動往左拖看更早。

---

## File Structure

- `src/chart_ui/static/index.html` — 在 sidebar 內 `list-table` 之後加 `.mini-wrap` 容器(label + `#mini-chart`)。
- `src/chart_ui/static/app.css` — 加 `.mini-wrap` / `.mini-title` / `#mini-chart` 樣式;`list-table` 維持 `flex:1`(已是)。
- `src/chart_ui/static/app.js` — 加 `ema()`、`computeMACD()`(純函式)、`miniChartState`、`initMiniChart()`、`miniRangeFrom()`、`loadMiniChart()`;在 `main()` 呼叫 `initMiniChart()`;在 `loadKline()` 結尾呼叫 `loadMiniChart()`。

後端無檔案異動。

---

## Task 1: HTML 容器 + CSS 版面

**Files:**
- Modify: `src/chart_ui/static/index.html`(sidebar 區塊,約 12-18 行)
- Modify: `src/chart_ui/static/app.css`(sidebar 相關,約 10-18 行)

- [ ] **Step 1: 在 sidebar 加入 mini 容器**

把 `src/chart_ui/static/index.html` 中這段:

```html
    <aside class="sidebar">
      <div class="list-picker">
        <select id="list-select"></select>
      </div>
      <div class="list-summary" id="list-summary"></div>
      <div class="list-table" id="list-table"></div>
    </aside>
```

改成:

```html
    <aside class="sidebar">
      <div class="list-picker">
        <select id="list-select"></select>
      </div>
      <div class="list-summary" id="list-summary"></div>
      <div class="list-table" id="list-table"></div>
      <div class="mini-wrap">
        <div class="mini-title">1H K + MACD（含夜盤）</div>
        <div id="mini-chart"></div>
      </div>
    </aside>
```

- [ ] **Step 2: 加 CSS 樣式**

在 `src/chart_ui/static/app.css` 的 `.list-table { ... }` 規則(約第 17 行)之後新增:

```css
.mini-wrap { flex: 0 0 auto; height: 260px; border-top: 1px solid var(--border);
  display: flex; flex-direction: column; }
.mini-title { color: var(--muted); font-size: 11px; letter-spacing: 0.05em;
  padding: 4px 10px; flex: 0 0 auto; }
#mini-chart { flex: 1; min-height: 0; width: 100%; }
```

- [ ] **Step 3: 啟動並驗證版面**

Run: `uv run chart-ui`
開啟 http://127.0.0.1:8888/
Expected: 左側 sidebar 最下方出現「1H K + MACD（含夜盤）」標題,下方一塊約 240px 高的空白區(尚未畫圖);上方清單表縮短、仍可捲動。主圖、右側 rail 不受影響。

- [ ] **Step 4: Commit**

```bash
git add src/chart_ui/static/index.html src/chart_ui/static/app.css
git commit -m "feat(chart-ui): sidebar 下方加入 1H K + MACD 參考圖容器與版面"
```

---

## Task 2: MACD 純函式(ema + computeMACD)

**Files:**
- Modify: `src/chart_ui/static/app.js`(在既有 `sma()` 函式約第 228 行之後新增)
- Test: 臨時檔 `/tmp/macd_test.mjs`(驗證後刪除,不進版控)

- [ ] **Step 1: 寫失敗測試**

建立 `/tmp/macd_test.mjs`:

```js
// 複製自 app.js 的 ema / computeMACD(實作完成後兩邊需一致)
function ema(values, period) {
  const out = [];
  const k = 2 / (period + 1);
  let prev = null;
  for (let i = 0; i < values.length; i++) {
    prev = prev == null ? values[i] : values[i] * k + prev * (1 - k);
    out[i] = prev;
  }
  return out;
}
function computeMACD(closes, fast = 12, slow = 26, signal = 9) {
  const emaFast = ema(closes, fast);
  const emaSlow = ema(closes, slow);
  const dif = closes.map((_, i) => emaFast[i] - emaSlow[i]);
  const dea = ema(dif, signal);
  const hist = dif.map((v, i) => v - dea[i]);
  return { dif, dea, hist };
}

// 測 1:常數序列 → DIF/DEA/hist 全 0
{
  const c = new Array(40).fill(100);
  const { dif, dea, hist } = computeMACD(c);
  console.assert(dif.length === 40 && dea.length === 40 && hist.length === 40, 'length 應等於輸入長度');
  console.assert(Math.abs(dif[39]) < 1e-9, '常數序列 DIF 末值應 ~0,實得 ' + dif[39]);
  console.assert(Math.abs(hist[39]) < 1e-9, '常數序列 hist 末值應 ~0,實得 ' + hist[39]);
}
// 測 2:ema 首值 = 輸入首值;單調遞增序列末段 DIF > 0(快線在慢線之上)
{
  const e = ema([10, 20, 30], 12);
  console.assert(e[0] === 10, 'ema 首值應等於輸入首值,實得 ' + e[0]);
  const up = Array.from({ length: 60 }, (_, i) => 100 + i);
  const { dif } = computeMACD(up);
  console.assert(dif[59] > 0, '遞增序列末端 DIF 應為正,實得 ' + dif[59]);
}
// 測 3:hist === dif - dea(逐項)
{
  const c = Array.from({ length: 50 }, (_, i) => 100 + Math.sin(i));
  const { dif, dea, hist } = computeMACD(c);
  let ok = true;
  for (let i = 0; i < c.length; i++) if (Math.abs(hist[i] - (dif[i] - dea[i])) > 1e-9) ok = false;
  console.assert(ok, 'hist 必須逐項等於 dif - dea');
}
console.log('MACD tests done');
```

- [ ] **Step 2: 跑測試確認目前（尚未實作 app.js 部分）測試檔可獨立通過**

Run: `node /tmp/macd_test.mjs`
Expected: 印出 `MACD tests done`,且無任何 `Assertion failed`。
(此步確認測試本身與 MACD 數學正確;Step 3 再把同一份函式植入 app.js。)

- [ ] **Step 3: 在 app.js 植入 ema 與 computeMACD**

在 `src/chart_ui/static/app.js` 的 `sma()` 函式(結尾在約第 228 行的 `}`)之後、`vwap` 註解之前,插入:

```js
// EMA（指數移動平均）；以首值為種子,逐根遞推。closes 皆為數字（無 null）。
function ema(values, period) {
  const out = [];
  const k = 2 / (period + 1);
  let prev = null;
  for (let i = 0; i < values.length; i++) {
    prev = prev == null ? values[i] : values[i] * k + prev * (1 - k);
    out[i] = prev;
  }
  return out;
}

// MACD（標準 12/26/9）→ {dif, dea, hist} 三個與 closes 等長的陣列。
function computeMACD(closes, fast = 12, slow = 26, signal = 9) {
  const emaFast = ema(closes, fast);
  const emaSlow = ema(closes, slow);
  const dif = closes.map((_, i) => emaFast[i] - emaSlow[i]);
  const dea = ema(dif, signal);
  const hist = dif.map((v, i) => v - dea[i]);
  return { dif, dea, hist };
}
```

- [ ] **Step 4: 確認 app.js 內外函式一致(語法檢查)**

Run: `node --check src/chart_ui/static/app.js`
Expected: 無輸出(語法正確)。
人工比對:app.js 的 `ema`/`computeMACD` 內容須與 `/tmp/macd_test.mjs` 內的定義逐字相同。

- [ ] **Step 5: 清理臨時測試檔**

Run: `rm /tmp/macd_test.mjs`
Expected: 無輸出。

- [ ] **Step 6: Commit**

```bash
git add src/chart_ui/static/app.js
git commit -m "feat(chart-ui): 加入 ema 與 computeMACD 純函式（12/26/9）"
```

---

## Task 3: mini 圖初始化(initMiniChart)

**Files:**
- Modify: `src/chart_ui/static/app.js`(在 `initChart()` 函式之後,約第 660 行附近的 `initChart` 結尾 `}` 之後新增;以及 `main()` 內,約第 1262 行)

- [ ] **Step 1: 新增 miniChartState 與 initMiniChart**

在 `src/chart_ui/static/app.js` 的 `initChart()` 函式結尾 `}` 之後新增(緊接其後):

```js
// ── 左側 1H K + MACD 參考圖（唯讀,獨立 state,固定含夜盤）──────────────────
const miniChartState = { chart: null, candle: null, dif: null, dea: null, hist: null };

function initMiniChart() {
  const el = document.getElementById('mini-chart');
  if (!el) return;
  const chart = LightweightCharts.createChart(el, {
    layout: { background: { color: '#0d0d0d' }, textColor: '#e0e0e0' },
    grid: { vertLines: { color: '#1a1a1a' }, horzLines: { color: '#1a1a1a' } },
    rightPriceScale: { borderColor: '#333' },
    timeScale: { borderColor: '#333', timeVisible: true, secondsVisible: false },
    localization: { timeFormatter: fmtAxisTime },
    crosshair: { mode: LightweightCharts.CrosshairMode.Hidden },
    handleScroll: false,           // 唯讀:停用拖曳捲動
    handleScale: false,            // 唯讀:停用縮放
    autoSize: true,
  });
  miniChartState.chart = chart;
  miniChartState.candle = chart.addSeries(LightweightCharts.CandlestickSeries, {
    upColor: COLORS.up, downColor: COLORS.down,
    borderUpColor: COLORS.up, borderDownColor: COLORS.down,
    wickUpColor: COLORS.wick, wickDownColor: COLORS.wick,
    priceLineVisible: false, lastValueVisible: false,
    priceFormat: { type: 'price', precision: 0, minMove: 1 },
  });
  // MACD 副圖（pane 1）:柱(漲紅跌綠) + DIF + DEA
  miniChartState.hist = chart.addSeries(
    LightweightCharts.HistogramSeries,
    { priceScaleId: 'macd', priceLineVisible: false, lastValueVisible: false },
    1,
  );
  miniChartState.dif = chart.addSeries(
    LightweightCharts.LineSeries,
    { color: COLORS.accent, lineWidth: 1, priceScaleId: 'macd',
      priceLineVisible: false, lastValueVisible: false },
    1,
  );
  miniChartState.dea = chart.addSeries(
    LightweightCharts.LineSeries,
    { color: '#6aa3ff', lineWidth: 1, priceScaleId: 'macd',
      priceLineVisible: false, lastValueVisible: false },
    1,
  );
}
```

- [ ] **Step 2: 在 main() 呼叫 initMiniChart**

在 `src/chart_ui/static/app.js` 的 `main()` 中,把:

```js
async function main() {
  initChart();
  wireToolbar();
```

改成:

```js
async function main() {
  initChart();
  initMiniChart();
  wireToolbar();
```

- [ ] **Step 3: 語法檢查**

Run: `node --check src/chart_ui/static/app.js`
Expected: 無輸出。

- [ ] **Step 4: 啟動驗證 mini 圖框架出現**

Run: `uv run chart-ui`(若已在跑則重新整理瀏覽器)
開啟 http://127.0.0.1:8888/
Expected: 左側 mini 區塊內出現空的圖表框架(上方 K 線 pane、下方 MACD pane、右側價格軸、底部時間軸),尚無資料。Console(F12)無錯誤。

- [ ] **Step 5: Commit**

```bash
git add src/chart_ui/static/app.js
git commit -m "feat(chart-ui): 初始化 mini 1H 圖（candle + MACD 雙 pane,唯讀）"
```

---

## Task 4: 載入資料 + MACD 連動(loadMiniChart + hook)

**Files:**
- Modify: `src/chart_ui/static/app.js`(在 Task 3 的 `initMiniChart()` 之後新增 `miniRangeFrom` / `loadMiniChart`;並在 `loadKline()` 結尾掛呼叫,約第 1136 行)

- [ ] **Step 1: 新增 miniRangeFrom 與 loadMiniChart**

在 `src/chart_ui/static/app.js` 的 `initMiniChart()` 函式結尾 `}` 之後新增:

```js
// center 日期往前 days 個日曆天,回傳 'YYYY-MM-DD'(mini 圖的 from 起點)。
function miniRangeFrom(centerDate, days) {
  const d = new Date(centerDate + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

// 載入 mini 1H 圖:固定 tf=60m、session=full(含夜盤),adjust 跟主圖;
// 區間 = [center-14 日曆天, center]。唯讀,失敗不影響主圖。
async function loadMiniChart(centerDate, adjust) {
  if (!miniChartState.chart || !centerDate) return;
  const p = new URLSearchParams({
    from: miniRangeFrom(centerDate, 14), to: centerDate,
    tf: '60m', session: 'full', adjust,
  });
  let bars;
  try {
    bars = await fetchJSON(`/api/kline?${p}`);
  } catch (e) {
    console.warn('mini 圖載入失敗:', e);            // 維持上一次內容,不丟給主圖
    return;
  }
  miniChartState.candle.setData(bars.map((b) => ({
    time: b.time, open: b.open, high: b.high, low: b.low, close: b.close,
  })));
  if (bars.length >= 26) {
    const closes = bars.map((b) => b.close);
    const { dif, dea, hist } = computeMACD(closes);
    miniChartState.dif.setData(bars.flatMap((b, i) => (dif[i] != null ? [{ time: b.time, value: dif[i] }] : [])));
    miniChartState.dea.setData(bars.flatMap((b, i) => (dea[i] != null ? [{ time: b.time, value: dea[i] }] : [])));
    miniChartState.hist.setData(bars.flatMap((b, i) => (hist[i] != null
      ? [{ time: b.time, value: hist[i], color: hist[i] >= 0 ? COLORS.up : COLORS.down }]
      : [])));
  } else {                                           // 資料不足以算 MACD → 留空,K 線照畫
    miniChartState.dif.setData([]);
    miniChartState.dea.setData([]);
    miniChartState.hist.setData([]);
  }
  // 預設顯示最近約 60 根 1H K(含夜盤 ≈ 3 個交易日);右側留 2 根 padding。
  const n = bars.length;
  miniChartState.chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - 60), to: n - 1 + 2 });
}
```

- [ ] **Step 2: 在 loadKline 結尾掛呼叫**

在 `src/chart_ui/static/app.js` 的 `loadKline()` 結尾,把:

```js
  focusTime(centerEpochToFocus);
  if (window._afterKline) window._afterKline();        // Task 10 掛 marker
  if (sessionReqUpdate) sessionReqUpdate();            // 觸發盤別分界線重畫
  updateLegend(null);                                  // 預設顯示最新一根
}
```

改成:

```js
  focusTime(centerEpochToFocus);
  if (window._afterKline) window._afterKline();        // Task 10 掛 marker
  if (sessionReqUpdate) sessionReqUpdate();            // 觸發盤別分界線重畫
  updateLegend(null);                                  // 預設顯示最新一根
  loadMiniChart(state.centerDate, state.adjust);       // 左側 1H 參考圖(唯讀,含夜盤)
}
```

- [ ] **Step 3: 語法檢查**

Run: `node --check src/chart_ui/static/app.js`
Expected: 無輸出。

- [ ] **Step 4: 端對端驗證(資料、連動、夜盤、唯讀)**

Run: `uv run chart-ui`(已在跑則重整瀏覽器)
開啟 http://127.0.0.1:8888/,從左側清單點選任一交易日。
Expected,逐項確認:
1. mini 圖出現 1H 紅綠 K 線,下方 MACD 有 DIF(米色)、DEA(藍色)兩線與紅綠柱。
2. 點清單不同日期 → mini 圖換到該日期區間(最右一根接近所選日)。
3. mini 圖可見夜盤 K:把游標移到底部時間軸,有 15:00 之後的 1H K(主圖日盤模式看不到的時段)。
4. 主圖 toolbar 切「原始 ↔ 調整」→ mini K 價位跟著平移。
5. 主圖 toolbar 切「日盤 ↔ 全日盤」→ mini 圖**不變**(永遠含夜盤)。
6. 在 mini 圖上拖曳/滾輪 → 無反應(唯讀);主圖操作完全正常。
7. Console(F12)無錯誤。

- [ ] **Step 5: 驗證 adjust 連動的細節(調整模式重整後仍正確)**

在瀏覽器把主圖切到「調整」,重新整理頁面,再點一個日期。
Expected: mini 圖以調整後價位顯示(與主圖調整價同一基準),無錯誤。

- [ ] **Step 6: Commit**

```bash
git add src/chart_ui/static/app.js
git commit -m "feat(chart-ui): mini 1H 圖載入資料 + MACD,跟主圖日期/adjust 連動"
```

---

## Task 5: 既有功能回歸驗證

**Files:**
- 無異動(純驗證)

- [ ] **Step 1: 主圖回歸**

Run: `uv run chart-ui`(已在跑則重整)
逐項確認主圖未受影響:
- 切換 tf(1分/5分/15分/30分/60分/日)正常。
- 進出場 marker、VWAP、均線、布林、MA Turn 副圖、支撐壓力 rail、覆盤時間線皆正常。
- 切換可見 K 棒數(180/360/540/720)正常。
- Console 無錯誤。

- [ ] **Step 2: 確認無未提交殘留**

Run: `git status`
Expected: working tree clean(Task 1–4 皆已 commit,無臨時檔殘留)。

---

## Self-Review 對照(spec → task)

- 左側 sidebar 下方固定高度區塊(1H K + MACD) → Task 1(版面)+ Task 3(圖)。
- 1H 圖固定含夜盤(session=full) → Task 4 Step 1(`session: 'full'` 固定)+ Step 4 第 3、5 項驗證。
- 跟主圖日期 → Task 4 Step 2(loadKline 掛呼叫,傳 `state.centerDate`)。
- 沿用主圖 adjust → Task 4 Step 1(傳 `adjust`)+ Step 4 第 4 項驗證。
- MACD 12/26/9 DIF/DEA/柱 → Task 2(數學)+ Task 3(series)+ Task 4(setData)。
- 漲紅跌綠柱 → Task 4 Step 1(`hist[i] >= 0 ? COLORS.up : COLORS.down`)。
- 唯讀(無遊標/點擊/marker) → Task 3(crosshair Hidden、handleScroll/Scale false)+ Task 4 Step 4 第 6 項驗證。
- 用 from/to 有界載入(非 center) → Task 4 Step 1(`miniRangeFrom` + `from`/`to`)。
- 獨立 miniChartState,不影響主圖 → Task 3(獨立 state)+ Task 5(回歸驗證)。
- 後端不需修改 → 全程無後端檔案異動。
- 錯誤處理:空資料/不足 26 根/fetch 失敗 → Task 4 Step 1(三種分支)。
