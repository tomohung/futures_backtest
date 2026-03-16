# 轉折回歸策略（Reversal Strategy）

## 1. 背景與動機

現有策略（ORBLong、EstHL）皆以**突破**為核心邏輯，表現最佳時段為單邊趨勢明顯的日子。

本策略針對**開盤與機構成本有相對位置關係**的情境：價格在機構成本附近震盪時，**均值回歸**策略較有優勢。

### 核心假設
- 開盤價與 BigCost1（昨日）/ BigCost2（前日）的相對位置決定可交易方向
- 5m K 120MA 斜率提供大方向（日內趨勢偏多或偏空）
- 1 分 K BB 極值（超買/超賣）+ 放量 + CCD 確認 → 短期反彈/反壓 setup
- 1 分 K 5MA 穿越確認動能轉向 → trigger 進場

---

## 2. 策略設計（當前版本）

### 2.1 BC Zone Gate（進場前提，當天判定一次）

| Open 位置 | 允許方向 |
|-----------|---------|
| Open > max(BC1, BC2) | 做多 only |
| Open < min(BC1, BC2) | 做空 only |
| Open 在 BC1 與 BC2 之間 | 多空皆可 |
| BC 資料缺失（NaN） | 當天不進場 |

- `BigCost1`：昨日日盤放量 VWAP
- `BigCost2`：前日日盤放量 VWAP

### 2.2 方向判斷（5m K 120MA 斜率，日盤限定）

| 信號 | 條件 |
|------|------|
| Bullish | MA5m_120 > MA5m_120_Prev（MA 向上）|
| Bearish | MA5m_120 < MA5m_120_Prev（MA 向下）|
| **最低斜率** | \|slope\| / MA ≥ min_slope_pct（預設 0.006%）|

只使用日盤（08:45–13:45）資料計算，避免夜盤污染。
min_slope_pct 過濾 MA 走平的時段（方向不明確），減少 20% 低品質交易。

### 2.3 兩步進場（Setup → Trigger）

**Step 1 — Setup latch**（條件全部成立時鎖定）：

| 指標 | 做多（Bullish 日） | 做空（Bearish 日） |
|------|-------------------|-------------------|
| **BB** 1m K, period=15, std=2 | close ≤ BB_Lower | close ≥ BB_Upper |
| **Volume** 1m K | volume > vol_ratio × VolMA20 | 同左 |
| **CCD** 5m K（日內累積） | CCD_5m > 0（淨買壓） | CCD_5m < 0（淨賣壓） |

**Step 2 — Trigger**（setup 鎖定後，第一根滿足即進場）：

| 做多 | 做空 |
|------|------|
| close > MA5_1m | close < MA5_1m |

**Setup 重置規則**：close 穿越 MA5 時重置（機會已過，需重新滿足 BB 極值才能再 latch）。

**signal_skip 參數**：
- `signal_skip=0`（預設）→ 進第 1 筆觸發的交易
- `signal_skip=1` → 跳過第 1 筆，進第 2 筆觸發的交易

### 2.4 出場

| 優先順序 | 出場類型 | 做多 | 做空 |
|---------|----------|------|------|
| 1 | Fixed SL | entry - EmaHL × sl_ema_fraction | entry + EmaHL × sl_ema_fraction |
| 2 | Fixed TP | day_low + EmaHL × tp_ema_fraction | day_high - EmaHL × tp_ema_fraction |
| 3 | Pivot trailing (09:45 後) | pivotlow(5,5) | pivothigh(5,5) |
| 4 | Force exit | 13:40 | 13:40 |

TP 邏輯：假設已出現的極值可能是當天極值，用 EmaHL 估算對側目標價。
tp=2.0 時 TP 很少觸發（87% 由 trailing 出場），實質上是安全網。
降低 fraction（如 0.7）可讓 TP 更積極觸發（WR>50%），但會截斷大贏家。

### 2.5 進場時窗

