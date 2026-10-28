#!/usr/bin/env bash
# 只读预检：venv、env_guard、MySQL 单元、systemd unit、8000 端口、静态目录。
# 不修改系统配置，不需要 sudo。
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
WEB_ROOT="${UAMS_WEB_ROOT:-/var/www/uams}"
STATUS=0

ok()   { printf '  [OK]      %s\n' "$*"; }
warn() { printf '  [WARN]    %s\n' "$*"; STATUS=1; }
fail() { printf '  [BLOCKED] %s\n' "$*"; STATUS=2; }

echo "== UAMS systemd/后端部署预检 =="
[[ -x "$BACKEND/.venv/bin/python" ]] && ok "venv：$BACKEND/.venv/bin/python" \
  || fail "缺少后端 venv：$BACKEND/.venv/bin/python"
[[ -f "$BACKEND/scripts/env_guard.py" ]] && ok "env_guard.py 存在" \
  || fail "缺少 backend/scripts/env_guard.py"
[[ -f "$BACKEND/.env" ]] && ok "backend/.env 存在" \
  || fail "缺少 backend/.env（禁止使用内置默认连接）"

echo "-- MySQL --"
if systemctl is-active --quiet mysql.service 2>/dev/null; then
  ok "mysql.service 运行中"
else
  fail "mysql.service 未运行"
fi

echo "-- systemd unit --"
if systemctl cat uams-backend.service >/dev/null 2>&1; then
  ok "uams-backend.service 已安装"
  systemctl is-active uams-backend.service 2>/dev/null | sed 's/^/  当前状态：/'
else
  warn "uams-backend.service 未安装（sudo cp deploy/systemd/...）"
fi
if command -v systemd-analyze >/dev/null 2>&1; then
  if systemd-analyze verify "$ROOT/deploy/systemd/uams-backend.service" 2>&1 | grep -q "uams-backend"; then
    fail "systemd-analyze verify 报告 UAMS unit 问题"
  else
    ok "systemd-analyze verify 未报告 UAMS unit 问题"
  fi
fi

echo "-- 8000 端口 --"
if ss -ltnp 2>/dev/null | grep -qE ':8000\s'; then
  warn "8000 已被占用；启动 systemd 前请先 ./start.sh stop"
  ss -ltnp 2>/dev/null | grep -E ':8000\s' | sed 's/^/  /'
else
  ok "8000 空闲"
fi

echo "-- 静态目录 --"
[[ -f "$WEB_ROOT/current/index.html" ]] && ok "$WEB_ROOT/current/index.html 存在" \
  || warn "前端尚未发布到 $WEB_ROOT/current（先运行 deploy/deploy-frontend.sh）"

echo "-- journal --"
ok "后端日志：journalctl -u uams-backend -f"
echo
case "$STATUS" in
  0) echo "RESULT: READY" ;;
  1) echo "RESULT: NEEDS_ATTENTION" ;;
  *) echo "RESULT: BLOCKED" ;;
esac
exit "$STATUS"
