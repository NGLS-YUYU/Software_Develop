#!/usr/bin/env bash
# UAMS 统一启动脚本（FIX-007）
#
#   ./start.sh              启动后端 + 前端（默认 dev 模式：Vite 开发服务器）
#   ./start.sh prod         生产模式：先构建前端，再用 vite preview 提供静态服务
#   ./start.sh stop         停止本脚本启动的进程
#   ./start.sh restart      重启
#   ./start.sh status       查看运行状态与健康检查
#
# 安全约定（FIX-007 §十九）：本脚本不写死任何数据库密码或 JWT_SECRET，
# 一律沿用 backend/.env（pydantic-settings 读取）或外部环境变量。
#
# 可用环境变量覆盖（都有默认值）：
#   UAMS_BACKEND_HOST=0.0.0.0  UAMS_BACKEND_PORT=8000
#   UAMS_FRONTEND_HOST=0.0.0.0 UAMS_FRONTEND_PORT=5173（prod 模式为 4173）
#   UAMS_BACKEND_URL=http://127.0.0.1:8000   # 前端代理目标
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
RUN_DIR="$ROOT/.run"
LOG_DIR="$ROOT/logs"

BACKEND_HOST="${UAMS_BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${UAMS_BACKEND_PORT:-8000}"
FRONTEND_HOST="${UAMS_FRONTEND_HOST:-0.0.0.0}"
MODE="dev"
FRONTEND_PORT="${UAMS_FRONTEND_PORT:-5173}"

BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"

log()  { printf '\033[1;34m[UAMS]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[UAMS]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[UAMS]\033[0m %s\n' "$*" >&2; }

lan_ip() {
  # 取默认路由使用的网卡地址；失败时退回 hostname -I 的第一个
  ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K[0-9.]+' | head -1 \
    || hostname -I 2>/dev/null | awk '{print $1}'
}

pid_alive() {
  local f="$1"
  [[ -f "$f" ]] && kill -0 "$(cat "$f")" 2>/dev/null
}

# ---------------------------------------------------------------- 环境检查
check_env() {
  log "检查运行环境..."

  [[ -x "$BACKEND_DIR/.venv/bin/python" ]] || {
    err "未找到后端虚拟环境：$BACKEND_DIR/.venv"
    err "请先执行： cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
  }
  log "  后端 venv         OK"

  command -v node >/dev/null 2>&1 || { err "未找到 node，请先安装 Node.js"; exit 1; }
  [[ -d "$FRONTEND_DIR/node_modules" ]] || {
    err "未找到前端依赖：$FRONTEND_DIR/node_modules"
    err "请先执行： cd frontend && npm install"
    exit 1
  }
  log "  前端 node_modules OK"

  if [[ -f "$BACKEND_DIR/.env" ]]; then
    log "  配置文件          backend/.env"
  else
    warn "未找到 backend/.env —— 将使用 backend/app/core/config.py 的内置默认值"
    warn "  默认值包含演示用数据库口令与占位 JWT_SECRET，仅适合本机演示；"
    warn "  局域网部署前请复制 backend/.env.example 为 backend/.env 并修改（见 docs/DEPLOYMENT.md §2）"
  fi
}

# ---------------------------------------------------------------- 数据库检查
check_database() {
  log "检查数据库连接..."
  local out
  if out="$(cd "$BACKEND_DIR" && .venv/bin/python - <<'PY' 2>&1
import sys
try:
    from sqlalchemy import text
    from app.db.session import engine
    with engine.connect() as c:
        c.execute(text("SELECT 1"))
    print("OK")
except Exception as e:  # noqa: BLE001
    print("FAIL " + str(e).splitlines()[0][:160])
    sys.exit(1)
PY
  )" && [[ "$out" == "OK" ]]; then
    log "  MySQL            OK"
  else
    err "数据库连接失败：${out:-未知错误}"
    err "请确认 MySQL 已启动、数据库已迁移（cd backend && .venv/bin/alembic upgrade head）"
    exit 1
  fi
}

