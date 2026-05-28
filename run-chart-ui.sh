#!/usr/bin/env bash
# 啟動 chart-ui。預設綁 127.0.0.1:8888；可用 CHART_UI_HOST / CHART_UI_PORT 覆寫。
# 綁 tailscale：CHART_UI_HOST=$(tailscale ip -4) ./run-chart-ui.sh
set -euo pipefail
export CHART_UI_HOST="${CHART_UI_HOST:-127.0.0.1}"
export CHART_UI_PORT="${CHART_UI_PORT:-8888}"
echo "chart-ui → http://${CHART_UI_HOST}:${CHART_UI_PORT}/"
exec uv run chart-ui
