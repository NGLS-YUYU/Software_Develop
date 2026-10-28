# 部署说明

> 记录当前实际部署方式（TASK-DOC-001，2026-09-17；FIX-007 更新，2026-10-08：统一启动脚本与局域网访问；
> **V3.0 更新，2026-10-09：补充 Windows 部署，并明确正式部署前的安全要求**）。
>
> **V3.2 起正式部署采用 Nginx + systemd + MySQL。**
> 本文第 0 章为正式部署；第 1 章之后保留 Vite/uvicorn 的本地开发与测试方式。
>
> **Windows 与 Ubuntu 共用同一套业务配置**：数据库结构、环境变量名、API、前端构建、
> 业务逻辑完全一致，**只有操作系统命令不同**。因此下面先讲共用部分，再分系统讲命令。

---

## 0. 正式部署（V3.2，Nginx + systemd）

### 0.1 目标架构

```text
浏览器 → Nginx :80
           ├─ /        → /var/www/uams/current（Vue 构建产物）
           └─ /api/    → 127.0.0.1:8000（FastAPI，systemd）
                              └→ MySQL 127.0.0.1:3306（uams）
```

- 正式环境不运行 Vite 5173；
- FastAPI 只监听回环，由 Nginx 对外；
- 教学资料走鉴权 API，不作为 Nginx 静态文件；
- Nginx 不暴露源码、`.env`、Git、备份。

### 0.2 配置与脚本

| 文件 | 用途 |
|---|---|
| `deploy/nginx/uams.conf` | SPA 回退、`/api` 代理、缓存、敏感文件拒绝 |
| `deploy/systemd/uams-backend.service` | FastAPI 长期运行，启动前校验 `uams` 与 head |
| `deploy/deploy-frontend.sh` | 构建并原子发布到 `/var/www/uams/current` |
| `deploy/README.md` | 安装、验收、日常管理、回滚 |

### 0.3 安装顺序

```bash
# 1. 备份现有 Nginx/systemd 配置（若存在）
# 2. 安装 Nginx + rsync（需要 sudo）
sudo apt update && sudo apt install -y nginx rsync

# 3. 只读预检（Nginx/80/default_server/静态目录/8000）
./deploy/preflight-nginx.sh || true
./deploy/preflight-system.sh || true

# 4. 安装站点配置，并把默认站点移出 sites-enabled（仅在目录内改名仍会被 include）
STAMP=$(date +%Y%m%d_%H%M%S)
sudo cp deploy/nginx/uams.conf /etc/nginx/sites-available/uams
sudo ln -sfn /etc/nginx/sites-available/uams /etc/nginx/sites-enabled/uams
sudo mv /etc/nginx/sites-enabled/default "/etc/nginx/default.disabled.$STAMP"
sudo nginx -t

# 5. 构建并原子发布前端（脚本会再次 nginx -t/reload，并校验首页是 UAMS）
bash deploy/deploy-frontend.sh

# 6. 预验证：Nginx 静态页/子路由 + 旧 uvicorn 的 /api（此时旧后端仍在 8000）
IP=$(hostname -I | awk '{print $1}')
curl -s "http://$IP/" | grep -q '<div id="app"></div>'
curl -s "http://$IP/admin/students" | grep -q '<div id="app"></div>'
curl -s -o /dev/null -w '%{http_code}\n' "http://$IP/api/v1/terms/active"

# 7. 停止旧开发模式后端，安装并启动 systemd 后端
./start.sh stop
sudo cp deploy/systemd/uams-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now uams-backend.service
sudo systemctl restart nginx

# 8. 校验
sudo systemctl status uams-backend nginx --no-pager
curl -s http://127.0.0.1:8000/health
curl -s -o /dev/null -w '%{http_code}\n' "http://$IP/"
curl -s -o /dev/null -w '%{http_code}\n' "http://$IP/api/v1/terms/active"
./start.sh --env production
./start.sh status
```

> 当前执行环境没有可用的免密 sudo；Nginx 已安装并运行，但 80 由 Ubuntu 默认站点占用，UAMS 站点与 systemd 服务尚未安装，上述系统级步骤尚未执行。
> 在此之前正式环境仍由现有 Vite + uvicorn 临时方式提供。

