# Proposal: 漲停熱絡持續作為動量延續訊號

## ID
H090

## Derived From
H079（漲停萎縮溫度計，confirmed）的反向補集。
H079 已驗證「漲停萎縮 → 大跌前兆」（防守訊號），
H090 測「漲停熱絡持續 → 動量延續」（多頭訊號）。
- H079 探索時聚焦 lu_value_ratio bottom（萎縮）side
- 本研究的觸發是 H087 ETL 完成後做漲停/跌停 × 大盤走勢相關性分析的快速 finding：
  `lu_value_ratio_ma7` top 10% 對 +60d/+120d forward return 有 +2.54% / +2.29% lift over baseline

## Trading Intuition

H079 確認漲停萎縮預警下跌（消失訊號）。對稱地，**當漲停的成交額占比連續多日維持高水準**，
代表市場「資金集中強勢股、賺錢效應未消退」，這個 regime 可能傾向延續。

具體觀察：在 quick correlation 分析中（2010-2026, N=3987 日）：
- `lu_value_ratio_ma7` top 10%（漲停 7 日均成交額占比最熱的 10% 日子）：
  - +60d median return: **+6.12%**（baseline +3.58%，lift +2.54%）
  - +120d median return: **+7.86%**（baseline +5.56%，lift +2.29%）
- 不是簡單同日 tautology（同日相關只 +0.20），是 forward 表現的提升

關鍵差異：raw daily lu_value_ratio top 5% 沒有強訊號（+120d lift -0.40%），
**只有 ma7 smoothed 後 + 持續高才有訊號**。這跟 H079 對稱（H079 也是 ma7 + consecutive）。

## Hypothesis

> 當 `lu_value_ratio_ma7`（漲停成交額占全市場 7 日均比例）**連續 N 天**位於歷史 top 15% 之後，
> 進場買 0050 含息持有 60-120 天，能產生 forward median return 比 monthly DCA baseline
> **高 ≥ 2%**，且訊號 cluster 數 8-30 個（事件感合理）。

## Expected Distribution

Phase 1 預期：
- 取 lu_value_ratio_ma7 top 10/15/20% threshold
- 試 consecutive=1 / 3 / 5 天的不同要求
- 預期看到：
  - cluster 數隨 threshold 嚴格度遞減
  - +60/120d lift > +2%（已從 raw quantile 觀察到）
  - 觸發日多集中在 **bull regime** + Tier C 短回檔結束後
- 應該與 H085 panic days 幾乎無交集（H085 是 fear, H090 是 greed）

## Invalidation Condition

任一成立 → reject：

1. **無 edge over DCA**：所有 (threshold × consecutive) 組合的 +60d 和 +120d median
   都不超過 DCA baseline + 2%
2. **訊號太密**：top 10% + consec 1 下 cluster > 50（無法當「事件」）
3. **方向錯誤**：lift 為負（漲停熱絡反而預示後續弱 → 動量反轉）
4. **過度依賴 bull regime**：拿掉 macro_tier='bull' 子樣本後 lift < +1%
   （訊號只在牛市work不算 robust）
5. **與 H085 重疊**：Jaccard > 0.3（觸發日 overlap 太多代表只是另一種 fear/greed cycle proxy）

## Notes

- **與 H079 互補**：H079 漲停萎縮 = 「賣訊」；H090 漲停熱絡持續 = 「買訊」。
  若 confirm，兩者構成完整「漲停溫度計」雙向訊號。
- 重要 caveat：動量訊號傾向在牛市生效，bear/regime change 時可能失效。要看 IS/OOS。
- 不需要重建 ETL：market_breadth + stock_day 已涵蓋 2010-2026 完整資料（H087 已 backfill）
- DCA baseline 沿用 H085 monthly 算法（+60d med +3.58%、+120d +5.56%、+250d +11.38%）
- 若 confirm，可作為**多頭加碼**訊號（與 H085 panic 抄底互補），構成 fear/greed dual entry
- 預期成功機率比 H089 高 — 因為動量訊號在統計上常顯示穩健 lift，且本研究有具體 quantitative motivation（+2.54% / +2.29% 已從 raw quantile 觀察到）
