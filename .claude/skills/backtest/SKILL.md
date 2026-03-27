---
name: backtest
description: >
  執行假設的 Phase 2 回測驗證。當使用者想對已通過 GATE 的假設進行回測、
  測試進出場規則、做 walk-forward 驗證時觸發。也適用於「跑回測」、「Phase 2」、
  「驗證 HXXX」、「測試策略」等情境。必須先通過 Phase 1 GATE 才能執行。
---

# Backtest — Phase 2 回測驗證

對通過 GATE 的假設執行完整回測，產出 verdict。

## 流程

### Step 1：確認 GATE 已通過

讀取 `research/active/HXXX-名稱/results/distribution.md`，確認 Gate Decision 填寫為「進入 Phase 2」。

**如果 GATE 未通過或未填寫，停止執行並通知使用者。** 不在未通過 GATE 的情況下執行回測。

### Step 2：載入背景

讀取：
- `research/active/HXXX-名稱/proposal.md` — 假設與無效條件
- `research/active/HXXX-名稱/tasks.md` — Phase 2 任務清單
- `research/active/HXXX-名稱/results/distribution.md` — Phase 1 發現

### Step 3：執行 Phase 2 任務

根據 tasks.md 中 Phase 2 的任務清單：

1. 定義進出場規則
2. 設定回測參數（手續費、滑價）
3. 執行 in-sample 回測
4. 執行 out-of-sample 驗證
5. Walk-forward 測試
6. 參數敏感度分析

參數優化後**必須**做 out-of-sample 驗證，否則不能標記 Confirmed。

每完成一項，更新 tasks.md 中對應的 checkbox。

### Step 4：寫入結果

生成 `research/active/HXXX-名稱/results/backtest.md`：

```markdown
# Backtest Results: [假設名稱]

## Date
YYYY-MM-DD

## Parameters
[最終使用的參數]

## Results

| Metric | In-Sample | Out-of-Sample |
|---|---|---|
| Sharpe Ratio | | |
| Annual Return | | |
| Max Drawdown | | |
| Win Rate | | |
| # of Trades | | |
| Avg Hold Period | | |

## Walk-Forward Summary
[結果描述]

## Parameter Sensitivity
[對哪些參數敏感、對哪些穩健]

## Verdict
[ ] Confirmed　[ ] Rejected　[ ] Inconclusive

## Derived Hypotheses
- HXXX：[衍生想法簡述]
```

### Step 5：呈現 Verdict

在結果末尾明確呈現 Verdict，**等待使用者做出最終決定**。

提供判斷依據：
- IS 和 OOS 結果是否一致？
- 是否符合 proposal 的無效條件？
- 參數是否穩健？

## 注意事項

- 所有數字結論必須附上樣本數
- 績效用損益%（非絕對點數）做跨年度比較
- 發現衍生想法時，記錄在 backtest.md 的 Derived Hypotheses
- 回答用台灣繁體中文，技術術語保留英文
- **Python 腳本必須保留**：回測用的 Python 腳本必須存放在假設目錄下（如 `research/active/HXXX-名稱/backtest.py`），不可只輸出 markdown 結果而不保存腳本。這些腳本是後續衍生假設、重跑驗證、Pine Script 實作對照的基礎。
