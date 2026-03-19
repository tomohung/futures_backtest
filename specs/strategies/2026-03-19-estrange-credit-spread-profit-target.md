# EstRange Credit Spread — Profit Target 提早平倉

## 1. 背景與動機

Weekday 優化（2026-03-19-estrange-options-weekday-optimization.md）定案後，策略以固定 exit_time 平倉。
但 credit spread 的獲利在時間推進中並非線性——theta 加速點因 DTE 而異：

| Day | DTE | 特性 |
|-----|-----|------|
| Mon | 2 | theta 慢，持倉到 11:30 可能只吃到一小部分 credit |
| Tue | 1 | theta 中等，11:30 前大部分 theta 已釋放 |
| Wed | 0 | theta 極快，開盤後快速衰減 |
| Fri | 0 | 同 Wed |

**問題：** 固定 exit_time 無法應對盤中已「幾乎吃滿 credit」但仍持倉承受翻轉風險的情境。
若能在達到 credit × X% 時提早平倉，可能降低 drawdown 且釋放心理壓力。

---

## 2. 假設與方向

**核心假設：** 對於 DTE≥1（Mon/Tue），提早鎖利能降低尾部風險而不顯著犧牲總收益；
DTE=0（Wed/Fri）theta 衰減快，提早出場可能反而降低收益。

**方向：** 新增 `profit_target_pct` 參數，當持倉期間未實現獲利達 `credit × profit_target_pct` 時提早平倉。

---

## 3. Step 0（探索）— Credit Capture 路徑分析

在實作 profit target 之前，先觀察現有交易的「credit capture 路徑」：

- 對每筆交易，從 touch_time 到 exit_time，每分鐘取兩腿 last price，計算 `captured_pct = (credit - debit_now) / credit`
- 畫出各 weekday 的 captured_pct 時間曲線（mean ± std）
- 觀察：各 DTE 大約在幾分鐘後 capture 50%/70%/80%/90%？

**目的：** 確認提早出場是否有「甜蜜點」——capture 已高但尚未到最大風險區。

### 實作

新增 `src/analysis/credit_capture_path.py`：
- 複用 `backtest_estrange_options.py` 的進場邏輯取得交易清單
- 對每筆交易，從 `touch_time` 到 `exit_time`，每分鐘查 `ticks_options` 取 last known price
- 輸出 CSV：`date, weekday, minute_offset, sell_price, buy_price, debit, captured_pct`
- 列印 weekday × minute_offset 的 captured_pct 統計（mean/median/std）

### 注意事項

- OTM 選擇權 tick 可能稀疏（尤其 Wed/Fri DTE=0 的深 OTM），需用 `trade_time <= target_time ORDER BY trade_time DESC LIMIT 1` 取 last known price
- 若某分鐘兩腿都沒有 last price，跳過該分鐘
- 輸出需標註 DTE，方便後續分組

### Step 0 結果（2025-07 ~ 2026-03，89 筆交易）

#### Captured % by Weekday × Minute Offset（摘要）

**Mon (DTE=2, n=27)：** theta 極慢，120 分鐘後 mean captured 僅 13%，median 20%。

| min | mean | median | std |
|-----|------|--------|-----|
| 30 | 4.9% | 6.9% | 14.0% |
| 60 | 1.6% | 10.6% | 43.9% |
| 90 | 3.4% | 19.4% | 59.2% |
| 120 | 13.2% | 20.3% | 22.7% |

**Tue (DTE=1, n=31)：** theta 慢，但 median 穩定上升。少數大虧拉低 mean。

| min | mean | median | std |
|-----|------|--------|-----|
| 30 | 17.6% | 16.7% | 25.7% |
| 60 | 16.8% | 30.1% | 42.8% |
| 90 | 7.7% | 37.8% | 85.8% |
| 120 | 31.9% | 45.4% | 40.1% |

**Wed (DTE=0, n=12)：** theta 快，30 分鐘 mean 已達 52%，40 分鐘 69%。唯一有明顯 capture 加速的 weekday。

| min | mean | median | std |
|-----|------|--------|-----|
| 15 | 27.3% | 23.7% | 18.6% |
| 30 | 52.5% | 61.0% | 30.8% |
| 40 | 68.8% | 70.8% | 21.2% |
| 60 | 52.6% | 40.7% | 23.2% |

**Fri (DTE=0, n=19)：** std 爆炸（100%+），mean 幾乎不動甚至轉負。OTM 流動性差，價格雜訊太高。

| min | mean | median | std |
|-----|------|--------|-----|
| 30 | 11.6% | 45.8% | 72.3% |
| 60 | 6.2% | 61.1% | 139.7% |
| 90 | -49.7% | 54.7% | 397.6% |

#### Minutes to reach captured_pct thresholds (mean)

| Day | 50% | 70% | 80% | 90% |
|-----|-----|-----|-----|-----|
| Mon | never | never | never | never |
| Tue | never | never | never | never |
| Wed | 29 min | 41 min | never | never |
| Fri | never | never | never | never |

### Step 0 結論

**不繼續實作 profit target。** 理由：

1. **Mon/Tue (DTE≥1)：** theta 太慢，持倉全程 captured% 都很低（mean < 30%），設 profit target 幾乎不會觸發，等同無效參數
2. **Wed (DTE=0)：** 唯一有潛力的 weekday，但樣本僅 12 筆，且現有 exit_time=10:30 已很早（僅持倉 ~30 分鐘），再提早空間有限
3. **Fri (DTE=0)：** 流動性問題導致 captured% 的 std 高達 100%~400%，即時市價不可靠，用 profit target 反而可能在雜訊中誤觸發
4. **實務面：** 要監控即時選擇權報價並自動平倉，系統複雜度大增，但預期收益改善極小

**維持現有固定 exit_time 方案，本研究作為「已驗證不需要 profit target」的紀錄。**
