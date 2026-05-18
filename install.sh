#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/nanashiwang/ai-novel.git}"
BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/opt/ai-novel}"

if [ "$(uname -s)" != "Linux" ]; then
  echo "当前脚本面向 Linux 服务器。"
  exit 1
fi

if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
  RUN_USER="${SUDO_USER:-root}"
else
  if ! command -v sudo >/dev/null 2>&1; then
    echo "需要 sudo 权限安装 Docker 和系统依赖。"
    exit 1
  fi
  SUDO="sudo"
  RUN_USER="$(id -un)"
fi

run_as_root() {
  if [ -n "$SUDO" ]; then
    sudo "$@"
  else
    "$@"
  fi
}

install_packages() {
  if command -v apt-get >/dev/null 2>&1; then
    run_as_root apt-get update -y
    run_as_root apt-get install -y ca-certificates curl git make
  elif command -v dnf >/dev/null 2>&1; then
    run_as_root dnf install -y ca-certificates curl git make
  elif command -v yum >/dev/null 2>&1; then
    run_as_root yum install -y ca-certificates curl git make
  else
    echo "暂不支持当前系统包管理器，请先安装 curl/git/make/Docker。"
    exit 1
  fi
}

ensure_base_tools() {
  for tool in curl git make; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      install_packages
      break
    fi
  done
}

ensure_docker() {
  if command -v docker >/dev/null 2>&1; then
    if command -v systemctl >/dev/null 2>&1; then
      run_as_root systemctl start docker || true
    elif command -v service >/dev/null 2>&1; then
      run_as_root service docker start || true
    fi
    if docker info >/dev/null 2>&1 || { [ -n "$SUDO" ] && sudo docker info >/dev/null 2>&1; }; then
      return
    fi
  fi

  echo "开始安装 Docker..."
  curl -fsSL https://get.docker.com -o /tmp/ai-novel-get-docker.sh
  run_as_root sh /tmp/ai-novel-get-docker.sh
  rm -f /tmp/ai-novel-get-docker.sh

  if command -v systemctl >/dev/null 2>&1; then
    run_as_root systemctl enable --now docker
  elif command -v service >/dev/null 2>&1; then
    run_as_root service docker start || true
  fi

  if [ "$RUN_USER" != "root" ]; then
    run_as_root usermod -aG docker "$RUN_USER" || true
  fi
}

checkout_project() {
  if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR"
    if ! git diff --quiet || ! git diff --cached --quiet; then
      echo "$APP_DIR 有未提交改动，停止自动更新以免覆盖。"
      exit 1
    fi
    git fetch origin "$BRANCH"
    git checkout "$BRANCH"
    git pull --ff-only origin "$BRANCH"
    return
  fi

  if [ ! -d "$APP_DIR" ]; then
    run_as_root mkdir -p "$APP_DIR"
    if [ "$RUN_USER" != "root" ]; then
      run_as_root chown "$RUN_USER":"$(id -gn "$RUN_USER")" "$APP_DIR"
    fi
  fi

  git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
  cd "$APP_DIR"
}

ensure_base_tools
ensure_docker
checkout_project

echo "开始部署 AI Novel..."
make deploy

echo
echo "完成。默认访问地址："
echo "  前端：http://服务器IP:3000"
echo "  后端：http://服务器IP:8000/health"
