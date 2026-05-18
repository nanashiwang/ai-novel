#!/usr/bin/env bash
set -euo pipefail

if [ "${1:-}" = "config" ] || [ "${1:-}" = "version" ]; then
  exec docker compose "$@"
fi

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  exec docker compose "$@"
fi

if command -v sudo >/dev/null 2>&1 && sudo docker info >/dev/null 2>&1; then
  exec sudo docker compose "$@"
fi

echo "Docker 不可用或未启动。请先启动 Docker 后重试。"
exit 1
