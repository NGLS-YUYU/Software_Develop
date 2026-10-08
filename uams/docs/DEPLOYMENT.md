# 部署说明

> 记录当前实际部署方式（TASK-DOC-001，2026-09-17；**FIX-007 更新，2026-10-08：已实现统一启动脚本与局域网访问**）。

---

## 1. 部署拓扑（当前实现）

```
局域网客户端（另一台电脑 / 手机）
        │  http://<服务器IP>:5173
        ▼
Vite（前端：开发服务器或 `vite preview` 静态服务，监听 0.0.0.0）
        │  /api/* 同源代理（服务端 → 服务端）
        ▼
FastAPI（uvicorn，监听 0.0.0.0:8000）
        │  PyMySQL
        ▼
MySQL 8.4（127.0.0.1:3306，仅回环，不对外暴露）
```

**关键点（FIX-007 §十七）**：浏览器只请求 `http://<服务器IP>:5173/api/v1/...`，
由 Vite 在**服务器端**转发到 `127.0.0.1:8000`。因此浏览器里永远不会出现
`127.0.0.1`（那会指向访问者自己的电脑），也**不产生跨域请求**，无需为 LAN 单独配置 CORS。

### 1.1 端口

| 组件 | 监听 | 说明 |
|---|---|---|
| 前端（dev） | `0.0.0.0:5173` | Vite 开发服务器 |
| 前端（prod） | `0.0.0.0:4173` | `vite preview` 提供 `dist/` |
| 后端 | `0.0.0.0:8000` | uvicorn；`/health` 健康检查，`/docs` 仅 `DEBUG=true` 时开放 |
| MySQL | `127.0.0.1:3306` | **仅回环**，不对局域网暴露（§二十三） |

---

## 2. 环境要求

| 项 | 要求 |
|---|---|
| 操作系统 | Linux（已在 Ubuntu 类环境验证） |
| Python | 3.14（`backend/.venv`） |
| Node.js | 20+（`frontend/node_modules` 已安装） |
| MySQL | 8.4 LTS，InnoDB / utf8mb4 |
| 依赖安装 | `cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`<br>`cd frontend && npm install` |

---

## 3. 环境变量

配置一律走 `backend/.env`（`pydantic-settings` 读取），**启动脚本不写死任何口令**。

```bash
cp backend/.env.example backend/.env   # 首次部署
```

| 变量 | 说明 | 局域网部署要求 |
|---|---|---|
| `APP_ENV` | 运行环境 | `production` |
| `DEBUG` | 调试开关（控制 `/docs`） | **必须 `false`** |
| `DATABASE_URL` | MySQL 连接串 | 改为真实口令 |
| `DB_ECHO` | SQL 回显 | `false` |
| `JWT_SECRET` | 令牌签名密钥 | **必须替换为随机值**：`python3 -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 令牌有效期 | 按安全策略调整 |
| `CORS_ORIGINS` | 允许跨域的前端来源 | 同源代理模式下**无需**登记 LAN 地址；仅当浏览器直连后端端口时才需要 |

> ⚠️ **安全提示（FIX-007 §十九 报告项）**：`backend/app/core/config.py` 内置了演示用的
> 数据库口令与占位 `JWT_SECRET=CHANGE_ME_IN_ENV`。当前仓库内**没有** `.env`，
> 因此未配置时会直接使用这些默认值 —— 仅可用于本机演示。
> `./start.sh` 在检测不到 `.env` 时会明确告警；局域网部署前**必须**创建 `.env` 并替换。

---

## 4. 启动

### 4.1 一键启动（推荐）

```bash
cd uams
./start.sh            # 后端 + 前端（dev 模式）
./start.sh prod       # 先 npm run build，再用 vite preview 提供静态服务
./start.sh status     # 查看健康检查
./start.sh stop       # 停止
./start.sh restart    # 重启
```

脚本会依次完成：检查 venv / node_modules → 检查 MySQL 连通 → 启动后端 →
等待 `/health` 就绪 → 启动前端 → 打印本机与局域网访问地址。

可用环境变量覆盖默认值：`UAMS_BACKEND_HOST`、`UAMS_BACKEND_PORT`、
`UAMS_FRONTEND_HOST`、`UAMS_FRONTEND_PORT`、`UAMS_BACKEND_URL`（前端代理目标）。

### 4.2 数据库

```bash
systemctl start mysql
cd backend && .venv/bin/alembic upgrade head   # 迁移
.venv/bin/python -m scripts.seed_rbac          # 角色/权限（首次）
.venv/bin/python -m scripts.seed_demo          # 演示数据（可选）
```

### 4.3 手动启动（不使用脚本时）

```bash
# 后端（必须 0.0.0.0 才能被局域网访问）
cd backend && .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 前端（vite.config.ts 已设 host: 0.0.0.0）
cd frontend && npm run dev            # dev：http://<IP>:5173
cd frontend && npm run build && npx vite preview --host 0.0.0.0 --port 4173   # prod
```

---

## 5. 局域网访问

### 5.1 查看服务器 IP

```bash
ip route get 1.1.1.1 | grep -oP 'src \K[0-9.]+'   # 推荐：默认路由出口地址
hostname -I | awk '{print $1}'                    # 备选
```

`./start.sh` 启动时会自动打印，例如：

```
  本机访问：  http://127.0.0.1:5173
  局域网访问：http://192.168.1.10:5173
