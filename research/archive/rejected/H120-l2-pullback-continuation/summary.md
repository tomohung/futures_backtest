# Archive: L2 趨勢確立後拉回續攻（pullback breakout continuation）

> ## ⛔ INVALIDATED 2026-06-15 — 前視偏誤，原 Confirmed 作廢
> 下方 Key Evidence / Why Confirmed 全部**無效**。回測用 ZigZag leg 終點 `em`（反轉後才確認的
> 未來資訊）當進場搜尋上界，系統性濾掉失敗站回 → 灌高勝率/EV。完全 causal 逐根 streaming 重寫後：
> **Sharpe 0.48→0.04、總損益% 108→16、勝率 79→62%**，逐年接近 break-even；深度/離峰/空間濾網、
> 只做多空、按星期、單部位約束皆無法救回（最佳僅 Sharpe ~0.13、過擬合邊緣）。
> 驗證：`results/causal_validation.md`、`validate_causal.py`、`analyze_failures.py`、
> `analyze_segments.py`、`analyze_nooverlap.py`。S005 已退役至 `strategies/retired/`。
> Pine 指標與 chart-ui h120 圖層保留作行情參考。衍生救援方向見文末 Derived Hypotheses。

## Status
~~Confirmed（2026-06-14）~~ → **REJECTED / INVALID（2026-06-15，look-ahead bias）**

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
> ⚠️ 以下 H120b–H120g 均建立在前視偏誤回測上，結論不可信，需 causal 重做。

- **★ 救援候選（causal 預備，`analyze_longtail.py`）：只做空 + 抱尾長尾（trail）。**
  causal 全量下，trail（達 L3 改 trailing trail_frac×L3d 搏 L4/L5）相對 L3 全出能把總報酬約翻倍。
  唯一 IS/OOS **同號為正**的組合是「只做空 + trail 1.0」：
  IS N=442 win43% EV6.8 tot18.5% Sharpe0.072 avgR0.07；OOS N=185 win43% EV22.5 tot13.1% Sharpe0.115 avgR0.14。
  只做多在 IS 為負（不可用）。**但**：per-trade Sharpe 仍僅 ~0.07–0.12、勝率降到 43%、報酬高度依賴
  少數長尾單（maxR~7），屬 fat-tail、回撤風險與心理負擔大；trail_frac=1.0 為最佳含輕微挑參數。
  → 值得開**新假設**（causal-from-scratch、正式 GATE/OOS、成本與回撤、regime 檢查）認真驗，
  不可直接信此預備數字。對應 live 用法：用 Pine 指標**偏空操作、賺到 L3 後續抱**。
- H120b：抱尾 trail — 原結論（×1.3）來自前視回測，作廢；改由上述 causal 候選承接。
- H120d：regime 分層（升壓是否收緊抱尾）— 需 causal 重做。
- H120e：與 EstHL/Reversal 的相關性與資金配置。
- H120f：日內再上膛加碼 — causal 下「第2+筆」反而較差（`analyze_nooverlap.py`：被跳過的後續訊號勝率僅50%），原結論作廢。
- H120g：拉回深度分層加碼 — 來自前視回測，作廢。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Backtest：results/backtest.md
- 探索/分析腳本：explore.py / backtest.py / analyze.py / analyze_bb.py
- Live 策略：strategies/live/S005-l2-pullback/
