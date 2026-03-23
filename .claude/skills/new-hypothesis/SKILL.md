---
name: new-hypothesis
description: >
  建立新的交易假設研究。當使用者想探索新的交易想法、市場觀察、策略概念時觸發。
  也適用於使用者說「我有個想法」、「觀察到一個現象」、「想測試一下」、
  「從 HXXX 衍生出來的」等情境。用於建立 research/active/ 下的假設目錄與文件。
---

# New Hypothesis

建立假設驅動的交易研究，從直覺到可測試的假設。

## 流程

### Step 1：載入背景

讀取以下檔案作為交易背景，幫助引導使用者：
- `specs/trading-principles.md`
- `specs/market-context.md`
- `specs/data-sources.md`

### Step 2：引導使用者

透過對話釐清以下資訊（不需要一次問完，自然對話即可）：

1. **交易直覺**：觀察到什麼市場現象？
2. **假設陳述**：具體、可測試的陳述（例如「當 X 條件成立時，接下來 N 天的報酬分佈會呈現右偏」）
3. **預期分佈**：探索階段預期會看到什麼結果？
4. **無效條件**：什麼結果代表假設不成立？（必須在開始前就定義）
5. **來源**：這是原創想法，還是從某個已有的假設衍生？

### Step 3：決定編號

掃描 `research/active/` 和 `research/archive/` 下所有 `HXXX-*` 目錄，找到最大編號 +1。

格式：`HXXX-簡短英文名稱`（例如 H032-gap-reversal）

### Step 4：建立目錄與文件

建立 `research/active/HXXX-名稱/` 目錄，生成以下兩個文件：

#### proposal.md

```markdown
# Proposal: [假設名稱]

## ID
HXXX

## Derived From
HXXX（來源假設）的 [distribution / backtest] 階段
或 Origin（原創）

## Trading Intuition
[用自然語言描述觀察到的市場現象]

## Hypothesis
[具體、可測試的陳述]

## Expected Distribution
[預期探索階段會看到什麼]

## Invalidation Condition
[什麼樣的結果代表這個假設不成立]

## Notes
```

#### tasks.md

```markdown
# Tasks: [假設名稱]

## Phase 1: Distribution Research

- [ ] 定義篩選條件
- [ ] 探索符合條件的歷史樣本數量與分佈
- [ ] 分析報酬分佈的基本統計特性
- [ ] 視覺化關鍵分佈圖

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 樣本數是否足夠？（最低門檻：XXX 筆）
- 分佈方向是否符合預期？
- 是否有明顯的 data snooping 疑慮？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 定義進出場規則
- [ ] 設定回測參數（手續費、滑價）
- [ ] 執行 in-sample 回測
- [ ] 執行 out-of-sample 驗證
- [ ] Walk-forward 測試
- [ ] 參數敏感度分析
```

### Step 5：確認

向使用者確認：
- Derived From 欄位是否正確
- 假設陳述是否清楚
- 無效條件是否合理

根據使用者的回饋即時修改 proposal.md。

## 注意事項

- Phase 1 的任務項目可以根據假設性質調整，不必完全照模板
- GATE 的最低樣本數門檻應由使用者根據假設性質決定
- 如果使用者已經有很清楚的想法，不需要過度引導，直接建檔即可
- 回答用台灣繁體中文，技術術語保留英文
