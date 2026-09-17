# 开发规范

> 依据当前实际环境与 CLAUDE.md 整理（TASK-DOC-001，2026-09-17）。

---

## 1. 开发环境

| 项 | 当前实际版本 | 说明 |
|---|---|---|
| 操作系统 | Ubuntu 26.04 LTS (resolute) x86_64 | |
| Python | **3.14.4**（pyenv 管理） | `uams/.python-version` 锁定；系统自带 python3 亦为 3.14.4 |
| 虚拟环境 | `backend/.venv` | 由 `python3 -m venv` 创建 |
| Node.js | v22.22.1 | Ubuntu apt 提供 |
| npm | 11.19.1 | npm 12 要求 node ≥ 22.22.2，当前不可用 |
| MySQL | 8.4.11 | 原生安装（非 Docker），监听 `127.0.0.1:3306` |
| Git | 2.55.0 | |

> ⚠️ 环境细节（sudo 安装脚本、MySQL 初始化）记录在 `backend/scripts/setup_mysql.sh`。

### 1.1 后端依赖

```
fastapi==0.141.1        SQLAlchemy==2.0.52       alembic==1.20.0
pydantic==2.13.5        pydantic-settings==2.15.0 PyMySQL==1.2.0
uvicorn==0.53.0         bcrypt==5.0.0            python-jose==3.5.0
pytest==9.1.1           pytest-asyncio==1.4.0
```

完整清单见 `backend/requirements.txt`。

> **密码哈希不使用 passlib**：passlib 依赖 `bcrypt.__about__`，该属性在 bcrypt 4.1+ 已移除，在 bcrypt 5.x 下会直接报错。当前直接调用 `bcrypt`（见 `app/core/security.py`）。`requirements.txt` 中残留的 `passlib` 为历史依赖。

### 1.2 前端依赖

```
vue 3.5.42          element-plus 2.14.5    pinia 4.0.3
vue-router 5.3.1    axios 1.20.0           vite 8.3.0
typescript 6.0.2    vue-tsc 3.3.11         sass 1.104.1
```

---

## 2. 环境准备

### 2.1 数据库

MySQL 为**本机原生安装**（非容器）。凭据存放于 `~/uams-infra/.env`（`chmod 600`，不在仓库内）。

```bash
# 服务管理
systemctl status mysql
systemctl restart mysql

# 连接（应用用户）
mysql -h 127.0.0.1 -u uams_app -p -D uams
```

如需在新环境重建，执行 `sudo bash backend/scripts/setup_mysql.sh`（会创建 `uams` 库与 `uams_app` 用户、写入 utf8mb4/严格模式配置）。

### 2.2 后端

```bash
cd uams/backend

# 环境变量（.env 不入版本库）
cp .env.example .env
# 编辑 .env，填入真实 DATABASE_URL 与随机 JWT_SECRET

# 依赖
.venv/bin/pip install -r requirements.txt   # 若无 .venv 先 python3 -m venv .venv

# 迁移
.venv/bin/alembic upgrade head

# 种子数据
.venv/bin/python -m scripts.seed_rbac    # 角色、权限、admin 账号（幂等）
.venv/bin/python -m scripts.seed_demo    # 演示数据（幂等）

# 启动
.venv/bin/uvicorn app.main:app --port 8000 --reload
```

### 2.3 前端

```bash
cd uams/frontend
npm install
npm run dev     # http://localhost:5173，/api 自动代理到 127.0.0.1:8000
```

---

## 3. 配置管理

`.env` 位于 `backend/.env`，由 `app/core/config.py` 通过 pydantic-settings 读取。

| 变量 | 说明 |
|---|---|
| `APP_ENV` / `DEBUG` | 环境标识；`DEBUG=true` 才开放 `/docs` 与 `/redoc` |
| `DATABASE_URL` | `mysql+pymysql://用户:密码@127.0.0.1:3306/uams?charset=utf8mb4` |
| `DB_ECHO` | 是否打印 SQL |
| `JWT_SECRET` | **必须替换为随机值**，不得使用示例值 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 令牌有效期，默认 480 |
| `MAX_LOGIN_FAILURES` / `LOGIN_LOCK_MINUTES` | 登录失败限制，默认 5 次 / 15 分钟 |
| `CORS_ORIGINS` | 允许的前端来源，逗号分隔 |

**安全要求**（CLAUDE.md §23）：

- `.env` 已在 `.gitignore` 中，**禁止提交**
- 仓库只提交 `.env.example`（占位值）
- 密码含特殊字符时需在 URL 中转义（如 `@` → `%40`）
- 密码永远不明文存储（bcrypt）、不写入日志

---

## 4. Git 工作流

### 4.1 分支

