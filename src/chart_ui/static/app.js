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
// 主圖布林通道（同 15,2）：只畫上下兩條帶、不畫中線；可開關，預設關。
const BB_BAND_COLOR = '#c678dd';
// MA Turn（移植 5-ma-turn-from-deduction.pine）：另開副圖，柱狀 = 現價 − 扣抵值（close − close[period]）。
// 在固定較高週期 MATURN_TF 分上算（仿原 pine 的 request.security 5分）；過零 = 該週期 SMA 轉向，
// 柱高 = 現價還要再移動多少均線才翻向。正值(均線上彎=偏多)台灣慣例 → 紅，負值(下彎) → 綠。
// 註：MA Turn 副圖已移除（改為延伸力 EXT 副圖）；MATURN_TF/PERIOD 仍供 600分MA 疊線沿用（maTurnCompute 回傳 ma600）。
const MATURN_TF = 5;            // 600MA 的 bucket 週期（分鐘）
const MATURN_PERIOD = 120;     // 600MA = MATURN_TF×PERIOD = 600 分
const MATURN_ZERO_COLOR = '#888';
// 延伸力 EXT 強門檻（看盤參考線）：H111 ext_long top~20%≈+0.10、H112 ext_short(z-sum) top~20%≈+1.2。
const EXT_STRONG_LONG = 0.10;
const EXT_STRONG_SHORT = 1.2;
const MACD_DEA_COLOR = '#6aa3ff';   // mini 1H MACD 的 DEA(訊號)線
const MACD_MIN_BARS = 34;   // slow(26)+signal(9)-2 = 第一個有效 dea/hist index;不足則不畫 MACD
// MACD 柱 TradingView 式深淺：離零軸方向變大=飽和色,縮回零軸=淡色（漲紅跌綠）。
// fade 用「偏白的亮色」而非降透明度——黑底上低透明度會變暗看不清,往白混才會變淡且清楚。
const MACD_HIST_UP = COLORS.up;          // 正且增強 → 濃紅
const MACD_HIST_UP_FADE = '#f7a8a8';     // 正但縮小 → 淡紅（亮）
const MACD_HIST_DN = COLORS.down;        // 負且增強 → 濃綠
const MACD_HIST_DN_FADE = '#c4f5d6';     // 負但縮小 → 淡綠（亮薄荷,與濃綠拉開明度）
// cur=本根 hist,prev=前一根 hist（warm-up 為 null,視為增強）。
function macdHistColor(cur, prev) {
  if (cur >= 0) return (prev == null || cur >= prev) ? MACD_HIST_UP : MACD_HIST_UP_FADE;
  return (prev == null || cur <= prev) ? MACD_HIST_DN : MACD_HIST_DN_FADE;
}
// 主圖 6 條均線（SMA(close)），週期/顏色仿 screener-ui。mini 1H 圖也共用此定義。
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
const IND_VWAP = { color: '#ffd740' };   // VWAP 成交量加權均價（黃，虛線中斷線）
// 600MA：MA Turn 副圖預判的那條均線本體（MATURN_TF×MATURN_PERIOD = 5×120 = 600 分）。
// 用與副圖相同的 bucket 基準計算，故均線的轉向點恰對齊副圖柱狀過零。預設開。
const IND_MA600 = { color: '#e040fb' };  // 600分MA（亮紫）
// 昨日 / 前日「日盤 VWAP 收盤值」水平線：標在今日行情上，看今日開盤是否落在此區間。皆虛線。
// 同色系（黃），用透明度表達新舊：愈舊愈淡 → 昨日(近)較實、前日(舊)較透；深色底下也讓較近的較顯眼。
const PREV_VWAP = { prev1: 'rgba(255, 209, 64, 0.95)', prev2: 'rgba(255, 209, 64, 0.42)' };  // 昨日 / 前日
const PIVOT_LEN = 5;                     // pivot high/low 左右窗格根數
const PIVOT_LEGEND_COLOR = '#ff9800';    // legend 開關代表色（橘）
const PIVOT_HIGH_COLOR = '#ff7043';      // pivot high marker（橘紅，畫在上方）
const PIVOT_LOW_COLOR = '#42a5f5';       // pivot low marker（藍，畫在下方）
// ORB（開盤區間突破）：每交易日 08:45–08:57 為區間，08:58–09:15 收盤嚴格突破標記。
// 上、下各取窗內第一根突破；區間高低各畫一條水平線（延伸到 09:15）。
const ORB_RANGE_START = 525;   // 08:45（一日內分鐘數）
const ORB_RANGE_END = 537;     // 08:57（含）
const ORB_BREAK_START = 538;   // 08:58
const ORB_BREAK_END = 555;     // 09:15（含）
const ORB_HIGH_COLOR = '#ef4444';   // 區間高（紅，台灣慣例）
const ORB_LOW_COLOR = '#22c55e';    // 區間低（綠）
const ORB_LEGEND_COLOR = '#d4a574'; // legend 開關代表色
// 關卡觸及標示（從覆盤 overlay 抽出的獨立指標）：選定日多/空各階首觸。用自訂 primitive 畫
// 圓點+階數文字（v5 marker 無 offset，故自繪以拉開與 K 棒的距離）。
const TOUCH_BULL_COLOR = '#e0623d'; // 多方觸及（橘紅，畫下方）
const TOUCH_BEAR_COLOR = '#3d9e6a'; // 空方觸及（綠，畫上方）
const TOUCH_GAP = 14;               // 文字距圓點（關卡價）的像素間距（CSS px，往外側拉開）
const TOUCH_RADIUS = 4;             // 圓點半徑（CSS px）
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
  indMa600: localStorage.getItem('cu.indMa600') !== '0', // 600分MA（對齊 MA Turn 副圖，預設開）
  indPrevVwap: localStorage.getItem('cu.indPrevVwap') !== '0', // 昨/前日 日盤 VWAP 收盤水平線（預設開）
  indBB: localStorage.getItem('cu.indBB') === '1',       // 主圖布林通道上下帶（預設關）
  indPivot: localStorage.getItem('cu.indPivot') === '1', // pivot high/low（預設關）
  indOrb: localStorage.getItem('cu.indOrb') === '1',     // ORB 開盤區間突破（預設關）
  indTouch: localStorage.getItem('cu.indTouch') !== '0', // 關卡觸及標示（預設開）
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
  if (markerState.legSeries) { try { chartState.chart.removeSeries(markerState.legSeries); } catch (_) {} markerState.legSeries = null; }
  if (chartState.reviewDate) { chartState.reviewDate = null; if (reviewReqUpdate) reviewReqUpdate(); }  // 覆盤時間線跟著清
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
  if (state.list && state.list.entry_marker === false) return;  // 清單關閉 generic「進」箭頭（如 ORB，指標自帶標記）
  // 『所有交易日』項目只有 time、無交易資訊 → 不畫 marker。
  const hasTrade = item.side || item.entry != null || item.exit_time != null
    || (item.levels && item.levels.length) || (item.legPoints && item.legPoints.length);
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
  // 斜線 leg overlay（P0→P1→P2→…）：item.legPoints = [[time_str, price], ...]
  if (item.legPoints && item.legPoints.length >= 2) {
    const seen = new Set();
    const pts = [];
    for (const [ts, pr] of item.legPoints) {
      const bt = nearestBarTime(localToEpoch(ts));
      if (bt != null && pr != null && !seen.has(bt)) { seen.add(bt); pts.push({ time: bt, value: +pr }); }
    }
    pts.sort((a, b) => a.time - b.time);
    if (pts.length >= 2) {
      markerState.legSeries = chartState.chart.addSeries(LightweightCharts.LineSeries, {
        color: '#ff8c1a', lineWidth: 2, priceLineVisible: false, lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      markerState.legSeries.setData(pts);
    }
  }
}

// 覆盤 overlay：09:30/10:30/11:30 時間線（垂直虛線，由 reviewLinesPrimitive 自繪）。
// 關卡觸及標示已抽成獨立指標 applyTouchMarkers。
// 不自行 clearMarkers（由呼叫端 maybeDrawReview 清）；intraday 才畫。
function drawReviewOverlay(d) {
  if (state.tf === '1d' || !chartState.candle) return;
  if (!d) return;
  chartState.reviewDate = d.date;                  // 'YYYY-MM-DD'；reviewLinesPrimitive 據此畫線
  if (reviewReqUpdate) reviewReqUpdate();
}

// 關卡觸及標示（獨立指標，預設開）：選定日(window._dayStats)多/空各階首觸。顯示每一個有觸及
// 的關卡（L1–L5）。anchor.price = 該階關卡投射價（t.price）→ touchLinesPrimitive 把圓點畫在
// 關卡價上，階數文字往外側（多往上/空往下）拉開 TOUCH_GAP。需 bars 與 _dayStats 都就緒。
function applyTouchMarkers() {
  const d = window._dayStats;
  const bars = chartState.bars;
  const anchors = [];
  if (state.indTouch && state.tf !== '1d' && d && d.touches && bars && bars.length) {
    for (const t of (d.touches.bull || [])) {
      const bt = nearestBarTime(localToEpoch(`${d.date} ${t.time}:00`));
      if (bt != null && t.price != null) anchors.push({ time: bt, price: t.price, side: 'bull', label: t.level });
    }
    for (const t of (d.touches.bear || [])) {
      const bt = nearestBarTime(localToEpoch(`${d.date} ${t.time}:00`));
      if (bt != null && t.price != null) anchors.push({ time: bt, price: t.price, side: 'bear', label: t.level });
    }
  }
  chartState.touchAnchors = anchors;
  if (touchReqUpdate) touchReqUpdate();
}

// 在 bars 與 daystats 都就緒時，畫覆盤 overlay（09:30/10:30/11:30 時間線）。
// 時間線是當日時間格線、與交易 marker 無關，故所有清單一律畫（含 ORB 等交易清單）；
// 只有「非交易項」才順手 clearMarkers，交易項的 marker 由 drawTradeMarkers 畫、勿清。
function maybeDrawReview() {
  if (state.tf === '1d' || !chartState.candle) return;
  if (!chartState.bars || !chartState.bars.length) return;
  if (!window._dayStats) return;
  const it = window._pendingItem;
  const hasTrade = it && (it.side || it.entry != null || it.exit_time != null
    || (it.levels && it.levels.length));
  if (!hasTrade) clearMarkers();
  drawReviewOverlay(window._dayStats);
}

function pad2(n) { return String(n).padStart(2, '0'); }

function applyMaVisibility() {
  if (chartState.maSeries) chartState.maSeries.forEach((s, k) => s.applyOptions({ visible: state.maOn[k] }));
  if (chartState.ind5maSeries) chartState.ind5maSeries.applyOptions({ visible: state.ind5ma });
  (chartState.vwapSegs || []).forEach((s) => s.applyOptions({ visible: state.indVwap }));
  if (chartState.indMa600Series) chartState.indMa600Series.applyOptions({ visible: state.indMa600 });
  if (chartState.bbUpperSeries) chartState.bbUpperSeries.applyOptions({ visible: state.indBB });
  if (chartState.bbLowerSeries) chartState.bbLowerSeries.applyOptions({ visible: state.indBB });
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

// EMA（指數移動平均）；以首值為種子,逐根遞推。values 皆為數字（無 null）。
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
// EMA 以首值為種子,前段為暖機期、值不可靠,故暖機期填 null（caller 以 flatMap 略過）:
// dif 自 index slow-1 起有效;dea/hist 自 index slow+signal-2 起有效。
function computeMACD(closes, fast = 12, slow = 26, signal = 9) {
  const emaFast = ema(closes, fast);
  const emaSlow = ema(closes, slow);
  const difFull = closes.map((_, i) => emaFast[i] - emaSlow[i]);
  const deaFull = ema(difFull, signal);
  const difStart = slow - 1;
  const deaStart = slow + signal - 2;
  const dif = difFull.map((v, i) => (i >= difStart ? v : null));
  const dea = deaFull.map((v, i) => (i >= deaStart ? v : null));
  const hist = difFull.map((v, i) => (i >= deaStart ? v - deaFull[i] : null));
  return { dif, dea, hist };
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

// 各交易日「日盤 VWAP 收盤值」：只累積日盤(08:45–13:45) typical price×量，回傳 date→當日最終 VWAP。
// 與主圖 VWAP 同義，但獨立於 session 模式（full 盤也只取日盤段），供畫昨/前日水平線。
function dayVwapCloses(bars) {
  const out = {};
  const acc = {};
  for (const b of bars) {
    if (typeof b.time === 'string') continue;     // 日線無 intraday
    if (!isDayTod(b.time)) continue;              // 只取日盤段
    const d = epochDate(b.time);
    const a = acc[d] || (acc[d] = { pv: 0, v: 0 });
    const tp = (b.high + b.low + b.close) / 3;
    const vol = b.volume || 0;
    a.pv += tp * vol;
    a.v += vol;
    out[d] = a.v > 0 ? a.pv / a.v : tp;
  }
  return out;
}

// VWAP 每日一條 series 的樣式（黃色虛線、主圖右軸）。LWC v5 單一 line series 無法在 whitespace
// 斷線，故每個交易日各建一條 series 來達成「換日斷開」。
function _vwapSegOpts() {
  return {
    color: IND_VWAP.color, lineWidth: 2, priceScaleId: 'right',
    lineStyle: LightweightCharts.LineStyle.Dashed,
    priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
    priceFormat: { type: 'price', precision: 0, minMove: 1 },
  };
}

// 依交易日把 VWAP 切段，每段建立獨立 LineSeries → 換日自然斷開。每次 loadKline 先清舊段再重建。
function setVwapSegments(bars, arr) {
  const chart = chartState.chart;
  for (const s of chartState.vwapSegs || []) { try { chart.removeSeries(s); } catch (_) { /* noop */ } }
  chartState.vwapSegs = [];
  const groups = [];
  let cur = null, curDay = null;
  for (let i = 0; i < bars.length; i++) {
    if (arr[i] == null) continue;
    const b = bars[i];
    const day = typeof b.time === 'string' ? b.time : dayKey(b.time);
    if (day !== curDay) { curDay = day; cur = []; groups.push(cur); }
    cur.push({ time: b.time, value: arr[i] });
  }
  for (const pts of groups) {
    const s = chart.addSeries(LightweightCharts.LineSeries, _vwapSegOpts());
    s.applyOptions({ visible: state.indVwap });
    s.setData(pts);
    chartState.vwapSegs.push(s);
  }
}

// state.tf（'1m'..'60m'、'1d'）→ 分鐘數。
function tfMinutes(tf) {
  if (tf === '1d') return 1440;
  const m = /^(\d+)m$/.exec(tf || '');
  return m ? parseInt(m[1], 10) : 1;
}

// MA Turn 柱狀 + 對應 600分MA：在固定較高週期 bucketMin = max(MATURN_TF, 主圖週期) 上算，
// 仿原 pine 的 request.security("5", …)。主圖週期 > 設定週期時退化為逐根 bucket。
//   hist = 現價 − 扣抵值（period 個 bucket 前已收 bucket 的收盤）= 該週期 SMA 斜率 × period
//   ma   = SMA(period)：發展中那根收盤(=現價) + 前 (period−1) 個已收 bucket 收盤，平均
// 兩者同基準 → ma 的轉向點恰對齊 hist 過零。回傳 { hist, ma }（皆對齊顯示 K 的索引）。
function maTurnCompute(bars, periodN) {
  const bucketSec = Math.max(MATURN_TF, tfMinutes(state.tf)) * 60;
  const keyOf = (b) => (typeof b.time === 'string' ? b.time : Math.floor(b.time / bucketSec));
  const ordinal = new Map();     // bucket key → 出現順序
  const finalClose = new Map();  // bucket key → 該 bucket 最後收盤
  const order = [];
  for (const b of bars) {
    const k = keyOf(b);
    if (!ordinal.has(k)) { ordinal.set(k, order.length); order.push(k); }
    finalClose.set(k, b.close);
  }
  // 依序各 bucket 收盤的前綴和，供 SMA 區段求和
  const pref = new Array(order.length + 1).fill(0);
  for (let k = 0; k < order.length; k++) pref[k + 1] = pref[k] + finalClose.get(order[k]);
  const hist = new Array(bars.length).fill(null);
  const ma = new Array(bars.length).fill(null);
  for (let i = 0; i < bars.length; i++) {
    const g = ordinal.get(keyOf(bars[i]));
    if (g - periodN >= 0) hist[i] = bars[i].close - finalClose.get(order[g - periodN]);
    if (g - (periodN - 1) >= 0) ma[i] = (bars[i].close + (pref[g] - pref[g - (periodN - 1)])) / periodN;
  }
  return { hist, ma };
}

// 畫昨日(prev1,暗黃)/前日(prev2,淡黃)的日盤 VWAP 收盤虛線（createPriceLine，全寬+右軸標籤）。
// 值由 loadKline 算好存 chartState.prevVwapClose1/2；關閉或日線時只清除不畫。
function applyPrevVwapLines() {
  if (!chartState.candle) return;
  for (const pl of chartState.prevVwapLines || []) {
    try { chartState.candle.removePriceLine(pl); } catch (_) {}
  }
  chartState.prevVwapLines = [];
  if (!state.indPrevVwap || state.tf === '1d') return;
  const mk = (price, color, title) => {
    if (price == null) return;
    chartState.prevVwapLines.push(chartState.candle.createPriceLine({
      price, color, lineStyle: LightweightCharts.LineStyle.Dashed, lineWidth: 1,
      axisLabelVisible: true, title,
    }));
  };
  mk(chartState.prevVwapClose1, PREV_VWAP.prev1, '昨VWAP');
  mk(chartState.prevVwapClose2, PREV_VWAP.prev2, '前VWAP');
}

// Pivot high/low：以左右各 len 根為窗格。比較採不對稱平手規則 → 平台（等高/等低）取「最後一根」：
//   pivot high：左側須嚴格較低（>），右側允許相等（>=）→ 等高平台只有最後一根成立。
//   pivot low ：左側須嚴格較高（<），右側允許相等（<=）→ 等低平台只有最後一根成立。
// 歷史重播下可直接看完整資料判斷，不需等右側確認；marker 畫在 pivot 當根。
function computePivotMarkers(bars, len) {
  const marks = [];
  for (let i = len; i < bars.length - len; i++) {
    const h = bars[i].high, l = bars[i].low;
    let isHigh = true, isLow = true;
    for (let j = i - len; j <= i + len; j++) {
      if (j === i) continue;
      const left = j < i;
      if (left ? bars[j].high > h : bars[j].high >= h) isHigh = false;
      if (left ? bars[j].low < l : bars[j].low <= l) isLow = false;
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

// ORB：每交易日 08:45–08:57 區間，08:58–09:15 收盤嚴格突破。上、下各取窗內第一根。
// 回傳 windows（dayKey→{left,right,hi,lo}：區間高低 + 08:45–09:15 視窗左右界 bar time，供
// 自訂 primitive 畫每日獨立水平線段）、markers（突破當根箭頭）。線段用 primitive 而非 LineSeries：
// v5 LineSeries 會把 whitespace 直接連成斜線（不斷開），故改用 canvas 逐日畫。
function computeOrb(bars) {
  const n = bars.length;
  const windows = {};
  const markers = [];
  let i = 0;
  while (i < n) {
    if (typeof bars[i].time === 'string') { i++; continue; }   // 日線無 intraday
    const dk = dayKey(bars[i].time);
    let j = i;
    while (j < n && typeof bars[j].time !== 'string' && dayKey(bars[j].time) === dk) j++;
    // [i, j) 為同一交易日；先求區間高低
    let hi = -Infinity, lo = Infinity, hasRange = false;
    for (let k = i; k < j; k++) {
      const m = todMin(bars[k].time);
      if (m >= ORB_RANGE_START && m <= ORB_RANGE_END) {
        if (bars[k].high > hi) hi = bars[k].high;
        if (bars[k].low < lo) lo = bars[k].low;
        hasRange = true;
      }
    }
    if (hasRange) {
      let left = null, right = null;
      let longDone = false, shortDone = false;
      for (let k = i; k < j; k++) {
        const m = todMin(bars[k].time);
        if (m >= ORB_RANGE_START && m <= ORB_BREAK_END) {   // 線段視窗 08:45–09:15
          if (left == null) left = bars[k].time;
          right = bars[k].time;
        }
        if (m < ORB_BREAK_START || m > ORB_BREAK_END) continue;
        const c = bars[k].close;
        if (!longDone && c > hi) {                        // 標示進場價=突破當根收盤
          markers.push({ time: bars[k].time, position: 'belowBar', shape: 'arrowUp', color: ORB_HIGH_COLOR, text: `多突破 ${Math.round(c)}` });
          longDone = true;
        }
        if (!shortDone && c < lo) {
          markers.push({ time: bars[k].time, position: 'aboveBar', shape: 'arrowDown', color: ORB_LOW_COLOR, text: `空突破 ${Math.round(c)}` });
          shortDone = true;
        }
      }
      windows[dk] = { left, right, hi, lo };
    }
    i = j;
  }
  markers.sort((a, b) => a.time - b.time);
  return { windows, markers };
}

// 套用 ORB 突破 marker（獨立 handle）；關閉時清空。
function applyOrbMarkers() {
  if (!chartState.candle) return;
  const marks = state.indOrb ? (chartState.orbMarks || []) : [];
  chartState.orbMarkersHandle = chartState.orbMarkersHandle
    ? (chartState.orbMarkersHandle.setMarkers(marks), chartState.orbMarkersHandle)
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
  chartState.candle.attachPrimitive(reviewLinesPrimitive);    // 覆盤時間線 09:30/10:30/11:30
  chartState.candle.attachPrimitive(orbLinesPrimitive);       // ORB 區間高/低水平線段
  chartState.candle.attachPrimitive(touchLinesPrimitive);     // 關卡觸及圓點+階數
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
  // VWAP：黃色虛線、每交易日斷開。LWC v5 單一 line series 在 whitespace 不會斷，故改「每日一條
  // series」(見 setVwapSegments)，在 loadKline 動態建立，存於 chartState.vwapSegs。
  chartState.vwapSegs = [];
  chartState.indMa600Series = chart.addSeries(LightweightCharts.LineSeries, _indOpts(IND_MA600.color));
  // 布林通道上下帶（主圖右軸；只有兩條，無中線）
  const _bbBandOpts = {
    color: BB_BAND_COLOR, lineWidth: 1, priceScaleId: 'right',
    priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
    priceFormat: { type: 'price', precision: 0, minMove: 1 },
  };
  chartState.bbUpperSeries = chart.addSeries(LightweightCharts.LineSeries, _bbBandOpts);
  chartState.bbLowerSeries = chart.addSeries(LightweightCharts.LineSeries, _bbBandOpts);
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
  // 延伸力 EXT 副圖（盤中 open-anchor，預測關卡達成；H095/H111/H112）。
  //   pane 3 = ext_long（龍頭推力，漲紅）；pane 4 = ext_short（廣度，跌綠）。
  //   0 軸 + 強門檻虛線（ext_long≥+0.10、ext_short(z-sum)≥+1.2，看盤用）。
  chartState.extLong = chart.addSeries(
    LightweightCharts.LineSeries,
    { color: COLORS.up, lineWidth: 2, priceScaleId: 'extlong',
      priceLineVisible: false, lastValueVisible: false,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 } },
    3,
  );
  chartState.extLong.createPriceLine({ price: 0, color: MATURN_ZERO_COLOR, lineWidth: 1,
    lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: '0' });
  chartState.extLong.createPriceLine({ price: EXT_STRONG_LONG, color: COLORS.up, lineWidth: 1,
    lineStyle: LightweightCharts.LineStyle.Dotted, axisLabelVisible: true, title: '強' });
  chart.priceScale('extlong').applyOptions({ scaleMargins: { top: 0.2, bottom: 0.1 } });
  chartState.extShort = chart.addSeries(
    LightweightCharts.LineSeries,
    { color: COLORS.down, lineWidth: 2, priceScaleId: 'extshort',
      priceLineVisible: false, lastValueVisible: false,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 } },
    4,
  );
  // 顯示翻轉（畫 −ext_short）：下殺燃料↑ → 線往下，與走勢同相、好讀。強空門檻落在 −1.2。
  chartState.extShort.createPriceLine({ price: 0, color: MATURN_ZERO_COLOR, lineWidth: 1,
    lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: '0' });
  chartState.extShort.createPriceLine({ price: -EXT_STRONG_SHORT, color: COLORS.down, lineWidth: 1,
    lineStyle: LightweightCharts.LineStyle.Dotted, axisLabelVisible: true, title: '強空' });
  chart.priceScale('extshort').applyOptions({ scaleMargins: { top: 0.2, bottom: 0.1 } });
  // 副圖高度：主圖放大、量/%B/延伸力副圖縮小（pane 0 主圖佔大宗）。
  try {
    const panes = chart.panes();
    const stretch = [12, 2, 2.5, 2.5, 2.5];   // main, vol, bb, extLong, extShort
    panes.forEach((p, i) => { if (stretch[i] != null) p.setStretchFactor(stretch[i]); });
  } catch (_) { /* 舊版 lib 無 panes API 則略過 */ }
  chart.subscribeCrosshairMove((param) => updateLegend(param));
  chart.subscribeClick((param) => onChartClick(param));
  const wrap = document.querySelector('.chart-wrap');
  if (wrap) new ResizeObserver(() => {
    positionPaneLegend(document.getElementById('vol-legend'), 1);
    positionPaneLegend(document.getElementById('bb-legend'), 2);
    positionPaneLegend(document.getElementById('extlong-legend'), 3);
    positionPaneLegend(document.getElementById('extshort-legend'), 4);
  }).observe(wrap);
}

// ── 左側參考圖（唯讀,獨立 state）：1D 在上、1H 在下,共用 createMiniChart/drawMiniSeries ──
const miniChartState = { chart: null, candle: null, maSeries: null, hist: null, dif: null, dea: null, bars: [] };  // 1H（含夜盤）
const miniDayState   = { chart: null, candle: null, maSeries: null, hist: null, dif: null, dea: null, bars: [] };  // 1D（日線）
const MINI_DAY_VISIBLE_BARS = 45;    // 日線預設顯示根數（約 9 週;側欄窄,根數多會太擠）

// === mini 圖盤別分界垂直虛線：日盤起點 08:45 + 夜盤起點 15:00 ===
// 1H 全日盤 resample 後,日盤開盤那根落在 08:00 桶（含 08:45）,夜盤起點為 15:00 整點。
// 線畫在該根左緣（x - half）,剛好落在盤別交界、不穿過 K 棒。
let miniSessionReqUpdate = null;
const MINI_DAY_OPEN_COLOR = '#4a80c0';    // 日盤起點 08:45
const MINI_NIGHT_OPEN_COLOR = '#b08442';  // 夜盤起點 15:00
const MINI_DAY_OPEN_TOD = 480;            // 08:00 桶（含 08:45 開盤的那根）
const MINI_NIGHT_OPEN_TOD = 900;          // 15:00

const _miniSessionRenderer = {
  draw(target) {
    const chart = miniChartState.chart;
    const bars = miniChartState.bars || [];
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
      for (let i = lo; i <= hi; i++) {
        const tod = todMin(bars[i].time);
        const color = tod === MINI_DAY_OPEN_TOD ? MINI_DAY_OPEN_COLOR
          : tod === MINI_NIGHT_OPEN_TOD ? MINI_NIGHT_OPEN_COLOR : null;
        if (!color) continue;
        const x = ts.timeToCoordinate(bars[i].time);
        if (x == null) continue;
        const px = Math.round((x - half) * hpr);
        ctx.strokeStyle = color;
        ctx.beginPath();
        ctx.moveTo(px, 0);
        ctx.lineTo(px, h);
        ctx.stroke();
      }
      ctx.restore();
    });
  },
};
const _miniSessionPaneView = { renderer() { return _miniSessionRenderer; }, zOrder() { return 'top'; } };
const miniSessionLinesPrimitive = {
  attached(p) { miniSessionReqUpdate = p.requestUpdate; },
  detached() { miniSessionReqUpdate = null; },
  updateAllViews() {},
  paneViews() { return [_miniSessionPaneView]; },
};

// 共用：建立一張唯讀 mini 圖（candle + 6MA + MACD 雙 pane）。回傳 state 物件;el 不存在回 null。
function createMiniChart(elId) {
  const el = document.getElementById(elId);
  if (!el) return null;
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
  const st = { chart, candle: null, maSeries: null, hist: null, dif: null, dea: null, bars: [] };
  st.candle = chart.addSeries(LightweightCharts.CandlestickSeries, {
    upColor: COLORS.up, downColor: COLORS.down,
    borderUpColor: COLORS.up, borderDownColor: COLORS.down,
    wickUpColor: COLORS.wick, wickDownColor: COLORS.wick,
    priceLineVisible: false, lastValueVisible: false,
    priceFormat: { type: 'price', precision: 0, minMove: 1 },
  });
  // 主 pane 6 條均線（沿用主圖 MA_DEFS 的週期/顏色,畫在 K 線之上,同右軸）
  st.maSeries = MA_DEFS.map((d) => chart.addSeries(LightweightCharts.LineSeries, {
    color: d.color, lineWidth: 1, priceScaleId: 'right',
    priceLineVisible: false, lastValueVisible: false,
    priceFormat: { type: 'price', precision: 0, minMove: 1 },
  }));
  // MACD 副圖（pane 1）:柱(漲紅跌綠) + DIF + DEA
  st.hist = chart.addSeries(LightweightCharts.HistogramSeries,
    { color: COLORS.up, priceScaleId: 'macd', priceLineVisible: false, lastValueVisible: false }, 1);
  st.dif = chart.addSeries(LightweightCharts.LineSeries,
    { color: COLORS.accent, lineWidth: 1, priceScaleId: 'macd', priceLineVisible: false, lastValueVisible: false }, 1);
  st.dea = chart.addSeries(LightweightCharts.LineSeries,
    { color: MACD_DEA_COLOR, lineWidth: 1, priceScaleId: 'macd', priceLineVisible: false, lastValueVisible: false }, 1);
  chart.priceScale('macd').applyOptions({ scaleMargins: { top: 0.1, bottom: 0.1 } });
  return st;
}

// 共用：把 bars 畫到 mini 圖（candle + 6MA + MACD,沿用 warm-up null-skip）。
function drawMiniSeries(st, bars) {
  st.bars = bars;
  st.candle.setData(bars.map((b) => ({
    time: b.time, open: b.open, high: b.high, low: b.low, close: b.close,
  })));
  const closes = bars.map((b) => b.close);
  MA_DEFS.forEach((d, k) => {
    const arr = sma(closes, d.p);
    st.maSeries[k].setData(bars.flatMap((b, i) => (arr[i] != null ? [{ time: b.time, value: arr[i] }] : [])));
  });
  if (bars.length >= MACD_MIN_BARS) {
    const { dif, dea, hist } = computeMACD(closes);
    st.dif.setData(bars.flatMap((b, i) => (dif[i] != null ? [{ time: b.time, value: dif[i] }] : [])));
    st.dea.setData(bars.flatMap((b, i) => (dea[i] != null ? [{ time: b.time, value: dea[i] }] : [])));
    st.hist.setData(bars.flatMap((b, i) => (hist[i] != null
      ? [{ time: b.time, value: hist[i], color: macdHistColor(hist[i], hist[i - 1]) }]
      : [])));
  } else {                                           // 資料不足以算 MACD → 留空,K 線照畫
    st.dif.setData([]);
    st.dea.setData([]);
    st.hist.setData([]);
  }
}

// 建立 1D（上）+ 1H（下）兩張 mini 圖;只有 1H 掛盤別分界線（日線無盤中時段）。
function initMiniCharts() {
  const d = createMiniChart('mini-chart-d');
  if (d) Object.assign(miniDayState, d);
  const h = createMiniChart('mini-chart');
  if (h) {
    Object.assign(miniChartState, h);
    miniChartState.candle.attachPrimitive(miniSessionLinesPrimitive);   // 日盤/夜盤起點分界線
  }
}

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
    console.warn('mini 1H 圖載入失敗:', e);          // 維持上一次內容,不丟給主圖
    return;
  }
  drawMiniSeries(miniChartState, bars);
  // 預設顯示最近約 60 根 1H K(含夜盤 ≈ 3 個交易日);右側留 2 根 padding。
  const n = bars.length;
  miniChartState.chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - 60), to: n - 1 + 2 });
  if (miniSessionReqUpdate) miniSessionReqUpdate();  // 重畫盤別分界線
}

