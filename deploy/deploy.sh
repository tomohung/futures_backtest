#!/usr/bin/env bash
# 部署 launchd job：把 deploy/ 的 plist 模板（RESEND_API_KEY 為佔位符）
# 替換成真實金鑰後，安裝到 ~/Library/LaunchAgents 並重載。
#
# 真實金鑰只寫進 ~/Library/LaunchAgents 的複本，不進版控。
# 需求：互動 shell env 內已有 RESEND_API_KEY。
#
# 用法：
#   RESEND_API_KEY=... bash deploy/deploy.sh     # 或 key 已在 env 直接跑
set -euo pipefail

cd "$(dirname "$0")/.."   # 專案根目錄

PLIST=com.tomo.futures-daily.plist
SRC="deploy/$PLIST"
DEST="$HOME/Library/LaunchAgents/$PLIST"
LABEL="com.tomo.futures-daily"

if [ -z "${RESEND_API_KEY:-}" ]; then
    echo "❌ 環境變數 RESEND_API_KEY 未設定，無法替換佔位符。" >&2
    exit 1
fi

# 用 | 當 sed 分隔符，避免金鑰含 / 造成問題。
sed "s|__RESEND_API_KEY__|${RESEND_API_KEY}|" "$SRC" > "$DEST"

plutil -lint "$DEST"

launchctl unload "$DEST" 2>/dev/null || true
launchctl load "$DEST"

echo "✓ 已部署 ${LABEL} → ${DEST} （RESEND_API_KEY 已替換，未進版控）"
