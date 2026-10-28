# 项目启动说明

> 从零初始化到日常启动。
> **V3.2 起正式环境采用 Nginx + systemd；本地开发/测试仍可使用 Vite。**
> 正式部署与回滚见 [DEPLOYMENT.md](DEPLOYMENT.md) 与 [../deploy/README.md](../deploy/README.md)。

---

## 1. 组件拓扑

**正式环境**

```
浏览器 http://<服务器IP>/（80）
      ↓
Nginx ── 静态文件 → /var/www/uams/current（Vue 构建产物）
      └─ /api/     → FastAPI 127.0.0.1:8000（systemd）
                             ↓ PyMySQL
                     MySQL 127.0.0.1:3306（uams）
```

**本地开发/测试环境**

```
浏览器 http://localhost:5173（Vite）
      ↓ /api 同源代理
FastAPI 127.0.0.1:8000（uvicorn）
      ↓
MySQL 127.0.0.1:3306（uams / uams_test）
```

| 组件 | 正式环境 | 本地开发/测试 |
|---|---|---|
| 前端 | Nginx `:80`，静态构建 | Vite `:5173` |
| 后端 | systemd，`127.0.0.1:8000` | `start.sh` 子进程，`0.0.0.0:8000` |
| 健康检查 | `http://127.0.0.1:8000/health` | 同左 |
| API 文档 | 仅 `DEBUG=true` | 同左 |

---

## 2. 环境要求

| 项 | 版本 | 说明 |
|---|---|---|
| 操作系统 | Ubuntu 26.04 LTS（x86_64） | |
| Python | 3.14.4 | pyenv 管理，`uams/.python-version` 锁定 |
| Node.js | 22 | 前端构建与开发服务器 |
| MySQL | 8.4 LTS | 本机原生安装（非 Docker），InnoDB / utf8mb4 |

---

## 3. 首次启动（一次性初始化）

新环境需按顺序执行一次；已有环境可直接跳到「日常启动」。

```bash
# 1. 数据库初始化（首次需 sudo；创建 uams 库 + uams_app 用户 + utf8mb4 配置）
sudo bash uams/backend/scripts/setup_mysql.sh

# 2. 后端环境
cd uams/backend
python3 -m venv .venv                          # 若 .venv 已存在可跳过
.venv/bin/pip install -r requirements.txt
cp .env.example .env                           # 填入真实 DATABASE_URL 与随机 JWT_SECRET
.venv/bin/alembic upgrade head                 # 数据库迁移到最新
.venv/bin/python -m scripts.seed_rbac          # 角色/权限/admin 账号（幂等）
.venv/bin/python -m scripts.seed_demo          # 演示数据（可选，幂等）

# 3. 前端依赖
cd ../frontend
npm install
```

> ⚠️ **必须创建 `.env`**：若缺失，应用会回落 `app/core/config.py` 中的默认凭据（明文数据库密码 + 可预测 `JWT_SECRET`），存在安全隐患。仓库只提交 `.env.example`，`.env` 已被 `.gitignore` 排除。

---

## 4. 日常启动

### 4.1 统一入口（推荐）

```bash
cd uams
./start.sh
```

菜单：

1. **正式环境**：Nginx + systemd FastAPI + `uams`（要求 Nginx 与 `uams-backend.service` 已安装）
2. **测试环境**：Vite + FastAPI + `uams_test`
3. **恢复验证环境**：Vite + FastAPI + `uams_restore_20261027`（版本必须等于 head）

非交互：

```bash
./start.sh --env production
./start.sh --env testing
./start.sh --env restore
./start.sh status
./start.sh stop
```

### 4.2 本地开发手动启动（可选）

```bash
# 后端
cd uams/backend
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 前端（另一个终端）
cd uams/frontend
npm run dev
```

浏览器访问 `http://localhost:5173`。

### 4.3 正式环境（Nginx + systemd）

```bash
./start.sh --env production   # 只做检查，不启动 Vite
sudo systemctl status uams-backend nginx
journalctl -u uams-backend -f
```

安装与切换步骤见 [../deploy/README.md](../deploy/README.md)。

> 当前服务器（2026-10-29）：Nginx 未安装且没有免密 sudo，正式模式会拒绝启动并提示安装命令；
> 现有服务仍以 `./start.sh start`（Vite + uvicorn）临时运行。

---

## 5. 验证与演示账号

```bash
# 后端连通性
curl http://127.0.0.1:8000/health
# 期望：{"status":"ok","app":"UAMS","env":"production|testing","database":"up"}
```

| 角色 | 账号 | 密码 |
|---|---|---|
| 教务管理员 | admin | admin123 |
| 教师 | T001 | T001 |
| 学生 | 20260001 | 20260001 |

> 演示密码仅用于本地开发；`admin` 账号由 `seed_rbac` 创建，教师/学生由 `seed_demo` 创建。

---

## 6. 常见问题

| 现象 | 排查 |
|---|---|
| 后端启动即报数据库连接失败 | MySQL 未启动：`systemctl start mysql`；或 `.env` 中 `DATABASE_URL` 凭据/转义错误（含 `@` 等特殊字符需 `%40` 转义） |
| `GET /health` 返回 `database: down` | 确认 MySQL 运行中、库 `uams` 已建、`uams_app` 用户授权正确 |
| 迁移报版本不一致 | `cd uams/backend && .venv/bin/alembic upgrade head`（当前头版本见 `alembic current`） |
| 前端页面 401/403 | 先登录获取 token；前端代理仅处理 `/api`，直接访问后端时需手动带 `Authorization: Bearer <token>` |
| 端口被占用 | 后端 `--port` 换端口并同步改 `vite.config.ts` 的代理目标；前端 `vite.config.ts` 的 `server.port` |
| `/docs` 404 | `DEBUG=false` 时接口文档关闭，改为 `DEBUG=true` 后重启后端 |
| 账号登录失败 | 重新执行 `python -m scripts.seed_rbac` 与 `scripts.seed_demo`（幂等，不会重复建数据） |

---

## 7. 相关文档

- [DEVELOPMENT.md](DEVELOPMENT.md) — 开发环境与规范
- [DEPLOYMENT.md](DEPLOYMENT.md) — 部署方式与安全基线
- [DATABASE.md](DATABASE.md) — 数据库结构与迁移
- [TESTING.md](TESTING.md) — 测试运行方式