```

### 5.2 从另一台设备访问

1. 确认两台设备在同一局域网；
2. 浏览器打开 `http://<服务器IP>:5173`；
3. 用演示账号登录：教务 `admin/admin123`、教师 `T001/T001`、学生 `20260001/20260001`。

示例（IP 以实际为准，不要写死）：

```
服务器：   192.168.1.10
前端：     http://192.168.1.10:5173
后端接口： http://192.168.1.10:8000/health   （浏览器一般无需直接访问）
```

### 5.3 放行端口

```bash
# Ubuntu（ufw）示例
sudo ufw allow 5173/tcp     # 前端
sudo ufw allow 8000/tcp     # 后端（仅当需要直接访问接口/文档时）
# 3306 不要放行
```

---

## 6. 停止与日志

```bash
./start.sh stop                 # 停止脚本启动的进程
kill $(cat uams/.run/backend.pid)    # 单独停止后端

tail -f uams/logs/backend.log    # 后端日志
tail -f uams/logs/frontend.log   # 前端日志
tail -f uams/logs/frontend-build.log   # prod 模式构建日志
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
| 本机能开、别的电脑打不开 | 后端/前端只监听了 `127.0.0.1`；本脚本已用 `0.0.0.0`，检查是否手动启动过 |
| 页面能开但接口全红 / 一直转圈 | 前端代理目标不对：检查 `UAMS_BACKEND_URL` 与后端是否在 8000 端口 |
| 浏览器控制台出现 `127.0.0.1:8000` 请求失败 | 说明有地方写死了本机地址；本项目走同源代理，不应出现（见 §1 关键点） |
| 跨域（CORS）报错 | 同源代理模式下不会发生；若浏览器直连后端端口，需把前端地址加入 `CORS_ORIGINS` |
| 刷新子路由 404 | 静态服务未配置 History fallback；`vite preview` 已内置，Nginx 需 `try_files $uri /index.html` |
| 登录报「数据库连接失败」 | MySQL 未启动或 `DATABASE_URL` 口令不对；`curl /health` 会显示 `database: down` |
| 端口被占用 | `ss -ltnp \| grep -E '5173\|8000'`，先 `./start.sh stop` 再启动 |
| 防火墙拦截 | 见 §5.3 放行端口 |

---

## 9. 生产构建说明

**当前构建结果**：页面按路由自动代码分割，主包约 519 KB（gzip 167 KB）。

- `dist/` 为静态资源；`npm run preview` 已配置 `host: 0.0.0.0` 与 `/api` 同源代理，可直接用于局域网演示；
- 若改用 Nginx 托管：需配置 History fallback（`try_files $uri /index.html`）并把 `/api/` 反向代理到后端；
- 前端 API 基址为相对路径 `/api/v1`，因此**无需**配置 `VITE_API_BASE_URL`。

---

## 10. 数据备份

当前**无自动备份**。建议：

```bash
mysqldump -h 127.0.0.1 -u uams_app -p uams > uams_$(date +%Y%m%d).sql
```

备份文件不要放在数据库数据目录内；含敏感账号的备份不得提交到公开仓库。

---

## 11. 安全边界（FIX-007 §二十三）

- MySQL 保持仅回环监听，**不**对局域网暴露；
- 不关闭认证 / RBAC / 参数校验；CORS 仍按白名单；
- 不把口令与密钥写进 `start.sh`，一律走 `.env` / 环境变量；
- 局域网开放的最小集合：前端端口（必需）、后端端口（仅在需要直接访问接口文档时）。

---

## 12. 相关文档

- [DEVELOPMENT.md](DEVELOPMENT.md) — 开发环境
- [ARCHITECTURE.md](ARCHITECTURE.md) — 架构
- [API.md](API.md) — 接口清单
- [ROADMAP.md](ROADMAP.md) — 版本规划
