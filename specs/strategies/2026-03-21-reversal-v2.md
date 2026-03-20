# Reversal Strategy v2（2026-03-21）

## 1. 背景與動機

Reversal v1（`2026-03-12-reversal.md`）的核心問題：**強趨勢單邊行情中，BB 反向觸碰不會出現**，導致策略完全錯過高品質交易。

2026-03 實單回顧：7 筆「關鍵價轉折」交易中，v1 只捕捉 3 筆。主要阻擋因素：
1. CCD 方向衝突（開盤後強勢下跌，CCD 初期仍為正值）
2. BB 觸碰發生在 entry window（09:10）之前
3. vol_ratio = 1.5 過嚴

### 核心觀察

> 如果價格已經走了 EstRange 的一定比例（如 50%），多方/空方已經力竭，此時 CCD 方向與趨勢不一致是合理的——力竭本身就是反轉信號。

---

## 2. v1 → v2 變更清單

| 項目 | v1 | v2 | 理由 |
|------|-----|-----|------|
| **Entry window** | 09:10 – 13:00 | 09:10 – **10:05** | 縮短進場窗口 |
| **Setup window** | = Entry window | **08:45** – 10:05 | Setup（BB 觸碰）可在 entry window 前完成 |
| **SL** | EmaHL × 0.35 | EmaHL × **0.25** | 與 EstHL 策略一致 |
| **TP 出場** | Fixed TP（EmaHL × fraction） | **SatZone 兩段式**（EstimateHLExitMixin） | 與 EstHL 策略相同出場機制 |
| **MA 方向** | slope ≥ 0.006% 門檻 | **純方向**（MA > MA_prev） | 移除斜率門檻，與 Pine 一致 |
| **BC zone 內** | 雙向皆可 | **跟 MA 方向** | 減少逆勢交易 |
| **vol_ratio** | 1.5 | **1.2** | 放寬量能門檻 |
| **CCD 條件** | 必要條件 | CCD_ok **OR** exhaustion **OR** VWAP bypass | 力竭或盤中成本確認時放寬 CCD |
| **VWAP bypass** | 無 | 09:30 後 close vs intraday VWAP | 盤 45 分鐘仍在成本以上/下 = 強勢確認 |
| **BB 觸碰** | 即時檢查 | **獨立 latch** | BB+vol 觸碰記錄為 flag |
| **Exhaustion** | 無 | **獨立 latch**（EstRange × 0.5） | 力竭判定 |
| **Latch reset** | Setup flag 在 MA5 cross 時 reset | BB latch + exhaustion latch 皆在 **MA5 cross** 時 reset | 統一 reset 機制 |
| **移除參數** | tp_ema_fraction, tp_mode, tp_vol_fraction, min_slope_pct | — | 簡化 |
| **新增參數** | — | exhaust_fraction = 0.5 | 力竭門檻 |

---

## 3. 策略設計（v2）

### 3.1 BC Zone Gate（同 v1，但 inside zone 改為跟 MA）

| Open 位置 | 允許方向 |
|-----------|---------|
| Open > max(BC1, BC2) | 做多 only |
| Open < min(BC1, BC2) | 做空 only |
| Open 在 BC1 與 BC2 之間 | **跟 MA 方向**（bullish → 做多, bearish → 做空） |
| BC 資料缺失（NaN） | 當天不進場 |

### 3.2 方向判斷（簡化）

| 信號 | 條件 |
|------|------|
| Bullish | MA5m_120 > MA5m_120_Prev |
| Bearish | MA5m_120 < MA5m_120_Prev |

無斜率門檻，與 Pine Script `orb_est_hl_tx.pine` 一致。

### 3.3 三個獨立 Latch（全部在 MA5 cross 時 reset）

#### Latch 1: BB 觸碰（`_bb_long_touched` / `_bb_short_touched`）

| 做多 | 做空 |
|------|------|
| close ≤ BB_Lower AND vol > vol_ratio × VolMA20 | close ≥ BB_Upper AND vol > vol_ratio × VolMA20 |

- 可在 08:45 起任何時間觸發
- 不需要 CCD 方向

#### Latch 2: Exhaustion（`_bull_exhausted` / `_bear_exhausted`）

