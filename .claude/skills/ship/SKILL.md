---
name: ship
description: "Commit all changes and push to main. Use this whenever the user says 'commit', 'push', 'ship', 'commit and push', '上傳', '推上去', or any variation of wanting to save and upload their work to GitHub. Also trigger when the user finishes a task and says something like 'ok done' or '好了' followed by wanting to commit."
---

# Ship — Commit & Push to Main

把目前的 changes 分類打包成 commits，然後直接 push 到 main。

## 流程

### Step 1：檢視變更

同時執行：
- `git status`（看 untracked + modified files）
- `git diff`（看 staged + unstaged 的實際變更內容）
- `git log --oneline -5`（參考最近的 commit message 風格）

### Step 2：分類變更

根據檔案路徑和變更性質，把 changes 分成邏輯群組。每個群組一個 commit。

常見分類規則（依此專案慣例）：
- `research/` → `research: ...`
- `src/strategies/` → `feat:` 或 `refactor:`
- `src/etl/` → `feat:` 或 `fix:`
- `src/backtest/explore_*.py` → `research: ...`（探索腳本屬於研究）
- `indicators/tradingview/` → `feat:` 或 `fix:`（Pine Script）
- `specs/` / `docs/` → `docs: ...`
- `.claude/skills/` → `chore: ...`
- bug fixes → `fix: ...`
- 重構但不改行為 → `refactor: ...`

如果所有變更都屬於同一類，一個 commit 就好，不要硬拆。

### Step 3：逐一 Commit

對每個群組：
1. `git add <specific files>` — 只加該群組的檔案，不用 `git add -A`
2. 用 HEREDOC 寫 commit message：
   ```bash
   git commit -m "$(cat <<'EOF'
   category: concise description of what changed and why

   Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
   EOF
   )"
   ```

Commit message 規則：
- 第一行：`category: 簡短描述`（英文，< 72 字元）
- 聚焦 **why** 而非 what — 看 diff 就知道改了什麼，commit message 要說為什麼改
- 如果有多個相關變更可以用第二行之後補充，但通常一行就夠

### Step 4：Push

```bash
git push
```

直接推 main，不開 branch、不開 PR。

### Step 5：確認

跑 `git status` 確認 clean，回報完成。格式：
```
Done. <short-hash> pushed to main.
```
多個 commits 時列出每個。

## 注意事項

- 不要 commit `.env`、credentials、`.duckdb` 等敏感或大型檔案
- 如果 working tree 已經 clean（沒有任何變更），不要建空 commit，直接告知使用者
- 不要用 `--amend`、`--force`、`--no-verify`
- 如果 push 失敗（例如 remote 有新的 commits），先 `git pull --rebase` 再 push