- 09:10 – 13:00（延後 10 分鐘避開早盤雜訊，Sharpe 1.05→1.34）
- 每天最多一筆（跳過 signal_skip 筆後的第一筆）

---

## 3. 基準結果

### ReversalStrategy 當前預設值（vol=1.5, sl=0.35, tp=2.0, slope≥0.006%, entry 09:10）

| Year | n | WR% | EV | PF | Total | L/S |
|------|---|-----|-----|-----|-------|-----|
| 2021 | 144 | 48.6% | +4.2 | 1.24 | +605 | 87/57 |
| 2022 | 157 | 44.6% | +2.4 | 1.17 | +371 | 69/88 |
| 2023 | 104 | 51.0% | +5.0 | 1.54 | +523 | 60/44 |
| 2024 | 124 | 52.4% | +13.1 | 1.74 | +1622 | 76/48 |
| 2025 | 131 | 44.3% | +4.0 | 1.19 | +524 | 81/50 |
| 2026 | 30 | 73.3% | +64.2 | 3.17 | +1926 | 22/8 |
| **TOTAL** | **690** | **49.0%** | **+8.1** | **1.49** | **+5571** | 395/295 |

**Sharpe: 1.34 | PF: 1.49 | MaxDD: -596 | 每年都正（含 2022）**

### 參數演進紀錄

| 階段 | 改動 | n | Total | Sharpe |
|------|------|---|-------|--------|
| 原始 | sl=0.35, tp=1.0 (entry±), no filter, 09:00 | 919 | +6079 | 1.05 |
| +slope filter | min_slope_pct=0.006% | 735 | +5570 | 1.09 |
| +TP 邏輯改為 day_extreme | day_low/high + EmaHL×f | 735 | +5490 | 1.05 |
| +tp=2.0 | 讓 trailing 主導出場 | 735 | +5490 | 1.05 |
| +entry 09:10 | 避開早盤雜訊 | **690** | **+5571** | **1.34** |

### SL × TP 網格結果（sl=0.35 最佳，固定 slope≥0.006%）

| SL | TP | WR% | EV | PF | Total | Sharpe |
|----|-----|-----|-----|-----|-------|--------|
| 0.25 | 2.0 | 45.4% | +6.3 | 1.32 | +4620 | 0.80 |
| 0.30 | 2.0 | 46.8% | +7.9 | 1.40 | +5781 | 1.03 |
| **0.35** | **2.0** | **47.5%** | **+8.5** | **1.43** | **+6228** | **1.11** |
| 0.40 | 2.0 | 47.5% | +7.8 | 1.39 | +5753 | 1.00 |
| 0.35 | 0.6 | 47.6% | +7.5 | 1.38 | +5494 | 1.13 |
| 0.35 | 1.0 | 47.5% | +7.6 | 1.39 | +5570 | 1.09 |

> 注：上表是 entry 09:00 的數字。entry 09:10 後 Sharpe 更高。

### TP 邏輯（新：day_extreme + EmaHL×fraction）

| fraction | WR% | EV | PF | Total | Sharpe | TP 觸發率 |
|---------|-----|-----|-----|-------|--------|----------|
| 0.6 | 51.7% | +3.5 | 1.25 | +2607 | 0.70 | ~9% |
| **0.7** | **52.1%** | **+5.1** | **1.33** | **+3749** | **1.03** | ~8% |
| 1.0 | 48.8% | +5.6 | 1.31 | +4117 | 0.91 | ~2% |
| 2.0 | 47.8% | +7.5 | 1.38 | +5490 | 1.05 | ~0.5% |

tp=2.0 時 87% 由 trailing 出場，TP 為安全網。
tp=0.7 讓 TP 真正有意義（WR>50%），但截斷大贏家。

### 進場開始時間