### 0.4 日常管理

```bash
sudo systemctl status uams-backend nginx
sudo systemctl restart uams-backend
sudo systemctl reload nginx
journalctl -u uams-backend -f
sudo tail -f /var/log/nginx/access.log /var/log/nginx/error.log
./start.sh status
```

### 0.5 回滚

1. `sudo systemctl stop uams-backend && sudo systemctl disable uams-backend`
2. 移除 `/etc/nginx/sites-enabled/uams`，恢复备份的 Nginx 配置，`sudo nginx -t && sudo systemctl reload nginx`
3. 将 `/var/www/uams/current` 指回上一个 release
4. 必要时 `./start.sh start` 恢复原开发/演示方式

详见 [../deploy/README.md](../deploy/README.md) §5。

---

## 1. 本地开发拓扑（Vite）

```
客户端（本机或局域网内其他电脑 / 手机）
        │  http://<服务器IP>:5173   （生产预览模式为 :4173）
        ▼
Vite（前端：开发服务器或 `vite preview` 静态服务，监听 0.0.0.0）
        │  /api/* 同源代理（服务端 → 服务端）
        ▼
FastAPI（uvicorn，监听 0.0.0.0:8000）
        │  PyMySQL
        ▼
MySQL 8.4（127.0.0.1:3306，仅回环，不对外暴露）
```

**关键点**：浏览器只请求 `http://<服务器IP>:5173/api/v1/...`，由 Vite 在**服务器端**转发到
`127.0.0.1:8000`。因此浏览器里永远不会出现 `127.0.0.1`（那会指向访问者自己的电脑），
也**不产生跨域请求**，无需为局域网单独配置 CORS。

### 1.1 端口

| 组件 | 监听 | 说明 |
|---|---|---|
| 前端（dev） | `0.0.0.0:5173` | Vite 开发服务器 |
| 前端（prod） | `0.0.0.0:4173` | `vite preview` 提供 `dist/` |
| 后端 | `0.0.0.0:8000` | uvicorn；`/health` 健康检查，`/docs` 仅 `DEBUG=true` 时开放 |
| MySQL | `127.0.0.1:3306` | **仅回环**，不对局域网暴露 |

---

## 2. 环境要求（两系统共用）

| 项 | 要求 |
|---|---|
| Python | 3.11+（本项目在 3.14 上开发验证） |
| Node.js | 20+（含 npm） |
| MySQL | **8.4 LTS**，InnoDB / utf8mb4（不支持 SQLite / PostgreSQL / MariaDB） |
| Git | 用于克隆项目 |
| 浏览器 | Chrome / Edge 近两年版本 |

---

## 3. 环境变量（两系统共用）

配置一律走 `backend/.env`（由 `pydantic-settings` 读取）。

```bash
cp backend/.env.example backend/.env      # Ubuntu
copy backend\.env.example backend\.env    # Windows（cmd）
Copy-Item backend\.env.example backend\.env   # Windows（PowerShell）
```

| 变量 | 说明 | 正式部署要求 |
|---|---|---|
| `APP_ENV` | 运行环境 | `production` |
| `DEBUG` | 调试开关（控制 `/docs`） | **必须 `false`** |
| `DATABASE_URL` | MySQL 连接串 | **必须改为真实口令** |
| `DB_ECHO` | SQL 回显 | `false` |
| `JWT_SECRET` | 令牌签名密钥 | **必须替换为随机值**（见下） |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 令牌有效期 | 按安全策略调整 |
| `CORS_ORIGINS` | 允许跨域的前端来源 | 同源代理模式下无需登记局域网地址 |

生成随机密钥：

```bash
# Ubuntu
python3 -c "import secrets;print(secrets.token_urlsafe(48))"
# Windows（PowerShell）
python -c "import secrets;print(secrets.token_urlsafe(48))"
```

> ⚠️ **安全声明（必读）**
> `backend/app/core/config.py` 内置了演示用的数据库口令与占位 `JWT_SECRET`，仅用于本机演示。
> **正式部署（含局域网）之前，必须创建 `backend/.env` 并替换数据库口令与 `JWT_SECRET`。**
> `./start.sh` 在检测不到 `.env` 时会明确告警。
> 演示账号只用于演示/答辩环境，**不得**作为生产环境默认账号密码。

