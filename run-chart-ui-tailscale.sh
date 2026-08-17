#!/usr/bin/env bash
# 啟動 chart-ui 並只綁 Tailscale 介面，讓 tailnet 內的其它裝置可連。
#
# ⚠️ chart-ui 沒有任何認證機制。綁 tailnet 位址是靠 tailscale 本身做存取控制；
#    綁 0.0.0.0 等於把行情瀏覽介面直接開給外網，除非你已自行加上認證，否則別這樣做。
#
# Usage:
#   ./run-chart-ui-tailscale.sh             # 自動抓 tailscale ip -4
#   ./run-chart-ui-tailscale.sh 0.0.0.0     # 覆寫 host（無認證，自負風險）
#   CHART_UI_PORT=9000 ./run-chart-ui-tailscale.sh

set -euo pipefail
cd "$(dirname "$0")"

if ! command -v tailscale >/dev/null 2>&1; then
  echo "❌ 找不到 tailscale CLI，請先安裝並登入 Tailscale。" >&2
  exit 1
fi

host="${1:-}"
if [[ -z "$host" ]]; then
  host="$(tailscale ip -4 2>/dev/null | head -n1 || true)"
  if [[ -z "$host" ]]; then
    echo "❌ 無法從 'tailscale ip -4' 取得 IP，請確認 Tailscale 是否已連線。" >&2
    exit 1
  fi
fi

port="${CHART_UI_PORT:-8888}"
hostname_short="$(tailscale status --json 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("Self",{}).get("HostName",""))' 2>/dev/null || true)"

echo "=== chart-ui via Tailscale ==="
echo "  Host (bind): $host"
echo "  Port:        $port"
if [[ -n "$hostname_short" ]]; then
  echo "  其它裝置可連: http://${hostname_short}:${port}/  或  http://${host}:${port}/"
else
  echo "  其它裝置可連: http://${host}:${port}/"
fi
echo ""

export CHART_UI_HOST="$host"
export CHART_UI_PORT="$port"
exec uv run chart-ui