| 做空用 | 做多用 |
|--------|--------|
| close ≥ day_low + EmaHL × exhaust_fraction | close ≤ day_high - EmaHL × exhaust_fraction |
| 多方已走完 50% 振幅 → 力竭 | 空方已走完 50% 振幅 → 力竭 |

- 一旦觸發即持續有效（latch）
- 只在 MA5 cross 時 reset

#### Latch 3: CCD 方向（即時，非 latch）

- 做多：CCD_5m > 0
- 做空：CCD_5m < 0

#### Bypass 4: Intraday VWAP（09:30 後啟用）

```
VWAP = sum(close × volume) / sum(volume)   ← 當日盤中累計
```

- 做多：09:30 後 close > VWAP → CCD 為負也可做多（盤了 45 分鐘仍在成本以上 = 多方強勢）
- 做空：09:30 後 close < VWAP → CCD 為正也可做空
- 不是 latch，每根 bar 即時判斷

### 3.4 Setup 組合

```
Setup = BB_touched AND (CCD_ok OR Exhausted OR VWAP_bypass)
```

BB 觸碰是必要條件。CCD、Exhaustion、VWAP bypass 三者任一成立即可。
VWAP bypass 僅 09:30 後生效。

### 3.5 Trigger（進場確認）

- 時間窗口：**09:10 – 10:05**
- 做多：close > MA5_1m
- 做空：close < MA5_1m

### 3.6 Reset 規則

在 entry window 內，MA5 cross 時 reset 所有 latch：
- close > MA5 → `_bb_long_touched = False`, `_bear_exhausted = False`
- close < MA5 → `_bb_short_touched = False`, `_bull_exhausted = False`

Entry window 外的 BB 觸碰和 exhaustion 會持續累積，不被 reset。

### 3.7 出場（與 EstHL 策略統一）

| 優先序 | 出場類型 | 做多 | 做空 |
|--------|----------|------|------|
| 1 | Fixed SL | entry - EmaHL × 0.25 | entry + EmaHL × 0.25 |
| 2 | SatZone Phase 1 | High ≥ SatZoneUpper | Low ≤ SatZoneLower |
| 2 | SatZone Phase 2 | close < 5MA | close > 5MA |
| 3 | Pivot trailing (09:45 後) | pivotlow(5,5) | pivothigh(5,5) |
| 4 | Force exit | 13:40 | 13:40 |

---

## 4. 參數一覽

| 參數 | 預設值 | 說明 |
|------|--------|------|
| vol_ratio | 1.2 | volume > vol_ratio × VolMA20 |
| sl_ema_fraction | 0.25 | SL = EmaHL × fraction |
| exhaust_fraction | 0.5 | 力竭門檻 = EstRange × fraction |
| signal_skip | 0 | 跳過前 N 個觸發 |

---

## 5. 2026-03 回測結果（v2 vs 實單）

### v2 回測

| 日期 | 方向 | 進場 | 出場 | 進場價 | 出場價 | 損益 |
|------|------|------|------|--------|--------|------|
| 03/03 | S | 09:14 | 09:54 | 35230 | 34853 | **+377** |
| 03/04 | S | 09:44 | 10:46 | 33508 | 33241 | **+267** |
| 03/05 | S | 09:15 | 09:58 | 34201 | 33775 | **+426** |
| 03/06 | B | 09:29 | 09:57 | 33420 | 33620 | **+200** |
| 03/10 | S | 09:55 | 10:57 | 33201 | 32830 | **+371** |
| 03/12 | B | 09:58 | 10:22 | 33713 | 33573 | -140 |
| 03/13 | S | 09:35 | 10:04 | 33257 | 33447 | -190 |
| 03/16 | S | 09:52 | 10:52 | 33351 | 33296 | **+55** |
| 03/17 | B | 09:48 | 10:18 | 33830 | 33814 | -16 |
| 03/18 | B | 09:32 | 11:50 | 34384 | 34516 | **+132** |

**10 筆 +1482 pts | 勝率 70%**

### 實單「關鍵價轉折」對照

| 日期 | 實單 | v2 回測 | 匹配 |
|------|------|---------|------|
| 03/03 | S +377 | S **+377** | 完全一致 |
| 03/04 | S +258 | S **+267** | 進場同，出場差 9 pts |
| 03/05 | S +425 | S **+426** | 幾乎一致 |
| 03/06 | B +143 | B +200 | 進場差 57 pts |
| 03/10 | S -166 | S +371 | 不同進場點 |
| 03/12 | B -87 | B -140 | VWAP bypass 觸發，接受 |
| 03/19 | B +48 | 無 | MA 走平翻覆（見 §6 分析） |