---

## 4. Ubuntu 本地开发部署（Vite）

### 4.1 环境要求与安装

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
# Node.js 20+
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs
```

### 4.2 安装 MySQL 8.4 并建库

```bash
sudo apt install -y mysql-server
sudo systemctl start mysql && sudo systemctl enable mysql

sudo mysql -e "CREATE DATABASE uams CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"
sudo mysql -e "CREATE USER 'uams_app'@'127.0.0.1' IDENTIFIED BY '<你的强口令>';"
sudo mysql -e "GRANT ALL PRIVILEGES ON uams.* TO 'uams_app'@'127.0.0.1'; FLUSH PRIVILEGES;"
```

> 仓库内也提供了 `uams/scripts/setup_mysql.sh` 可参考；**口令不要写进任何提交到 Git 的文件**。

### 4.3 克隆项目

```bash
git clone <仓库地址> && cd <项目目录>/uams
```

### 4.4 配置 .env

```bash
cp backend/.env.example backend/.env
vi backend/.env     # 修改 DATABASE_URL 口令与 JWT_SECRET
```

### 4.5 安装依赖

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && cd ..
cd frontend && npm install && cd ..
```

### 4.6 数据库初始化（执行迁移 + 角色权限）

```bash
cd backend
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.seed_rbac       # 角色与权限（必需）
.venv/bin/python -m scripts.seed_demo       # 演示数据（可选，仅演示环境需要）
cd ..
```

### 4.7 启动（推荐 `start.sh`）

```bash
./start.sh                    # 交互菜单（正式/测试/恢复）
./start.sh --env testing      # 测试环境
./start.sh start              # 本地开发/临时模式（Vite + uams）
./start.sh --env production   # 正式环境（要求 Nginx + systemd 已安装）
./start.sh status             # 模式、数据库、Nginx/systemd 状态
./start.sh stop               # 停止 start.sh 启动的本地开发服务
```

脚本会依次：检查 venv / node_modules → 检查 MySQL 连通 → 启动后端并轮询 `/health` →
启动前端 → 打印本机与局域网访问地址。

### 4.8 手动启动（不使用脚本）

```bash
cd backend && .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
cd frontend && npm run dev -- --host 0.0.0.0 --port 5173
```

### 4.9 浏览器访问

```
本机：    http://127.0.0.1:5173
局域网：  http://<服务器IP>:5173
接口文档：http://<服务器IP>:8000/docs   （仅 DEBUG=true）
```

### 4.10 局域网访问与放行端口

```bash
ip route get 1.1.1.1 | grep -oP 'src \K[0-9.]+'   # 查看服务器 IP
# 正式环境只需要 80（HTTPS 另加 443）
sudo ufw allow 80/tcp
# 本地开发临时方式才放行 5173；8000/3306 不对局域网开放
```

### 4.11 停止服务

```bash
./start.sh stop
# 或手动：kill $(cat .run/backend.pid) / kill $(cat .run/frontend.pid)
```

### 4.12 查看日志

```bash
# 正式环境（Nginx + systemd）
journalctl -u uams-backend -f
sudo tail -f /var/log/nginx/access.log /var/log/nginx/error.log

# 本地开发/测试
tail -f logs/backend.log
tail -f logs/frontend.log
journalctl -u mysql -n 50
```

### 4.13 常见问题（Ubuntu）

| 现象 | 处理 |
|---|---|
| `ModuleNotFoundError: app` | 未在 `backend/` 目录下用 `.venv/bin/python` 启动 |
| 端口被占用 | `ss -ltnp \| grep -E '5173\|8000'`，先 `./start.sh stop` |
| 数据库连不上 | `sudo systemctl status mysql`；`curl http://127.0.0.1:8000/health` 看 `database` |
| 局域网打不开 | 确认监听 `0.0.0.0`、ufw 已放行、两台设备同网段 |

---

## 5. Windows 部署

> 与 Ubuntu **只有命令不同**，业务配置完全一致。

### 5.1 环境要求与安装

