const COLORS = { up: '#ef4444', down: '#22c55e', wick: '#e0e0e0', accent: '#d4a574' };
const WD = ['日', '一', '二', '三', '四', '五', '六'];
// 成交量：仿 TradingView「Volume vs 1.5x MA」——量 > MA(20)×1.5 → 紅，否則灰；附 MA 線與門檻線。
const VOL_MA_LEN = 20;
const VOL_MA_MULT = 1.5;
const VOL_HI = '#ef4444';      // 放量（> 門檻）
const VOL_LO = '#787b86aa';    // 一般量
const VOL_MA_COLOR = '#2196f3';      // 量能均線（藍）
const VOL_THRESH_COLOR = '#ff9800';  // 1.5×MA 門檻（橘）
// BB %B（length 15, mult 2）：另開副圖，y 軸畫 1/0 虛線；突破 1 或跌破 0 標記每段第一筆。
const BB_LEN = 15;
const BB_MULT = 2;
const BB_COLOR = '#c678dd';
const BB_REF_COLOR = '#888';
// 主圖 6 條均線（SMA(close)），週期/顏色仿 screener-ui。
const MA_DEFS = [
  { p: 5, color: '#ff9800' },
  { p: 10, color: '#4caf50' },
  { p: 21, color: '#00bcd4' },
  { p: 65, color: '#2196f3' },
  { p: 130, color: '#9c27b0' },
  { p: 233, color: '#f44336' },
];

// 獨立指標（與 6 均線群組分開、各自開關、預設關）
const IND_5MA = { color: '#ffeb3b' };    // 1分K 5MA（黃）
const IND_VWAP = { color: '#00bcd4' };   // VWAP 成交量加權均價（青）
const PIVOT_LEN = 5;                     // pivot high/low 左右窗格根數
const PIVOT_LEGEND_COLOR = '#ff9800';    // legend 開關代表色（橘）
const PIVOT_HIGH_COLOR = '#ff7043';      // pivot high marker（橘紅，畫在上方）
const PIVOT_LOW_COLOR = '#42a5f5';       // pivot low marker（藍，畫在下方）
// EstRisk：移植 close_risk_lines.pine。risk/safe 來自後端 /api/risklevels（全歷史 EMA20 日盤
// 高低範圍，risk=ema/4、safe=risk/5），每個交易日一組值；純 legend 數值（同 pine 的
// display.status_line），不在圖上畫線。EMA 必須用全歷史算，故不在前端（只載入數日視窗）計算。
const RISK_COLORS = { upR: '#ef4444', safeHi: '#ffeb3b', safeLo: '#ff9800', dnR: '#22c55e' };
// 點 PL/PH → 由該點延伸 safe 停損線到觸及的 K 並標出場。沿用覆盤多空配色（多橘紅/空綠）。
const EXIT_PL_COLOR = '#e0623d';   // PL 多單停損延伸線 + 出場 marker
const EXIT_PH_COLOR = '#3d9e6a';   // PH 空單停損延伸線 + 出場 marker

const state = {
  tf: localStorage.getItem('cu.tf') || '1m',
  session: localStorage.getItem('cu.session') || 'day',
  adjust: localStorage.getItem('cu.adjust') || 'raw',
  barCount: localStorage.getItem('cu.barCount') || '360',   // 可見 K 棒數
  // 6 條均線各自開關（預設全關）；存成 '000000' 字串（key 改版以強制重置成關）
  maOn: (localStorage.getItem('cu.maOn2') || '000000').padEnd(6, '0').slice(0, 6).split('').map((c) => c === '1'),
  ind5ma: localStorage.getItem('cu.ind5ma') === '1',     // 獨立 1分K 5MA（預設關）
  indVwap: localStorage.getItem('cu.indVwap') === '1',   // 獨立 VWAP（預設關）
  indPivot: localStorage.getItem('cu.indPivot') === '1', // pivot high/low（預設關）
  indRisk: localStorage.getItem('cu.indRisk') !== '0',   // EstRisk 風險/安全價位（預設開）
  centerDate: null,           // 'YYYY-MM-DD'
  list: null,                 // 目前清單 payload
  listId: null,
  activeIdx: -1,
};

const chartState = { chart: null, candle: null, volume: null, bars: [] };
let sessionReqUpdate = null;        // primitive 的 requestUpdate（資料變動時觸發重畫）

const markerState = { handle: null, priceLines: [] };

function clearMarkers() {
  if (markerState.handle) { try { markerState.handle.setMarkers([]); } catch (_) {} }
  for (const pl of markerState.priceLines) { try { chartState.candle.removePriceLine(pl); } catch (_) {} }
  markerState.priceLines = [];
}

// 把目標 epoch 對齊到最近的 bar time（marker/priceline 需落在資料點上）。
function nearestBarTime(targetEpoch) {
  const bars = chartState.bars;
  if (!bars.length) return null;
  let best = bars[0].time, bestDiff = Infinity;
  for (const b of bars) {
    const t = typeof b.time === 'string' ? localToEpoch(b.time + ' 08:45:00') : b.time;
    const diff = Math.abs(t - targetEpoch);
    if (diff < bestDiff) { bestDiff = diff; best = b.time; }
  }
  return best;
}

function drawTradeMarkers(item) {
  clearMarkers();
  if (!item || state.tf === '1d') return;            // 進出場 marker 僅 intraday
  // 『所有交易日』項目只有 time、無交易資訊 → 不畫 marker。
  const hasTrade = item.side || item.entry != null || item.exit_time != null
    || (item.levels && item.levels.length);
  if (!hasTrade) return;
  const isLong = /long|buy|做多/i.test(item.side || '');
  const markers = [];
  const entryEpoch = item.time ? localToEpoch(item.time) : null;
  if (entryEpoch != null) {
    markers.push({
      time: nearestBarTime(entryEpoch), position: isLong ? 'belowBar' : 'aboveBar',
      shape: isLong ? 'arrowUp' : 'arrowDown', color: isLong ? COLORS.up : COLORS.down,
      text: `進${item.pnl_pts != null ? ` ${item.pnl_pts > 0 ? '+' : ''}${item.pnl_pts}` : ''}`,
    });
  }
  if (item.exit_time) {
    const ex = localToEpoch(item.exit_time);
    if (ex != null) markers.push({
      time: nearestBarTime(ex), position: isLong ? 'aboveBar' : 'belowBar',
      shape: isLong ? 'arrowDown' : 'arrowUp', color: COLORS.accent, text: '出',
    });
  }
  if (markers.length) {
    markers.sort((a, b) => a.time - b.time);
    markerState.handle = markerState.handle
      ? (markerState.handle.setMarkers(markers), markerState.handle)
      : LightweightCharts.createSeriesMarkers(chartState.candle, markers);
  }
  if (item.entry != null) {
    markerState.priceLines.push(chartState.candle.createPriceLine({
      price: +item.entry, color: COLORS.accent, lineStyle: 1, lineWidth: 1,
      axisLabelVisible: true, title: '進場',
    }));
  }
  for (const lv of item.levels || []) {
    if (lv && lv.price != null) markerState.priceLines.push(chartState.candle.createPriceLine({
      price: +lv.price, color: '#6aa3ff', lineStyle: 2, lineWidth: 1,
      axisLabelVisible: true, title: lv.label || '',
    }));
  }
}

