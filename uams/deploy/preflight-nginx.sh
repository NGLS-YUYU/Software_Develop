#!/usr/bin/env bash
# 只读预检：Nginx/80 端口/default_server/静态目录/API 端口。
# 不修改任何系统配置，不需要 sudo。
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_ROOT="${UAMS_WEB_ROOT:-/var/www/uams}"
STATUS=0

ok()   { printf '  [OK]      %s\n' "$*"; }
warn() { printf '  [WARN]    %s\n' "$*"; STATUS=1; }
fail() { printf '  [BLOCKED] %s\n' "$*"; STATUS=2; }

echo "== UAMS Nginx 部署预检 =="
if command -v nginx >/dev/null 2>&1; then
  ok "Nginx 已安装：$(command -v nginx)"
else
  fail "Nginx 未安装（需要 sudo apt install nginx）"
fi

echo "-- 80 端口 --"
if ss -ltnp 2>/dev/null | grep -qE ':80\s'; then
  ss -ltnp 2>/dev/null | grep -E ':80\s' | sed 's/^/  /'
else
  warn "80 端口当前空闲（Nginx 尚未运行）"
fi

echo "-- 站点配置 --"
if [[ -d /etc/nginx/sites-enabled ]]; then
  DEFAULT_SITE=0
  [[ -L /etc/nginx/sites-enabled/default || -f /etc/nginx/sites-enabled/default ]] && DEFAULT_SITE=1
  [[ "$DEFAULT_SITE" -eq 1 ]] && warn "Ubuntu 默认站点仍启用：需先备份并停用，否则 IP 访问可能进入欢迎页" \
                               || ok "Ubuntu 默认站点未启用"
  if [[ -L /etc/nginx/sites-enabled/uams || -f /etc/nginx/sites-enabled/uams ]]; then
    ok "UAMS 站点已启用"
  else
    warn "UAMS 站点未启用（sites-enabled/uams 不存在）"
  fi
  if find /etc/nginx/sites-enabled -maxdepth 1 \( -type f -o -type l \) -name '*disabled*' | grep -q .; then
    warn "sites-enabled 中存在 *disabled* 文件；Nginx 的 include sites-enabled/* 仍会加载，请移出该目录"
  fi
  echo "  default_server 声明："
  grep -Rsn "default_server" /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null | sed 's/^/    /' \
    || echo "    无"
  echo "  监听 80 的配置："
  grep -Rsn "listen[[:space:]]\+80" /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null | sed 's/^/    /' \
    || echo "    无"
  OTHERS=$(grep -Rls "listen[[:space:]]\+80" /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null \
    | grep -vE '/uams$|/default$' || true)
  if [[ -n "$OTHERS" ]]; then
    warn "除 UAMS/default 外还有其他 80 站点，请确认 IP 访问落到 UAMS："
    printf '    %s\n' $OTHERS
  fi
else
  fail "未找到 /etc/nginx/sites-enabled（Nginx 未安装或未初始化）"
fi

echo "-- 静态目录 --"
if [[ -f "$WEB_ROOT/current/index.html" ]]; then
  ok "前端已发布：$WEB_ROOT/current"
  [[ -L "$WEB_ROOT/current" ]] && echo "  current -> $(readlink -f "$WEB_ROOT/current")"
else
  warn "前端尚未发布到 $WEB_ROOT/current"
fi

echo "-- 后端 --"
if ss -ltn 2>/dev/null | grep -qE '127\.0\.0\.1:8000|0\.0\.0\.0:8000'; then
  warn "8000 已被占用；切 systemd 前需停止旧 uvicorn（./start.sh stop）"
  ss -ltnp 2>/dev/null | grep -E ':8000\s' | sed 's/^/  /'
else
  ok "8000 空闲"
fi

echo
case "$STATUS" in
  0) echo "RESULT: READY（可继续安装/切换）" ;;
  1) echo "RESULT: NEEDS_ATTENTION（按 WARN 处理后再切换）" ;;
  *) echo "RESULT: BLOCKED（先解决 BLOCKED 项）" ;;
esac
exit "$STATUS"
