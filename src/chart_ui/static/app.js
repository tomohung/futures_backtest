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

const state = {
  tf: localStorage.getItem('cu.tf') || '1m',
  session: localStorage.getItem('cu.session') || 'day',
  adjust: localStorage.getItem('cu.adjust') || 'raw',
  barCount: localStorage.getItem('cu.barCount') || '360',   // 可見 K 棒數
  showMa: localStorage.getItem('cu.ma') !== '0',            // 均線開關（預設開）
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

function pad2(n) { return String(n).padStart(2, '0'); }

function applyMaVisibility() {
  if (chartState.maSeries) chartState.maSeries.forEach((s) => s.applyOptions({ visible: state.showMa }));
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

// 把 'YYYY-MM-DD HH:MM:SS' 當 UTC 算 epoch 秒（與後端 _to_epoch 一致）。
function localToEpoch(s) {
  const m = s.match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/);
  if (!m) return null;
  return Math.floor(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6] || 0) / 1000);
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
    const maLine = state.showMa ? MA_DEFS.map((d, k) => {
      const v = chartState.maArrs ? chartState.maArrs[k][idx] : null;
      return v == null ? '' : `<span style="color:${d.color}">${d.p} ${r(v)}</span>`;
    }).filter(Boolean).join('　') : '';
    main.innerHTML =
      `<span class="muted">${tStr}</span>　` +
      `開 <span class="${oc}">${r(b.open)}</span>　高 <span class="${oc}">${r(b.high)}</span>　` +
      `低 <span class="${oc}">${r(b.low)}</span>　收 <span class="${oc}">${r(b.close)}</span>${chgStr}` +
      (maLine ? `<br>${maLine}` : '');
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
  // 開關按鈕（顯示/隱藏圖層）
  document.querySelectorAll('.toggle').forEach((btn) => {
    const key = btn.dataset.toggle;                       // 'ma'
    const sKey = 'show' + key.charAt(0).toUpperCase() + key.slice(1);  // 'showMa'
    btn.classList.toggle('active', !!state[sKey]);
    btn.addEventListener('click', () => {
      state[sKey] = !state[sKey];
      localStorage.setItem(`cu.${key}`, state[sKey] ? '1' : '0');
      btn.classList.toggle('active', state[sKey]);
      if (key === 'ma') { applyMaVisibility(); updateLegend(null); }
    });
  });
}

async function main() {
  initChart();
  wireToolbar();
  setTitle();
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

async function selectItem(i) {
  const it = state.list.items[i];
  if (!it) return;
  state.activeIdx = i;
  state.centerDate = it.time.slice(0, 10);
  setTitle();
  renderSidebar();
  const focus = state.tf === '1d' ? state.centerDate : localToEpoch(it.time);
  window._pendingItem = it;
  await loadKline(focus);
  document.querySelector('.list-row.active')?.scrollIntoView({ block: 'nearest' });
}

window._afterKline = () => { drawTradeMarkers(window._pendingItem); };

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
