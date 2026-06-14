# Archive: L2 趨勢確立後拉回續攻（pullback breakout continuation）

## Status
Confirmed（2026-06-14；已晉升 strategies/live/S005-l2-pullback）

## Summary
TX 日盤：波段達 L2（0.497×EMA20）確立方向後，等一個小回檔、收盤站回 1 分 K 5MA 再進場，吃 L2→L3 的續攻段。高勝率、低賠率 profile；賠率靠「拉回深度」放大並據此分級加碼。多空皆做（空方略強）。

## Key Evidence
- **進場法對照（同 anchor 停損, target L3）**：等拉回+5MA站回(A) 勝率 72.5%/EV+20pt ≫ 確立即進(null N) 58.8%/+4pt ≫ 突破前峰(B) 67.9%/+3pt。證明「等拉回」非 tautology、相對正確 null 有大幅 edge。
- **部署版（A, alpha=0.75, ≤12:00, 深度≥0.25, cost 3pt）**：IS N=546 勝率76.7% Sharpe0.40；OOS N=246 勝率85% Sharpe0.68；逐年全正、walk-forward 全正；maxDD≤−2.3%、最大連敗≤4；成本≤6pt 仍正。
- **停損**：拉回極值往錨靠 alpha=0.75（寬結構停損）；緊停(alpha=0)連敗達16不可用，IS/WF 穩定收斂 0.75。
- **分時段**：午後尾盤(12:45+)幾乎無 edge → 進場上限 12:00。
- **日內順序**：控制時段後，早盤/中段同時段「第2+筆」優於「第1筆」（再上膛=趨勢日確認）；午後相反。
- **拉回深度**：與賠率強相關（avgR 0.08→0.90、勝率 75→84%）；深度≥0.5 為加碼分水嶺(×2)。BB(15,2) 打到軌經證實只是深拉回的較差代理，不採用。

## Why Confirmed
IS/OOS 一致且 OOS 不衰退、逐年+walk-forward 全部為正、參數最佳化通過 OOS+WF、對成本穩健、回撤與連敗低（保護心理資本）。proposal 無效條件無一成立（樣本足、條件勝率 >> base rate、R:R 正）。

## Derived Hypotheses
- H120b：抱尾 trail（達 L3 改 trail 0.5，總點數×1.3、Sharpe 持平）值得獨立做分批出。
- H120d：regime 分層（升壓是否收緊抱尾）。
- H120e：與 EstHL/Reversal 的相關性與資金配置。
- H120f：日內再上膛加碼（趨勢日第2+筆品質更高），需正確 null（活躍日基準）控選擇偏誤。
- H120g（已驗證並落地）：拉回深度分層加碼，BB 為深拉回代理不採用。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Backtest：results/backtest.md
- 探索/分析腳本：explore.py / backtest.py / analyze.py / analyze_bb.py
- Live 策略：strategies/live/S005-l2-pullback/