// 載入 mini 1D 圖:tf=1d、session=full(含夜盤),adjust 跟主圖;後端回全歷史日線,
// 畫全部後把視窗對齊到 centerDate、往前顯示 MINI_DAY_VISIBLE_BARS 根。唯讀,失敗不影響主圖。
async function loadMiniDayChart(centerDate, adjust) {
  if (!miniDayState.chart || !centerDate) return;
  const p = new URLSearchParams({ tf: '1d', session: 'full', adjust });
  let bars;
  try {
    bars = await fetchJSON(`/api/kline?${p}`);
  } catch (e) {
    console.warn('mini 1D 圖載入失敗:', e);
    return;
  }
  drawMiniSeries(miniDayState, bars);
  // 視窗對齊 centerDate（日線 time 為 'YYYY-MM-DD' 字串,可直接比較）。
  let idx = bars.findIndex((b) => b.time >= centerDate);
  if (idx < 0) idx = bars.length - 1;
  miniDayState.chart.timeScale().setVisibleLogicalRange({
    from: Math.max(0, idx - MINI_DAY_VISIBLE_BARS), to: idx + 2,
  });
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
  const extL = document.getElementById('extlong-legend');
  const extS = document.getElementById('extshort-legend');
  const bars = chartState.bars || [];
  if (!bars.length) { for (const e of [main, vol, bb, extL, extS]) if (e) e.innerHTML = ''; return; }
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
    const indMa600 = indTog(state.indMa600, 'ma600', '600MA', IND_MA600.color, chartState.ma600Arr);
    // 昨/前日 日盤 VWAP 收盤（值固定、非隨 hover；無前一日資料 → —）
    const pvw = !state.indPrevVwap
      ? `<span class="ind-toggle ma-off" data-toggle="pvwap">昨/前VWAP</span>`
      : `<span class="ind-toggle" data-toggle="pvwap" style="color:${PREV_VWAP.prev1}">昨VWAP`
        + `${chartState.prevVwapClose1 != null ? ' ' + r(chartState.prevVwapClose1) : ' —'}</span>`
        + ` · <span style="color:${PREV_VWAP.prev2}">前VWAP`
        + `${chartState.prevVwapClose2 != null ? ' ' + r(chartState.prevVwapClose2) : ' —'}</span>`;
    // 布林通道：開啟時顯示 hover 那根的上/下帶值
    const bbU = chartState.bbUpArr ? chartState.bbUpArr[idx] : null;
    const bbL = chartState.bbLoArr ? chartState.bbLoArr[idx] : null;
    const indBB = state.indBB
      ? `<span class="ind-toggle" data-toggle="bbband" style="color:${BB_BAND_COLOR}">BB(${BB_LEN},${BB_MULT})</span>`
        + (bbU != null ? ` 上 ${r(bbU)} · 下 ${r(bbL)}` : ' <span class="muted">—</span>')
      : `<span class="ind-toggle ma-off" data-toggle="bbband">BB(${BB_LEN},${BB_MULT})</span>`;
    const indPiv = indTog(state.indPivot, 'pivot', `Pivot${PIVOT_LEN}`, PIVOT_LEGEND_COLOR, null);
    // ORB：開啟時顯示 hover 那根所屬交易日的區間高/低
    const orbDk = typeof b.time === 'string' ? null : dayKey(b.time);
    const orbRange = orbDk != null && chartState.orbWindows ? chartState.orbWindows[orbDk] : null;
    let indOrb;
    if (!state.indOrb) {
      indOrb = `<span class="ind-toggle ma-off" data-toggle="orb">ORB</span>`;
    } else if (orbRange) {
      indOrb = `<span class="ind-toggle" data-toggle="orb" style="color:${ORB_LEGEND_COLOR}">ORB</span>`
        + ` <span style="color:${ORB_HIGH_COLOR}">高 ${r(orbRange.hi)}</span>`
        + ` · <span style="color:${ORB_LOW_COLOR}">低 ${r(orbRange.lo)}</span>`;
    } else {
      indOrb = `<span class="ind-toggle" data-toggle="orb" style="color:${ORB_LEGEND_COLOR}">ORB</span> <span class="muted">—</span>`;
    }
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
    // 關卡觸及：選定日 touches 的多/空觸及數（不隨 hover 變）
    const tch = window._dayStats && window._dayStats.touches;
    const nTouch = tch ? ((tch.bull || []).length + (tch.bear || []).length) : 0;
    const indTouch = state.indTouch
      ? `<span class="ind-toggle" data-toggle="touch" style="color:${TOUCH_BULL_COLOR}">關卡觸及${nTouch ? ` ${nTouch}` : ''}</span>`
      : `<span class="ind-toggle ma-off" data-toggle="touch">關卡觸及</span>`;
    const maLine = `${master}　${perMa}`;
    const indLine = `${ind5}　${indMa600}<br>${indV}<br>${pvw}<br>${indBB}<br>${indPiv}<br>${indOrb}<br>${indTouch}<br>${indRisk}`;   // 5MA+600MA / VWAP / 昨前VWAP / BB / Pivot / ORB / 關卡觸及 / Risk 各自獨立一行
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
  const ext = (chartState.extMap && chartState.extMap.get(b.time)) || null;
  if (extL) {
    positionPaneLegend(extL, 3);
    const v = ext ? ext.ext_long : null;
    const strong = v != null && v >= EXT_STRONG_LONG;
    const cls = v == null ? 'muted' : (v > 0 ? 'up' : 'down');
    extL.innerHTML = `<span style="color:${COLORS.up}">延伸力·多(W10)</span> `
      + `<span class="${cls}">${v == null ? '—' : (v >= 0 ? '+' : '') + v.toFixed(2)}${strong ? ' 強' : ''}</span>`;
  }
  if (extS) {
    positionPaneLegend(extS, 4);
    const raw = ext ? ext.ext_short : null;
    const v = raw == null ? null : -raw;                       // 翻轉顯示（負=空方燃料/偏空）
    const strong = v != null && v <= -EXT_STRONG_SHORT;        // 強空
    const cls = v == null ? 'muted' : (v < 0 ? 'down' : 'up');
    extS.innerHTML = `<span style="color:${COLORS.down}">延伸力·空(廣度)</span> `
      + `<span class="${cls}">${v == null ? '—' : (v >= 0 ? '+' : '') + v.toFixed(2)}${strong ? ' 強空' : ''}</span>`;
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
// 一日內分鐘數（t = epoch 秒，intraday）；08:45 → 525。
function todMin(t) {
  const d = new Date(t * 1000);
  return d.getUTCHours() * 60 + d.getUTCMinutes();
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

// === 覆盤時間線（09:30 / 10:30 / 11:30 同色垂直虛線；僅覆盤日、無交易時畫）===
let reviewReqUpdate = null;
const REVIEW_COLOR = '#888';
const REVIEW_TIMES = [[570, '09:30'], [630, '10:30'], [690, '11:30']];   // 分鐘 → 標籤
const _reviewRenderer = {
  draw(target) {
    if (state.tf === '1d') return;
    const chart = chartState.chart;
    const bars = chartState.bars || [];
    const rd = chartState.reviewDate;                  // 'YYYY-MM-DD' 或 null
    if (!chart || !bars.length || !rd) return;
    const rdKey = Number(rd.slice(0, 4) + rd.slice(5, 7) + rd.slice(8, 10));
    const ts = chart.timeScale();
    const logical = ts.getVisibleLogicalRange();
    if (!logical) return;
    const lo = Math.max(0, Math.floor(logical.from));
    const hi = Math.min(bars.length - 1, Math.ceil(logical.to));
    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      const hpr = scope.horizontalPixelRatio;
      const vpr = scope.verticalPixelRatio;
      const h = scope.bitmapSize.height;
      ctx.save();
      ctx.lineWidth = Math.max(1, Math.floor(hpr));
      ctx.setLineDash([5 * hpr, 4 * hpr]);
      ctx.strokeStyle = REVIEW_COLOR;
      ctx.fillStyle = REVIEW_COLOR;
      ctx.font = `${Math.round(11 * vpr)}px sans-serif`;
      ctx.textBaseline = 'top';
      for (let i = lo; i <= hi; i++) {
        const t = bars[i].time;
        if (dayKey(t) !== rdKey) continue;
        const m = todMin(t);
        const lbl = REVIEW_TIMES.find((r) => r[0] === m);
        if (!lbl) continue;
        const x = ts.timeToCoordinate(t);
        if (x == null) continue;
        const px = Math.round(x * hpr);
        ctx.beginPath();
        ctx.moveTo(px, 0);
        ctx.lineTo(px, h);
        ctx.stroke();
        ctx.setLineDash([]);                           // 標籤文字不沿用虛線
        ctx.fillText(lbl[1], px + 3 * hpr, 3 * vpr);
        ctx.setLineDash([5 * hpr, 4 * hpr]);
      }
      ctx.restore();
    });
  },
};
const _reviewPaneView = { renderer() { return _reviewRenderer; }, zOrder() { return 'top'; } };
const reviewLinesPrimitive = {
  attached(p) { reviewReqUpdate = p.requestUpdate; },
  detached() { reviewReqUpdate = null; },
  updateAllViews() {},
  paneViews() { return [_reviewPaneView]; },
};

// === ORB 區間高/低水平線段（primitive；逐日畫，跨日不連線）===
let orbReqUpdate = null;
const _orbRenderer = {
  draw(target) {
    if (state.tf === '1d' || !state.indOrb) return;
    const chart = chartState.chart;
    const series = chartState.candle;
    const windows = chartState.orbWindows;
    if (!chart || !series || !windows) return;
    const ts = chart.timeScale();
    const half = (ts.options().barSpacing || 6) / 2;
    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      const hpr = scope.horizontalPixelRatio;
      const vpr = scope.verticalPixelRatio;
      ctx.save();
      ctx.lineWidth = Math.max(1, Math.floor(hpr));
      for (const dk in windows) {
        const w = windows[dk];
        if (w.left == null || w.right == null) continue;
        const xL = ts.timeToCoordinate(w.left);
        const xR = ts.timeToCoordinate(w.right);
        if (xL == null || xR == null) continue;
        const x1 = (xL - half) * hpr;
        const x2 = (xR + half) * hpr;
        const seg = (price, color) => {
          const y = series.priceToCoordinate(price);
          if (y == null) return;
          const py = Math.round(y * vpr);
          ctx.strokeStyle = color;
          ctx.beginPath();
          ctx.moveTo(x1, py);
          ctx.lineTo(x2, py);
          ctx.stroke();
        };
        seg(w.hi, ORB_HIGH_COLOR);
        seg(w.lo, ORB_LOW_COLOR);
      }
      ctx.restore();
    });
  },
};
const _orbPaneView = { renderer() { return _orbRenderer; }, zOrder() { return 'top'; } };
const orbLinesPrimitive = {
  attached(p) { orbReqUpdate = p.requestUpdate; },
  detached() { orbReqUpdate = null; },
  updateAllViews() {},
  paneViews() { return [_orbPaneView]; },
};

