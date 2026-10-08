# 高校教务教学管理系统（UAMS）

**University Academic Affairs & Teaching Management System**

一个基于 Web 的高校教务教学管理系统，面向学生、教师、教务管理员三类用户，
覆盖「课程 → 教学班 → 排课 → 选课 → 课表 → 成绩 → 审核 → 学生成绩」完整业务闭环。

> 当前版本：**V3.0（最终交付版）** —— 业务基线为 V2.1（已通过最终发布审计），
> V3.0 完成 UI/UX 与响应式产品化重构，未改动任何业务逻辑与数据模型。

## 技术栈

| 端 | 技术 |
|---|---|
| Backend | Python 3.14（pyenv）/ FastAPI / SQLAlchemy 2.x / Alembic / PyMySQL / Pydantic v2 / bcrypt |
| Frontend | Vue 3 / TypeScript / Vite / Element Plus / Pinia / Vue Router / Axios |
| Database | MySQL 8.4 LTS（InnoDB / utf8mb4） |

> 技术栈详情以代码为准，见 [docs/ARCHITECTURE.md](uams/docs/ARCHITECTURE.md)。

## 功能模块

| 角色 | 主要功能 |
|---|---|
| 教务管理员 | 组织机构（学院/专业/班级/教室）、学生与教师管理、课程与培养方案、开课与排课、选课管理、学期管理、批量导入（学生/教师/课程/成绩 Excel）、成绩审核、考试管理、公告管理、数据统计 |
| 教师 | 工作台、我的课程与学生名单、我的课表、成绩录入（草稿/提交/导入 Excel 模板）、教学评价 |
| 学生 | 工作台、个人信息、在线选课、我的课表、我的成绩（含绩点与班级/专业排名）、我的考试、教学评价 |
| 公共 | 统一认证登录、RBAC 权限隔离、通知公告、403/404 状态页 |

## 项目结构

```
Software_Develop/                 # Git 仓库根
├── README.md                     # 本文件
├── uams/                         # 项目实际根目录
│   ├── CLAUDE.md                 # 项目规范与开发约定（最高优先级）
│   ├── start.sh                  # 统一启动脚本（Linux / macOS / Git Bash）
│   ├── backend/                  # FastAPI 后端
│   │   ├── app/                  #  应用代码（api / core / db / models / schemas / services）
│   │   ├── alembic/              #  数据库迁移
│   │   ├── scripts/              #  初始化与演示数据脚本
│   │   └── requirements.txt
│   ├── frontend/                 # Vue 3 前端
│   │   └── src/                  #  api / assets / components / composables / layouts / router / stores / types / views
│   ├── docs/                     # 项目文档
│   └── scripts/                  # 数据库环境脚本
└── .gitignore
```

## 部署

完整的 Windows / Ubuntu / 局域网部署步骤见 **[docs/DEPLOYMENT.md](uams/docs/DEPLOYMENT.md)**。
两套系统**只有命令不同**，数据库结构、环境变量名、API、前端构建与业务逻辑完全一致。

### Ubuntu（推荐 `start.sh`）

```bash
cd uams
cp backend/.env.example backend/.env    # 修改数据库口令与 JWT_SECRET
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && cd ..
cd frontend && npm install && cd ..
cd backend && .venv/bin/alembic upgrade head \
  && .venv/bin/python -m scripts.seed_rbac \
  && .venv/bin/python -m scripts.seed_demo && cd ..
./start.sh            # 后端 + 前端；./start.sh prod 为生产预览模式
```

### Windows（PowerShell）

```powershell
cd uams
Copy-Item backend\.env.example backend\.env       # 修改数据库口令与 JWT_SECRET
cd backend; python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt; cd ..
cd frontend; npm install; cd ..
cd backend; .\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m scripts.seed_rbac
.\.venv\Scripts\python.exe -m scripts.seed_demo; cd ..
# 两个窗口分别启动
cd backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
cd frontend; npm run dev -- --host 0.0.0.0 --port 5173
```

（`start.sh` 为 bash 脚本，Windows 可在 **Git Bash** 中执行 `bash start.sh`。）

### 默认访问地址

| 场景 | 地址 |
|---|---|
| 本机 | `http://127.0.0.1:5173` |
| 局域网 | `http://<服务器IP>:5173`（生产预览模式为 `:4173`） |
| 接口文档 | `http://<服务器IP>:8000/docs`（仅 `DEBUG=true` 时开放） |
| 健康检查 | `http://127.0.0.1:8000/health` |

查看服务器 IP：Ubuntu `ip route get 1.1.1.1 | grep -oP 'src \K[0-9.]+'`；
Windows `ipconfig`（取 IPv4 地址）。

### 启动与停止

| 操作 | Ubuntu | Windows |
|---|---|---|
| 启动 | `./start.sh`（或 `./start.sh prod`） | 见上方两个启动窗口 |
| 状态 | `./start.sh status` | `curl http://127.0.0.1:8000/health` |
| 停止 | `./start.sh stop` | 在对应窗口按 `Ctrl+C` |
| 日志 | `tail -f logs/backend.log` | 直接查看启动窗口输出 |

## 环境变量

配置位于 `backend/.env`（从 `.env.example` 复制）。**正式部署前必须修改**：

| 变量 | 说明 |
|---|---|
| `DATABASE_URL` | MySQL 连接串（含数据库口令） |
| `JWT_SECRET` | 令牌签名密钥，必须替换为随机值 |
| `DEBUG` | 正式部署必须设为 `false`（关闭 `/docs`） |
| `APP_ENV` / `ACCESS_TOKEN_EXPIRE_MINUTES` / `CORS_ORIGINS` / `DB_ECHO` | 见 `.env.example` 注释 |

生成随机密钥：`python -c "import secrets;print(secrets.token_urlsafe(48))"`

> ⚠️ `backend/app/core/config.py` 内置的数据库口令与 JWT_SECRET 仅用于本机演示，
> **不得用于正式部署**。

## 演示环境账号

> ⚠️ **以下仅为演示/答辩环境账号，不是生产环境默认账号密码。**
> 正式部署必须修改管理员密码，并在 `.env` 中设置随机 `JWT_SECRET`。

| 角色 | 账号 | 密码 |
|---|---|---|
| 教务管理员 | `admin` | `admin123` |
| 教师 | `T001` | `T001` |
| 学生 | `20260001` | `20260001` |

## 文档导航

- [docs/README.md](uams/docs/README.md) — 文档入口
- [docs/DEPLOYMENT.md](uams/docs/DEPLOYMENT.md) — **Windows / Ubuntu / 局域网部署**
- [docs/PRD.md](uams/docs/PRD.md) — 产品需求
- [docs/ARCHITECTURE.md](uams/docs/ARCHITECTURE.md) — 系统架构
- [docs/DATABASE.md](uams/docs/DATABASE.md) — 数据库设计
- [docs/API.md](uams/docs/API.md) — 后端 API
- [docs/DEVELOPMENT.md](uams/docs/DEVELOPMENT.md) — 开发规范
- [docs/STARTUP.md](uams/docs/STARTUP.md) — 一键快速开始
- [docs/ROADMAP.md](uams/docs/ROADMAP.md) — 版本规划

---

**项目规范与开发约定**：以 [CLAUDE.md](uams/CLAUDE.md) 为准。