| Start | n | WR% | EV | PF | Total | Sharpe |
|-------|---|-----|-----|-----|-------|--------|
| 09:00 | 735 | 47.8% | +7.5 | 1.38 | +5490 | 1.05 |
| 09:05 | 701 | 48.5% | +7.4 | 1.43 | +5172 | 1.21 |
| **09:10** | **690** | **49.0%** | **+8.1** | **1.49** | **+5571** | **1.34** |
| 09:15 | 683 | 48.9% | +8.0 | 1.48 | +5436 | 1.31 |
| 09:20 | 676 | 48.7% | +8.2 | 1.50 | +5520 | 1.32 |

### 5m MA 方向（120 period 最佳）

| Period | ≈30m MA | Total | 備註 |
|--------|---------|-------|------|
| 60 | 10MA | +4695 | 太短 |
| **120** | **20MA** | **+6079** | **最佳，每年都正** |
| 200 | 33MA | +2871 | 太慢 |

Slope% 門檻（0.006%）過濾 MA 走平期間，各年效果穩定。

---

## 4. 多筆信號分析

每日信號分布（2021–2026）：
- 1 筆：18% 的天數
- 2 筆：18%
- 3 筆：18%
- 4+ 筆：46%

信號品質隨序號遞減：

| 第幾筆 | n | WR% | EV | Total |
|--------|---|-----|-----|-------|
| 1st | 915 | 48.0% | +7.6 | +6963 |
| 2nd | 752 | 49.5% | +4.2 | +3172 |
| 3rd | 590 | 50.7% | +1.0 | +619 |
| 4th+ | 897 | 53.1% | -0.8 | 負 |

### 1st 與 2nd 信號的關係
- **97.6% 同方向**（5m 120MA 一天內很少翻轉）
- 1st WIN → 2nd WR=59.1%, EV=+20.6（非常好）
- 1st LOSS → 2nd WR=34.4%, EV=-6.9（不該做）
- 45% 的天數有時間重疊（2nd 在 1st 還持倉時觸發）

---

## 5. ReversalFollowStrategy（第二筆跟進策略）

**檔案：** `src/strategies/reversal_follow.py`

解決 lookahead 問題：不使用 1st 最終 PnL，而是在 2nd 觸發當下檢查「close vs 1st entry price」判斷同向發展。

| 條件 | 做多 | 做空 |
|------|------|------|
| 2nd trigger | close > 1st_entry_price | close < 1st_entry_price |

### 結果

| Year | n | WR% | EV | PF | Total |
|------|---|-----|-----|-----|-------|
| 2021 | 69 | 58.0% | +17.8 | 2.65 | +1225 |
| 2022 | 65 | 43.1% | +4.7 | 1.38 | +306 |
| 2023 | 60 | 43.3% | +0.9 | 1.11 | +52 |
| 2024 | 66 | 42.4% | +6.6 | 1.45 | +435 |
| 2025 | 62 | 48.4% | -0.3 | 0.98 | -19 |
| 2026 | 16 | 62.5% | +16.4 | 1.51 | +263 |
| **TOTAL** | **338** | **47.9%** | **+6.7** | **1.49** | **+2262** |

**Sharpe: 1.16 | 品質好（PF 1.49）但交易量較少**

> 注意：上述數字是使用舊 TP 邏輯（entry ± EmaHL×1.0）的結果。
> 新 TP 邏輯（day_extreme + EmaHL×fraction）對 Follow 不適用 —
> Follow 進場較晚，day_extreme 算出的 TP 太遠導致 TP 失效。
> Follow 若要繼續使用，應保留 entry-based TP。

### Follow TP 邏輯影響

| 配置 | n | Total | 備註 |
|------|---|-------|------|
| entry±EmaHL×1.0, 09:00（舊） | 338 | +2262 | 原始結果 |
| day_extreme+EmaHL×2.0, 09:00 | 338 | +1696 | TP 太遠 |
| day_extreme+EmaHL×2.0, 09:10 | 316 | +1327 | 更差 |
| +slope filter | 256 | +1934 | slope 有幫助但 2023/2025 虧 |

