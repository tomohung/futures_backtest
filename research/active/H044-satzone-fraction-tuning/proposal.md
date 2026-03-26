# Proposal: SatZone Fraction 策略別調校

## ID
H044

## Derived From
H031 的 Phase 1 分佈探索 + 補充分析

## Trading Intuition
H031 發現 SatZone（1.0 × EmaHL）的 touch rate 僅 34~56%（視計算版本），意味著大多數交易日 SatZone 出場邏輯根本不觸發，部位最終靠 Dow trailing stop 或 13:30 強制平倉出場。

進一步分析發現：
- fraction 從 1.0 降到 0.90，touch rate 從 56% 升到 70%（+14pp）
- 降到 0.85，touch rate 升到 77%（+21pp）
- 大跳空日（Gap > 1.0 × EmaHL）untouched 率高達 73%

三個 live 策略（S001-esthl、S002-reversal、S003-exhaustion）共用同一個 EstimateHLExitMixin，fraction 都硬編為 1.0。但三者的進場邏輯完全不同：
- S001：ORB 順勢突破 → 期望大行情，fraction 不宜太低
- S002：BB 力竭反轉 → 期望均值回歸，目標較保守，fraction 可較低
- S003：BB(open) 極值反轉 → 類似 S002

不同策略的最適 fraction 可能不同。

## Hypothesis
將 SatZone 目標距離從固定 1.0 × EmaHL 改為 fraction × EmaHL（fraction < 1.0），可以提高 SatZone 出場的觸發率，減少「持倉到收盤」的情境。在適當的 fraction 下，各策略的 EV% 可以維持或改善。

具體預期：
- S002/S003（反轉策略）：適合較低 fraction（0.85~0.90），因為反轉交易的利潤空間本來就較小
- S001（順勢策略）：fraction 不宜太低（0.90~0.95），避免在趨勢日提早出場

## Expected Distribution
### Phase 1
- 各 fraction（0.80, 0.85, 0.90, 0.95, 1.00）下的 touch rate（全體 + 各策略進場日）
- 各 fraction 下觸及後的「剩餘續行空間」分佈（確認降 fraction 不會在觸及日損失太多）
- 各策略目前 untouched 日的損益分佈（了解「沒碰到 SatZone」的交易結果）

### 預期方向
- Touch rate 隨 fraction 下降而上升（已確認）
- 反轉策略（S002/S003）在較低 fraction 下 EV 改善（因為更多交易在有利位置出場）
- 順勢策略（S001）在太低的 fraction 下 EV 下降（因為提早出場錯失趨勢利潤）

## Invalidation Condition
- 所有策略在所有 fraction 下的 EV% 均 <= baseline（fraction=1.0），代表目前的 1.0 已是最適值
- 或者：改善幅度在逐年檢驗中不一致（某些年改善、某些年惡化），代表 fraction 效果不穩定

## Notes
### 測試框架
- Phase 1：分佈探索，各策略各 fraction 的 touch rate 和損益統計
- Phase 2：回測驗證（僅對 Phase 1 有信號的策略 × fraction 組合）
- 判定標準沿用 H031：EV% 必須在 2022~2025 **每年都 >= baseline**，OOS 2025~2026 驗證
- 每個策略獨立判定，不需要三個策略同時通過

### 實作方式
- 現行公式：`SatZoneUpper = session_low + EstHL - EmaHL/8`
- fraction 作用在整個目標距離：`SatZoneUpper = session_low + fraction × (EstHL - EmaHL/8)`
- fraction=1.0 等同現行行為，fraction=0.9 目標距離縮短 10%
- 在策略層面調整即可，不需修改 `compute_estimate_hl_zones()`