### v1 → v2 改善

| 指標 | v1（2026-03） | v2（2026-03） |
|------|-------------|-------------|
| 筆數 | 5 | 10 |
| 損益 | +547 | **+1482** |
| 勝率 | 60% | **70%** |
| 捕捉實單關鍵價轉折 | 3/7 | **6/7** |

---

## 6. 未捕捉交易分析

### 2026-03 未捕捉

#### 03/12（B -87 實單，v2 B -140）→ VWAP bypass 觸發

- 09:48 BB_Lo 觸碰 + vol_ok → `bb_long` latched，CCD=+3474
- 09:50 CCD 翻負 → 但 09:58 close > intraday VWAP（VWAP bypass 生效）
- 09:58 close > MA5 → trigger 進場，結果 -140

**結論**：VWAP bypass 在此案例造成虧損進場，但實單也虧 -87。接受此副作用。

#### 03/19（B +48 實單，v2 無交易）→ MA 走平翻覆

- MA5m_120 在 34141–34143 之間波動（差距 < 2 點），5 分鐘內翻轉 3 次
- 09:14 BB_Lo 觸碰（MA=B）→ bb_long latched
- 09:17 close > MA5 → reset
- 09:25 MA 翻空（34142.5 vs 34142.7，差 0.2 點）
- 09:30 BB_Lo 再次觸碰（MA=S）→ latch 的是 `bb_short`（非 bb_long）
- 09:35 MA 翻回多 → 但 bb_long 已被 reset，只有 bb_short

**結論**：MA 在平坦期抖動造成方向判斷不穩。這與 v1 的 `min_slope_pct` 想解決的是同一問題，但目前選擇接受：MA 走平時方向本就不確定，不做合理。

### 2026-01 未捕捉

#### 01/08（B +156 實單，v2 無交易）→ BC zone = below

- Open=30362 < BC_lo=30468 → `_allow_short = True`（short only）
- MA=Bullish → 做空方向不符，無法進場
- 實際是跳空開低反彈，MA 向上有力道

**結論**：BC zone below 限制做多。跳空開低可能是例外情境，但樣本不足，暫不修改規則。

#### 01/15（S +105 實單，v2 無交易）→ MA 翻覆（同 03/19 類型）

- 09:02 BB_Up + vol_ok → `bb_short` latched（MA=S）
- 09:14 close < MA5 → reset
- 09:30 BB_Up + vol_ok → `bb_short` re-latched
- 09:32 close < MA5 → reset
- 09:35 **MA 翻 B**（30908.7 > 30908.2）→ 之後做空方向不符
- CCD 全程為正，exhaustion 未觸發

**結論**：同 03/19，MA 走平翻覆問題。接受漏掉。

#### 01/20（B +118 實單，v2 B +203）→ VWAP bypass 解決

- CCD 全程為負（-5680 ~ -19368），exhaustion 未觸發
- 09:38 BB_Lo + vol_ok → `bb_long` latched
- 09:43 close > MA5 且 close > intraday VWAP（09:30 後 VWAP bypass 生效）→ trigger 進場
- 回測 +203（實單 +118）

**結論**：VWAP bypass 成功捕捉。盤了 45 分鐘 close 仍在成本以上，確認多方強勢。

#### 01/28（B +145 實單，v2 無交易）→ BB + vol 不同步

- 09:35 close=32739 碰到 BB_Lo=32742 但 vol=850 不夠（需 ×1.2）
- 09:37 vol=1154 有補量但 close=32739 > BB_Lo=32727 已離開 BB
- 緩跌行情：BB band 收窄跟著價格走，close 在 BB_Lo 附近但不夠極端

**結論**：BB 觸碰和放量差一根 bar。曾測試將 BB 和 vol 拆成獨立 latch，但副作用明顯（03/10 進場提前劣化），已復原。接受此類緩跌行情漏掉。

### 未捕捉交易分類總結