### Follow Long/Short × Weekday（無 slope filter, 09:10, tp=2.0）

Long 整體虧損（-394），只有 Tue 賺（+139）。
Short 很強（+1721），各天 PF 都 > 1。

| | Long | Short |
|--|------|-------|
| Mon | +10 (PF 1.03) | +118 (PF 1.73) |
| Tue | +139 (PF 1.36) | +682 (PF 1.97) |
| Wed | -249 (PF 0.69) | +118 (PF 1.36) |
| Thu | -96 (PF 0.86) | +183 (PF 1.37) |
| Fri | -198 (PF 0.64) | +620 (PF 7.74, n=17) |

> Fri Short n=17，樣本太少，可能是統計誤差。

**組合（舊 TP 數字）：Reversal +6079 + Follow +2262 = +8341**（無 lookahead）

---

## 6. 已測試但未採用的變更

### 百分比 Trailing Stop（取代 Pivot Trailing）
- 測試 trail_pct = 0.2%–1.0%
- skip=0 最佳 trail=0.3%: +6993（vs pivot +6079），Sharpe 1.14
- skip=1 最佳 trail=0.2%: +3315（vs pivot +5063），明顯劣化
- **結論**：百分比 trailing 對 1st 信號有改善，但對 2nd 信號有害，不統一採用

### Weekday 效應
- 週二最強（WR 52-53%, EV +12）
- 所有天 EV 皆為正，無需排除任何星期

### 進場時間分析
- 09:10 為最佳起始（已採用）
- 12:00 後偏弱（WR 31%）但筆數少（53 筆），未排除

### Long/Short × Weekday（候選濾網，尚未實作）

**Long Tue/Wed/Thu + Short Tue/Thu**：

|  | All | Filtered | Excluded |
|--|-----|----------|----------|
| n | 690 | 380 (-45%) | 310 |
| WR | 49.0% | **53.7%** | 43.2% |
| PF | 1.49 | **1.83** | 1.13 |
| Total | +5571 | +4859 (-13%) | +712 |
| Sharpe | 1.34 | **1.51** | 0.23 |
| MaxDD | -596 | **-378** | -967 |

- 2022 從 +371 → +704（PF 1.65）
- 每年都正，MaxDD 大幅改善
- 被排除的 310 筆 Sharpe 僅 0.23
- **注意**：交易量砍 45%，需評估是否過度擬合

---

## 7. Volume-Weighted Estimated Range（EstRange）

### 動機

現有 EmaHL 使用硬編碼的 15 分鐘 `TIME_FACTORS` 表反推預估量再算振幅。
EstRange 改用**實際歷史累積量**按 5 分鐘更新，自動適應市場變化，無需維護參數表。

### 公式

```
range_est = 近 20 日日盤 range (high-low) 的 EMA
vol_ratio = 今日累積量到 slot T / 近 20 日同時段累積量 EMA
EstRange  = range_est × vol_ratio
```

### 實作

- **函式**：`compute_vol_estimated_range(df, lookback=20, use_ema=True)` in `src/backtest/estimate_hl.py`
  - 5 分鐘 slot（08:45 ~ 13:40，共 60 個）
  - EMA 模式（預設）：running EMA for daily ranges 和 per-slot cumulative volume
  - SMA 模式：`deque(maxlen=20)` 滾動窗口
  - Lookahead 防護：寫入前一個 slot 的計算結果（延遲 1 slot = 5 分鐘）
  - 不足 20 日 → NaN
- **整合**：`load_data_for_reversal()` 自動計算，輸出 `EstRange` 欄位
- **策略參數**（`ReversalStrategy`）：
  - `tp_mode: str = "ema"` — `"ema"`（用 EmaHL）或 `"vol_range"`（用 EstRange）
  - `tp_vol_fraction: float = 0.8` — vol_range 模式的 fraction

### 測試結果（2026-03-16）

