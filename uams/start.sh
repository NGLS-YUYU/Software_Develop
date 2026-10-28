#!/usr/bin/env bash
# UAMS 统一启动与环境管理器
#
#   ./start.sh                         交互式选择运行环境并前台启动（Ctrl+C 停止）
#   ./start.sh --env production        非交互启动正式环境（uams）
#   ./start.sh --env testing           非交互启动测试环境（uams_test）
#   ./start.sh --env restore           非交互启动恢复环境（uams_restore_20261027）
#
# 兼容原有命令：
#   ./start.sh start [prod]            后台启动正式环境（dev / prod 前端）
#   ./start.sh prod                    后台启动正式环境（构建 + vite preview）
#   ./start.sh stop                    停止本脚本记录的前后端进程
#   ./start.sh restart [prod]          重启正式环境
#   ./start.sh status                  查看运行状态与当前数据库
#
# 安全约定：
# - 不修改 backend/.env，不把数据库密码写入脚本或输出到终端；
# - 运行模式与数据库绑定由 backend/scripts/env_guard.py 校验，
#   通过 SELECT DATABASE() 和 alembic_version 实际核对；
# - 版本不一致、连接失败、库名不符时拒绝启动，绝不静默回退正式库；
# - 不自动执行 Alembic 迁移、不 seed、不清库。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
RUN_DIR="$ROOT/.run"
LOG_DIR="$ROOT/logs"
PY="$BACKEND_DIR/.venv/bin/python"
GUARD="$BACKEND_DIR/scripts/env_guard.py"
VITE_BIN="$FRONTEND_DIR/node_modules/vite/bin/vite.js"

BACKEND_HOST="${UAMS_BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${UAMS_BACKEND_PORT:-8000}"
FRONTEND_HOST="${UAMS_FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${UAMS_FRONTEND_PORT:-5173}"

MODE=""
FRONTEND_MODE="dev"
FOREGROUND=0
BACKEND_PID=""
FRONTEND_PID=""
CHILD_PIDS=()
READER_PIDS=()
FIFO_FILES=()

log()  { printf '\033[1;34m[UAMS]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[UAMS]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[UAMS]\033[0m %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }

mode_db() {
  case "$1" in
    production) echo "uams" ;;
    testing) echo "uams_test" ;;
    restore) echo "uams_restore_20261027" ;;
    *) return 1 ;;
  esac
}

mode_label() {
  case "$1" in
    production) echo "正式环境（Production）" ;;
    testing) echo "测试环境（Testing）" ;;
    restore) echo "恢复验证环境（Restore）" ;;
    *) echo "未知环境" ;;
  esac
}

valid_mode() { case "$1" in production|testing|restore) return 0 ;; *) return 1 ;; esac; }

lan_ip() {
  # 优先真实私网地址：排除 loopback、link-local、VPN 常用的 198.18.0.0/15。
  local ip
  for ip in $(hostname -I 2>/dev/null); do
    [[ "$ip" == *:* ]] && continue
    case "$ip" in
      127.*|169.254.*|198.18.*|198.19.*) continue ;;
    esac
    echo "$ip"; return 0
  done
  ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K[0-9.]+' | head -1
}

pid_alive() {
  local f="$1"
  [[ -f "$f" ]] && kill -0 "$(cat "$f" 2>/dev/null)" 2>/dev/null
}

pid_cmdline() {
  tr '\0' ' ' <"/proc/$1/cmdline" 2>/dev/null || true
}

rotate_log() {
  local f="$1"
  [[ -f "$f" ]] || return 0
  local size
  size=$(stat -c %s "$f" 2>/dev/null || echo 0)
  if (( size > 20 * 1024 * 1024 )); then
    mv -f "$f" "$f.1" 2>/dev/null || true
  fi
}

# 前台日志：FIFO → sed 加前缀（无缓冲）→ tee 同时写终端和文件。
# 后台模式仍直接重定向到文件，不经过 FIFO。
start_log_reader() {
  local name="$1" log="$2"
  local fifo="$RUN_DIR/${name,,}.pipe"
  rm -f "$fifo"
  mkfifo "$fifo"
  (sed -u "s/^/[${name}] /" <"$fifo" | tee -a "$log") &
  READER_PIDS+=("$!")
  FIFO_FILES+=("$fifo")
}