// 覆盤 overlay：多、空兩個方向的觸及 marker 都畫 + 09:30/10:45 時間線。
// 關卡水平線已移除(太雜)。不自行 clearMarkers（由呼叫端 maybeDrawReview 清）；intraday 才畫。
function drawReviewOverlay(d) {
  if (state.tf === '1d' || !chartState.candle) return;
  if (!d || !d.touches) return;
  const tch = d.touches;
  const tm = [];
  for (const t of (tch.bull || [])) tm.push({
    time: nearestBarTime(localToEpoch(`${d.date} ${t.time}:00`)), position: 'belowBar',
    shape: 'circle', color: '#e0623d', text: `多${t.level} ${t.time}`,
  });
  for (const t of (tch.bear || [])) tm.push({
    time: nearestBarTime(localToEpoch(`${d.date} ${t.time}:00`)), position: 'aboveBar',
    shape: 'circle', color: '#3d9e6a', text: `空${t.level} ${t.time}`,
  });
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

// 在 bars 與 daystats 都就緒、且非回測交易項時，畫覆盤 overlay。
function maybeDrawReview() {
  const it = window._pendingItem;
  const hasTrade = it && (it.side || it.entry != null || it.exit_time != null
    || (it.levels && it.levels.length));
  if (hasTrade) return;                                  // 交易日交給 drawTradeMarkers
  if (!chartState.bars || !chartState.bars.length) return;
  if (!window._dayStats) return;
  clearMarkers();
  drawReviewOverlay(window._dayStats);
}

function pad2(n) { return String(n).padStart(2, '0'); }

function applyMaVisibility() {
  if (chartState.maSeries) chartState.maSeries.forEach((s, k) => s.applyOptions({ visible: state.maOn[k] }));
  if (chartState.ind5maSeries) chartState.ind5maSeries.applyOptions({ visible: state.ind5ma });
  if (chartState.indVwapSeries) chartState.indVwapSeries.applyOptions({ visible: state.indVwap });
}
function saveMaOn() {
  localStorage.setItem('cu.maOn2', state.maOn.map((b) => (b ? '1' : '0')).join(''));
}

// 滑動視窗 SMA；不足 period 的前段為 null。
function sma(values, period) {
  const out = [];
  let run = 0;
  for (let i = 0; i < values.length; i++) {
    run += values[i];
    if (i >= period) run -= values[i - period];
    out[i] = i >= period - 1 ? run / period : null;
  }
  return out;
}

// VWAP（成交量加權均價）；每個交易日（日期變更）重置。典型價 = (H+L+C)/3。
function vwap(bars) {
  const out = new Array(bars.length).fill(null);
  let curDay = null, cumPV = 0, cumV = 0;
  for (let i = 0; i < bars.length; i++) {
    const b = bars[i];
    const day = typeof b.time === 'string'
      ? b.time
      : new Date(b.time * 1000).toISOString().slice(0, 10);
    if (day !== curDay) { curDay = day; cumPV = 0; cumV = 0; }
    const tp = (b.high + b.low + b.close) / 3;
    const v = b.volume || 0;
    cumPV += tp * v;
    cumV += v;
    out[i] = cumV > 0 ? cumPV / cumV : tp;
  }
  return out;
}

// Pivot high/low：以左右各 len 根為窗格。某根 high 嚴格大於兩側所有 high → pivot high；
// low 嚴格小於兩側所有 low → pivot low（與兩側相等即不成立，避免平台重複標記）。
// 歷史重播下可直接看完整資料判斷，不需等右側確認；marker 畫在 pivot 當根。
function computePivotMarkers(bars, len) {
  const marks = [];
  for (let i = len; i < bars.length - len; i++) {
    const h = bars[i].high, l = bars[i].low;
    let isHigh = true, isLow = true;
    for (let j = i - len; j <= i + len; j++) {
      if (j === i) continue;
      if (bars[j].high >= h) isHigh = false;
      if (bars[j].low <= l) isLow = false;
    }
    if (isHigh) marks.push({ time: bars[i].time, position: 'aboveBar', shape: 'arrowDown', color: PIVOT_HIGH_COLOR, text: 'PH' });
    if (isLow) marks.push({ time: bars[i].time, position: 'belowBar', shape: 'arrowUp', color: PIVOT_LOW_COLOR, text: 'PL' });
  }
  return marks;   // i 遞增 → time 已遞增；同一根不可能同時為高低點
}

// 套用 pivot marker（獨立於進出場/覆盤 marker handle）；關閉時清空。
function applyPivotMarkers() {
  if (!chartState.candle) return;
  const marks = state.indPivot ? (chartState.pivotMarks || []) : [];
  chartState.pivotMarkersHandle = chartState.pivotMarkersHandle
    ? (chartState.pivotMarkersHandle.setMarkers(marks), chartState.pivotMarkersHandle)
    : LightweightCharts.createSeriesMarkers(chartState.candle, marks);
}

// EstRisk：每根 K 對應其交易日的 {risk, safe}，由後端 riskMap（date→{risk,safe}）查表。
// intraday 用 K 的日期；tf==='1d' 時 b.time 本身即 'YYYY-MM-DD'。查不到（資料不足/首 20 日）→ null。
function computeRiskSafe(bars) {
  const map = chartState.riskMap || {};
  const daily = state.tf === '1d';
  return bars.map((b) => map[daily ? b.time : epochDate(b.time)] || null);
}

// 取某根 K 所屬交易日的 safe（停損緩衝）；查無 → null。
function barSafe(b) {
  const map = chartState.riskMap || {};
  const date = typeof b.time === 'string' ? b.time : epochDate(b.time);
  const e = map[date];
  return e ? e.safe : null;
}

// 清除點 PL/PH 延伸出的停損線與出場 marker。
function clearExitOverlay() {
  if (chartState.exitSeries) chartState.exitSeries.setData([]);
  if (chartState.exitMarkersHandle) chartState.exitMarkersHandle.setMarkers([]);
  chartState.exitAnchor = null;
}

// 從 anchor（被點的 pivot bar）延伸停損線：PL → low−safe 往右、第一根 low≤level 出場；
// PH → high+safe 往右、第一根 high≥level 出場。出場價 = level（水平線價）。沒觸及則延到最後一根。
function drawExitFromPivot(i, side) {
  const bars = chartState.bars || [];
  const anchor = bars[i];
  if (!anchor) return;
  const safe = barSafe(anchor);
  if (safe == null) return;                       // 該日無 safe → 不動作
  const isPL = side === 'pl';
  const level = isPL ? anchor.low - safe : anchor.high + safe;
  let j = -1;
  for (let k = i + 1; k < bars.length; k++) {
    if (isPL ? bars[k].low <= level : bars[k].high >= level) { j = k; break; }
  }
  const end = j >= 0 ? j : bars.length - 1;
  const seg = [];
  for (let k = i; k <= end; k++) seg.push({ time: bars[k].time, value: level });
  const color = isPL ? EXIT_PL_COLOR : EXIT_PH_COLOR;
  chartState.exitSeries.applyOptions({ color });
  chartState.exitSeries.setData(seg);
  const marks = j >= 0 ? [{
    time: bars[j].time, position: isPL ? 'belowBar' : 'aboveBar',
    shape: isPL ? 'arrowDown' : 'arrowUp', color, text: `出 ${Math.round(level)}`,
  }] : [];
  chartState.exitMarkersHandle = chartState.exitMarkersHandle
    ? (chartState.exitMarkersHandle.setMarkers(marks), chartState.exitMarkersHandle)
    : LightweightCharts.createSeriesMarkers(chartState.candle, marks);
  chartState.exitAnchor = { i, side };
}

// 點擊主圖：命中 Pivot 指標的 PL/PH（需 Pivot 開啟）→ 畫停損延伸線。再點同一點同側 → 清除。
function onChartClick(param) {
  if (!param || param.time == null || !state.indPivot) return;
  const bars = chartState.bars || [];
  const i = bars.findIndex((b) => b.time === param.time);
  if (i < 0) return;
  const marks = (chartState.pivotMarks || []).filter((m) => m.time === param.time);
  if (!marks.length) return;
  let side;
  if (marks.length === 1) {
    side = marks[0].text === 'PL' ? 'pl' : 'ph';
  } else {                                         // 同根同時 PH+PL（罕見）→ 依點擊高度判定
    const py = param.point ? chartState.candle.coordinateToPrice(param.point.y) : null;
    const mid = (bars[i].high + bars[i].low) / 2;
    side = (py != null && py < mid) ? 'pl' : 'ph';
  }
  if (chartState.exitAnchor && chartState.exitAnchor.i === i && chartState.exitAnchor.side === side) {
    clearExitOverlay();                            // toggle off
    return;
  }
  drawExitFromPivot(i, side);
}

// 把 'YYYY-MM-DD HH:MM:SS' 當 UTC 算 epoch 秒（與後端 _to_epoch 一致）。
function localToEpoch(s) {
  const m = s.match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/);
  if (!m) return null;
  return Math.floor(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6] || 0) / 1000);
}
// epoch 秒 → 'YYYY-MM-DD'（UTC，與 bar.time 編碼一致），供 riskMap 依交易日查表。
function epochDate(t) {
  const d = new Date(t * 1000);
  return `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}`;
}
function dateWeekday(dateStr) {
  const m = dateStr.match(/(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return dateStr;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return `${m[1]}-${m[2]}-${m[3]} (${WD[d.getUTCDay()]})`;
}
function fmtAxisTime(epochOrStr) {
  if (typeof epochOrStr === 'string') return epochOrStr;          // daily 'YYYY-MM-DD'
  const d = new Date(epochOrStr * 1000);
  return `${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())} ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}`;
}
// legend 用：日期帶星期幾（intraday 再加 HH:MM）。
function fmtLegendTime(time) {
  if (typeof time === 'string') return dateWeekday(time);         // daily 'YYYY-MM-DD (三)'
  const d = new Date(time * 1000);
  const date = `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}`;
  return `${date} (${WD[d.getUTCDay()]}) ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}`;
}

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} (${url})`);
  return r.json();
}

function initChart() {
  const el = document.getElementById('chart');
  const chart = LightweightCharts.createChart(el, {
    layout: { background: { color: '#0d0d0d' }, textColor: '#e0e0e0' },
    grid: { vertLines: { color: '#1a1a1a' }, horzLines: { color: '#1a1a1a' } },
    rightPriceScale: { borderColor: '#333' },
    timeScale: { borderColor: '#333', timeVisible: true, secondsVisible: false },
    localization: { timeFormatter: fmtAxisTime },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    autoSize: true,
  });
  chartState.chart = chart;
  chartState.candle = chart.addSeries(LightweightCharts.CandlestickSeries, {
    upColor: COLORS.up, downColor: COLORS.down,
    borderUpColor: COLORS.up, borderDownColor: COLORS.down,
    wickUpColor: COLORS.wick, wickDownColor: COLORS.wick,
    priceLineVisible: false, lastValueVisible: false,
    priceFormat: { type: 'price', precision: 0, minMove: 1 },   // 台指期為整數，y 軸不顯示小數
  });
  chartState.candle.attachPrimitive(sessionLinesPrimitive);   // 盤別分界垂直線
  chartState.maSeries = MA_DEFS.map((d) => chart.addSeries(LightweightCharts.LineSeries, {
    color: d.color, lineWidth: 1, priceScaleId: 'right',
    priceLineVisible: false, lastValueVisible: false,
    priceFormat: { type: 'price', precision: 0, minMove: 1 },
  }));
  const _indOpts = (color) => ({
    color, lineWidth: 2, priceScaleId: 'right',
    priceLineVisible: false, lastValueVisible: false,
    priceFormat: { type: 'price', precision: 0, minMove: 1 },
  });
  chartState.ind5maSeries = chart.addSeries(LightweightCharts.LineSeries, _indOpts(IND_5MA.color));
  chartState.indVwapSeries = chart.addSeries(LightweightCharts.LineSeries, _indOpts(IND_VWAP.color));
  // 點 PL/PH 延伸的停損線（虛線、主圖右軸）；資料只在 anchor→觸及那段，平時為空。
  chartState.exitSeries = chart.addSeries(LightweightCharts.LineSeries, {
    color: EXIT_PL_COLOR, lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Dashed,
    priceScaleId: 'right', priceLineVisible: false, lastValueVisible: false,
    crosshairMarkerVisible: false,
    priceFormat: { type: 'price', precision: 0, minMove: 1 },
  });
  applyMaVisibility();
  chartState.volume = chart.addSeries(
    LightweightCharts.HistogramSeries,
    { priceFormat: { type: 'volume' }, priceScaleId: 'volume',
      priceLineVisible: false, lastValueVisible: false },
    1,                       // pane index 1 = 成交量副圖
  );
  chartState.volMa = chart.addSeries(
    LightweightCharts.LineSeries,
    { color: VOL_MA_COLOR, lineWidth: 2, priceScaleId: 'volume',
      priceLineVisible: false, lastValueVisible: false },
    1,
  );
  chartState.volThresh = chart.addSeries(
    LightweightCharts.LineSeries,
    { color: VOL_THRESH_COLOR, lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed,
      priceScaleId: 'volume', priceLineVisible: false, lastValueVisible: false },
    1,
  );
  chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.2, bottom: 0 } });
  // BB %B 副圖（pane 2）：自動縮放但永遠包含 0~1，使 0/1 虛線恆可見。
  chartState.bb = chart.addSeries(
    LightweightCharts.LineSeries,
    {
      color: BB_COLOR, lineWidth: 1, priceScaleId: 'bb',
      priceLineVisible: false, lastValueVisible: false,
      autoscaleInfoProvider: (orig) => {
        const r = orig();
        if (!r || !r.priceRange) return { priceRange: { minValue: 0, maxValue: 1 } };
        return { priceRange: { minValue: Math.min(0, r.priceRange.minValue), maxValue: Math.max(1, r.priceRange.maxValue) } };
      },
    },
    2,
  );
  chartState.bb.createPriceLine({ price: 1, color: BB_REF_COLOR, lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: '1' });
  chartState.bb.createPriceLine({ price: 0, color: BB_REF_COLOR, lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: '0' });
  chart.priceScale('bb').applyOptions({ scaleMargins: { top: 0.15, bottom: 0.15 } });
  chart.subscribeCrosshairMove((param) => updateLegend(param));
  chart.subscribeClick((param) => onChartClick(param));
  const wrap = document.querySelector('.chart-wrap');
  if (wrap) new ResizeObserver(() => {
    positionPaneLegend(document.getElementById('vol-legend'), 1);
    positionPaneLegend(document.getElementById('bb-legend'), 2);
  }).observe(wrap);
}

// 把副圖 legend 對齊到對應 pane 頂端（同在 .chart-wrap 內，定位才不會被 canvas 蓋住）。
function positionPaneLegend(el, paneIndex) {
  const wrap = document.querySelector('.chart-wrap');
  const chart = chartState.chart;
  if (!wrap || !el || !chart || typeof chart.panes !== 'function') return;
  const panes = chart.panes();
  const paneEl = panes && panes.length > paneIndex ? panes[paneIndex].getHTMLElement?.() : null;
  if (!paneEl) return;
  const top = paneEl.getBoundingClientRect().top - wrap.getBoundingClientRect().top + 4;
  el.style.top = `${top}px`;
}

// 遊標移動時顯示該位置的主圖 OHLC（主圖 legend）、量能與 %B（各副圖 legend）。無 hover → 最新一根。
function updateLegend(param) {
  const main = document.getElementById('legend');
  const vol = document.getElementById('vol-legend');
  const bb = document.getElementById('bb-legend');
  const bars = chartState.bars || [];
  if (!bars.length) { for (const e of [main, vol, bb]) if (e) e.innerHTML = ''; return; }
  let idx = param && param.time != null ? bars.findIndex((b) => b.time === param.time) : -1;
  if (idx < 0) idx = bars.length - 1;
  const b = bars[idx];
  const prev = idx > 0 ? bars[idx - 1] : null;
  const r = Math.round;
  const oc = b.close >= b.open ? 'up' : 'down';
  const tStr = fmtLegendTime(b.time);
  let chgStr = '';
  if (prev && prev.close) {
    const chg = b.close - prev.close;
    const pct = (chg / prev.close) * 100;
    const cls = chg >= 0 ? 'up' : 'down';
    chgStr = ` <span class="${cls}">${chg >= 0 ? '+' : ''}${r(chg)} (${chg >= 0 ? '+' : ''}${pct.toFixed(2)}%)</span>`;
  }
  if (main) {
    const anyMaOn = state.maOn.some(Boolean);
    const master = `<span class="ind-toggle ${anyMaOn ? 'on' : 'off'}" data-toggle="ma">均線</span>`;
    const perMa = MA_DEFS.map((d, k) => {
      const on = state.maOn[k];
      const v = chartState.maArrs ? chartState.maArrs[k][idx] : null;
      const label = on && v != null ? `${d.p} ${r(v)}` : `${d.p}`;
      return on
        ? `<span class="ind-toggle" data-ma="${k}" style="color:${d.color}">${label}</span>`
        : `<span class="ind-toggle ma-off" data-ma="${k}">${label}</span>`;
    }).join('　');
    const indTog = (on, key, name, color, arr) => {
      const v = on && arr && arr[idx] != null ? ` ${r(arr[idx])}` : '';
      return on
        ? `<span class="ind-toggle" data-toggle="${key}" style="color:${color}">${name}${v}</span>`
        : `<span class="ind-toggle ma-off" data-toggle="${key}">${name}</span>`;
    };
    const ind5 = indTog(state.ind5ma, '5ma', '5MA', IND_5MA.color, chartState.ind5maArr);
    const indV = indTog(state.indVwap, 'vwap', 'VWAP', IND_VWAP.color, chartState.indVwapArr);
    const indPiv = indTog(state.indPivot, 'pivot', `Pivot${PIVOT_LEN}`, PIVOT_LEGEND_COLOR, null);
    // EstRisk：開啟時顯示四個值（收+R / 高+S / 低−S / 收−R），各自上色；無完成日 → —
    const rs = chartState.riskArr ? chartState.riskArr[idx] : null;
    const C = RISK_COLORS;
    let indRisk;
    if (!state.indRisk) {
      indRisk = `<span class="ind-toggle ma-off" data-toggle="risk">Risk</span>`;
    } else if (rs) {
      indRisk = `<span class="ind-toggle" data-toggle="risk" style="color:${C.upR}">Risk</span>`
        + ` <span style="color:${C.upR}">收+R ${r(b.close + rs.risk)}</span>`
        + ` · <span style="color:${C.safeHi}">高+S ${r(b.high + rs.safe)}</span>`
        + ` · <span style="color:${C.safeLo}">低−S ${r(b.low - rs.safe)}</span>`
        + ` · <span style="color:${C.dnR}">收−R ${r(b.close - rs.risk)}</span>`;
    } else {
      indRisk = `<span class="ind-toggle" data-toggle="risk" style="color:${C.upR}">Risk</span> <span class="muted">—</span>`;
    }
    const maLine = `${master}　${perMa}`;
    const indLine = `${ind5}<br>${indV}<br>${indPiv}<br>${indRisk}`;   // 5MA / VWAP / Pivot / Risk 各自獨立一行
    main.innerHTML =
      `<span class="muted">${tStr}</span>　` +
      `開 <span class="${oc}">${r(b.open)}</span>　高 <span class="${oc}">${r(b.high)}</span>　` +
      `低 <span class="${oc}">${r(b.low)}</span>　收 <span class="${oc}">${r(b.close)}</span>${chgStr}` +
      (maLine ? `<br>${maLine}` : '') +
      `<br>${indLine}`;
  }
  if (vol) {
    positionPaneLegend(vol, 1);
    const volMa = chartState.volMaArr ? chartState.volMaArr[idx] : null;
    const thr = volMa != null ? volMa * VOL_MA_MULT : null;
    const volCls = thr != null && b.volume > thr ? 'up' : 'muted';
    vol.innerHTML =
      `量 <span class="${volCls}">${b.volume.toLocaleString()}</span>` +
      (volMa != null ? `　<span style="color:${VOL_MA_COLOR}">MA${VOL_MA_LEN} ${r(volMa).toLocaleString()}</span>` : '') +
      (thr != null ? `　<span style="color:${VOL_THRESH_COLOR}">×${VOL_MA_MULT} ${r(thr).toLocaleString()}</span>` : '');
  }
  if (bb) {
    positionPaneLegend(bb, 2);
    const v = chartState.bbArr ? chartState.bbArr[idx] : null;
    const cls = v == null ? 'muted' : (v > 1 ? 'up' : (v < 0 ? 'down' : ''));
    bb.innerHTML = `<span style="color:${BB_COLOR}">%B(${BB_LEN},${BB_MULT})</span> <span class="${cls}">${v == null ? '-' : v.toFixed(2)}</span>`;
  }
}

// === 盤別分界垂直線（Lightweight Charts series primitive，畫在主圖自身座標系，x 必與 K 棒對齊）===
function isDayTod(t) {                       // t = epoch 秒（intraday）
  const d = new Date(t * 1000);
  const tod = d.getUTCHours() * 60 + d.getUTCMinutes();
  return tod >= 525 && tod <= 825;           // 08:45 ~ 13:45
}
function dayKey(t) {
  const d = new Date(t * 1000);
  return d.getUTCFullYear() * 10000 + (d.getUTCMonth() + 1) * 100 + d.getUTCDate();
}

const _sessionRenderer = {
  draw(target) {
    if (state.tf === '1d') return;                     // 日線無盤中分界
    const chart = chartState.chart;
    const bars = chartState.bars || [];
    if (!chart || !bars.length) return;
    const ts = chart.timeScale();
    const logical = ts.getVisibleLogicalRange();
    if (!logical) return;
    const half = (ts.options().barSpacing || 6) / 2;
    const lo = Math.max(0, Math.floor(logical.from));
    const hi = Math.min(bars.length - 1, Math.ceil(logical.to));
    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      const hpr = scope.horizontalPixelRatio;
      const h = scope.bitmapSize.height;
      ctx.save();
      ctx.lineWidth = Math.max(1, Math.floor(hpr));
      ctx.setLineDash([5 * hpr, 4 * hpr]);
      const line = (x, color) => {
        const px = Math.round(x * hpr);
        ctx.strokeStyle = color;
        ctx.beginPath();
        ctx.moveTo(px, 0);
        ctx.lineTo(px, h);
        ctx.stroke();
      };
      for (let i = lo; i <= hi; i++) {
        const t = bars[i].time;
        if (!isDayTod(t)) continue;
        const x = ts.timeToCoordinate(t);
        if (x == null) continue;
        // 只在「相鄰兩根」真正換盤/換日時畫；資料視窗頭尾不算交界。
        const isOpen = i > 0 && (!isDayTod(bars[i - 1].time) || dayKey(bars[i - 1].time) !== dayKey(t));
        const isClose = i < bars.length - 1 && (!isDayTod(bars[i + 1].time) || dayKey(bars[i + 1].time) !== dayKey(t));
        if (isOpen) line(x - half, '#4a80c0');   // 換日：日盤開始（08:45 前）
        if (isClose) line(x + half, '#b08442');  // 日盤結束（13:45 後）
      }
      ctx.restore();
    });
  },
};
const _sessionPaneView = { renderer() { return _sessionRenderer; }, zOrder() { return 'top'; } };
const sessionLinesPrimitive = {
  attached(p) { sessionReqUpdate = p.requestUpdate; },
  detached() { sessionReqUpdate = null; },
  updateAllViews() {},
  paneViews() { return [_sessionPaneView]; },
};

function klineUrl() {
  const p = new URLSearchParams({ tf: state.tf, session: state.session, adjust: state.adjust });
  if (state.tf === '1d') return `/api/kline?${p}`;
  p.set('center', state.centerDate || '');
  return `/api/kline?${p}`;
}

async function loadKline(centerEpochToFocus) {
  if (state.tf !== '1d' && !state.centerDate) return;
  const bars = await fetchJSON(klineUrl());
  chartState.bars = bars;
  chartState.candle.setData(bars.map((b) => ({
    time: b.time, open: b.open, high: b.high, low: b.low, close: b.close,
  })));
  // 主圖 6 條均線
  const closes = bars.map((b) => b.close);
  chartState.maArrs = MA_DEFS.map((d) => sma(closes, d.p));
  chartState.maArrs.forEach((arr, k) => {
    chartState.maSeries[k].setData(
      bars.flatMap((b, i) => (arr[i] != null ? [{ time: b.time, value: arr[i] }] : [])),
    );
  });
  // 獨立 5MA / VWAP
  const _toData = (arr) => bars.flatMap((b, i) => (arr[i] != null ? [{ time: b.time, value: arr[i] }] : []));
  chartState.ind5maArr = sma(closes, 5);
  chartState.indVwapArr = vwap(bars);
  chartState.ind5maSeries.setData(_toData(chartState.ind5maArr));
  chartState.indVwapSeries.setData(_toData(chartState.indVwapArr));
  // Pivot high/low（左右各 PIVOT_LEN 根）
  chartState.pivotMarks = computePivotMarkers(bars, PIVOT_LEN);
  applyPivotMarkers();
  // EstRisk 風險/安全價位（legend 數值，每根 K 的 {risk, safe}）
  chartState.riskArr = computeRiskSafe(bars);
  clearExitOverlay();                            // 換日/換 tf → anchor index 失效，清掉停損延伸線
  // 量能 MA(20) 與 1.5× 門檻（滑動視窗，前 19 根不足 → null）
  const volMa = [];
  let run = 0;
  for (let i = 0; i < bars.length; i++) {
    run += bars[i].volume;
    if (i >= VOL_MA_LEN) run -= bars[i - VOL_MA_LEN].volume;
    volMa[i] = i >= VOL_MA_LEN - 1 ? run / VOL_MA_LEN : null;
  }
  chartState.volMaArr = volMa;        // 供 legend 查詢
  chartState.volume.setData(bars.map((b, i) => {
    const thr = volMa[i] != null ? volMa[i] * VOL_MA_MULT : null;
    return { time: b.time, value: b.volume, color: (thr != null && b.volume > thr) ? VOL_HI : VOL_LO };
  }));
  chartState.volMa.setData(
    bars.flatMap((b, i) => (volMa[i] != null ? [{ time: b.time, value: volMa[i] }] : [])),
  );
  chartState.volThresh.setData(
    bars.flatMap((b, i) => (volMa[i] != null ? [{ time: b.time, value: volMa[i] * VOL_MA_MULT }] : [])),
  );
  // BB %B（length 15, mult 2，population stdev）；突破 1 / 跌破 0 標記每段第一筆。
  const bbArr = [];
  let bs = 0, bs2 = 0;
  for (let i = 0; i < bars.length; i++) {
    const c = bars[i].close;
    bs += c; bs2 += c * c;
    if (i >= BB_LEN) { const o = bars[i - BB_LEN].close; bs -= o; bs2 -= o * o; }
    if (i >= BB_LEN - 1) {
      const mean = bs / BB_LEN;
      const sd = Math.sqrt(Math.max(0, bs2 / BB_LEN - mean * mean));
      const up = mean + BB_MULT * sd, lo = mean - BB_MULT * sd;
      bbArr[i] = up > lo ? (c - lo) / (up - lo) : null;
    } else bbArr[i] = null;
  }
  chartState.bbArr = bbArr;
  chartState.bb.setData(bars.flatMap((b, i) => (bbArr[i] != null ? [{ time: b.time, value: bbArr[i] }] : [])));
  const bbMarks = [];
  for (let i = 0; i < bars.length; i++) {
    const v = bbArr[i];
    if (v == null) continue;
    const prev = i > 0 ? bbArr[i - 1] : null;
    if (v > 1 && (prev == null || prev <= 1)) bbMarks.push({ time: bars[i].time, position: 'aboveBar', shape: 'circle', color: COLORS.up });
    if (v < 0 && (prev == null || prev >= 0)) bbMarks.push({ time: bars[i].time, position: 'belowBar', shape: 'circle', color: COLORS.down });
  }
  chartState.bbMarkersHandle = chartState.bbMarkersHandle
    ? (chartState.bbMarkersHandle.setMarkers(bbMarks), chartState.bbMarkersHandle)
    : LightweightCharts.createSeriesMarkers(chartState.bb, bbMarks);
  focusTime(centerEpochToFocus);
  if (window._afterKline) window._afterKline();        // Task 10 掛 marker
  if (sessionReqUpdate) sessionReqUpdate();            // 觸發盤別分界線重畫
  updateLegend(null);                                  // 預設顯示最新一根
}

// 將視窗置中到某 time（epoch 或 'YYYY-MM-DD'）；找不到就顯示尾段。
function focusTime(target) {
  const bars = chartState.bars;
  if (!bars.length) return;
  let idx = bars.length - 1;
  if (target != null) {
    let best = Infinity;
    bars.forEach((b, i) => {
      const diff = Math.abs((typeof b.time === 'string' ? localToEpoch(b.time + ' 00:00:00') : b.time)
                            - (typeof target === 'string' ? localToEpoch(target + ' 00:00:00') : target));
      if (diff < best) { best = diff; idx = i; }
    });
  }
  // 可見 K 棒數由 toolbar 切換（state.barCount）；目標放螢幕左側約 1/8，右側留更多看行情。
  const want = parseInt(state.barCount, 10) || 360;
  const before = Math.floor(want / 8);
  let from = idx - before;
  let to = idx + (want - before);
  const maxTo = bars.length - 1 + 3;           // 右側少量 padding
  if (to > maxTo) { from -= (to - maxTo); to = maxTo; }  // 觸右界 → 整段左移，維持視窗大小
  from = Math.max(0, from);
  chartState.chart.timeScale().setVisibleLogicalRange({ from, to });
}

function setTitle() {
  document.getElementById('chart-title').textContent =
    state.centerDate ? dateWeekday(state.centerDate) : (state.tf === '1d' ? '日線' : '—');
}

function wireToolbar() {
  document.querySelectorAll('.seg').forEach((seg) => {
    const group = seg.dataset.group;
    seg.querySelectorAll('button').forEach((btn) => {
      if (btn.dataset.v === state[group]) btn.classList.add('active');
      btn.addEventListener('click', () => {
        state[group] = btn.dataset.v;
        localStorage.setItem(`cu.${group}`, btn.dataset.v);
        seg.querySelectorAll('button').forEach((b) => b.classList.toggle('active', b === btn));
        const focus = state.centerDate ? (state.tf === '1d' ? state.centerDate : localToEpoch(`${state.centerDate} 08:45:00`)) : null;
        if (group === 'barCount') { focusTime(focus); return; }   // 只重新縮放，不必重抓資料
        setTitle();
        loadKline(focus);
      });
    });
  });
}

// 指標 legend 上的開關（事件委派；legend 為 pointer-events:none，但 .ind-toggle 為 auto，
// 點擊會冒泡到 legend 容器）。
function wireIndicatorToggles() {
  for (const id of ['legend', 'vol-legend', 'bb-legend']) {
    const el = document.getElementById(id);
    if (!el) continue;
    el.addEventListener('click', (e) => {
      const maEl = e.target.closest('[data-ma]');
      if (maEl) {                                   // 單條均線開關
        const k = +maEl.dataset.ma;
        state.maOn[k] = !state.maOn[k];
        saveMaOn();
        applyMaVisibility();
        updateLegend(null);
        return;
      }
      const t = e.target.closest('[data-toggle]');
      if (!t) return;
      const which = t.dataset.toggle;
      if (which === 'ma') {                          // 「均線」總開關：全關→全開，否則全關
        const anyOn = state.maOn.some(Boolean);
        state.maOn = state.maOn.map(() => !anyOn);
        saveMaOn();
        applyMaVisibility();
        updateLegend(null);
      } else if (which === '5ma') {
        state.ind5ma = !state.ind5ma;
        localStorage.setItem('cu.ind5ma', state.ind5ma ? '1' : '0');
        applyMaVisibility();
        updateLegend(null);
      } else if (which === 'vwap') {
        state.indVwap = !state.indVwap;
        localStorage.setItem('cu.indVwap', state.indVwap ? '1' : '0');
        applyMaVisibility();
        updateLegend(null);
      } else if (which === 'pivot') {
        state.indPivot = !state.indPivot;
        localStorage.setItem('cu.indPivot', state.indPivot ? '1' : '0');
        applyPivotMarkers();
        updateLegend(null);
      } else if (which === 'risk') {
        state.indRisk = !state.indRisk;
        localStorage.setItem('cu.indRisk', state.indRisk ? '1' : '0');
        updateLegend(null);
      }
    });
  }
}

async function main() {
  initChart();
  wireToolbar();
  wireIndicatorToggles();
  setTitle();
  // EstRisk 風險/安全價位對照表（全歷史 EMA20，後端算）；失敗則留空 → legend 顯示 —。
  try { chartState.riskMap = await fetchJSON('/api/risklevels'); } catch (_) { chartState.riskMap = {}; }
  if (window._initLists) await window._initLists();    // Task 10 提供
}

function renderSidebar() {
  const tbl = document.getElementById('list-table');
  const sum = document.getElementById('list-summary');
  const list = state.list;
  tbl.innerHTML = '';
  if (!list) { sum.textContent = ''; return; }
  const s = list.summary;
  sum.textContent = s
    ? `${s.trades ?? list.items.length} 筆　勝率 ${s.win_rate != null ? (s.win_rate * 100).toFixed(0) + '%' : '—'}　PF ${s.pf ?? '—'}　損益 ${s.pnl_pts ?? '—'}`
    : `${list.items.length} 筆`;
  list.items.forEach((it, i) => {
    const row = document.createElement('div');
    row.className = 'list-row' + (i === state.activeIdx ? ' active' : '');
    const when = dateWeekday(it.time) + (state.list.id === '__all_days__' ? '' : ' ' + (it.time.split(' ')[1] || '').slice(0, 5));
    const sideCls = /long|buy|做多/i.test(it.side || '') ? 'side-long' : (/short|sell|做空/i.test(it.side || '') ? 'side-short' : '');
    const pnlCls = it.pnl_pts == null ? '' : (it.pnl_pts > 0 ? 'pnl-pos' : 'pnl-neg');
    row.innerHTML = `<span class="when">${when}</span>`
      + `<span class="${sideCls}">${it.side ? it.side.slice(0, 6) : ''}</span>`
      + `<span class="${pnlCls}">${it.pnl_pts != null ? (it.pnl_pts > 0 ? '+' : '') + it.pnl_pts : ''}</span>`;
    row.addEventListener('click', () => selectItem(i));
    tbl.appendChild(row);
  });
}

// 右側欄：每日統計（20日平均振幅 / 同星期振幅 / 今日日盤高低 / 夜盤波動 / 加權成交金額 / 前一日 TWNVIX / 關卡價）。切換日期時更新。
async function renderDayStats(date) {
  const el = document.getElementById('rail');
  if (!el) return;
  window._dayStats = null;
  if (!date) { el.innerHTML = ''; return; }
  let d;
  try { d = await fetchJSON(`/api/daystats?date=${encodeURIComponent(date)}`); }
  catch (_) { el.innerHTML = '<div class="sec sec-title">統計載入失敗</div>'; return; }
  window._dayStats = d;
  maybeDrawReview();
  const r = (x) => (x == null ? '—' : Math.round(x).toLocaleString());
  const ar = d.avg_range_20 || {};
  const t = d.today;
  const pv = d.prev_vix;

  const avgSec =
    `<div class="sec"><div class="sec-title">20日平均振幅</div>`
    + `<div class="kv"><span class="k">日盤</span><span class="v">${r(ar.day)}<span class="n"> n=${ar.n_day ?? 0}</span></span></div>`
    + `<div class="kv"><span class="k">全日盤</span><span class="v">${r(ar.full)}<span class="n"> n=${ar.n_full ?? 0}</span></span></div></div>`;

  const todaySec =
    `<div class="sec"><div class="sec-title">今日 ${dateWeekday(d.date)}（日盤）</div>`
    + (t
      ? `<div class="kv"><span class="k">最高</span><span class="v up">${r(t.high)}</span></div>`
        + `<div class="kv"><span class="k">最低</span><span class="v down">${r(t.low)}</span></div>`
        + `<div class="kv"><span class="k">振幅</span><span class="v">${r(t.range)}</span></div>`
      : `<div class="kv"><span class="k">—</span><span class="v">無日盤資料</span></div>`)
    + `</div>`;

  const wr = d.weekday_range;
  const wdSec =
    `<div class="sec"><div class="sec-title">同星期平均振幅（近2月）</div>`
    + (wr
      ? `<div class="kv"><span class="k">${wr.wd}</span><span class="v">${r(wr.avg)}<span class="n"> n=${wr.n}</span></span></div>`
      : `<div class="kv"><span class="k">—</span><span class="v">資料不足</span></div>`)
    + `</div>`;

  const nv = d.night_vol;
  const nvSec =
    `<div class="sec"><div class="sec-title">夜盤波動（昨夜）</div>`
    + (nv
      ? `<div class="kv"><span class="k">振幅</span><span class="v">${r(nv.range)}</span></div>`
        + (nv.norm != null
          ? `<div class="kv"><span class="k">norm</span><span class="v">${nv.norm.toFixed(2)}<span class="n"> EMA20 ${r(nv.ema20)}</span></span></div>`
            + `<div class="kv"><span class="k">分級</span><span class="v">${nv.icon || ''} ${nv.tier}</span></div>`
          : `<div class="kv"><span class="k">norm</span><span class="v">—</span></div>`)
      : `<div class="kv"><span class="k">—</span><span class="v">無夜盤資料</span></div>`)
    + `</div>`;

  const to = d.turnover;
  const pct = (a, b) => {
    if (a == null || b == null || !b) return '';
    const p = a / b * 100;
    const cls = p >= 100 ? 'up' : 'down';
    return ` <span class="${cls}">${Math.round(p)}%${p >= 100 ? '↑' : '↓'}</span>`;
  };
  const toSec =
    `<div class="sec"><div class="sec-title">加權成交金額（億）</div>`
    + (to
      ? `<div class="kv"><span class="k">今日</span><span class="v">${r(to.today)}${pct(to.today, to.avg20)}</span></div>`
        + `<div class="kv"><span class="k">20日均</span><span class="v">${r(to.avg20)}<span class="n"> n=${to.n}</span></span></div>`
      : `<div class="kv"><span class="k">—</span><span class="v">無資料</span></div>`)
    + `</div>`;

  const vixSec =
    `<div class="sec"><div class="sec-title">前一日 TWNVIX</div>`
    + (pv
      ? `<div class="kv"><span class="k">${pv.date}</span><span class="v">${pv.vix.toFixed(2)}</span></div>`
      : `<div class="kv"><span class="k">—</span><span class="v">—</span></div>`)
    + `</div>`;

  const lvlRow = (cls, o) =>
    `<div class="lvl ${cls}${o.today ? ' today' : ''}"><span class="lbl">${o.label}</span><span class="px">${(+o.price).toLocaleString()}</span></div>`;
  const lvlBody = (d.bull && d.bear)
    ? d.bull.map((o) => lvlRow('bull', o)).join('') + `<div class="gap"></div>` + d.bear.map((o) => lvlRow('bear', o)).join('')
    : `<div class="kv"><span class="k">—</span><span class="v">資料不足</span></div>`;
  const er = d.est_range;
  let lvlSub = '';
  if (er) {
    lvlSub = ` 90%地板${r(er.floor90)}·EMA20 ${r(er.ema20)}`;
    if (er.bump != null) lvlSub += `·量能${er.bump >= 0 ? '+' : ''}${r(er.bump)}(事後,量比${er.q})`;
    lvlSub = `<span class="n">${lvlSub}</span>`;
  }
  // 兩段式：碰 L1 → 依續航決定瞄到第幾階；碰 L2 → 再更新一次續 L3 機率(H093，更強)。
  const t1 = d.level1;
  const touchLine = (o, side) => {
    if (!o || !o.l1) return `<div class="kv"><span class="k">${side}1</span><span class="v n">未觸及</span></div>`;
    const h = o.l1;
    const cls = h.action === '瞄' ? 'up' : 'down';
    const body = h.action === '瞄' ? `瞄${side}${h.target} ${h.cont}%` : `拿${side}1`;
    let html = `<div class="kv"><span class="k">${side}1 ${h.time}觸</span>`
      + `<span class="v"><span class="${cls}">${body}</span></span></div>`;
    if (o.l2) {
      const c2 = o.l2.action === '瞄' ? 'up' : 'down';
      const b2 = o.l2.action === '瞄' ? `瞄${side}3 ${o.l2.contL3}%` : `守${side}2 ${o.l2.contL3}%`;
      html += `<div class="kv"><span class="k">${side}2 ${o.l2.time}觸</span>`
        + `<span class="v"><span class="${c2}">${b2}</span></span></div>`;
    }
    return html;
  };
  const touchHtml = t1 ? `<div class="gap"></div>` + touchLine(t1.bull, '多') + touchLine(t1.bear, '空') : '';
  const lvlSec = `<div class="sec"><div class="sec-title">關卡價(達到率)${lvlSub}</div>${lvlBody}${touchHtml}</div>`;

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

  el.innerHTML = avgSec + wdSec + todaySec + nvSec + toSec + vixSec + lvlSec + dciSec;
}

async function selectItem(i) {
  const it = state.list.items[i];
  if (!it) return;
  state.activeIdx = i;
  state.centerDate = it.time.slice(0, 10);
  setTitle();
  renderSidebar();
  renderDayStats(state.centerDate);
  const focus = state.tf === '1d' ? state.centerDate : localToEpoch(it.time);
  window._pendingItem = it;
  await loadKline(focus);
  document.querySelector('.list-row.active')?.scrollIntoView({ block: 'nearest' });
}

window._afterKline = () => { drawTradeMarkers(window._pendingItem); maybeDrawReview(); };

async function loadList(listId) {
  state.list = await fetchJSON(`/api/lists/${encodeURIComponent(listId)}`);
  state.listId = listId;
  state.activeIdx = -1;
  renderSidebar();
  if (state.list.items.length) selectItem(0);          // 預設選第一筆
}

window._initLists = async () => {
  const lists = await fetchJSON('/api/lists');
  const sel = document.getElementById('list-select');
  sel.innerHTML = '';
  for (const l of lists) {
    const o = document.createElement('option');
    o.value = l.id; o.textContent = `${l.name}（${l.count}）`;
    sel.appendChild(o);
  }
  sel.addEventListener('change', () => loadList(sel.value));
  if (lists.length) await loadList(lists[0].id);        // 預設『所有交易日』
};

window.addEventListener('keydown', (e) => {
  if (!state.list || !state.list.items.length) return;
  if (e.key === 'ArrowDown') { e.preventDefault(); selectItem(Math.min(state.list.items.length - 1, state.activeIdx + 1)); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); selectItem(Math.max(0, state.activeIdx - 1)); }
});

main();