// === 關卡觸及圓點+階數（primitive；自繪以拉開文字與 K 棒的距離）===
let touchReqUpdate = null;
const _touchRenderer = {
  draw(target) {
    if (state.tf === '1d' || !state.indTouch) return;
    const chart = chartState.chart;
    const series = chartState.candle;
    const anchors = chartState.touchAnchors;
    if (!chart || !series || !anchors || !anchors.length) return;
    const ts = chart.timeScale();
    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      const hpr = scope.horizontalPixelRatio;
      const vpr = scope.verticalPixelRatio;
      ctx.save();
      ctx.textAlign = 'center';
      ctx.font = `${Math.round(11 * vpr)}px -apple-system, sans-serif`;
      for (const a of anchors) {
        const x = ts.timeToCoordinate(a.time);
        const yLevel = series.priceToCoordinate(a.price);   // 圓點畫在關卡價上
        if (x == null || yLevel == null) continue;
        const dir = a.side === 'bull' ? -1 : 1;            // 外側方向：多在上(↑)、空在下(↓)
        const cx = x * hpr;
        const cy = yLevel * vpr;
        const color = a.side === 'bull' ? TOUCH_BULL_COLOR : TOUCH_BEAR_COLOR;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(cx, cy, TOUCH_RADIUS * vpr, 0, Math.PI * 2);
        ctx.fill();
        // 文字往外側拉開：多→圓點上方、空→圓點下方
        ctx.textBaseline = a.side === 'bull' ? 'bottom' : 'top';
        ctx.fillText(a.label, cx, cy + dir * TOUCH_GAP * vpr);
      }
      ctx.restore();
    });
  },
};
const _touchPaneView = { renderer() { return _touchRenderer; }, zOrder() { return 'top'; } };
const touchLinesPrimitive = {
  attached(p) { touchReqUpdate = p.requestUpdate; },
  detached() { touchReqUpdate = null; },
  updateAllViews() {},
  paneViews() { return [_touchPaneView]; },
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
  setVwapSegments(bars, chartState.indVwapArr);   // 每日一條 series → 換日斷開
  // 昨/前日 日盤 VWAP 收盤水平線（相對 centerDate 的前兩個交易日，皆取自已載入的 bars）
  const _vwClose = dayVwapCloses(bars);
  const _vwDates = Object.keys(_vwClose).filter((d) => d < state.centerDate).sort();
  chartState.prevVwapClose1 = _vwDates.length ? _vwClose[_vwDates[_vwDates.length - 1]] : null;
  chartState.prevVwapClose2 = _vwDates.length > 1 ? _vwClose[_vwDates[_vwDates.length - 2]] : null;
  applyPrevVwapLines();
  // Pivot high/low（左右各 PIVOT_LEN 根）
  chartState.pivotMarks = computePivotMarkers(bars, PIVOT_LEN);
  applyPivotMarkers();
  // ORB 開盤區間突破（每日區間高低線段由 orbLinesPrimitive 畫 + 突破箭頭 marker）
  const orb = computeOrb(bars);
  chartState.orbWindows = orb.windows;
  chartState.orbMarks = orb.markers;
  applyOrbMarkers();
  if (orbReqUpdate) orbReqUpdate();
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
  // 同一輪順便算主圖布林上下帶（bbUpArr/bbLoArr）。
  const bbArr = [], bbUpArr = [], bbLoArr = [];
  let bs = 0, bs2 = 0;
  for (let i = 0; i < bars.length; i++) {
    const c = bars[i].close;
    bs += c; bs2 += c * c;
    if (i >= BB_LEN) { const o = bars[i - BB_LEN].close; bs -= o; bs2 -= o * o; }
    if (i >= BB_LEN - 1) {
      const mean = bs / BB_LEN;
      const sd = Math.sqrt(Math.max(0, bs2 / BB_LEN - mean * mean));
      const up = mean + BB_MULT * sd, lo = mean - BB_MULT * sd;
      bbUpArr[i] = up; bbLoArr[i] = lo;
      bbArr[i] = up > lo ? (c - lo) / (up - lo) : null;
    } else { bbUpArr[i] = null; bbLoArr[i] = null; bbArr[i] = null; }
  }
  chartState.bbArr = bbArr;
  chartState.bbUpArr = bbUpArr;
  chartState.bbLoArr = bbLoArr;
  chartState.bb.setData(bars.flatMap((b, i) => (bbArr[i] != null ? [{ time: b.time, value: bbArr[i] }] : [])));
  chartState.bbUpperSeries.setData(bars.flatMap((b, i) => (bbUpArr[i] != null ? [{ time: b.time, value: bbUpArr[i] }] : [])));
  chartState.bbLowerSeries.setData(bars.flatMap((b, i) => (bbLoArr[i] != null ? [{ time: b.time, value: bbLoArr[i] }] : [])));
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
  // 600分MA 疊線（沿用 maTurnCompute 回傳的 ma；MA Turn 柱已移除）。
  const { ma: ma600Arr } = maTurnCompute(bars, MATURN_PERIOD);
  chartState.ma600Arr = ma600Arr;
  chartState.indMa600Series.setData(_toData(ma600Arr));
  loadExtension(state.centerDate);          // 延伸力 EXT 副圖（盤中，按日 fetch）
  focusTime(centerEpochToFocus);
  if (window._afterKline) window._afterKline();        // Task 10 掛 marker
  if (sessionReqUpdate) sessionReqUpdate();            // 觸發盤別分界線重畫
  updateLegend(null);                                  // 預設顯示最新一根
  // 左側 1H 參考圖(唯讀,固定含夜盤)。日線檢視也載入(顯示該日 1H 細節);
  // session 切換時 mini 仍抓 full,等同 no-op,不值得加 guard。
  loadMiniChart(state.centerDate, state.adjust);
  loadMiniDayChart(state.centerDate, state.adjust);
}

