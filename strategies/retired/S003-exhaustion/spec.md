# Strategy Spec: Exhaustion — 趨勢竭盡反轉

## ID
S003

## Source Hypothesis
H036-trend-exhaustion-reversal（research/archive/confirmed/）

## Description
趨勢延伸到極端後的竭盡反轉策略。利用 30 分 K 趨勢方向 + BB%B(open) 判定極端位置 + 夜盤創近二日新高/低確認趨勢延伸，在日盤 ORB 被反向突破時進場。出場同 EstHL（SatZone 兩段式 + Dow trailing + 固定 SL）。

核心邏輯：趨勢已延伸到 Bollinger Band 之外，夜盤又進一步推升創新極值 → 多/空方力竭 → ORB 反向突破確認反轉 → 進場。

## Entry Conditions

### 多方竭盡做空
1. 30 分 K SMA(20) 方向向上（日盤）
2. 30 分 K BB%B(20, **open**, 2σ) > 1（開盤價在上軌之上）
3. 夜盤 high > 近二日日盤 high（創新高）
4. ORB(08:45~08:58) 被跌破（09:00 後 low < ORB low）→ 做空
5. 進場價 = ORB low

### 空方竭盡做多
1. 30 分 K SMA(20) 方向向下（日盤）
2. 30 分 K BB%B(20, **open**, 2σ) < 0（開盤價在下軌之下）
3. 夜盤 low < 近二日日盤 low（創新低）
4. ORB(08:45~08:58) 被突破（09:00 後 high > ORB high）→ 做多
5. 進場價 = ORB high

### 濾網
- **ORB% >= 0.25%**：ORB 寬度 / 開盤價 × 100，過濾太窄的 ORB
- **跳過週三、四**：這兩天反轉效果差（PF 0.60, 0.85）
- 進場截止：10:30

### BB%B(open) 說明
使用 30 分 K 的 **開盤價** 計算 Bollinger Bands，而非收盤價。好處是 08:45 開盤就有值，不需等 bar 收完。BB%B > 1 表示開盤價在上軌之上（多方極端），< 0 表示在下軌之下（空方極端）。

### 夜盤對齊
夜盤 session = 前一交易日 15:00 ~ 當日 05:00。週一的夜盤對應週五晚上的 session（跨週末）。

## Exit Conditions
- **SatZone 兩段式**：Phase 1 價格觸碰 SatZone → Phase 2 close 穿越 5MA 出場
- **停損**：EmaHL × 0.25
- **Dow Theory trailing stop**：09:45 後啟動，追蹤 pivot high/low
- **時間停損**：13:30 強制平倉

## Parameters
| Parameter | Value | Sensitivity |
|-----------|-------|-------------|
| 30 分 K MA | SMA(20), day-only | 未詳測 |
| BB period / std | 20 / 2σ | BB 越極端效果越好 |
| 近 N 日新高低 | 2 日 | — |
| ORB 時段 | 08:45~08:58 | 對齊 EstHL |
| ORB% 門檻 | >= 0.25% | IS 翻正臨界點 |
| 跳過星期 | Wed, Thu | Mon 最強(PF=1.50) |
| SL | EmaHL × 0.25 | Low（同 EstHL） |
| 進場截止 | 10:30 | 未詳測 |

## Universe
- 交易標的：台指期（TX）日盤
- 排除條件：週三、四不交易；ORB% < 0.25%

## Execution
- 頻率：日盤 Mon, Tue, Fri
- 下單時機：09:00 後 ORB 反向突破時進場
- 倉位大小：待定（建議初期 ½ 口，與 EstHL、Reversal 搭配）

## Constraints
- 最大持倉數：1
- 單筆最大風險：EmaHL × 0.25

## Performance Summary（回測）

| Metric | IS (2021-2024) | OOS (2025-2026) |
|--------|---------------|-----------------|
| N | 55 | 36 |
| Win Rate | 40.0% | 50.0% |
| PF | 1.08 | 1.70 |
| Avg PnL | +2.4pt | +21.7pt |
| 年均交易 | ~14 筆 | ~18 筆 |

實盤驗證（2026-03）：4/4 獲利，+1028pt。

## Risk Notes
- IS PF=1.08 僅勉強正，2021 和 2023 年虧損
- 週一效果特別好（PF=1.50），可能與週末消化有關
- SL 觸發率 ~38%，進場後快速反向是主要虧損來源
- 與 EstHL (S001) 邏輯相反（逆勢 vs 順勢），可能有互補效果

## Source Code
- Strategy：尚未實作（回測用獨立腳本）
- Pine Script：`indicators/tradingview/exhaustion_tx.pine`

## 與現有策略的關係

| | S001 EstHL | S002 Reversal | S003 Exhaustion |
|---|-----------|---------------|-----------------|
| 方向 | 順勢 | 反轉 | 反轉 |
| 進場 | ORB 突破順勢 | BB + 力竭 | BB(open) + 夜盤極端 + ORB 反向 |
| 條件 | MA↑, VWAP | BB touch + EstRange 50% | MA 極端 + 夜盤新高低 |
| 交易日 | Mon~Wed | 每日 | Mon, Tue, Fri |
| 年均交易 | ~60 | ~80 | ~17 |
