#!/usr/bin/env bash
#
# UAMS 开发环境 —— MySQL 原生安装与初始化
# ===========================================================================
# 项目   : 高校教务教学管理系统 (UAMS)
# 依据   : uams/CLAUDE.md §2 核心技术栈 / §3 数据库规则
# 目标   : Ubuntu 26.04.1 LTS (resolute) / x86_64
# 生成时间: 2026-09-15
#
# 用法（在你自己的终端里执行，会提示输入密码）：
#
#     sudo bash uams/scripts/setup_mysql.sh
#
# 本脚本【不做】的事：
#   - 不创建任何业务表（那是 Alembic migration 的职责）
#   - 不写任何业务代码
#   - 不安装 Python 依赖（venv 里由 pip 装，不需要 root）
#
# 每一步都会打印将要执行的命令，可逐行审阅。
# ===========================================================================

set -euo pipefail

# --- 配色与日志 -----------------------------------------------------------
BOLD=$'\033[1m'; RED=$'\033[31m'; GREEN=$'\033[32m'; YEL=$'\033[33m'; NC=$'\033[0m'
step() { echo; echo "${BOLD}==> $*${NC}"; }
info() { echo "    $*"; }
ok()   { echo "    ${GREEN}✔${NC} $*"; }
warn() { echo "    ${YEL}!${NC} $*"; }
die()  { echo "${RED}✘ $*${NC}" >&2; exit 1; }

# --- 0. 前置检查 ----------------------------------------------------------
step "0/6  前置检查"

[ "$(id -u)" -eq 0 ] || die "请用 root 运行：sudo bash uams/scripts/setup_mysql.sh"

REAL_USER="${SUDO_USER:-root}"
[ "$REAL_USER" != "root" ] || die "检测不到 SUDO_USER。请用普通用户执行 sudo bash ...，而不是直接 root 登录。"
REAL_HOME="$(getent passwd "$REAL_USER" | cut -d: -f6)"
ok "目标用户: $REAL_USER"

ENV_FILE="$REAL_HOME/uams-infra/.env"
[ -f "$ENV_FILE" ] || die "找不到凭据文件: $ENV_FILE"

# 从 .env 读取密码；这样密码不出现在脚本里，也不出现在命令行历史中
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a
[ -n "${MYSQL_ROOT_PASSWORD:-}" ] || die "$ENV_FILE 中缺少 MYSQL_ROOT_PASSWORD"
[ -n "${UAMS_DB_PASSWORD:-}" ]    || die "$ENV_FILE 中缺少 UAMS_DB_PASSWORD"
ok "已从 $ENV_FILE 读取凭据"

if ss -lntp 2>/dev/null | grep -q ':3306 '; then
    warn "3306 端口已被占用，可能已有 MySQL/MariaDB 在运行"
    read -rp "    仍要继续吗? [y/N] " a; [ "$a" = "y" ] || die "已中止"
else
    ok "3306 端口空闲"
fi

# --- 1. 安装 MySQL Server -------------------------------------------------
step "1/6  安装 MySQL Server"
if dpkg-query -W -f='${Status}' mysql-server 2>/dev/null | grep -q "install ok installed"; then
    ok "mysql-server 已安装（$(dpkg-query -W -f='${Version}' mysql-server)）"
else
    info "\$ apt-get update"
    apt-get update
    info "\$ apt-get install -y mysql-server"
    DEBIAN_FRONTEND=noninteractive apt-get install -y mysql-server
    ok "已安装 $(dpkg-query -W -f='${Version}' mysql-server)"
fi

# --- 2. 启动服务 ----------------------------------------------------------
step "2/6  启动 MySQL 服务"
info "\$ systemctl enable --now mysql"
systemctl enable --now mysql
for i in $(seq 1 30); do
    mysqladmin ping >/dev/null 2>&1 && break
    sleep 1
done
mysqladmin ping >/dev/null 2>&1 || die "MySQL 启动失败，请查看: journalctl -u mysql -n 50"
ok "MySQL 正在运行（$(systemctl is-active mysql)）"

# --- 3. 服务端配置 --------------------------------------------------------
# utf8mb4 是 MySQL 上存中文的唯一正确选择（旧的 utf8 实为 3 字节，存不下部分汉字和 emoji）。
# 严格模式让非法数据直接报错而不是静默截断 —— 对成绩、学分这类数值字段很关键。
step "3/6  写入 UAMS 服务端配置"
CONF=/etc/mysql/mysql.conf.d/99-uams.cnf
info "写入 $CONF"
cat > "$CONF" <<'CNF'
# UAMS 高校教务教学管理系统 —— 服务端配置
# 由 uams/scripts/setup_mysql.sh 生成

[mysqld]
character-set-server = utf8mb4
collation-server     = utf8mb4_0900_ai_ci

# 教务系统涉及成绩、选课统计，统一时区避免跨时区歧义
default-time-zone    = '+08:00'

