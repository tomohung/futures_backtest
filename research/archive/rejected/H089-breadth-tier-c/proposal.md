# Proposal: 廣度指標作為 Tier C 標準回檔的獨立進場 trigger

## ID
H089

## Derived From
- **H087-margin-breadth-augment** 的 Phase 1.3 結果：廣度指標（new lows 52w / high-low diff / adv/dec）
  在 Tier C 事件 hit rate ~100%，但加進 H085 panic composite 反而稀釋訊號 →
  也許**應該獨立用、不混合**
- **H088-tier-c-entry** 的 open question：原 H088 用傳統訊號（margin / z125 / econ）測 Tier C
  全部無法贏過 DCA baseline，但 Limitations 明示「未測廣度指標」並列為 derived 方向

## Trading Intuition

H085（S004 fg-composite）抓的是 Tier B 急速 panic（VIX+margin+z125+econ 同時極端），對 Tier C
標準回檔 13 個事件幾乎全漏。H088 試圖用 traditional fear 訊號補 Tier C entry，結果發現：
- 能標記 Tier C 事件的訊號 forward return 跑輸 DCA −1.3%
- forward return 略好的訊號 hit rate 只有 15-30%

H087 跑完發現 4 個廣度指標在 Tier B+C 21 個 trough 上 hit rate 75-88%。其中 Tier C 子集 hit rate 接近 100%。
這代表廣度指標標記「不同類型」的底部（個股廣泛打底而非單一指數 panic），可能正好對 Tier C 有效。

但 H088 結論「Tier C 結構性無 edge」可能仍正確。要先測才能確認。

## Hypothesis

> 用廣度指標（**new lows 52w**、**high-low diff**、**adv/dec** 中至少一個）單獨作為 trigger，
> 對 Tier C 事件（H085 漏抓的場景）能產生 forward return median 比 DCA monthly baseline
> 高 **≥ 5%**（+120d 或 +250d horizon），且觸發頻率合理（每年 < 30 個 cluster）。

## Expected Distribution

Phase 1 預期：
- 取每個廣度指標的 top 5% / top 10% threshold，看觸發日的事件分佈
- **若假設成立**：觸發日多落在 Tier C trough 附近 + forward return 顯著高於 DCA
- **若假設不成立**：觸發頻繁但 forward return 接近 DCA（H088 結論的延伸）或低於 DCA

關鍵子問題：
- 廣度極值是否真的「廣泛打底」訊號，還是只是「跟著指數跌」的同步指標？
- 廣度與 H085 panic 觸發日有無 Jaccard 重疊？（若高度重疊則無新價值）
- 是否能單獨拉出「**只有廣度極值、H085 沒觸發**」的 Tier C 專屬訊號？

## Invalidation Condition

任一成立 → reject：

1. **無 edge over DCA**：3 個廣度指標單獨 trigger 的 +120d median forward return
   都不超過 DCA baseline +5%（H088 標準是 +1%，但既然已有先例證據要更嚴）
2. **訊號太稀**：top 5% threshold 下 cluster 數 < 6（樣本不足以驗證）
3. **訊號太密**：top 5% threshold 下 cluster 數 > 50（不像「事件」，等於 noise）
4. **與 H085 高度重疊**：Jaccard similarity > 0.5（不提供新覆蓋）
5. **方向錯誤**：廣度單獨 trigger 也 underperform DCA → 確認 H088「Tier C 無 edge」結構結論

## Notes

- **預設失敗機率高**：H087 已測「廣度進 H085 composite」失敗，H088 已測「傳統訊號 in Tier C」失敗。
  H089 是把兩個失敗的「正交補集」測掉。
- 重要 derived-from constraint：**不能跟 H085 共享觸發日**（要刻意排除）。否則就只是 H085 的子集。
- DCA baseline 用 H085 explore 已建立的「monthly DCA」算法
- 若 reject，把 H088 + H089 合併結論「Tier C 結構性無 edge」寫進 H085 spec.md
- 若 confirm，可能衍生 S005 廣度 trigger 策略（Tier C specialist）
