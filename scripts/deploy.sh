#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker 未安装或不可用。"
  exit 1
fi

if ! ./scripts/compose.sh version >/dev/null 2>&1; then
  echo "Docker Compose 未安装或不可用。"
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "已从 .env.example 创建 .env。生产部署前请修改密钥。"
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

FRONTEND_PORT="${FRONTEND_PORT:-13000}"
BACKEND_PORT="${BACKEND_PORT:-8000}"

./scripts/compose.sh build
./scripts/compose.sh up -d

echo
echo "部署完成："
echo "  前端：http://localhost:${FRONTEND_PORT}"
echo "  后端：http://localhost:${BACKEND_PORT}/health"
echo "  Temporal UI：http://localhost:8080"
echo "  MinIO Console：http://localhost:9001"
