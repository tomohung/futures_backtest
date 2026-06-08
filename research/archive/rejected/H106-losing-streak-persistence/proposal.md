# Proposal: 連虧後收手（Losing-Streak Persistence / Cold-Streak Conditional Expectancy）

## ID
H106

## Derived From
`research/angell-backlog.md` 候選 **DH-02**（衍生自 Angell 心法「單一時段虧 3 次就收手 / search-and-destroy days」）。
**版本調整**：真實 live 策略（EstHL/Reversal）為 1 筆/日，無「同一天連虧」序列，故把 Angell 的日內版
改寫為**日度版**——連續 k 個交易日虧損後，下一交易日的條件期望（策略冷街持續性）。

## Trading Intuition
Angell 認為連續虧損是「壞日子 / 壞 regime」的訊號，該收手保護心理與資金資本。在 1 筆/日的策略上，
對應的可量化問題是：**某策略連續虧 k 個交易日後，下一筆的條件期望值與勝率，是否顯著低於其無條件
基準？** 若是，代表虧損會「成群」（regime 持續性），「連虧 k 日就暫停/降碼」有實質 edge；若否，
則虧損序列接近獨立（IID），「連虧就收手」只是賭徒謬誤。

## Hypothesis
**設定**：EstHL（S001）、Reversal（S002）真實 trade log（重跑回測產全期 2021–2026，1 筆/日），
各策略獨立 + 合併池都測。
- 連虧定義：連續 k 個「有交易且虧損」的交易日（k=1,2,3,…）。
- 條件量：`E[下一筆 損益% | 前 k 筆連虧]`、下一筆勝率；對比無條件基準。

**陳述**：連虧 k 越大 → 下一筆條件期望/勝率單調越低，且在 **k≥某門檻（如 3）時顯著低於無條件基準**。

**關鍵：IID guard（避免賭徒謬誤，judgement 依據）**——連虧後期望偏低可能只是有限樣本的隨機
streak。必須對比 **IID 虛無分佈**：把同一策略的損益序列隨機洗牌 N 次（保留邊際分佈、打散順序），
重算同一條件統計，看真實值是否落在洗牌分佈之外（顯著正自相關）。同時報 win/loss 序列的 lag-1
自相關與 runs test。**唯有真實連虧訊號顯著強於 IID 洗牌，DH-02 才成立。**

## Expected Distribution
- 若策略 edge 隨市場 regime（如波動體制）變化、且 regime 有持續性 → 虧損成群、條件期望單調下降、
  顯著偏離 IID。
- 效率市場先驗：策略單筆結果接近 IID → 條件期望 ≈ 無條件、落在洗牌分佈內 → 連虧無資訊（傾向此結果）。
- 即使期望不轉負，連虧後的**波動/連敗長度**仍可能放大（與 `[[feedback_filter_eval_includes_streaks]]`
  相關）——順帶報，但不作為本假設成立依據。

## Invalidation Condition
- `E[下一筆 | 連虧 k]` 與無條件基準**無顯著差異**（落在 IID 洗牌分佈內）、win/loss 序列無顯著正自相關
  → 連虧不帶資訊，「連虧收手」為賭徒謬誤，DH-02 不成立。
- 條件期望雖偏低但僅來自極少數樣本（k≥3 的 N 太小、無統計力）→ inconclusive，不可宣稱。
- 多策略間方向不一致、無共同 regime 訊號。

## Notes
- 資料：需重跑 `strategies/live/S001-esthl/backtest.py`、`S002-reversal/backtest.py` 產全期 trade log
  （現有 CSV 僅片段，如 reversal 只 2025）。零新「市場資料」，但需重生策略交易序列。
- 績效標準化用 損益%（對齊 CLAUDE.md）。
- IID guard 是本研究核心方法（沿用 H105 教訓 [[feedback_excursion_needs_forward_tautology_guard]] 的精神：
  描述性條件統計需對比正確虛無分佈，否則隨機結構被誤當訊號）。
- 若成立，衍生「連虧 → 降碼 / 暫停 規則回測（含對心理資本的連敗/DD 改善）」為下一假設；
  若僅波動放大而期望不變，則導向 sizing 規則而非停手。
