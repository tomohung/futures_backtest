#!/usr/bin/env bash
# 台指期行情每日更新 wrapper（給 launchd 排程用，也可手動執行）
#
# launchd 環境極簡（無 shell rc、PATH 不含 asdf shims），故：
#   1. plist 已在 EnvironmentVariables 設好 PATH（含 ~/.asdf/shims，使 uv 可被找到）
#   2. 本 script cd 到專案根目錄後，呼叫 uv run daily_update.py
#
# 用法：
#   bash run-daily-update.sh                 # 完整更新
#   bash run-daily-update.sh --skip-validate # 透傳參數給 daily_update.py
set -euo pipefail

cd "$(dirname "$0")"

LOG_DIR="logs/launchd"
mkdir -p "$LOG_DIR"

# 執行鎖：避免 6am/6pm 兩次更新（或手動執行）意外重疊造成 DuckDB 寫鎖衝突。
# mkdir 是原子操作；若鎖已存在則跳過本次。
LOCK_DIR=".daily_update.lock"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 另一個更新仍在執行中（$LOCK_DIR 存在），略過本次。"
    exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

echo "======================================================================"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 開始每日更新  args=$*"
echo "======================================================================"

# 找不到 uv 時給出明確錯誤（launchd PATH 設錯最常見的症狀）
if ! command -v uv >/dev/null 2>&1; then
    echo "❌ 找不到 uv。launchd plist 的 PATH 需包含 /Users/$(whoami)/.asdf/shims" >&2
    exit 1
fi

uv run python src/etl/daily_update.py "$@"
status=$?

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 更新結束 (exit=$status)"
exit $status
