# Proposal: XQ 發財橘子純價量策略候選清單

## ID
H050

## Derived From
Origin — 系統性掃描 XQ 發財橘子部落格（114 頁、~1140 篇文章）

## Source
https://www.xq.com.tw/xstrader/author/eddie/

## Trading Intuition
發財橘子（Eddie）長期在 XQ 部落格分享大量技術指標與策略概念，涵蓋量價分析、K 線型態、動能指標、波動率通道等。
這些概念原本針對台股個股，但其中「只需價量資料」的部分可以直接或改造後應用於台指期日盤當沖/波段策略。

## Hypothesis
從 62 個純價量策略/指標候選中，能篩選出至少 3-5 個在台指期日盤有統計顯著性的策略或濾網，
補足現有 EstHL/ORB 策略在盤整日、反轉日的弱點。

## Approach
這是一個 **meta-hypothesis**（候選清單），不直接進行 Phase 1/2。
流程為：逐一評估候選 → 有潛力者獨立建立 HXXX 假說 → 走標準 Phase 1 → Phase 2 流程。

## Candidate List
完整清單見 `research/xq-eddie-strategy-candidates.md`（62 個候選，7 大類）

### 優先候選（直接適用台指期當沖）

**獨立策略：**
1. **G1 開盤五分鐘不回頭** — 前 5 根 1mK 連續收漲收最高，強力追價
2. **G2 開高破平盤後又站回** — 開高→跌破平盤→站回，洗盤結束訊號
3. **G3 開盤 N 分鐘連續收紅** — 連續 N 根分鐘 K 收紅
4. **A1 SuperTrend** — ATR 通道趨勢跟隨，可對比 ORB
5. **C1 VSA 無供應** — 窄幅低量回檔 = 賣壓枯竭
6. **C2 Weis Wave Volume** — 按價格波段累積量的背離

**濾網（疊加在現有策略上）：**
7. **E1 CHOP 斬波指標** — 盤整 vs 趨勢判斷
8. **E2 Choppy Market Index** — 同上替代方案
9. **D1 STARC 平均波幅通道** — ATR 通道，可對比 EstRange SatZone

**量價深度分析：**
10. **C3 VWMACD** — 量加權 MACD，放量時更靈敏
11. **C4 TSV** — 資金流背離
12. **C10 Force Index** — 每根 K 棒多空力度

## Invalidation Condition
- 若評估超過 20 個候選後，沒有任何一個在台指期 1m K 上產出有意義的分佈差異 → 終止此方向
- 個別候選的無效條件在各自的 HXXX 假說中定義

## Notes
- 部落格文章多針對台股個股，轉換到期貨需注意：無市值篩選、無基本面、交易時段不同
- G4/G5（盤中多空指標）需個股資料，目前資料不支援，暫時排除
- 候選清單會持續更新，發現新來源可追加