cleanup_readers() {
  local pid _i
  for pid in "${READER_PIDS[@]:-}"; do
    [[ -n "$pid" ]] || continue
    for _i in $(seq 1 25); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.2
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    wait "$pid" 2>/dev/null || true
  done
  local fifo
  for fifo in "${FIFO_FILES[@]:-}"; do
    [[ -n "$fifo" ]] && rm -f "$fifo"
  done
  READER_PIDS=()
  FIFO_FILES=()
}

# ---------------------------------------------------------------- 交互菜单
show_menu() {
  cat <<EOF
============================================
        UAMS V3.1 启动管理器
============================================

请选择运行环境：

  [1] 正式环境（Production）
      数据库：uams

  [2] 测试环境（Testing）
      数据库：uams_test

  [3] 恢复验证环境（Restore）
      数据库：uams_restore_20261027

  [0] 退出

============================================
EOF
}

interactive_menu() {
  show_menu
  printf '请输入选项：'
  local choice
  read -r choice || true
  case "$choice" in
    1) MODE=production ;;
    2) MODE=testing ;;
    3) MODE=restore ;;
    0) log "已退出。"; exit 0 ;;
    *) err "无效选项：${choice:-<空>}，拒绝启动。"; exit 1 ;;
  esac
  FOREGROUND=1
  start_flow
}

# ---------------------------------------------------------------- 环境检查
check_env() {
  log "检查运行环境..."
  [[ -x "$PY" ]] || die "未找到后端虚拟环境：$BACKEND_DIR/.venv"
  log "  后端 venv         OK"
  [[ -f "$GUARD" ]] || die "缺少环境守卫脚本：$GUARD"
  (cd "$BACKEND_DIR" && "$PY" -c "import fastapi, sqlalchemy, pymysql, alembic" >/dev/null 2>&1) \
    || die "后端依赖不完整，请执行：cd backend && .venv/bin/pip install -r requirements.txt"
  log "  后端依赖          OK"
  command -v node >/dev/null 2>&1 || die "未找到 node，请先安装 Node.js"
  [[ -f "$VITE_BIN" ]] || die "未找到前端依赖：$VITE_BIN，请先执行 cd frontend && npm install"
  log "  前端 node_modules OK"
  local env_file="${UAMS_ENV_FILE:-$BACKEND_DIR/.env}"
  [[ -f "$env_file" ]] || die "未找到数据库配置文件：$env_file（不会回退到任何内置默认连接）"
  log "  配置文件          $env_file"
}

run_guard_check() {
  local out rc
  set +e
  out="$(cd "$BACKEND_DIR" && "$PY" scripts/env_guard.py check "$MODE" 2>&1)"
  rc=$?
  set -e
  if [[ $rc -ne 0 ]]; then
    [[ -n "$out" ]] && printf '%s\n' "$out" >&2
    case "$rc" in
      2) err "连接配置缺失或非法，拒绝启动。" ;;
      3) err "数据库版本不匹配，拒绝启动；启动器不会自动执行迁移。";;
      4) err "数据库连接失败，拒绝启动。" ;;
      5) err "运行环境与实际数据库身份不一致，拒绝启动。" ;;
      *) err "环境检查失败（rc=$rc），拒绝启动。" ;;
    esac
    exit "$rc"
  fi
  DB_ACTUAL=""; DB_CURRENT=""; DB_HEAD=""
  local token
  for token in $out; do
    case "$token" in
      db=*) DB_ACTUAL="${token#db=}" ;;
      current=*) DB_CURRENT="${token#current=}" ;;
      head=*) DB_HEAD="${token#head=}" ;;
    esac
  done
  local expected; expected="$(mode_db "$MODE")"
  [[ "$DB_ACTUAL" == "$expected" ]] || die "数据库身份不符：期望 $expected，实际 ${DB_ACTUAL:-未知}"
  [[ "$DB_CURRENT" == "$DB_HEAD" ]] || die "数据库版本不一致：当前 ${DB_CURRENT:-未知}，目标 ${DB_HEAD:-未知}"
  log "  数据库            ${DB_ACTUAL} @ ${DB_CURRENT}（head 一致）"
}

