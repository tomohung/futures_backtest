# Backtest Results: H118 CDF 盤前延伸 → 做多 TX

## Date
2026-06-11

## Parameters
- 訊號：CDF(台積電期) open-anchor 延伸 @09:00（錨 08:45），盤前流動性 gate ≥20 ticks
- 進場：延伸 ≥ θ(=0.20 代表) → 09:01 TX open 做多（long-only）
- 出場：(a) EOD 13:45 收盤；(b) target=open+M×EMA20 / stop=open−S×EMA20
- 成本：baseline 0（專案慣例），另列扣成本敏感度
- 績效：損益% = (exit−entry)/entry×100；Sharpe = 每筆 mean/std
- 樣本：N=1287 可交易日（2021-01 ~ 2026-06，CDF 盤前達流動性）

## Results

### (a) EOD 出場
| θ | N | 勝率 | 均% | Sharpe | maxDD% |
|---|---|------|-----|--------|--------|
| 0（always-long 基準）| 1287 | 49.4% | −0.016 | −0.02 | 34.5 |
| 0.20 | 255 | 47.1% | −0.021 | −0.03 | 14.5 |
| 0.30 | 118 | 51.7% | +0.001 | 0.00 | 13.1 |

→ EOD 各門檻 Sharpe≈0、均% 負。**訊號未轉成方向性收盤 edge**（reach≠收盤）。

### (b) Target-exit（θ≥0.20）
| target / stop | N | 勝率 | 均% | Sharpe | 目標達成率 |
|---|---|------|-----|--------|-----------|
| L3 / 0.6 | 254 | 53.5% | −0.007 | −0.01 | 40% |
| **L4 / 0.6** | 255 | 48.2% | **+0.016** | **+0.02** | 22% |
| L4 / 0.8 | 255 | 48.2% | +0.010 | +0.01 | 22% |

訊號日 L4 達成率 22%（> base ~15%，reach 預測成立），但 target 遠/stop 近，淨 EV ~打平。

| | In-Sample (≤2024) | Out-of-Sample (≥2025) |
|---|---|---|
| (target L3/stop0.6) 均% | **−0.025** | +0.039 |
| Sharpe | −0.04 | +0.06 |
| N | 183 | 71 |

## Walk-Forward Summary（target L3/stop0.6, θ≥0.2）
2021 −0.029 / 2022 −0.070 / **2023 +0.116(Sh+0.30)** / 2024 −0.120 / 2025 −0.055 / **2026 +0.248(Sh+0.38)**
→ 6 年 2 正 4 負，無跨 regime 一致性。好年(2023/2026)被壞年(2022/2024)抵銷。

## Parameter Sensitivity
- θ、target(L3/L4)、stop(0.4–0.8) 全掃過，最佳組合僅「L4/stop0.6」勉強 Sharpe +0.02。
- 對成本敏感：扣 0.02%/趟即轉明顯負。
- **無任何參數組合產生穩健正 EV**；正值集中在少數年份 → 疑似 regime/運氣，非結構 edge。

## Verdict
[ ] Confirmed　[ ] Rejected　[x] **Inconclusive（單獨策略）／Confirmed（描述性預測訊號）**

判斷依據：
- **假設的預測力（Phase 1 H1/H2/H3）成立且嚴謹**：盤前領先、forward guard 過、跨 regime
  正、同日 head-to-head 贏 cash。這部分是**真訊號**。
- **但單獨當進場器做不出穩健可交易 EV**：corr ~+0.16(09:00) 太弱，reach≠收盤、停損先觸發；
  IS 負、OOS 微正、walk-forward 2/6 年 → 不符 Confirmed 的「IS/OOS 一致 + 參數穩健」。
- 未觸發 proposal 的 invalidation（corr≈0/tautology/劣於 cash 皆未發生）。
- 與 ext_long 一貫定位一致：**順勢族的偏向濾網，非獨立機械規則**（cf. H117 描述性 Confirmed）。

## Derived Hypotheses
- **H120（濾網用法）**：CDF/NYF 盤前延伸 ≥ θ 當「今日偏多」閘，**疊在既有順勢族
  （EstHL / ORB）**上 → 看是否提升那些策略的勝率/Sharpe（這才是訊號的正確用法）。
- **H121（更強訊號時點）**：corr 在 09:15/09:30 升到 +0.29/+0.33，改晚進場（犧牲 runway
  換訊號強度）是否翻正？需防 data snooping。
- **H122（chart-ui 盤前 rail）**：即使不可單獨交易，盤前 CDF/NYF 延伸讀數仍可上 morning
  briefing / chart-ui 當「今日上行傾向」描述性看盤指標（已部分實作 0050期 副圖）。
