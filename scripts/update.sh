#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "当前有未提交改动，先停止更新，避免覆盖本地工作。"
  echo "请先提交或暂存后再运行：make update"
  exit 1
fi

git pull --ff-only origin "$CURRENT_BRANCH"
./scripts/deploy.sh