port_busy() {
  ss -ltnH "sport = :$1" 2>/dev/null | head -1
}

port_owner() {
  ss -ltnpH "sport = :$1" 2>/dev/null | sed -n 's/.*users:((\(.*\))).*/\1/p' | head -1
}

check_not_running() {
  if pid_alive "$RUN_DIR/backend.pid" || pid_alive "$RUN_DIR/frontend.pid"; then
    local bp="-" fp="-"
    pid_alive "$RUN_DIR/backend.pid" && bp="$(cat "$RUN_DIR/backend.pid")"
    pid_alive "$RUN_DIR/frontend.pid" && fp="$(cat "$RUN_DIR/frontend.pid")"
    err "检测到 UAMS 已在运行（后端 pid=$bp，前端 pid=$fp）。"
    err "请先执行：./start.sh stop"
    exit 1
  fi
}

check_ports() {
  local fport="$FRONTEND_PORT"
  [[ "$FRONTEND_MODE" == "prod" ]] && fport="${UAMS_FRONTEND_PORT:-4173}"
  local port hit
  for port in "$BACKEND_PORT" "$fport"; do
    hit="$(port_busy "$port")"
    if [[ -n "$hit" ]]; then
      err "端口 $port 已被占用，拒绝启动。"
      local owner; owner="$(port_owner "$port")"
      [[ -n "$owner" ]] && err "  占用进程：$owner"
      err "  本脚本不会杀死来源不明的进程。"
      exit 1
    fi
  done
  log "  端口              ${BACKEND_PORT} / ${fport} 可用"
}

# ---------------------------------------------------------------- 进程管理
stop_pid() {
  local pid="$1" pattern="$2" label="$3"
  if ! kill -0 "$pid" 2>/dev/null; then
    return 0
  fi
  local cmd; cmd="$(pid_cmdline "$pid")"
  if [[ "$cmd" != *"$pattern"* ]]; then
    warn "$label pid=$pid 不属于 UAMS（$cmd），跳过，不杀死来源不明进程。"
    return 1
  fi
  # 兼容旧版 npx 启动：先记录子进程，父进程退出后仍需清理。
  local kids; kids="$(pgrep -P "$pid" 2>/dev/null || true)"
  log "停止 $label（pid $pid）..."
  kill "$pid" 2>/dev/null || true
  local _i
  for _i in $(seq 1 40); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.2
  done
  if kill -0 "$pid" 2>/dev/null; then
    warn "$label 未在 8 秒内退出，发送 SIGKILL（仅限本脚本启动的进程）。"
    kill -9 "$pid" 2>/dev/null || true
  fi
  local kid
  for kid in $kids; do
    if kill -0 "$kid" 2>/dev/null; then
      local kcmd; kcmd="$(pid_cmdline "$kid")"
      if [[ "$kcmd" == *"$pattern"* || "$kcmd" == *"node"* ]]; then
        kill "$kid" 2>/dev/null || true
        sleep 0.2
        kill -9 "$kid" 2>/dev/null || true
      fi
    fi
  done
  return 0
}

stop_project_orphans() {
  # 只匹配“工作目录属于本项目 + 命令含 uvicorn/vite”的进程；
  # 用于清理旧版 npx/npm 启动方式留下的子进程，不按端口或模糊进程名杀进程。
  local d pid cwd cmd
  for d in /proc/[0-9]*; do
    pid="${d##*/}"
    [[ "$pid" == "$$" ]] && continue
    cwd="$(readlink "$d/cwd" 2>/dev/null || true)"
    [[ "$cwd" == "$FRONTEND_DIR" || "$cwd" == "$BACKEND_DIR" ]] || continue
    cmd="$(pid_cmdline "$pid")"
    if [[ "$cwd" == "$FRONTEND_DIR" && "$cmd" == *"vite"* ]]; then
      stop_pid "$pid" "vite" "前端残留" || true
    elif [[ "$cwd" == "$BACKEND_DIR" && "$cmd" == *"uvicorn app.main:app"* ]]; then
      stop_pid "$pid" "uvicorn app.main:app" "后端残留" || true
    fi
  done
}