| 類型 | 日期 | 合計損益 | 處理方式 |
|------|------|----------|----------|
| BC zone below 限制 | 01/08 | +156 | 跳空開低例外，需更多樣本 |
| MA 走平翻覆 | 01/15, 03/19 | +153 | 接受，MA 不確定時不做 |
| BB + vol 不同步 | 01/28 | +145 | 拆分 latch 有副作用，已復原 |
| ~~CCD 結構性為負~~ | ~~01/20~~ | — | ~~已由 VWAP bypass 解決~~ |

---

## 7. 2026-01 回測結果（v2 vs 實單）

### v2 回測

| 日期 | 方向 | 進場 | 出場 | 進場價 | 出場價 | 損益 |
|------|------|------|------|--------|--------|------|
| 01/06 | B | 09:41 | 09:57 | 30323 | 30362 | +39 |
| 01/07 | B | 09:23 | 11:42 | 30511 | 30610 | +99 |
| 01/12 | B | 09:17 | 09:56 | 30709 | 30619 | -90 |
| 01/13 | B | 09:48 | 10:17 | 30804 | 30707 | -97 |
| 01/16 | B | 09:27 | 11:38 | 31218 | 31404 | **+186** |
| 01/19 | B | 09:58 | 10:32 | 31378 | 31457 | +79 |
| 01/20 | B | 09:43 | 10:40 | 31482 | 31685 | **+203** |
| 01/23 | B | 09:30 | 10:57 | 31959 | 32038 | +79 |
| 01/26 | B | 09:20 | 10:44 | 32176 | 32140 | -36 |
| 01/27 | B | 09:24 | 10:18 | 32248 | 32483 | **+235** |
| 01/29 | B | 09:28 | 10:05 | 32713 | 32695 | -18 |

**11 筆 +679 pts | 勝率 64% | 全部做多**

### 實單「關鍵價轉折」對照

| 日期 | 實單 | v2 回測 | 匹配 |
|------|------|---------|------|
| 01/06 | B +58 | B +39 | 進場同，出場差 19 pts |
| 01/07 | B +142 | B +99 | 進場同，出場差 43 pts |
| 01/08 | B +156 | 無 | BC zone=below（跳空開低） |
| 01/12 | B -61 | B -90 | 不同進場點 |
| 01/15 | S +105 | 無 | MA 翻覆 |
| 01/16 | B +217 | B +186 | 幾乎一致 |
| 01/19 | B +69 | B +79 | 進場同 |
| 01/20 | B +118 | B **+203** | VWAP bypass 觸發，進場差 2 分鐘 |
| 01/26 | B -20 | B -36 | 不同進場點 |
| 01/27 | B +235 | B +235 | 完全一致 |
| 01/28 | B +145 | 無 | BB + vol 不同步 |

**捕捉率：8/11（73%）**

---

## 8. 已測試但未採用的變更

### BB 觸碰與放量拆分為獨立 latch

將 BB 觸碰和 vol_ok 拆成兩個獨立 latch（不需同一根 bar 同時成立）。

- **目的**：解決 01/28 緩跌行情中 BB 和 vol 差一根 bar 的問題
- **結果**：01/28 成功進場（進場價完全一致），但 03/10 進場從 09:55 提前到 09:15（vol spike 提前 latch），損益從 +371 降到 +254
- **結論**：vol latch 獨立後過於寬鬆，容易在不理想的時間點觸發進場。**已復原**。

---

## 9. 待驗證

1. **全期回測**（2021–2026）— v2 參數的跨年度表現
2. **exhaust_fraction 敏感度**：0.3 / 0.4 / 0.5 / 0.618 比較
3. **vol_ratio 敏感度**：1.0 / 1.2 / 1.5 比較
4. **跳空開低情境**：01/08, 01/20 皆為跳空開低 + MA 向上，需收集更多樣本判斷是否應放寬 BC zone / CCD 規則

---

## 10. 檔案索引

| 檔案 | 用途 |
|------|------|
| `src/strategies/reversal.py` | ReversalStrategy v2（含 EstimateHLExitMixin） |
| `src/strategies/estimate_hl_exit.py` | SatZone 兩段式出場 mixin |
| `src/backtest/runner.py` | `load_data_for_reversal()` 資料載入 |
| `specs/strategies/2026-03-12-reversal.md` | v1 原始規格（保留作為歷史紀錄） |
