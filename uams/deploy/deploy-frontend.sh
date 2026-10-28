#!/usr/bin/env bash
# UAMS 前端原子发布：构建 → 复制到 /var/www/uams/releases/<时间戳> → 切换 current。
# 需要 sudo 写入 /var/www；构建阶段以当前用户执行。
# 用法：bash deploy/deploy-frontend.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="$ROOT/frontend"
DIST="$FRONTEND/dist"
WEB_ROOT="${UAMS_WEB_ROOT:-/var/www/uams}"
STAMP="$(date +%Y%m%d_%H%M%S)"
RELEASE="$WEB_ROOT/releases/$STAMP"

log() { printf '\033[1;34m[deploy]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[deploy]\033[0m %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" -ne 0 ]] || die "请以普通用户运行；脚本只在复制阶段调用 sudo，避免构建产物归 root 所有。"
command -v npm >/dev/null || die "未找到 npm"
command -v rsync >/dev/null || die "未找到 rsync（sudo apt install rsync）"

log "构建前端..."
(cd "$FRONTEND" && npm run build)
[[ -f "$DIST/index.html" ]] || die "构建产物缺少 index.html"

log "创建发布目录 $RELEASE"
sudo install -d -m 755 "$WEB_ROOT/releases"
sudo install -d -m 755 "$RELEASE"
sudo rsync -a --delete "$DIST/" "$RELEASE/"

log "原子切换 current -> $STAMP"
sudo ln -sfn "$RELEASE" "$WEB_ROOT/current"

log "校验 Nginx 配置并重载"
sudo nginx -t
sudo systemctl reload nginx

# 保留最近 3 个发布版本
mapfile -t old < <(find "$WEB_ROOT/releases" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort | head -n -3)
for d in "${old[@]:-}"; do
  [[ -n "$d" ]] || continue
  log "清理旧发布 $d"
  sudo rm -rf "$WEB_ROOT/releases/$d"
done

log "发布完成：$WEB_ROOT/current -> $RELEASE"
log "访问：http://127.0.0.1/"