stop_all() {
  local bp="" fp=""
  [[ -f "$RUN_DIR/backend.pid" ]] && bp="$(cat "$RUN_DIR/backend.pid" 2>/dev/null || true)"
  [[ -f "$RUN_DIR/frontend.pid" ]] && fp="$(cat "$RUN_DIR/frontend.pid" 2>/dev/null || true)"
  [[ -n "$bp" ]] && stop_pid "$bp" "uvicorn app.main:app" "后端" || true
  [[ -n "$fp" ]] && stop_pid "$fp" "vite" "前端" || true
  stop_project_orphans
  rm -f "$RUN_DIR/backend.pid" "$RUN_DIR/frontend.pid" "$RUN_DIR/environment"
  log "已停止本脚本记录的进程。"
}

cleanup_children() {
  trap - INT TERM EXIT
  local pid
  for pid in "${CHILD_PIDS[@]:-}"; do
    [[ -n "$pid" ]] || continue
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  local _i
  for _i in $(seq 1 40); do
    local any=0
    for pid in "${CHILD_PIDS[@]:-}"; do
      [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null && any=1
    done
    (( any == 0 )) && break
    sleep 0.2
  done
  for pid in "${CHILD_PIDS[@]:-}"; do
    [[ -n "$pid" ]] || continue
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    wait "$pid" 2>/dev/null || true
  done
  cleanup_readers
  local cur
  for pair in "backend:$BACKEND_PID" "frontend:$FRONTEND_PID"; do
    local name="${pair%%:*}" p="${pair#*:}"
    [[ -n "$p" ]] || continue
    cur="$(cat "$RUN_DIR/$name.pid" 2>/dev/null || true)"
    [[ "$cur" == "$p" ]] && rm -f "$RUN_DIR/$name.pid"
  done
  rm -f "$RUN_DIR/environment"
}

on_signal() {
  local code="$1"
  warn "收到退出信号，正在停止本次启动的服务..."
  cleanup_children
  exit "$code"
}

# ---------------------------------------------------------------- 启动
wait_http() {
  local url="$1" tries="$2" expect="${3:-}"
  local _i
  for _i in $(seq 1 "$tries"); do
    if curl -fsS "$url" 2>/dev/null | grep -q "${expect:-.}"; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

start_backend() {
  mkdir -p "$RUN_DIR" "$LOG_DIR"
  rotate_log "$LOG_DIR/backend.log"
  log "启动后端（$MODE → $(mode_db "$MODE")）..."
  if [[ "$FOREGROUND" -eq 1 ]]; then
    start_log_reader Backend "$LOG_DIR/backend.log"
    (
      cd "$BACKEND_DIR"
      exec "$PY" scripts/env_guard.py exec "$MODE" -- \
        .venv/bin/python -m uvicorn app.main:app \
        --host "$BACKEND_HOST" --port "$BACKEND_PORT"
    ) >"$RUN_DIR/backend.pipe" 2>&1 &
    BACKEND_PID=$!
    CHILD_PIDS+=("$BACKEND_PID")
  else
    (
      cd "$BACKEND_DIR"
      nohup "$PY" scripts/env_guard.py exec "$MODE" -- \
        .venv/bin/python -m uvicorn app.main:app \
        --host "$BACKEND_HOST" --port "$BACKEND_PORT" \
        >"$LOG_DIR/backend.log" 2>&1 &
      echo $! >"$RUN_DIR/backend.pid"
    )
    BACKEND_PID="$(cat "$RUN_DIR/backend.pid")"
  fi
  echo "$BACKEND_PID" >"$RUN_DIR/backend.pid"

  if wait_http "http://127.0.0.1:$BACKEND_PORT/health" 40 '"database":"up"'; then
    log "  后端就绪（pid $BACKEND_PID）"
  else
    err "后端启动失败或数据库不健康，日志：$LOG_DIR/backend.log"
    tail -20 "$LOG_DIR/backend.log" >&2 || true
    [[ "$FOREGROUND" -eq 1 ]] && cleanup_children
    return 1
  fi
}

start_frontend() {
  local fport="$FRONTEND_PORT"
  local cmd=(node "$VITE_BIN")
  if [[ "$FRONTEND_MODE" == "prod" ]]; then
    fport="${UAMS_FRONTEND_PORT:-4173}"
    log "构建前端（生产模式）..."
    (cd "$FRONTEND_DIR" && npm run build >"$LOG_DIR/frontend-build.log" 2>&1) \
      || { err "前端构建失败，日志：$LOG_DIR/frontend-build.log"; return 1; }
    cmd+=(preview)
  fi
  cmd+=(--host "$FRONTEND_HOST" --port "$fport")
  rotate_log "$LOG_DIR/frontend.log"
  log "启动前端（$FRONTEND_MODE，端口 $fport）..."
  if [[ "$FOREGROUND" -eq 1 ]]; then
    start_log_reader Frontend "$LOG_DIR/frontend.log"
    (
      cd "$FRONTEND_DIR"
      export UAMS_BACKEND_URL="${UAMS_BACKEND_URL:-http://127.0.0.1:$BACKEND_PORT}"
      exec "${cmd[@]}"
    ) >"$RUN_DIR/frontend.pipe" 2>&1 &
    FRONTEND_PID=$!
    CHILD_PIDS+=("$FRONTEND_PID")
  else
    (
      cd "$FRONTEND_DIR"
      export UAMS_BACKEND_URL="${UAMS_BACKEND_URL:-http://127.0.0.1:$BACKEND_PORT}"
      nohup "${cmd[@]}" >"$LOG_DIR/frontend.log" 2>&1 &
      echo $! >"$RUN_DIR/frontend.pid"
    )
    FRONTEND_PID="$(cat "$RUN_DIR/frontend.pid")"
  fi
  echo "$FRONTEND_PID" >"$RUN_DIR/frontend.pid"

  if wait_http "http://127.0.0.1:$fport/" 60 ''; then
    log "  前端就绪（pid $FRONTEND_PID）"
  else
    err "前端启动失败，日志：$LOG_DIR/frontend.log"
    tail -20 "$LOG_DIR/frontend.log" >&2 || true
    [[ "$FOREGROUND" -eq 1 ]] && cleanup_children
    return 1
  fi
}

print_success() {
  local ip fport
  ip="$(lan_ip || true)"
  fport="$FRONTEND_PORT"
  [[ "$FRONTEND_MODE" == "prod" ]] && fport="${UAMS_FRONTEND_PORT:-4173}"
  echo
  echo "============================================"
  if [[ "$FOREGROUND" -eq 1 ]]; then
    echo "UAMS 启动成功"
  else
    echo "UAMS 已在后台启动"
  fi
  echo
  echo "运行环境：$(mode_label "$MODE")"
  echo "数据库：${DB_ACTUAL}"
  echo "数据库版本：已与 Alembic head 一致（${DB_HEAD}）"
  echo
  echo "本机访问："
  echo "http://127.0.0.1:$fport"
  if [[ -n "${ip:-}" ]]; then
    echo
    echo "局域网访问："
    echo "http://$ip:$fport"
  fi
  echo
  echo "后端服务："
  echo "http://127.0.0.1:$BACKEND_PORT"
  echo
  if [[ "$FOREGROUND" -eq 1 ]]; then
    echo "按 Ctrl+C 停止服务"
  else
    echo "停止服务：./start.sh stop"
  fi
  echo "============================================"
}

start_flow() {
  valid_mode "$MODE" || die "未知运行环境：$MODE"
  FOREGROUND="${FOREGROUND:-0}"
  check_env
  check_not_running
  run_guard_check
  check_ports
  mkdir -p "$RUN_DIR" "$LOG_DIR"
  echo "$MODE" >"$RUN_DIR/environment"

  if [[ "$FOREGROUND" -eq 1 ]]; then
    # 在启动子进程前安装信号处理，避免启动过程中 Ctrl+C 留下孤儿进程。
    trap 'on_signal 130' INT
    trap 'on_signal 143' TERM
  fi

  if ! start_backend; then
    if [[ "$FOREGROUND" -eq 1 ]]; then
      cleanup_children
    else
      stop_all
    fi
    exit 1
  fi
  if ! start_frontend; then
    if [[ "$FOREGROUND" -eq 1 ]]; then
      cleanup_children
    else
      stop_all
    fi
    exit 1
  fi

  print_success

  if [[ "$FOREGROUND" -eq 1 ]]; then
    # 任一子进程退出时，停止另一个，避免残留。
    wait -n "$BACKEND_PID" "$FRONTEND_PID" || true
    warn "检测到服务退出，正在停止其余服务..."
    cleanup_children
    exit 1
  fi
}

# ---------------------------------------------------------------- 状态
health() {
  log "健康检查"
  if curl -fsS "http://127.0.0.1:$BACKEND_PORT/health" 2>/dev/null; then
    echo
  else
    warn "  后端未响应（可能未启动）"
  fi
  local fport="$FRONTEND_PORT"
  [[ "$FRONTEND_MODE" == "prod" ]] && fport="${UAMS_FRONTEND_PORT:-4173}"
  curl -fsS -o /dev/null -w "  前端 HTTP %{http_code}\n" "http://127.0.0.1:$fport/" 2>/dev/null \
    || warn "  前端未响应（可能未启动）"
}

show_status() {
  local mode=""
  [[ -f "$RUN_DIR/environment" ]] && mode="$(cat "$RUN_DIR/environment" 2>/dev/null || true)"
  if valid_mode "$mode"; then
    MODE="$mode"
    log "记录运行环境：$(mode_label "$MODE")（$(mode_db "$MODE")）"
    set +e
    local out; out="$(cd "$BACKEND_DIR" && "$PY" scripts/env_guard.py check "$MODE" 2>&1)"
    local rc=$?
    set -e
    printf '%s\n' "$out"
    [[ $rc -eq 0 ]] || warn "  环境守卫检查未通过（rc=$rc）"
  else
    warn "未找到本次启动记录的环境（.run/environment）。"
  fi
  health
}

# ---------------------------------------------------------------- 帮助
usage() {
  cat <<EOF
用法：
  ./start.sh                         交互式选择运行环境（前台，Ctrl+C 停止）
  ./start.sh --env production        正式环境 uams
  ./start.sh --env testing           测试环境 uams_test
  ./start.sh --env restore           恢复环境 uams_restore_20261027
  ./start.sh start [prod]            后台启动正式环境（兼容旧用法）
  ./start.sh prod                    后台启动正式环境（生产前端）
  ./start.sh stop                    停止本脚本启动的服务
  ./start.sh restart [prod]          重启正式环境
  ./start.sh status                  查看状态、实际数据库与版本
EOF
}

# ---------------------------------------------------------------- 入口
case "${1:-}" in
  "")
    interactive_menu
    ;;
  --env)
    MODE="${2:-}"
    valid_mode "$MODE" || { err "无效的 --env 参数：${MODE:-<空>}"; usage; exit 1; }
    FOREGROUND=1
    start_flow
    ;;
  start)
    MODE=production
    [[ "${2:-}" == "prod" ]] && FRONTEND_MODE="prod"
    FOREGROUND=0
    start_flow
    ;;
  prod)
    MODE=production
    FRONTEND_MODE="prod"
    FOREGROUND=0
    start_flow
    ;;
  stop)
    stop_all
    ;;
  restart)
    stop_all
    sleep 1
    MODE=production
    [[ "${2:-}" == "prod" ]] && FRONTEND_MODE="prod"
    FOREGROUND=0
    start_flow
    ;;
  status)
    show_status
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    err "未知命令：$1"
    usage
    exit 1
    ;;
esac