1. **Python 3.11+**：官网安装包，安装时勾选 **Add Python to PATH**。
2. **Node.js 20+**：官网 LTS 安装包（含 npm）。
3. **MySQL 8.4**：官网 MySQL Installer，选择 *Server only* 或 *Custom*；
   安装时设置 root 口令，字符集选 **utf8mb4**。
4. **Git for Windows**（含 Git Bash，可选但推荐）。

验证：

```powershell
python --version
node --version
npm --version
mysql --version
```

### 5.2 建库（PowerShell / cmd）

```powershell
mysql -u root -p -e "CREATE DATABASE uams CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"
mysql -u root -p -e "CREATE USER 'uams_app'@'127.0.0.1' IDENTIFIED BY '<你的强口令>';"
mysql -u root -p -e "GRANT ALL PRIVILEGES ON uams.* TO 'uams_app'@'127.0.0.1'; FLUSH PRIVILEGES;"
```

确认 MySQL 服务已启动：

```powershell
Get-Service MySQL*        # 状态应为 Running
# 若未启动： Start-Service MySQL84   （服务名以实际安装为准）
```

### 5.3 克隆项目

```powershell
git clone <仓库地址>
cd <项目目录>\uams
```

### 5.4 配置 .env

```powershell
Copy-Item backend\.env.example backend\.env
notepad backend\.env      # 修改 DATABASE_URL 口令与 JWT_SECRET
```

> `DATABASE_URL` 中的口令若含 `@ : / ?` 等字符需做 URL 编码，否则连接会失败；
> 建议使用仅含字母数字与 `-_.~` 的强口令。

### 5.5 安装后端依赖

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..
```

### 5.6 安装前端依赖

```powershell
cd frontend
npm install
cd ..
```

### 5.7 数据库初始化

```powershell
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m scripts.seed_rbac     # 必需
.\.venv\Scripts\python.exe -m scripts.seed_demo     # 可选（演示数据）
cd ..
```

### 5.8 启动后端（新开一个 PowerShell 窗口）

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

后端就绪自检：

```powershell
curl http://127.0.0.1:8000/health
# {"status":"ok","app":"UAMS","env":"development","database":"up"}
```

### 5.9 构建与启动前端（再开一个窗口）

```powershell
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173
# 生产：npm run build ；然后 npx vite preview --host 0.0.0.0 --port 4173
```

> `start.sh` 是 bash 脚本，在 Windows 上请用 **Git Bash** 运行：
> `./start.sh`（需先 `chmod +x start.sh`，或在 Git Bash 中直接 `bash start.sh`）。
> 使用 PowerShell / cmd 时按本节步骤手动启动即可，行为完全一致。

### 5.10 浏览器访问

```
本机：    http://127.0.0.1:5173
局域网：  http://<服务器IP>:5173
```

### 5.11 查看服务器 IP（局域网用）

```powershell
ipconfig
# 取当前网卡的 "IPv4 地址"，例如 192.168.1.10
```

### 5.12 局域网访问（Windows 防火墙）

首次启动时 Windows 会弹出防火墙提示，勾选 **专用网络** 允许；
若未弹出或误点取消：

```powershell
New-NetFirewallRule -DisplayName "UAMS Frontend 5173" -Direction Inbound -Protocol TCP -LocalPort 5173 -Action Allow
# 仅在需要直接访问接口文档时才放行 8000
New-NetFirewallRule -DisplayName "UAMS Backend 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
```

> **不要**放行 3306：数据库只允许本机后端访问。

### 5.13 停止服务

```powershell
# 在运行后端的窗口按 Ctrl+C
# 若窗口已关闭：
Get-Process python | Where-Object {$_.Path -like "*\.venv\*"} | Stop-Process
# 前端同理（node 进程），或直接关闭对应窗口
```

### 5.14 常见问题（Windows）

| 现象 | 处理 |
|---|---|
| `python` 不是内部或外部命令 | 安装 Python 时未勾选 Add to PATH，重新安装或手动加入 PATH |
| 执行策略禁止 npm.ps1 | 用 `npm.cmd`，或 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| 数据库连接报 `Access denied` | `.env` 中口令错误，或未创建 `uams_app@127.0.0.1` 用户 |
| 局域网其他设备打不开 | 防火墙未放行 5173/8000；或后端用了 `--host 127.0.0.1` |
| 端口被占用 | `netstat -ano \| findstr :5173` 找到 PID 后 `taskkill /PID <pid> /F` |
| 路径过长导致 npm install 失败 | 在较短的路径下克隆，或启用 Windows 长路径支持 |

---

## 6. 局域网访问（两系统通用说明）

1. 确认两台设备在同一局域网；
2. 浏览器打开 `http://<服务器IP>:5173`；
3. 使用账号登录（演示环境下见 README「演示环境账号」一节）。