# ---------------------------------------------------------------- 启动 / 停止
start_backend() {
  if pid_alive "$BACKEND_PID_FILE"; then
    warn "后端已在运行（pid $(cat "$BACKEND_PID_FILE")），跳过"
    return
  fi
  mkdir -p "$RUN_DIR" "$LOG_DIR"
  log "启动后端 http://$BACKEND_HOST:$BACKEND_PORT ..."
  (
    cd "$BACKEND_DIR"
    nohup .venv/bin/python -m uvicorn app.main:app \
      --host "$BACKEND_HOST" --port "$BACKEND_PORT" \
      >"$LOG_DIR/backend.log" 2>&1 &
    echo $! >"$BACKEND_PID_FILE"
  )
  for _ in $(seq 1 40); do
    if curl -fsS "http://127.0.0.1:$BACKEND_PORT/health" >/dev/null 2>&1; then
      log "  后端就绪"
      return
    fi
    sleep 0.5
  done
  err "后端启动超时，请查看 $LOG_DIR/backend.log"
  exit 1
}

start_frontend() {
  if pid_alive "$FRONTEND_PID_FILE"; then
    warn "前端已在运行（pid $(cat "$FRONTEND_PID_FILE")），跳过"
    return
  fi
  mkdir -p "$RUN_DIR" "$LOG_DIR"
  if [[ "$MODE" == "prod" ]]; then
    log "构建前端（生产模式）..."
    (cd "$FRONTEND_DIR" && npm run build >"$LOG_DIR/frontend-build.log" 2>&1) \
      || { err "前端构建失败，请查看 $LOG_DIR/frontend-build.log"; exit 1; }
    FRONTEND_PORT="${UAMS_FRONTEND_PORT:-4173}"
    log "启动前端静态服务 http://$FRONTEND_HOST:$FRONTEND_PORT ..."
    (
      cd "$FRONTEND_DIR"
      nohup npx vite preview --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" \
        >"$LOG_DIR/frontend.log" 2>&1 &
      echo $! >"$FRONTEND_PID_FILE"
    )
  else
    log "启动前端开发服务器 http://$FRONTEND_HOST:$FRONTEND_PORT ..."
    (
      cd "$FRONTEND_DIR"
      nohup npx vite --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" \
        >"$LOG_DIR/frontend.log" 2>&1 &
      echo $! >"$FRONTEND_PID_FILE"
    )
  fi
  for _ in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:$FRONTEND_PORT/" >/dev/null 2>&1; then
      log "  前端就绪"
      return
    fi
    sleep 0.5
  done
  err "前端启动超时，请查看 $LOG_DIR/frontend.log"
  exit 1
}

stop_all() {
  for name in frontend backend; do
    local f="$RUN_DIR/$name.pid"
    if pid_alive "$f"; then
      local pid; pid="$(cat "$f")"
      log "停止 $name（pid $pid）..."
      kill "$pid" 2>/dev/null || true
      for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.3; done
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$f"
  done
  log "已停止。"
}

health() {
  log "健康检查"
  if curl -fsS "http://127.0.0.1:$BACKEND_PORT/health" 2>/dev/null; then
    echo
  else
    warn "  后端未响应（可能未启动）"
  fi
  local fport="$FRONTEND_PORT"
  [[ "$MODE" == "prod" ]] && fport="${UAMS_FRONTEND_PORT:-4173}"
  curl -fsS -o /dev/null -w "  前端 HTTP %{http_code}\n" "http://127.0.0.1:$fport/" 2>/dev/null \
    || warn "  前端未响应（可能未启动）"
}

print_urls() {
  local ip; ip="$(lan_ip || true)"
  local fport="$FRONTEND_PORT"
  [[ "$MODE" == "prod" ]] && fport="${UAMS_FRONTEND_PORT:-4173}"
  echo
  log "启动完成（模式：$MODE）"
  echo "  本机访问：  http://127.0.0.1:$fport"
  if [[ -n "${ip:-}" ]]; then
    echo "  局域网访问：http://$ip:$fport"
    echo "  接口文档：  http://$ip:$BACKEND_PORT/docs  （仅 DEBUG=true 时开放）"
  fi
  echo "  日志：      $LOG_DIR/backend.log  $LOG_DIR/frontend.log"
  echo "  停止：      ./start.sh stop"
  echo
}

case "${1:-start}" in
  start)
    [[ "${2:-}" == "prod" ]] && MODE="prod"
    check_env
    check_database
    start_backend
    start_frontend
    health
    print_urls
    ;;
  prod)
    MODE="prod"
    check_env
    check_database
    start_backend
    start_frontend
    health
    print_urls
    ;;
  stop)    stop_all ;;
  restart) stop_all; sleep 1; "$0" "${2:-start}" ;;
  status)  health ;;
  *)
    err "未知命令：$1"
    echo "用法：$0 [start|prod|stop|restart|status]"
    exit 1
    ;;
esac
