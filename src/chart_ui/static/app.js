const COLORS = { up: '#ef4444', down: '#22c55e', wick: '#e0e0e0', accent: '#d4a574' };
const WD = ['日', '一', '二', '三', '四', '五', '六'];

const state = {
  tf: localStorage.getItem('cu.tf') || '1m',
  session: localStorage.getItem('cu.session') || 'day',
  adjust: localStorage.getItem('cu.adjust') || 'raw',
  centerDate: null,           // 'YYYY-MM-DD'
  list: null,                 // 目前清單 payload
  listId: null,
  activeIdx: -1,
};

const chartState = { chart: null, candle: null, volume: null, bars: [] };

function pad2(n) { return String(n).padStart(2, '0'); }

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
  });
  chartState.volume = chart.addSeries(
    LightweightCharts.HistogramSeries,
    { priceFormat: { type: 'volume' }, priceScaleId: 'volume',
      priceLineVisible: false, lastValueVisible: false },
    1,                       // pane index 1 = 成交量副圖
  );
  chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
}

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
  chartState.volume.setData(bars.map((b) => ({
    time: b.time, value: b.volume,
    color: b.close >= b.open ? '#ef444488' : '#22c55e88',
  })));
  focusTime(centerEpochToFocus);
  if (window._afterKline) window._afterKline();        // Task 10 掛 marker
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
  const want = state.tf === '1d' ? 120 : 90;
  const half = Math.floor(want / 2);
  const from = Math.max(0, idx - half);
  const to = Math.min(bars.length - 1 + 2, idx + half);
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
        const focus = state.centerDate ? `${state.centerDate} 08:45:00` : null;
        setTitle();
        loadKline(state.tf === '1d' ? state.centerDate : (focus ? localToEpoch(focus) : null));
      });
    });
  });
}

async function main() {
  initChart();
  wireToolbar();
  setTitle();
  if (window._initLists) await window._initLists();    // Task 10 提供
}

main();
