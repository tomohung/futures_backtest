# Proposal: TW Fear & Greed 合成版 forward-return 驗證

## ID
H085

## Derived From
H084-correction-bottom-survey 的 Phase 0 Survey GATE PASS

## Trading Intuition

H084 確認 4 個非冗餘指標都在歷史底部呈現極值：
- VIX_pct（panic / fast）
- z 125MA（technical / fast）
- margin_drop_60d（fundamental deleveraging / slow）
- econ_score（regime classifier / very slow）

H085 要驗證：把這 4 個指標**合成**為單一 score（仿 CNN F&G），歷史每天有一個值。當合成 score 達極值時的買入點，未來 +60D / +120D / +250D 0050（含息）總報酬，是否系統性優於同期 monthly DCA baseline。

這是 H084 framework 的「把指標變成可下單訊號」階段。

## Hypothesis

> 由 4 個非冗餘指標合成的 TW F&G 指數，在達閾值（top 10% 或 top 5%）時觸發買入單一 tranche，**未來 +120D/+250D 含息報酬中位數 ≥ monthly DCA baseline + 3%（絕對值）**，且樣本數 ≥ 30 個觸發日。

## Expected Distribution

Phase 1 預期觀察：
- 合成 score 直方圖呈現右偏（多數日子在低分區）
- 高分區（極端恐懼）的事件少而集中（如 2008、2020、2022、2025）
- 觸發日數約 100-300 天（依閾值）
- forward-return 分佈：高分日的右尾應較 baseline 厚

## Invalidation Condition

下列任一成立 → reject：

1. 高分日（top 10%）的 forward 120D/250D 報酬中位數**不顯著高於** baseline（差距 < 1%）
2. 樣本太集中於 1-2 個事件（每個獨立 cluster < 5 個觸發日）
3. 合成 score 的最佳閾值對 OOS 不穩定（in-sample top decile vs out-of-sample top decile 報酬差距 > 5%）
4. 合成不勝過單因子（單看 VIX_pct 已有同等表現 → 用 VIX_pct 即可，不需合成）

## Notes

- 合成方式 Phase 1 要測：
  - **z-score 加總**：每個指標減其歷史中位數除以歷史 IQR，加總
  - **計票（vote count）**：每個指標達極值算 1 票
  - **權重最佳化**（先不做，留 Phase 2）
- 標的固定 0050 含息調整收盤
- baseline：每月最後一交易日固定金額買入
- 與 H087 切換規則互動：本假設先不分 Mode 1/2，全期間統一閾值；如有需要，Phase 2 再做 mode-conditional 版本
