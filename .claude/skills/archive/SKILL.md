---
name: archive
description: >
  歸檔已完成的假設研究。當使用者想把假設標記為 confirmed/rejected/inconclusive、
  整理研究結論、歸檔完成的研究時觸發。也適用於「歸檔 HXXX」、「這個假設結束了」、
  「標記為 rejected」等情境。
---

# Archive — 歸檔假設研究

將已有 verdict 的假設歸入對應的 archive 分類。

## 流程

### Step 1：讀取假設資料

讀取該假設的所有文件：
- `research/active/HXXX-名稱/proposal.md`
- `research/active/HXXX-名稱/results/distribution.md`（如存在）
- `research/active/HXXX-名稱/results/backtest.md`（如存在）

### Step 2：決定分類

根據 Verdict 或使用者指示，決定放入：
- `research/archive/confirmed/` — 假設成立，策略可用
- `research/archive/rejected/` — 假設不成立，無 edge
- `research/archive/inconclusive/` — 結果不明確，可能未來重新探索

### Step 3：生成 archive 摘要

在目標目錄建立 `HXXX-名稱/` 子目錄，生成 `summary.md`：

```markdown
# Archive: [假設名稱]

## Status
Confirmed / Rejected / Inconclusive

## Summary
[兩三句話說明這個假設是什麼、結果如何]

## Key Evidence
[支持這個結論的關鍵數字或觀察]

## Why Confirmed / Rejected / Inconclusive
[核心原因]

## Derived Hypotheses
- HXXX：[從這裡衍生出去的假設]

## Links
- Proposal：research/active/HXXX-名稱/proposal.md
- Distribution：research/active/HXXX-名稱/results/distribution.md
- Backtest：research/active/HXXX-名稱/results/backtest.md
```

### Step 4：處理原始文件

將 `research/active/HXXX-名稱/` 目錄下的原始 spec 和 proposal 等文件，
複製到 archive 目錄中（保留 active 目錄不刪除，作為完整記錄）。

### Step 5：衍生假設

列出所有 Derived Hypotheses，詢問使用者是否要立即開新假設。
如果要，觸發 /new-hypothesis 流程。

## 注意事項

- active 目錄保留不刪除
- archive 只存摘要 + 原始文件副本
- 如果假設 confirmed，提醒使用者考慮是否要建立 strategies/live/ 下的策略規格
- 回答用台灣繁體中文，技術術語保留英文
