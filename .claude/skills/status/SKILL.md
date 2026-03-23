---
name: status
description: >
  顯示研究專案的整體狀態總覽。當使用者想知道目前有哪些進行中的假設、
  最近完成的研究、待處理的衍生想法時觸發。也適用於「現在在做什麼」、
  「研究進度」、「有哪些假設」、「overview」等情境。
---

# Status — 研究狀態總覽

快速掃描所有假設研究的進度。

## 流程

### Step 1：掃描 active 假設

列出 `research/active/` 下所有 `HXXX-*` 目錄，對每個假設判斷當前階段：

- **Proposal only**：只有 proposal.md，尚未開始探索
- **Phase 1 進行中**：有 tasks.md 但 distribution.md 不存在或 GATE 未填
- **Awaiting GATE**：distribution.md 存在，Gate Decision 未填
- **Phase 2 進行中**：GATE 通過，backtest.md 不存在或 Verdict 未填
- **Awaiting Verdict**：backtest.md 存在，Verdict 未填
- **Ready to Archive**：Verdict 已填，尚未歸檔

### Step 2：掃描 archive

列出 `research/archive/{confirmed,rejected,inconclusive}/` 下最近 3 個假設（依目錄名排序）。

### Step 3：收集衍生想法

掃描所有 `distribution.md` 和 `backtest.md` 中的 `Derived Hypotheses` 段落，
找出尚未建立對應 `research/active/HXXX-*` 目錄的衍生想法。

### Step 4：輸出報告

格式範例：

```
## Active Hypotheses
| ID | Name | Stage |
|---|---|---|
| H030 | orblong-research | Proposal only |
| H031 | estimate-hl-breakout-days | Phase 1 進行中 |

## Recent Archives
| ID | Name | Status |
|---|---|---|
| H016 | est-hl-latch | Rejected |
| H010 | settlement-volume-satzone | Confirmed |
| H006 | reversal-v2 | Confirmed |

## Unstarted Derived Ideas
- From H019: [theta decay 改用 DTE=0 策略]
- From H021: [E1 gap exhaustion reversal]
```

## 注意事項

- 這是唯讀操作，不修改任何文件
- 回答用台灣繁體中文，技術術語保留英文