IP 以实际为准，不要写死到任何配置文件：

```
服务器：   192.168.1.10           （示例）
前端：     http://192.168.1.10:5173
后端接口： http://192.168.1.10:8000/health   （浏览器一般无需直接访问）
```

---

## 7. 健康检查

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","app":"UAMS","env":"development","database":"up"}
```

- `status=ok` 且 `database=up` → 应用与数据库均正常；
- `status=degraded` → 应用已起但**数据库连接失败**，检查 MySQL 与 `DATABASE_URL`。

`./start.sh status` 会同时检查后端 `/health` 与前端 HTTP 状态码。

---

## 8. 常见访问失败原因

| 现象 | 原因与处理 |
|---|---|
| 本机能开、别的电脑打不开 | 后端/前端只监听了 `127.0.0.1`；必须用 `--host 0.0.0.0`（`start.sh` 已默认） |
| 页面能开但接口一直转圈 | 前端代理目标不对：检查 `UAMS_BACKEND_URL` 与后端是否在 8000 端口 |
| 控制台出现 `127.0.0.1:8000` 请求失败 | 说明有地方写死了本机地址；本项目走同源代理，不应出现 |
| 跨域（CORS）报错 | 同源代理模式下不会发生；若浏览器直连后端端口，需把前端地址加入 `CORS_ORIGINS` |
| 刷新子路由 404 | 静态服务未配置 History fallback；`vite preview` 已内置，Nginx 需 `try_files $uri /index.html` |
| 登录报数据库错误 | MySQL 未启动或 `DATABASE_URL` 口令不对；`curl /health` 会显示 `database: down` |
| 端口被占用 | Ubuntu：`ss -ltnp`；Windows：`netstat -ano \| findstr :5173` |
| 防火墙拦截 | 见 §4.10（Ubuntu）/ §5.12（Windows） |

---

## 9. 生产构建

- `dist/` 为静态资源；`npm run preview` 已配置 `host: 0.0.0.0` 与 `/api` 同源代理，可直接用于局域网演示；
- 若改用 Nginx 托管：配置 History fallback（`try_files $uri /index.html`）并把 `/api/` 反向代理到后端；
- 前端 API 基址为相对路径 `/api/v1`，**无需**配置 `VITE_API_BASE_URL`。

---

## 10. 数据备份

```bash
# Ubuntu
mysqldump -h 127.0.0.1 -u uams_app -p uams > uams_$(date +%Y%m%d).sql

# Windows（PowerShell）
mysqldump -h 127.0.0.1 -u uams_app -p uams > uams_$(Get-Date -Format yyyyMMdd).sql
```

备份文件不要放在数据库数据目录内；含敏感账号的备份不得提交到公开仓库。

---

## 11. 安全边界

- MySQL 保持仅回环监听，**不**对局域网暴露；
- 不关闭认证 / RBAC / 参数校验；CORS 仍按白名单；
- 不把口令与密钥写进启动脚本，一律走 `.env` / 环境变量；
- 局域网开放的最小集合：前端端口（必需）、后端端口（仅在需要直接访问接口文档时）；
- **正式部署前必须**：创建 `.env`、替换数据库口令、设置随机 `JWT_SECRET`、把 `DEBUG` 设为 `false`。

---

## 12. 相关文档

- [README.md](../README.md) — 项目简介、目录结构、账号说明
- [DEVELOPMENT.md](DEVELOPMENT.md) — 开发环境
- [ARCHITECTURE.md](ARCHITECTURE.md) — 架构
- [API.md](API.md) — 接口清单
