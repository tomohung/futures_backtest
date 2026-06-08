# Archive: H106 — 連虧後收手（Losing-Streak Persistence）

## Status
Rejected（連虧無期望持續性＝賭徒謬誤；Phase 1 即否）

## Summary
源自 backlog DH-02（Angell「虧 3 次收手」）。真實 live 策略 1 筆/日，故改測日度版：EstHL/Reversal
連續 k 個虧損交易日後，下一筆條件期望是否顯著低於無條件基準。核心用 IID 洗牌虛無檢定——結果條件
期望全程落在洗牌信賴帶內、序列零自相關 → 連虧不帶資訊，「連虧收手」無期望 edge，GATE 直接 Archive。

## Key Evidence（EstHL N=170、Reversal N=508，2021–2026；IID 洗牌 N=5000）
- 序列零自相關：lag-1(勝負) EstHL +0.03 / Reversal −0.04；runs-test z 在 ±1 內（不聚集）。
- 連虧 k 後條件期望 p(真≤虛無) 各策略全 >0.10：EstHL 連虧3 後勝率 64%>基準59%（更強）；Reversal 連虧3 E=−0.018% 但 p=0.12（IID 內）。
- Pooled 唯一 p=0.02（k=2）排查為多重比較雜訊：非單調（k3 p=0.07、k4 p=0.29）、仍正值、組合假象排除（連虧後 Reversal 占比 75%=無條件，無偏移）。

## Why Rejected
連虧後條件期望未顯著偏離 IID 虛無、序列無自相關 → 每筆 edge 與近期勝負獨立。「連虧 k 日就收手」
是賭徒謬誤，對 EstHL/Reversal 無期望改善。正中 proposal 無效條件。

## Derived Hypotheses
- **連虧 = sizing/心理面，非期望面**：「連虧降碼/暫停」若做，理由只能是變異數/心理資本（連
  [[feedback_filter_eval_includes_streaks]] / [[feedback_regime_modulate_not_block]]），**不可宣稱改善期望**。
- **meta pattern（重要）**：H104 缺口、H105 早期套牢、H106 連虧收手——三個 Angell 直覺對「正確虛無/前瞻
  檢定」後全部蒸發。描述性看似有理 ≠ 可量化 edge；Angell 心法在台指電子盤多為心理建議。強化
  [[feedback_excursion_needs_forward_tautology_guard]]：條件統計類研究必配虛無分佈對照。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md（GATE：Archive Rejected）
- 腳本：explore.py；圖 results/h106_distribution.png；trade log：output/s001_esthl_2021-01-01.csv、output/s002_reversal_2021-01-01.csv
