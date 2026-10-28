#!/usr/bin/env bash
# UAMS 前端原子发布：构建 → 复制到 /var/www/uams/releases/<时间戳> → 原子切换 current。
# 需要 sudo 写入 /var/www；构建阶段以当前用户执行。
# 用法：bash deploy/deploy-frontend.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="$ROOT/frontend"
DIST="$FRONTEND/dist"
WEB_ROOT="${UAMS_WEB_ROOT:-/var/www/uams}"
STAMP="$(date +%Y%m%d_%H%M%S)"
RELEASE="$WEB_ROOT/releases/$STAMP"
KEEP_RELEASES="${UAMS_KEEP_RELEASES:-3}"

log()  { printf '\033[1;34m[deploy]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[deploy]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[deploy]\033[0m %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" -ne 0 ]] || die "请以普通用户运行；脚本只在复制阶段调用 sudo，避免构建产物归 root 所有。"
command -v npm >/dev/null || die "未找到 npm"
command -v rsync >/dev/null || die "未找到 rsync（sudo apt install rsync）"
command -v curl >/dev/null || die "未找到 curl"
[[ "$KEEP_RELEASES" =~ ^[0-9]+$ ]] || die "UAMS_KEEP_RELEASES 必须是整数"

SUDO=()
if [[ "$(id -u)" -ne 0 ]]; then
  command -v sudo >/dev/null || die "未找到 sudo；请以具备写权限的用户运行"
  SUDO=(sudo)
fi

log "构建前端..."
(cd "$FRONTEND" && npm run build)
[[ -f "$DIST/index.html" ]] || die "构建产物缺少 index.html（构建失败，未创建发布版本）"
log "构建成功"

log "创建发布目录 $RELEASE"
"${SUDO[@]}" install -d -m 755 "$WEB_ROOT" "$WEB_ROOT/releases" "$RELEASE"
"${SUDO[@]}" rsync -a --delete "$DIST/" "$RELEASE/"
# 目录 755 / 文件 644，确保 Nginx worker 可读且不保留无需的组写权限。
"${SUDO[@]}" chmod -R u=rwX,go=rX "$RELEASE"

# --- 发布前校验 Nginx 配置（Nginx 未安装时仅发布静态文件） ---
NGINX_INSTALLED=0
NGINX_RUNNING=0
UAMS_SITE_ENABLED=0
[[ -e /etc/nginx/sites-enabled/uams ]] && UAMS_SITE_ENABLED=1
if command -v nginx >/dev/null 2>&1; then
  NGINX_INSTALLED=1
  if ! "${SUDO[@]}" nginx -t; then
    die "nginx -t 失败，未切换 current；新 release 保留在 $RELEASE 供排查"
  fi
  if systemctl is-active --quiet nginx 2>/dev/null; then
    NGINX_RUNNING=1
  else
    warn "Nginx 已安装但未运行；将发布静态文件，跳过 reload"
  fi
  if [[ "$UAMS_SITE_ENABLED" -eq 0 ]]; then
    warn "UAMS 站点未启用（/etc/nginx/sites-enabled/uams）；静态文件发布后不会对外"
  fi
else
  warn "Nginx 未安装；仅发布静态文件，不执行 nginx -t/reload"
fi

PREV="$(readlink -f "$WEB_ROOT/current" 2>/dev/null || true)"
case "$PREV" in
  "$WEB_ROOT"/releases/*) ;;
  *) PREV="" ;;
esac

switch_current() {
  local target="$1"
  local tmp="$WEB_ROOT/.current.tmp.$$"
  "${SUDO[@]}" ln -sfn "$target" "$tmp"
  # 同一文件系统上的 rename，原子替换 current
  "${SUDO[@]}" mv -Tf "$tmp" "$WEB_ROOT/current"
}

rollback() {
  if [[ -n "$PREV" && -d "$PREV" ]]; then
    switch_current "$PREV" || true
    warn "已回滚 current -> $PREV"
  else
    "${SUDO[@]}" rm -f "$WEB_ROOT/current" || true
    warn "无上一有效版本，已移除 current（不影响旧启动器服务）"
  fi
  if [[ "$NGINX_RUNNING" -eq 1 ]]; then
    "${SUDO[@]}" systemctl reload nginx 2>/dev/null || warn "回滚后 Nginx reload 失败，请手动检查"
  fi
}

log "切换 current -> $STAMP"
switch_current "$RELEASE" || { rollback; die "current 切换失败"; }

if [[ "$NGINX_RUNNING" -eq 1 ]]; then
  if ! "${SUDO[@]}" systemctl reload nginx; then
    rollback
    die "Nginx reload 失败，已尝试回滚"
  fi
  if [[ "$UAMS_SITE_ENABLED" -eq 1 ]]; then
    if ! curl -fsS "http://127.0.0.1/" 2>/dev/null | grep -q '<div id="app"></div>'; then
      rollback
      die "Nginx 首页未返回 UAMS 前端（可能仍由默认站点响应），已尝试回滚"
    fi
  fi
fi

# --- 记录前一个有效版本，供人工回滚 ---
if [[ -n "$PREV" && -d "$PREV" ]]; then
  tmp="$WEB_ROOT/.previous.tmp.$$"
  "${SUDO[@]}" ln -sfn "$PREV" "$tmp"
  "${SUDO[@]}" mv -Tf "$tmp" "$WEB_ROOT/previous"
else
  "${SUDO[@]}" rm -f "$WEB_ROOT/previous"
fi

# --- 只清理 releases 下符合时间戳命名、且不是 current/previous 的旧版本 ---
CURRENT="$(readlink -f "$WEB_ROOT/current" 2>/dev/null || true)"
PREVIOUS="$(readlink -f "$WEB_ROOT/previous" 2>/dev/null || true)"
mapfile -t releases < <(
  find "$WEB_ROOT/releases" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' \
    | grep -E '^[0-9]{8}_[0-9]{6}$' | sort
)
if (( ${#releases[@]} > KEEP_RELEASES )); then
  remove_count=$(( ${#releases[@]} - KEEP_RELEASES ))
  for old in "${releases[@]:0:$remove_count}"; do
    path="$WEB_ROOT/releases/$old"
    if [[ "$path" == "$CURRENT" || "$path" == "$PREVIOUS" ]]; then
      continue
    fi
    log "清理旧发布 $old"
    "${SUDO[@]}" rm -rf -- "$path"
  done
fi

log "发布完成：$WEB_ROOT/current -> $RELEASE"
if [[ -n "$PREV" ]]; then
  log "上一版本：$PREV（同时记录在 $WEB_ROOT/previous）"
fi
if [[ "$NGINX_INSTALLED" -eq 1 && "$NGINX_RUNNING" -eq 1 ]]; then
  log "访问：http://127.0.0.1/"
else
  warn "Nginx 尚未运行；安装/启动 Nginx 后访问 http://127.0.0.1/"
fi
