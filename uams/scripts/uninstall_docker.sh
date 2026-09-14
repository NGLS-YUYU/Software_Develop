#!/usr/bin/env bash
#
# UAMS —— 卸载 Docker 及其残留（项目已改用本机原生 MySQL，不再需要 Docker）
# ===========================================================================
# 用法：
#     sudo bash uams/scripts/uninstall_docker.sh
#
# 预计回收磁盘约 7.8 GB
# ===========================================================================

set -euo pipefail

BOLD=$'\033[1m'; RED=$'\033[31m'; GREEN=$'\033[32m'; YEL=$'\033[33m'; NC=$'\033[0m'
step() { echo; echo "${BOLD}==> $*${NC}"; }
ok()   { echo "    ${GREEN}✔${NC} $*"; }
warn() { echo "    ${YEL}!${NC} $*"; }
die()  { echo "${RED}✘ $*${NC}" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "请用 root 运行：sudo bash uams/scripts/uninstall_docker.sh"
REAL_USER="${SUDO_USER:-}"
[ -n "$REAL_USER" ] || die "请用普通用户执行 sudo bash ...，而不是直接 root 登录。"
REAL_HOME="$(getent passwd "$REAL_USER" | cut -d: -f6)"

BEFORE="$(df -h / | awk 'NR==2{print $4}')"

# --- 1. 停止服务 ----------------------------------------------------------
step "1/5  停止 Docker Desktop"
sudo -u "$REAL_USER" XDG_RUNTIME_DIR="/run/user/$(id -u "$REAL_USER")" \
    systemctl --user disable --now docker-desktop 2>/dev/null || true
pkill -u "$REAL_USER" -f 'docker-desktop|com.docker' 2>/dev/null || true
sleep 2
ok "已停止"

# --- 2. 卸载软件包 --------------------------------------------------------
step "2/5  卸载 Docker 软件包"
apt-get purge -y docker-desktop docker-ce-cli docker-buildx-plugin docker-compose-plugin 2>&1 | tail -3
ok "Docker 包已卸载"

# --- 3. 卸载 Docker Desktop 带来的依赖 ------------------------------------
# qemu / ovmf / seabios 等是 Docker Desktop 的依赖，本项目不再需要。
# autoremove 只会删除「因依赖而安装、现在无人依赖」的包，手动装的不受影响。
step "3/5  清理孤立依赖（qemu / ovmf / seabios 等）"
apt-get autoremove --purge -y 2>&1 | tail -5
ok "孤立依赖已清理"

# --- 4. 删除残留文件 ------------------------------------------------------
step "4/5  删除残留文件与配置"
for p in \
    /opt/docker-desktop \
    /etc/docker \
    /var/lib/docker \
    /var/lib/containerd \
    /etc/apt/sources.list.d/docker.list \
    /etc/apt/keyrings/docker.asc \
    "$REAL_HOME/.docker" \
    "$REAL_HOME/.local/share/docker-desktop" \
    "$REAL_HOME/.config/docker-desktop" \
    "$REAL_HOME/.config/systemd/user/docker-desktop.service" \
    "$REAL_HOME/Downloads/docker-desktop-amd64.deb" \
; do
    if [ -e "$p" ]; then
        rm -rf "$p" && echo "    删除 $p"
    fi
done

# kubernetes.docker.internal 是 Docker Desktop 装时写进 /etc/hosts 的
if grep -q 'kubernetes.docker.internal' /etc/hosts 2>/dev/null; then
    sed -i '/kubernetes.docker.internal/d' /etc/hosts
    echo "    清理 /etc/hosts 中的 kubernetes.docker.internal"
fi

# 把用户移出 kvm 组（当初是为 Docker Desktop 加的）
if id -nG "$REAL_USER" | tr ' ' '\n' | grep -qx kvm; then
    gpasswd -d "$REAL_USER" kvm >/dev/null 2>&1 && echo "    已将 $REAL_USER 移出 kvm 组"
fi

apt-get update 2>&1 | tail -2
ok "残留已清理"

# --- 5. 校验 --------------------------------------------------------------
step "5/5  校验"
if command -v docker >/dev/null 2>&1; then
    warn "docker 命令仍存在: $(command -v docker)"
else
    ok "docker 命令已移除"
fi
dpkg -l 2>/dev/null | grep -qE '^ii.*docker' && warn "仍有 docker 相关包残留" || ok "无 docker 软件包残留"

AFTER="$(df -h / | awk 'NR==2{print $4}')"
echo
echo "    磁盘可用: $BEFORE  ->  $AFTER"

cat <<EOF

${BOLD}${GREEN}Docker 已完全卸载。${NC}

项目数据库现为本机原生 MySQL 8.4，不受影响：
    systemctl status mysql

EOF