# 严格模式：非法数据报错而非静默截断
sql-mode = STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO

# 只监听本地回环，不对外暴露
bind-address = 127.0.0.1

[client]
default-character-set = utf8mb4
CNF
chmod 644 "$CONF"
info "\$ systemctl restart mysql"
systemctl restart mysql
for i in $(seq 1 30); do mysqladmin ping >/dev/null 2>&1 && break; sleep 1; done
ok "配置已生效"

# --- 4. 创建数据库与应用用户 ----------------------------------------------
# 应用不使用 root 连接，符合最小权限原则（CLAUDE.md §23）。
# root@localhost 在 Ubuntu 上默认是 auth_socket 认证，sudo mysql 可直接进入，
# 这里保持该机制不变，只额外设置密码以便需要时使用。
step "4/6  创建 uams 数据库与 uams_app 用户"

# Ubuntu 的 mysql-server 默认不安装 validate_password 组件，简单密码可用。
# 但如果它被启用了，CREATE USER 会直接报错，这里先检测并给出可操作的提示。
VP="$(mysql --protocol=socket -N -B -e \
     "SELECT COUNT(*) FROM mysql.component WHERE component_urn LIKE '%validate_password%';" \
     2>/dev/null || echo 0)"
if [ "${VP:-0}" != "0" ]; then
    warn "检测到 validate_password 组件已启用 —— 简单密码会被拒绝。"
    warn "如需使用简单密码，可在 mysql 中执行："
    warn "    UNINSTALL COMPONENT 'file://component_validate_password';"
    warn "或改用满足策略的强密码后重跑本脚本。"
    read -rp "    仍要继续尝试吗? [y/N] " a; [ "$a" = "y" ] || die "已中止"
else
    ok "validate_password 未启用，简单密码可用"
fi

mysql --protocol=socket <<SQL
CREATE DATABASE IF NOT EXISTS uams
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

CREATE USER IF NOT EXISTS 'uams_app'@'localhost'
    IDENTIFIED BY '${UAMS_DB_PASSWORD}';
CREATE USER IF NOT EXISTS 'uams_app'@'127.0.0.1'
    IDENTIFIED BY '${UAMS_DB_PASSWORD}';

ALTER USER 'uams_app'@'localhost' IDENTIFIED BY '${UAMS_DB_PASSWORD}';
ALTER USER 'uams_app'@'127.0.0.1' IDENTIFIED BY '${UAMS_DB_PASSWORD}';

-- 应用用户只在 uams 库上有权限，不授予全局权限
GRANT ALL PRIVILEGES ON uams.* TO 'uams_app'@'localhost';
GRANT ALL PRIVILEGES ON uams.* TO 'uams_app'@'127.0.0.1';

-- Alembic 迁移与 pytest 需要能建临时库
GRANT ALL PRIVILEGES ON \`uams_test\`.* TO 'uams_app'@'localhost';
GRANT ALL PRIVILEGES ON \`uams_test\`.* TO 'uams_app'@'127.0.0.1';

FLUSH PRIVILEGES;
SQL
ok "数据库 uams 与用户 uams_app 已就绪"

# --- 5. 校验 --------------------------------------------------------------
step "5/6  校验"
info "以 uams_app 身份连接测试..."
mysql -h 127.0.0.1 -P 3306 -u uams_app -p"${UAMS_DB_PASSWORD}" -D uams -e "
SELECT VERSION() AS mysql_version;
SELECT DATABASE() AS current_db;
SELECT @@character_set_database AS charset, @@collation_database AS collation;
SELECT @@sql_mode AS sql_mode\G
" 2>/dev/null || die "uams_app 连接失败"
ok "uams_app 可以正常连接"

# --- 6. 结果 --------------------------------------------------------------
step "6/6  完成"
printf '    %-18s %s\n' "MySQL 版本:" "$(mysql --version | awk '{print $3}')"
printf '    %-18s %s\n' "服务状态:"   "$(systemctl is-active mysql)"
printf '    %-18s %s\n' "开机自启:"   "$(systemctl is-enabled mysql)"
printf '    %-18s %s\n' "监听:"       "$(ss -lntp 2>/dev/null | grep ':3306 ' | awk '{print $4}' | head -1)"
printf '    %-18s %s\n' "数据库:"     "uams (utf8mb4)"
printf '    %-18s %s\n' "应用用户:"   "uams_app"

cat <<EOF

${BOLD}${GREEN}MySQL 已就绪。${NC}

连接信息（已写入 $ENV_FILE）：
    host 127.0.0.1   port 3306   db uams   user uams_app

回到 Claude Code，它会接着做：
  - 在 backend/.venv 安装 SQLAlchemy / PyMySQL / Alembic 等依赖
  - 用 SQLAlchemy 做连接测试
  - 继续整理项目文档

EOF
