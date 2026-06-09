# Archive: Reversal 方向濾網改用 DCI 盤中廣度訊號

## Status
Rejected

## Summary
測試把 Reversal(S002) 的 5m120MA 方向濾網（決定當天 fade 多/空偏向）換成 H095 衍生的
**09:10 DCI 盤中廣度/龍頭 thrust** 方向。三組對照 base / dci(強分位信 DCI) / both(同向才進)。
結論：DCI 方向**對 reversal 無 edge**——表面改善是單筆雜訊，乾淨多方訊號對 reversal 多單零排序力。
根因為結構性：reversal 是 fade（賺反彈），DCI 是延伸訊號（賺趨勢），兩者正交。

## Key Evidence
窗 2025-06-02~2026-02-26（上市-only、in-sample only、偏多頭、無 OOS）：

| arm | n | 總損益% | Sharpe | PF | 勝率 |
|---|---|---|---|---|---|
| base | 68 | 4.54 | 0.218 | 1.81 | 54.4% |
| dci | 48 | 5.65 | 0.327 | 2.54 | 58.3% |
| dcilong（只多方訊號） | 58 | 4.67 | 0.257 | 2.03 | 55.2% |

- **歸因**：dci−base=+1.11 **全來自 1 筆 dci 獨有交易(+1.16)**；翻向機制 0 貢獻（無任一日兩組同進反向）。
- **多方隔離**：dcilong 多單(n=49, 3.10) **與 base 逐欄完全相同**；dci_long 對 base 49 筆多單
  **corr(損益%)=+0.069 ≈ 0**，「強且正」子集(n=6)還更差。
- **結構性對照**：dci_long 對 EstHL（順勢）交易 corr(MFE)=**+0.53**；對 Reversal 多單 **+0.069**。
- 命中預登記 Invalidation #3（改善落雜訊內）。Phase 1 雖顯示歧異日 dci 方向命中 72% vs base 28%，
  但 reversal 是 fade，**方向猜對≠賺**（base 在歧異日的單仍打平 +0.04，沒虧）。

## Why Rejected
- DCI 是「趨勢/延伸」訊號（預測當天往上衝多遠），fade 策略賺的是「回檔後反彈」，兩者正交 → 機制上幫不上。
- 表面績效改善歸因到單筆，非系統性 edge；乾淨多方訊號隔離後對 reversal 多單零作用。
- 獨立再確認 H101：方向濾網非 reversal 的 alpha 源、base 難打敗——連廣度型外部訊號也一樣，
  因為問題是結構性的（fade ≠ 方向賭注），非訊號品質不足。
- 空方 dci_short 形式上未測（使用者選擇先放），但結構性理由預期亦然。

## Derived Hypotheses
- **H110-d3（結構性結論）**：方向預測訊號該配**順勢/突破族**（方向對=賺），不該配 fade/均值回歸族。
  DCI 的價值在「順勢延伸」場景（呼應 H095 對 EstHL 的 +0.53 排序力）。
- **H110-d4**：DCI 當「趨勢日 veto」（高信心趨勢日縮量/不 fade，而非翻向）是否提供真實防禦性 selectivity？
  與本案「翻向」不同槓桿，待更大樣本。
- **H110-d1**：層 A 最強分位 09:05 即 75% 方向命中 → 「強 thrust 早盤定方向」或可獨立成開盤方向訊號。
- **H110-d2**：5m120MA 在 reversal 歧異日命中僅 28% → 是否為「力竭反轉日」的落後反指標，值得單獨檢視。

## Code Note
`src/strategies/reversal.py` 保留新增的 `dir_mode` ∈ {'dci','both','dcilong'}（讀注入的 DCI_Dir/DCI_Strong；
live 預設 'base' 行為零變動，比照 H101 留 A/B/C 的慣例），供本目錄 `backtest.py` 重跑。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Backtest：results/backtest.md
- Scripts：explore.py, backtest.py（依賴 H095 的 DCI 計算與 results/dci_checkpoint_panel.csv）