#### 測試 1：tp_mode 比較（tp_vol_fraction 作為 TP 計算，固定 vol=1.5, sl=0.35, tp_ema=2.0）

| Mode | vf | Total | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|------|-----|-------|------|------|------|------|------|------|
| **ema (baseline)** | — | **+5700** | +987 | +380 | +541 | +1378 | +860 | +1554 |
| vol_range | 0.6 | +2713 | +339 | -38 | +279 | +657 | +790 | +686 |
| vol_range | 0.8 | +3527 | +649 | +23 | +303 | +878 | +623 | +1051 |
| vol_range | 1.0 | +5014 | +1064 | +157 | +487 | +1175 | +859 | +1272 |

**結論**：vol_range 作為獨立 TP 模式不如 ema baseline。TP 太容易觸發反而截斷大贏家。

#### 測試 2：EstRange 替換 EmaHL（SL/TP 都用 EstRange，保持 ema 公式）

將 `EmaHL` 欄位直接替換為 `EstRange`，測試 EstRange 作為振幅估算的品質。

| 模式 | Total | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|------|-------|------|------|------|------|------|------|
| EmaHL (baseline) | +5700 | +987 | +380 | +541 | +1378 | +860 | +1554 |
| EstRange SMA | +5631 | +783 | +471 | +545 | +1405 | +799 | +1628 |
| **EstRange EMA** | **+6032** | +825 | +435 | +558 | **+1590** | **+996** | +1628 |

**結論**：
- EstRange EMA 最佳（+6032），比 baseline +332 點（+5.8%）
- EMA 對波動壓縮→放大的轉換反應更快，2024/2025 改善明顯
- SMA 幾乎等同 baseline，EMA 的近期權重是關鍵差異
- **已將 `use_ema=True` 設為預設**

**注意**：Reversal 使用**日內 EstRange**（含當天量資訊）替換 EmaHL，因為進場在 09:10+，
此時 EstRange 已有數個 slot 更新，反映今日量能。若改用固定日值（`EstRange_Daily`），
結果等同原 EmaHL baseline（+5700），無改善。
ORB 策略進場在 08:58，太早無法用日內 EstRange，改用固定日值 `EstRange_Daily`。

### Edge Cases

- 前 20 個交易日：`EstRange = NaN` → fallback 到 EmaHL
- 08:45~08:49（第一個 slot）：無前一 slot → NaN（不影響，entry 從 09:10 開始）
- 短交易日（颱風）：只對有該 slot 資料的天數取平均
- 量異常日（結算日）：vol_ratio > 1 → est_range 放大（符合預期）

### 下一步

- 評估是否正式將 Reversal 預設 SL/TP 從 EmaHL 切換到 EstRange EMA
- SL 和 TP 可以分別選擇用 EmaHL 或 EstRange（目前只有 TP 有 mode 參數）

---

## 8. 待優化事項

1. **vol_ratio 測試**：目前固定 1.5，可測 [1.0, 1.2, 1.5, 2.0]
2. **Weekday 濾網實作**：L:Tue/Wed/Thu + S:Tue/Thu（已驗證有效）
3. **ReversalFollow TP 邏輯**：新 day_extreme TP 不適用，需保留 entry-based TP
4. **ReversalFollow Long 很弱**：整體 -394，考慮只做空或 Long 只做 Tue
5. **ReversalFollow 2023/2025 虧損**：需研究原因
5. **其他濾網**：VIX、ADX、OR% 等

---

## 9. 檔案索引

| 檔案 | 用途 |
|------|------|
| `src/strategies/reversal.py` | ReversalStrategy（signal_skip 參數化）|
| `src/strategies/reversal_follow.py` | ReversalFollowStrategy（2nd 信號 + 同向確認）|
| `src/backtest/runner.py` | `load_data_for_reversal()` 資料載入 |
| `src/backtest/optimize_reversal.py` | 優化腳本（尚未執行）|
