# Proposal: Weak-Open OR Break Short（弱勢開局破底續跌）

## ID
H123

## Derived From
H122（distribution 階段）。H122 確立：成本之上開高走低破底「淺跌」(L3 了結)，
而**成本之下破底 reach 顯著更深**（對照 B 組 L3=62% / L4=35% / P(L4|L3)=57%）。
H123 把這個「值得抱」的鏡像方向獨立出來，並進一步驗證**可交易性**。

## Trading Intuition
開盤就站在昨日+前日日盤 VWAP（成本）之下——弱勢開局，賣方已掌握主動。
若在 08:58–09:15 又向下跌破開盤區間(08:45–08:57) low，代表沒有成本支撐墊接手，
跌勢容易延續且走得深。這是 H122 反面，理論上是可順勢做空、可抱續跌的 setup。

## Hypothesis
當「開盤 < 昨日日盤 VWAP **且** < 前日日盤 VWAP」（嚴格弱勢開局，AND）
且 08:58–09:15 出現「收破 OR low」事件時：
1. **（分佈）** 當日自最高點往下的下行 reach 顯著偏深——L3/L4/L5 達成率明顯高於
   全體 baseline 與虛無分佈，且高於 H122 的成本之上破底。
2. **（可交易）** 以破 OR low 為進場、ladder 為出場的空單，在含手續費滑價後具正期望，
   且抱到較深階（L3/L4）相對 L2 早出有正向 edge。

## 定義（本假設採用）
- session_open = 08:45 第一根 open
- 日盤 VWAP = SUM(close×vol)/SUM(vol)，08:45–13:45（沿用 H122 / key_prices.py）
- **弱勢開局（嚴格 AND）**：`open < VWAP_t1` 且 `open < VWAP_t2`
- OR = 08:45–08:57 high/low；破底事件 = 08:58–09:15 任一根 `close < OR low`（取首次）
- Ladder（running-high anchored，H092 定義）：`low ≤ running_high − m×EmaHL`
  - m: L1=0.385 / L2=0.497 / L3=0.711 / L4=0.977 / L5=1.30；EmaHL=前一日 EMA20(日盤 H-L)

## Expected Distribution
- 事件日樣本：H122 寬鬆 B 組 N=347；嚴格 AND「雙雙在成本之下」會更少，但預期仍 ≥ 100。
- 若成立：嚴格弱勢組的 L3/L4/L5 應 ≥ H122 寬鬆 B 組（62/35/17%），且顯著 > baseline。
- Phase 2：空單在 L3/L4 出場的淨 P&L > 0、PF > 1，且連敗/回撤可控（保護心理資本）。

## Invalidation Condition
- 嚴格弱勢組的 L3/L4/L5 達成率與 baseline / 虛無分佈**無顯著差異**，或不深於 H122 寬鬆 B 組
  → 代表「嚴格雙雙在成本下」沒有額外 edge，退回 H122 既有結論即可（Inconclusive/Reject）。
- 或 Phase 2 含成本後**淨期望 ≤ 0**、或抱深階相對早出無 edge → 不可交易（Reject 可交易性）。
- 樣本 < 50 → Inconclusive。

## Notes
- 對照虛無分佈必做（IID 洗牌 / 前瞻條件期望）。
- regime confound：標註事件年度分佈；OOS(2026-03~06)≡高波。
- **進場可行性檢查**（Phase 1 就要看）：破 OR low 的首次觸發時點，距離當日最低/各 ladder 階首達成
  是否仍有足夠空間可進場——避免「訊號出現時行情已走完」的前瞻陷阱。
- 方向命中 ≠ P&L：分佈深 ≠ 可賺，停損會吃掉部分；Phase 2 才是可交易性的真正裁決。
