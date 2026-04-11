---
name: explore
description: >
  執行假設的 Phase 1 分佈探索研究。當使用者想分析某個假設的歷史數據分佈、
  執行探索性分析、查看樣本統計時觸發。也適用於「跑一下分佈」、「看看數據」、
  「Phase 1」、「探索 HXXX」等情境。
---

# Explore — Phase 1 Distribution Research

對 active hypothesis 執行分佈探索，產出數據支持 GATE 決策。

## 流程

### Step 1：定位假設

如果使用者指定了假設編號（HXXX），直接讀取。否則列出 `research/active/` 下所有假設讓使用者選擇。

讀取：
- `research/active/HXXX-名稱/proposal.md` — 了解假設與無效條件
- `research/active/HXXX-名稱/tasks.md` — 了解待辦任務

### Step 2：執行 Phase 1 任務

根據 tasks.md 中 Phase 1 的任務清單逐項執行：

1. 定義篩選條件
2. 探索歷史樣本數量與分佈
3. 分析報酬分佈的基本統計特性
4. 視覺化關鍵分佈圖（輸出圖檔或表格）

每完成一項，更新 tasks.md 中對應的 checkbox。

### Step 3：寫入結果

建立 `research/active/HXXX-名稱/results/` 目錄，生成 `distribution.md`：

```markdown
# Distribution Research Results: [假設名稱]

## Date
YYYY-MM-DD

## Conditions Tested
[實際用的篩選條件]

## Sample
- 總樣本數：
- 時間範圍：
- 市場：

## Key Findings
[數字、圖表描述、關鍵觀察]

## Vs. Expected
[跟 proposal 裡的預期比較，符合 / 不符合 / 部分符合]

## Gate Decision
[ ] 進入 Phase 2
[ ] Archive（原因：）
[ ] 修改假設（修改內容：）

## Derived Hypotheses
- HXXX：[衍生想法簡述]
```

### Step 4：呈現 GATE

在結果末尾明確呈現 GATE 問題，**等待使用者做出決定**：

- 樣本數是否足夠？
- 分佈方向是否符合預期？
- 是否有明顯的 data snooping 疑慮？

不要自行決定是否通過 GATE。

## 注意事項

- 所有數字結論必須附上樣本數（N=XXX）
- 發現衍生想法時，記錄在 distribution.md 的 Derived Hypotheses，不主動修改其他文件
- 如果數據不支持假設，誠實呈現，不要試圖美化結果
- 回答用台灣繁體中文，技術術語保留英文
- **Python 腳本必須保留**：探索分析用的 Python 腳本必須存放在假設目錄下（如 `research/active/HXXX-名稱/explore.py`），不可只輸出 markdown 結果而不保存腳本。這些腳本是後續衍生假設、重跑驗證、跨假設比對的基礎。