// 延伸力 EXT 副圖：按交易日 fetch /api/extension，設 ext_long/ext_short 兩線並存 time→值 map（legend 用）。
// 只有有 stock_min 的日子(2025-06~2026-02)有資料；其餘/日線檢視清空。
async function loadExtension(centerDate) {
  if (!chartState.extLong) return;
  const clear = () => { chartState.extLong.setData([]); chartState.extShort.setData([]); chartState.extMap = null; };
  if (!centerDate || state.tf === '1d') { clear(); return; }
  chartState.extReqDate = centerDate;                 // race guard：換日後舊回應丟棄
  let res = null;
  try { res = await fetchJSON(`/api/extension?date=${encodeURIComponent(centerDate)}`); } catch (_) { /* noop */ }
  if (chartState.extReqDate !== centerDate) return;   // 已換日
  const bars = (res && res.bars) || [];
  chartState.extLong.setData(bars.map((b) => ({ time: b.time, value: b.ext_long })));
  chartState.extShort.setData(bars.map((b) => ({ time: b.time, value: -b.ext_short })));   // 翻轉顯示
  chartState.extMap = bars.length ? new Map(bars.map((b) => [b.time, b])) : null;
  updateLegend(null);
  // ext setData 可能把主圖視窗推掉（非同步、在 focusTime 之後才回來）→ 重新對焦修正
  if (chartState._focusTarget != null) focusTime(chartState._focusTarget);
}