```
main                # 稳定分支
develop             # 集成分支
feature/*           # 功能分支
```

示例：`feature/student-course-selection`、`feature/teacher-grade-entry`、`feature/admin-course-management`

### 4.2 提交流程

```
修改代码
  ↓
运行测试（pytest / npm run build）
  ↓
git diff 审阅改动
  ↓
git commit
```

### 4.3 提交信息前缀

| 前缀 | 用途 |
|---|---|
| `feat:` | 新功能 |
| `fix:` | 缺陷修复 |
| `refactor:` | 重构（不改变行为） |
| `docs:` | 文档 |
| `test:` | 测试 |
| `chore:` | 构建、依赖、杂项 |

示例：`feat: add student course selection`

---

## 5. 编码规范

### 5.1 后端

- **分层不可跨越**：Router 不直接查库；Service 不处理 HTTP 细节；Repository 不含业务规则
- **新增模型必须**在 `app/models/__init__.py` 中登记，否则 Alembic 会漏表
- **数据库结构变更必须**通过 Alembic migration，禁止手工改库
- 禁止删除已提交的历史迁移（CLAUDE.md §27）
- 禁止字符串拼接构造 SQL，统一使用 SQLAlchemy ORM
- 业务异常继承 `app/core/exceptions.py` 中的 `BizError`，带明确 `code`
- 事务边界放在 Service 方法内，失败整体回滚

### 5.2 前端

- 权限控制只用于体验（菜单/路由），**不得替代后端校验**
- API 调用统一走 `src/api/index.ts`，不散落 axios
- 类型定义集中在 `src/types/index.ts`，与后端 Schema 对应
- 页面复用 `useCrudTable` 组合式函数处理分页表格，避免重复样板
- Element Plus 按需自动导入（`unplugin-auto-import` / `unplugin-vue-components`），无需手动 import 组件

### 5.3 数据库

- 类型选择见 [DATABASE.md](DATABASE.md) §1.4：成绩/学分/绩点**必须用 DECIMAL**，禁止 FLOAT/DOUBLE
- 状态字段用 `VARCHAR(20)` + `CHECK` 约束
- 字符集统一 utf8mb4，引擎统一 InnoDB
- 新增冗余字段必须在 DATABASE.md §13.3 登记并说明一致性责任方

---

## 6. Claude Code 开发约定

**核心原则：单任务迭代**（CLAUDE.md §32）

```
一个 TASK
  ↓
阅读 CLAUDE.md 与相关代码
  ↓
实现
  ↓
运行测试
  ↓
修复问题
  ↓
更新文档
  ↓
git commit
  ↓
下一个 TASK
```

### 6.1 每次开始开发前必须

1. 阅读 `CLAUDE.md`
2. 查看当前 Git 状态
3. 阅读相关模块代码
4. 确认当前数据库结构
5. 确认现有 API
6. 不随意重构无关模块

### 6.2 禁止事项（CLAUDE.md §27）

- 删除已有业务代码后重新实现
- 未经说明的大规模重构
- 随意更换技术栈或数据库
- 使用 SQLite / PostgreSQL 替代 MySQL
- 创建不必要的数据库扩展
- 将数据库密码提交到 Git
- 删除 Alembic 历史迁移
- 修改 API 返回格式而不说明
- 为了通过测试而直接修改测试结果
- **一次执行多个大型业务任务**

### 6.3 任务完成标准（CLAUDE.md §33）

代码完成 + 数据库迁移完成 + API 完成 + 权限完成 + 测试完成 + 前端页面完成（如涉及）+ 手工验证完成 + 文档同步更新。

---

## 7. 常见操作

```bash
# 后端：新增迁移
cd uams/backend
.venv/bin/alembic revision --autogenerate -m "描述"
.venv/bin/alembic upgrade head

# 查看当前迁移版本
.venv/bin/alembic current

# 回滚一个版本
.venv/bin/alembic downgrade -1

# 运行测试
.venv/bin/python -m pytest tests/ -q

# 前端：类型检查
cd uams/frontend && node_modules/.bin/vue-tsc --noEmit

# 前端：生产构建
npm run build
```

> ⚠️ 前端类型检查请使用 `node_modules/.bin/vue-tsc`，不要用 `npx vue-tsc`（npx 缓存版本与本地 TypeScript 6.0 不兼容）。

---

## 8. 相关文档

- [ARCHITECTURE.md](ARCHITECTURE.md) — 架构与分层
- [DATABASE.md](DATABASE.md) — 数据库约定
- [TESTING.md](TESTING.md) — 测试规范
- [DEPLOYMENT.md](DEPLOYMENT.md) — 部署说明
- [CLAUDE.md](../CLAUDE.md) — 项目规范（最高依据）
