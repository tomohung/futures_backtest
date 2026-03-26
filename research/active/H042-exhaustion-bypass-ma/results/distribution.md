# Distribution Research Results: BB Extreme Bypass MA Direction

## Date
2026-03-26

## Conditions Tested
- 30 分 K BB(20, open) %B：日盤 only，BB bands 和 %B 都用 open，不 shift（open 一開盤就可拿到）
- 極端定義：BB%B > 1（超買極端）或 BB%B < 0（超賣極端）
- MA 方向判定：5m 120MA slope（MA5m_120 > MA5m_120_Prev = bullish）
- 模擬 Reversal 進場邏輯，追蹤被 MA 方向阻擋的 setup（BB touch + vol 符合，但 MA 方向不允許）
- MFE/MAE 以進場後 60 分鐘窗口計算

## Sample
- 總交易日：1,264 天
- 時間範圍：2021-01-01 ~ 2026-03-25
- 市場：台指期 TX 日盤

## Key Findings

### 1. 30 分 K BB%B 極端值頻率（修正後：日盤 only, open-based）

| 指標 | 數值 |
|------|------|
| 日盤 30 分 K 總 bars | 12,633 |
| BB%B > 1 bars | 697 (5.5%) |
| BB%B < 0 bars | 646 (5.1%) |
| 極端 bars 合計 | 1,343 (10.6%) |
| 有極端 BB%B 的交易日 | 626 / 1,264 (49.5%) |

BB%B 極端約佔 10.6% bars，約一半交易日出現。

### 2. 被 MA 方向阻擋的 Reversal Setup：46 筆

#### 按 Block Type

| 類型 | N | Win% | MFE/MAE | Avg PnL | Total |
|------|---|------|---------|---------|-------|
| above → 做多但 MA bearish | 13 | 53.8% | 1.67 | +13.8 | +180 |
| below → 做空但 MA bullish | 11 | 54.5% | 1.32 | +9.1 | +100 |
| inside → MA bullish 想做空 | 13 | 53.8% | **1.68** | **+26.2** | **+340** |
| inside → MA bearish 想做多 | 9 | **44.4%** | **0.68** | **-17.7** | **-159** |

**inside + MA bearish 想做多**是唯一虧損的類型。在 BC zone 內逆 MA 做多確實危險。

#### 按 Exhaustion 狀態（關鍵發現）

| | N | Win% | Avg PnL | Total |
|---|---|------|---------|-------|
| **已 Exhausted** | **36** | **55.6%** | **+17.7** | **+638** |
| 未 Exhausted | 10 | 40.0% | -17.7 | -177 |

Exhaustion 是比 BB%B 極端更有效的 bypass 篩選條件。Exhaustion 定義：
- bear_exhausted：`close <= day_high - EmaHL × 0.5`（價格從高點下跌 50% EstRange，空方動能耗盡）
- bull_exhausted：`close >= day_low + EmaHL × 0.5`（價格從低點反彈 50% EstRange，多方動能耗盡）

#### 按 BB%B 極端（修正後 open-based，效果不佳）

| | N | Win% | Total |
|---|---|------|-------|
| BB%B 極端 | 4 | 50.0% | +215 |
| BB%B 正常 | 42 | 52.4% | +246 |

修正 BB%B 計算後，極端 + MA 被擋的交叉只有 4 筆，BB%B 作為 bypass 條件不可行。

### 3. 完整回測比較：有 MA vs 無 MA

| | 有 MA（標準） | 無 MA | 差異 |
|---|---|---|---|
| Trades | 558 | 692 | +134 |
| WR | 45.0% | 43.9% | -1.1% |
| Total | 3,728 | 3,894 | +166 |
| **PF** | **1.32** | **1.25** | **-0.07** |

無條件移除 MA 濾網：PF 從 1.32 降到 1.25，品質下降。MA 整體仍有幫助。

## Vs. Expected

| 預期 | 實際 | 符合 |
|------|------|------|
| BB%B 極端每月數次 | 49.5% 交易日有極端值 | 部分符合（頻率合理但與 MA blocking 交叉太少） |
| 被擋交易的 P&L 偏正 | 46 筆整體 WR 52.2%、+461 pts | **符合** |
| 極端後傾向反轉 | BB%B 極端 + 被擋只有 4 筆，無法判斷 | **樣本不足** |

## Gate Decision
- [ ] 進入 Phase 2
- [ ] Archive（原因：）
- [x] 修改假設（修改內容：見下方）

### 假設轉向

原假設（BB%B 極端作為 bypass 條件）不可行：修正 BB%B 計算後與 MA blocking 交叉僅 4 筆。

**新方向**：改用 **Exhaustion 狀態**作為 MA bypass 條件。

數據支持：
- 36 筆 exhausted 被擋交易：WR 55.6%、MFE/MAE > 1、Total +638 pts
- 10 筆 non-exhausted：WR 40%、Total -177 pts
- Exhaustion 的邏輯基礎：對手方動能已走完 50% EstRange，MA 滯後尚未反應，但反轉條件已成熟

待決定：
1. 修改 H042 假設為「Exhaustion bypass MA」繼續研究
2. 或建立新假設 H04X 來探索

## Derived Hypotheses
- **H04X（建議優先）**：Exhaustion bypass MA — 當對手方已 exhausted 時，bypass MA 方向檢查允許逆勢進場。N=36 筆初步數據正向（WR 55.6%）
- H04X：檢查被 MA 擋掉的交易中，有多少筆與 H044 實盤 DIR_BLOCKED 清單重疊