// 將視窗置中到某 time（epoch 或 'YYYY-MM-DD'）；找不到就顯示尾段。
function focusTime(target) {
  const bars = chartState.bars;
  if (!bars.length) return;
  chartState._focusTarget = target;   // 存下供 loadExtension 回來後重新對焦（避免 ext setData 推掉視窗）
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
  // 剛 setData 那一幀套視窗範圍常無效（lightweight-charts 坑→「點第二次才切到正確日期」）；
  // 同步套一次 + 下一幀補套一次，確保新資料就緒後生效。
  const ts = chartState.chart.timeScale();
  ts.setVisibleLogicalRange({ from, to });
  requestAnimationFrame(() => ts.setVisibleLogicalRange({ from, to }));
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
      } else if (which === 'ma600') {
        state.indMa600 = !state.indMa600;
        localStorage.setItem('cu.indMa600', state.indMa600 ? '1' : '0');
        applyMaVisibility();
        updateLegend(null);
      } else if (which === 'pvwap') {
        state.indPrevVwap = !state.indPrevVwap;
        localStorage.setItem('cu.indPrevVwap', state.indPrevVwap ? '1' : '0');
        applyPrevVwapLines();
        updateLegend(null);
      } else if (which === 'bbband') {
        state.indBB = !state.indBB;
        localStorage.setItem('cu.indBB', state.indBB ? '1' : '0');
        applyMaVisibility();
        updateLegend(null);
      } else if (which === 'pivot') {
        state.indPivot = !state.indPivot;
        localStorage.setItem('cu.indPivot', state.indPivot ? '1' : '0');
        applyPivotMarkers();
        updateLegend(null);
      } else if (which === 'orb') {
        state.indOrb = !state.indOrb;
        localStorage.setItem('cu.indOrb', state.indOrb ? '1' : '0');
        applyOrbMarkers();
        if (orbReqUpdate) orbReqUpdate();
        updateLegend(null);
      } else if (which === 'touch') {
        state.indTouch = !state.indTouch;
        localStorage.setItem('cu.indTouch', state.indTouch ? '1' : '0');
        applyTouchMarkers();
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
  initMiniCharts();
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

// 右側欄：每日統計，三組分頁排列。切換日期時更新。
//   盤前預判：20日均振幅 / 同星期振幅 / 夜盤波動 / 前一日 TWNVIX(+regime 升壓降壓 + ladder reach 期望/動作,H117)
//   盤中實況：今日日盤高低 / 加權成交金額
//   關卡操作：關卡價(達到率+觸及提示) / DCI 方向共識(含出場建議)
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
  applyTouchMarkers();
  const r = (x) => (x == null ? '—' : Math.round(x).toLocaleString());
  const ar = d.avg_range_20 || {};
  const t = d.today;
  const pv = d.prev_vix;

  const avgSec =
    `<div class="sec"><div class="sec-title">20日平均振幅</div>`
    + `<div class="kv"><span class="k">日盤</span><span class="v">${r(ar.day)}<span class="n"> n=${ar.n_day ?? 0}</span></span></div>`
    + `<div class="kv"><span class="k">全日盤</span><span class="v">${r(ar.full)}<span class="n"> n=${ar.n_full ?? 0}</span></span></div></div>`;

  const todayRangePct = (t && t.range != null && ar.day)
    ? `<span class="n"> ${Math.round(t.range / ar.day * 100)}% 20日均</span>` : '';
  const todaySec =
    `<div class="sec"><div class="sec-title">今日 ${dateWeekday(d.date)}（日盤）</div>`
    + (t
      ? `<div class="kv"><span class="k">最高</span><span class="v up">${r(t.high)}</span></div>`
        + `<div class="kv"><span class="k">最低</span><span class="v down">${r(t.low)}</span></div>`
        + `<div class="kv"><span class="k">振幅</span><span class="v">${r(t.range)}${todayRangePct}</span></div>`
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

  const vixSec = (() => {
    if (!pv) return `<div class="sec"><div class="sec-title">前一日 TWNVIX</div><div class="kv"><span class="k">—</span><span class="v">—</span></div></div>`;
    const pc = (x) => Math.round(x * 100) + '%';
    let h = `<div class="sec"><div class="sec-title">盤前 regime（前一日資料）</div>`;
    const ex = pv.extreme ? ' 🔥≥35' : '';
    h += `<div class="kv"><span class="k">${pv.date}</span><span class="v">VIX ${pv.vix.toFixed(1)}`
      + (pv.ma20 != null ? `<span class="n"> /MA20 ${pv.ma20}</span>` : '') + `<span class="n"> ${pv.level || ''}${ex}</span></span></div>`;
    if (pv.regime) {
      h += `<div class="kv"><span class="k">VIX/已實現</span><span class="v">`
        + `${pv.vix_dir || '?'} / ${pv.rv_dir || '?'} → <b>${pv.regime}</b></span></div>`;
    }
    if (pv.expect) {
      const e = pv.expect;
      h += `<div class="kv"><span class="k">深reach 多</span><span class="v">L4 ${pc(e.uL4)} · L5 ${pc(e.uL5)}</span></div>`
        + `<div class="kv"><span class="k">深reach 空</span><span class="v">L4 ${pc(e.dL4)} · L5 ${pc(e.dL5)}</span></div>`
        + `<div class="kv"><span class="k n">全體基準</span><span class="v n">L4~25% · L5~12%</span></div>`;
    }
    if (pv.note) h += `<div class="vix-note n">${pv.note}</div>`;
    return h + `</div>`;
  })();

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
      const renderExit = (adv, sideZh, cls) => {
        if (!adv) return '';
        let h = `<div class="exit-head ${cls}">${sideZh}<span class="band">（${adv.band_label}）</span></div>`;
        if (adv.note) return h + `<div class="exit-empty">${adv.note}</div>`;
        for (const s of adv.steps) {
          h += `<div class="exit-step"><span class="t">${s.t}</span>`
            + `<span class="lv ${cls}">${s.level}</span>`
            + `<span class="act">${s.action}</span></div>`;
          if (s.branches) h += s.branches.map(b => `<div class="exit-br">${b}</div>`).join('');
          if (s.note) h += `<div class="exit-note">${s.note}</div>`;
        }
        return h;
      };
      dciSec += `<div class="gap"></div><div class="exit-adv">`
        + renderExit(d.exit_advice.bull, '多', 'up')
        + renderExit(d.exit_advice.bear, '空', 'dn')
        + `</div>`;
    }
    dciSec += `</div>`;
  }

  const grp = (title) => `<div class="grp">${title}</div>`;
  el.innerHTML =
    grp('盤前預判') + avgSec + wdSec + nvSec + vixSec
    + grp('盤中實況') + todaySec + toSec
    + grp('關卡操作') + lvlSec + dciSec;
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

window._afterKline = () => { drawTradeMarkers(window._pendingItem); maybeDrawReview(); applyTouchMarkers(); };

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
