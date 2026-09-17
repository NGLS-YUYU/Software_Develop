# 部署说明

> 记录当前实际部署方式与后续规划（TASK-DOC-001，2026-09-17）。
> **注意**：本项目当前只实现了本地开发部署；LAN 部署为规划内容，尚未配置。

---

## 1. 当前部署方式：本地开发

### 1.1 拓扑

```
Browser（Chrome/Edge）
      ↓  http://localhost:5173
Vite Dev Server（前端，含热更新）
      ↓  /api/* 反向代理到 :8000（vite.config.ts）
FastAPI（uvicorn，127.0.0.1:8000）
      ↓  PyMySQL
MySQL 8.4（127.0.0.1:3306，本机原生安装）
```

### 1.2 组件端口

| 组件 | 地址 | 说明 |
|---|---|---|
| 前端 | `http://localhost:5173` | Vite 开发服务器 |
| 后端 | `http://127.0.0.1:8000` | uvicorn |
| API 文档 | `http://127.0.0.1:8000/docs` | 仅 `DEBUG=true` 时开放 |
| MySQL | `127.0.0.1:3306` | 仅监听回环，不对外暴露 |

### 1.3 启动步骤

```bash
# 1. 数据库
systemctl start mysql

# 2. 后端
cd uams/backend
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 3. 前端
cd uams/frontend
npm run dev
```

### 1.4 首次部署

```bash
# 数据库初始化（需 sudo）
sudo bash uams/backend/scripts/setup_mysql.sh

# 后端环境
cd uams/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # 编辑填入真实凭据与随机 JWT_SECRET
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.seed_rbac
.venv/bin/python -m scripts.seed_demo    # 可选

# 前端环境
cd ../frontend
npm install
```

---

## 2. 当前安全基线

| 项 | 现状 |
|---|---|
| MySQL 监听 | `127.0.0.1` 仅回环（`99-uams.cnf` 中 `bind-address`） |
| 应用数据库用户 | `uams_app`，仅授予 `uams.*` 与 `uams_test.*` 权限，不使用 root |
| 密码存储 | bcrypt 哈希，永不存明文 |
| 凭据管理 | `~/uams-infra/.env`（chmod 600，仓库外）+ `backend/.env`（gitignore） |
| CORS | 仅允许 `localhost:5173` / `127.0.0.1:5173` |
| 令牌 | JWT，有效期 480 分钟 |
| 登录保护 | 连续失败 5 次锁定 15 分钟 |

> ⚠️ **已知问题**：`backend/.env` 缺失时应用会回落 `app/core/config.py` 中的默认凭据（明文数据库密码 + 可预测 JWT_SECRET）。这是 V0.2 的 P0 待修复项（见 [V0.2_AUDIT.md](V0.2_AUDIT.md)）。
>
> ⚠️ **生产必做**：修改所有演示账号密码（`admin`/`admin123`、`T001`/`T001`、`20260001`/`20260001`）。

---

## 3. 前端生产构建

```bash
cd uams/frontend
npm run build          # 产物输出到 dist/
```

构建包含 `vue-tsc -b` 类型检查，类型错误会中断构建。

**当前构建结果**：28 个页面全部按路由自动代码分割，主包约 534 KB（gzip 173 KB）。

### 3.1 部署注意事项

- `dist/` 为静态资源，需由 Nginx 等 Web 服务器托管
- 前端使用 `createWebHistory`（HTML5 History 模式），**服务器需配置 fallback 到 `index.html`**，否则刷新子路由会 404
- 前端 API 基址为相对路径 `/api/v1`，生产环境需由反向代理转发到后端

---

## 4. LAN 部署规划（尚未实施）

规划拓扑：

```
LAN Client
    ↓  http://<server-ip>
Nginx
    ├── /            → 前端静态资源（dist/）
    └── /api/        → 反向代理到 FastAPI（127.0.0.1:8000）
                          ↓
                      MySQL（127.0.0.1:3306）
```

**规划要点**（未配置，仅记录）：

| 项 | 规划 |
|---|---|
| 前端托管 | Nginx 提供 `dist/` 静态文件，配置 History fallback |
| 后端运行 | uvicorn 多 worker 或用 systemd 托管，仅监听回环 |
| CORS | 改为实际访问来源，或同源部署后移除跨域需求 |
| `DEBUG` | 必须设为 `false`（关闭 `/docs`） |
| `JWT_SECRET` | 使用强随机值 |
| MySQL | 保持仅回环监听，由后端同机访问 |
| 数据库备份 | 定期 `mysqldump`，备份文件存放于数据库数据目录之外 |

> 部署配置本身不在本任务范围内，此处只整理现状与后续方向。

---

## 5. 数据备份

当前**无自动备份**。建议（V0.2+）：

```bash
# 逻辑备份（示例）
mysqldump -h 127.0.0.1 -u uams_app -p uams > uams_$(date +%Y%m%d).sql

# 备份文件不要放在数据库数据目录内
# 含敏感账号的备份不得提交到公开仓库
```

数据库建模与 Alembic 迁移本身也是项目成果，建议每完成一个重要版本做一次逻辑备份。

---

## 6. 环境变量清单

| 变量 | 开发值 | 生产要求 |
|---|---|---|
| `APP_ENV` | `development` | `production` |
| `DEBUG` | `true` | **必须 `false`** |
| `DATABASE_URL` | 本机 MySQL | 生产数据库连接串 |
| `DB_ECHO` | `false` | `false` |
| `JWT_SECRET` | 需替换 | **必须强随机** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | 按安全策略调整 |
| `CORS_ORIGINS` | `http://localhost:5173` | 实际访问来源 |

---

## 7. 相关文档

- [DEVELOPMENT.md](DEVELOPMENT.md) — 开发环境
- [ARCHITECTURE.md](ARCHITECTURE.md) — 架构
- [ROADMAP.md](ROADMAP.md) — 版本规划
- [V0.2_AUDIT.md](V0.2_AUDIT.md) — 待修复问题
