# Proposal: 早盤期貨延伸強度當 ORB 突破的方向濾網

## ID
H119

## Derived From
H118（distribution + backtest）的 derived hypothesis ⑨：H118 證實早盤延伸強度
預測「今天會不會衝到關卡」，但**單獨做多無穩健 EV**（描述性、非進場器）。本假設把它
當**既有 ORB 進場的閘**。

## Trading Intuition
開盤區間突破（ORB）策略最大痛點是**假突破**：價格突破 OR_high 後不續走、回吐吃停損。
H118 發現早盤 NYF/CDF open-anchor 延伸強度能**連續單調**預測當日上行 reach
（NYF @09:00 五分位 L4 達成率 5%→27%；ext≥0.16 → L4 lift 1.9×）。

直覺：**ORB 多方突破若發生在「早盤期貨延伸強度高」的日子，較可能真續走到 L3/L4；
強度低的日子突破多為假突破。** 用強度當方向閘，過濾假突破。

時點對齊：既有 ORB（`src/strategies/orb.py`）OR 窗口 08:45→09:00/09:30，突破在其後；
故在 **OR 窗口結束時讀期貨強度**當閘，與突破同期或更早，無 look-ahead。

## Hypothesis
在既有 ORB 多方突破上加閘：**僅當 OR 結束時刻期貨延伸強度 ≥ θ 才放行多方突破**。

- **H1**：有濾網的 ORB 多方突破，**續走到 L3/L4 的達成率 / 勝率 / 每筆 EV ＞ 無濾網**
  （或 ≥ 低強度組），且**假突破率（突破後跌回 OR 內 / 吃 SL 未達 L3）下降**。
- **H2（增量價值）**：改善是**相對既有 ORB 的增量**——對照組是「無濾網 ORB」與
  「低強度日 ORB」，不是「濾網單獨交易」（H118 已證單獨不可交易）。

## Expected Distribution
- 高強度組 ORB 多突破：續走 L3/L4 率明顯高於低強度組；假突破率明顯較低。
- 濾網主要**砍掉低強度的假突破**，保留的突破勝率/EV 上升（即使交易數下降）。
- CDF 訊號跨 regime（2021–26）皆見此分離；NYF（2025+）一致。

## Invalidation Condition
任一成立即不支持：
- 高/低強度組 ORB 突破的**續走率、假突破率、EV 無顯著差異**（強度對 ORB 結果無分離力）。
- 濾網**只減少交易數、未提升每筆品質**（rate 不變，純樣本縮小，無增量 edge）。
- 表面改善來自 **forward tautology**（強度未嚴格在突破時點之前/同時讀，或續走未嚴格取之後）。

## Notes
- **對照設計是核心**：必比「無濾網 ORB」「低強度 ORB」，證明是**增量**而非重述 H118。
- forward guard：強度讀數時點 ≤ 突破時點；續走/假突破判定嚴格取突破之後。
- **主訊號 CDF**（盤前流動性回溯 2021、跨 regime），NYF 當近期 robustness check
  （承 H118 結論 [[project_oos_equals_highvol_regime]] 的 regime 考量）。
- ORB 突破定義沿用 `src/strategies/orb.py`（OR 窗口、OR_high/low、突破觸發）。
- 與 H118 ⑧ 區分：本假設是「**突破當下**用強度選方向」，非「站上 L3 賭續攻」（後者已 NULL）。
- 所有結論附樣本數；績效用損益%。
