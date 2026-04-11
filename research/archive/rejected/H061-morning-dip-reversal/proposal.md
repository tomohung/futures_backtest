# Proposal: Morning Dip Reversal

## ID
H061

## Derived From
Origin（個人交易經驗觀察）

## Trading Intuition
台指期日盤常在 9:30 或 10:20~10:30 出現明顯下殺，殺完後往上拉回。
實際交易中遇到的問題是：有時 9:30 殺完就直接上，有時 9:30 下殺後反彈不過高，
10:20 附近又再殺一波到更低才真正反轉上去。後者容易讓在第一次反彈進場的多單被停損。

4/10 就是典型的二次探底案例：等 9:30 下殺完做多，但盤沒有直接上，
10:20 左右又殺一波到底部才反轉，此時已經停損出場。

## Hypothesis
台指期日盤早盤存在普遍的 dip-then-reversal 模式，可作為做多策略的基礎。
具體而言：
1. 約 80% 的交易日在早盤有可辨識的 dip pattern（Phase 1 已驗證 ✅）
2. 透過「第一次反彈比例」可區分 single dip vs double dip，決定進場時機（Phase 1 已驗證 ✅）
3. 設計進出場規則後，morning dip 做多策略具有正期望值

## Phase 1 Key Findings
- 1,024 / 1,274 天（80%）有明確 morning dip pattern
- Single dip 68% / Double dip 31%
- 區分特徵：第一次反彈比例 single=0.65 vs double=0.47
- Single dip 到收盤 win rate 86.6%，震盪日 92.4%
- 二次探底間隔 median 23 分鐘

## Invalidation Condition
- 回測 win rate < 55%
- 扣除交易成本後淨期望值 < 0
- Out-of-sample 表現顯著劣於 in-sample

## Notes
- 需定義「下殺」的量化標準（例如：從近期高點回落 > N 點）
- 需考慮整體盤勢（趨勢日 vs 震盪日）對這個模式的影響
- 與 H018-early-session-direction 可能有關聯，需交叉比對
