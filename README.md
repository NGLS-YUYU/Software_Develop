# 高校教务教学管理系统（UAMS）

**University Academic Affairs & Teaching Management System**

一个基于 Web 的高校教务教学管理系统，面向学生、教师、教务管理员三类用户。

## 项目定位

- 用于智能软件工程课程设计与项目开发
- 前后端分离架构（Vue 3 + FastAPI + MySQL）
- 以实际高校教务业务为背景（选课、排课、成绩、考试等完整业务闭环）
- 当前处于 **V0.2 开发阶段**

## 技术栈

| 端 | 技术 |
|---|---|
| Backend | Python 3.14（pyenv）/ FastAPI / SQLAlchemy 2.x / Alembic / PyMySQL / Pydantic v2 / bcrypt / Pytest |
| Frontend | Vue 3 / TypeScript / Vite / Element Plus / Pinia / Vue Router / Axios |
| Database | MySQL 8.4 LTS（InnoDB / utf8mb4） |

> 技术栈详情以代码为准，见 [docs/ARCHITECTURE.md](uams/docs/ARCHITECTURE.md)。

## 项目结构

```
Software_Develop/                 # Git 仓库根
├── README.md                     # 本文件
├── uams/                         # 项目实际根目录
│   ├── CLAUDE.md                 # 项目规范与开发约定（最高优先级）
│   ├── .python-version           # pyenv Python 版本锁定
│   ├── backend/                  # FastAPI 后端
│   │   ├── app/                  #  应用代码（api / core / db / models / schemas / services / repositories）
│   │   ├── alembic/              #  数据库迁移
│   │   ├── tests/                #  测试
│   │   ├── scripts/              #  种子数据 / 环境脚本
│   │   └── requirements.txt
│   ├── frontend/                 # Vue 3 前端
│   │   └── src/                  #  api / components / composables / layouts / router / stores / types / views
│   ├── database/                 # 预留数据库相关
│   ├── docs/                     # 项目文档
│   └── scripts/                  # 预留（当前为空）
└── .gitignore
```

各目录职责见各目录 `README.md`。

## 快速开始

### 环境要求

- Ubuntu 26.04（或其他 x86_64 Linux）
- pyenv + Python 3.14.4（`uams/.python-version` 锁定）
- Node.js 22
- MySQL 8.4（本机运行，`uams_app` / 密码见 `~/uams-infra/.env`）

### 后端

```bash
cd uams/backend

# 1. 创建虚拟环境并安装依赖
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. 准备 .env（从示例复制并填入真实凭据）
cp .env.example .env

# 3. 数据库迁移
.venv/bin/alembic upgrade head

# 4. 初始化基础数据（角色、权限、管理员）
.venv/bin/python -m scripts.seed_rbac

# 5.（可选）生成演示数据
.venv/bin/python -m scripts.seed_demo

# 6. 启动后端
.venv/bin/uvicorn app.main:app --port 8000
```

### 前端

```bash
cd uams/frontend
npm install
npm run dev        # http://localhost:5173（自动代理 /api 到 8000）
```

### 测试与构建

```bash
# 后端测试
cd uams/backend && .venv/bin/python -m pytest tests/ -q

# 前端类型检查 + 生产构建
cd uams/frontend && npm run build
```

### 演示账号

| 角色 | 账号 | 密码 |
|---|---|---|
| 教务管理员 | admin | admin123 |
| 教师 | T001 | T001 |
| 学生 | 20260001 | 20260001 |

> 演示密码仅用于开发，正式环境必须修改（见 [docs/DEVELOPMENT.md](uams/docs/DEVELOPMENT.md)）。

## 文档导航

- [docs/README.md](uams/docs/README.md) — 文档入口
- [docs/PRD.md](uams/docs/PRD.md) — 产品需求
- [docs/ARCHITECTURE.md](uams/docs/ARCHITECTURE.md) — 系统架构
- [docs/DATABASE.md](uams/docs/DATABASE.md) — 数据库设计
- [docs/API.md](uams/docs/API.md) — 后端 API
- [docs/DEVELOPMENT.md](uams/docs/DEVELOPMENT.md) — 开发规范
- [docs/ROADMAP.md](uams/docs/ROADMAP.md) — 版本规划
- [docs/TESTING.md](uams/docs/TESTING.md) — 测试规范
- [docs/STARTUP.md](uams/docs/STARTUP.md) — 项目启动说明（一键快速开始）
- [docs/DEPLOYMENT.md](uams/docs/DEPLOYMENT.md) — 部署说明
- [docs/V0.2_AUDIT.md](uams/docs/V0.2_AUDIT.md) — V0.2 升级前审计
- [docs/DOCUMENTATION_UPDATE_REPORT.md](uams/docs/DOCUMENTATION_UPDATE_REPORT.md) — 文档整理报告

---

**项目规范与开发约定**：以 [CLAUDE.md](uams/CLAUDE.md) 为准。
