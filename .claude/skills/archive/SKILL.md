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

### Step 2.5：更新結果文件

**在搬移之前，必須先確認所有探索/回測結果已寫入對應的 markdown 文件。**

檢查項目：
- 對話中是否有額外跑過但尚未寫入 `results/distribution.md` 或 `results/backtest.md` 的分析結果（例如補充探索、追加測試、不同參數/timeframe 的結果）
- 如果有，先將這些結果補充寫入對應的結果文件，再進行後續步驟
- 確保結果文件完整反映所有已執行的分析，不只是第一輪的結果

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
- Proposal：proposal.md
- Distribution：results/distribution.md（如存在）
- Backtest：results/backtest.md（如存在）
```

### Step 4：搬移原始文件

將 `research/active/HXXX-名稱/` 整個目錄搬移到 archive 目錄中，然後刪除 active 下的原始目錄。
歸檔後 active 裡不應該還留有該假設的目錄。

### Step 5：衍生假設

列出所有 Derived Hypotheses，詢問使用者是否要立即開新假設。
如果要，觸發 /new-hypothesis 流程。

## 注意事項

- 歸檔後必須刪除 `research/active/HXXX-名稱/` 目錄
- archive 存 summary.md + 從 active 搬過來的完整文件
- 如果假設 confirmed，提醒使用者考慮是否要建立 strategies/live/ 下的策略規格
- **Confirmed → Live 時，必須將最新版的回測腳本（backtest.py）複製到 `strategies/live/SXXX-名稱/backtest.py`**，確保 live 策略隨時可重跑回測驗證
- 回答用台灣繁體中文，技術術語保留英文
