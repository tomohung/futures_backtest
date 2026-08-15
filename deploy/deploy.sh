#!/usr/bin/env bash
# 部署 launchd job：把 deploy/ 的 plist 模板（所有 __XXX__ 為佔位符）
# 替換成真實值後，安裝到 ~/Library/LaunchAgents 並重載。
#
# 真實金鑰與絕對路徑只寫進 ~/Library/LaunchAgents 的複本，不進版控。
# 需求：互動 shell env 內已有 RESEND_API_KEY 與 FINMIND_API_KEY。
#
# 用法：
#   RESEND_API_KEY=... FINMIND_API_KEY=... bash deploy/deploy.sh
#   （或兩把 key 已在 env 直接跑）
set -euo pipefail

cd "$(dirname "$0")/.."   # 專案根目錄
PROJECT_DIR="$(pwd)"

PLIST=com.tomo.futures-daily.plist
SRC="deploy/${PLIST}.template"
DEST="$HOME/Library/LaunchAgents/$PLIST"
LABEL="com.tomo.futures-daily"

for var in RESEND_API_KEY FINMIND_API_KEY; do
    if [ -z "${!var:-}" ]; then
        echo "❌ 環境變數 ${var} 未設定，無法替換佔位符。" >&2
        exit 1
    fi
done

# 用 | 當 sed 分隔符，避免金鑰或路徑含 / 造成問題。
sed -e "s|__RESEND_API_KEY__|${RESEND_API_KEY}|g" \
    -e "s|__FINMIND_API_KEY__|${FINMIND_API_KEY}|g" \
    -e "s|__PROJECT_DIR__|${PROJECT_DIR}|g" \
    -e "s|__HOME__|${HOME}|g" \
    "$SRC" > "$DEST"

# 防呆：確認沒有任何佔位符漏替換（漏掉會讓 launchd 拿到字面值 __XXX__）
if grep -q '__[A-Z_]\+__' "$DEST"; then
    echo "❌ 仍有未替換的佔位符：" >&2
    grep -o '__[A-Z_]\+__' "$DEST" | sort -u >&2
    rm -f "$DEST"
    exit 1
fi

plutil -lint "$DEST"

launchctl unload "$DEST" 2>/dev/null || true
launchctl load "$DEST"

echo "✓ 已部署 ${LABEL} → ${DEST}"
echo "  （金鑰與絕對路徑已替換，僅存在於此複本，未進版控）"
