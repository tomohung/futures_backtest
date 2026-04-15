# Proposal: S/R 支撐壓力有效性驗證

## ID
H062

## Derived From
Origin（源自 key_prices.py 現有功能的驗證需求）

## Trading Intuition
key_prices.py 計算了 Swing High/Low 聚類和 Volume Profile HVN 作為支撐壓力，
每天早盤簡報都會列出這些價位，但從未驗證過價格碰到這些位置時是否真的會產生反應。
如果 S/R 有效，可以作為策略濾網或獨立的進場依據。

## Hypothesis
key_prices.py 計算的支撐壓力（Swing 聚類 + VP HVN），當日盤價格觸及這些價位時，
產生有效反應（反彈/反轉）的比率顯著高於隨機價位。

## Expected Distribution
- 觸及 S/R 後反轉的命中率 > 50%（隨機基準約 50%）
- S/R 處的平均反彈幅度 > 隨機價位的平均反彈幅度
- Swing 聚類（touch count 越多）效果越好

## Invalidation Condition
- S/R 觸及後的反應率與隨機價位無顯著差異（p > 0.05）
- 或命中率雖高但平均反彈幅度太小（< 20 點），不具交易價值

## Notes
- 驗證方式：對歷史每個交易日 T，用 T-1 前的資料計算 S/R（模擬事前視角），再看 T 日的價格反應
- 需要建立隨機對照組：在同樣價格範圍內隨機取等量的價位，做相同的反應分析
- 分開統計 Swing High/Low 聚類 vs Volume Profile HVN 的效果
- 觸及定義：價格進入 SR ± N 點（N 待探索，初始 30 點）
- 有效反應定義：觸及後 M 根 1分K 內反轉超過 T 點（M, T 待探索）
