# UAMS 高校教务教学管理系统

面向学生、教师、教务管理员的高校教务系统，覆盖课程、培养方案、教学任务、排课、选课、课表、考试、成绩、评价、公告与统计。

## 快速开始

```bash
cd uams
./start.sh
```

交互菜单可选择：

1. **正式环境** — Nginx + FastAPI + `uams`
2. **测试环境** — Vite + FastAPI + `uams_test`
3. **恢复验证环境** — `uams_restore_20261027`（版本必须匹配 head）

非交互：

```bash
./start.sh --env production
./start.sh --env testing
./start.sh --env restore
./start.sh status
./start.sh stop
```

详见 [docs/UAMS_启动与环境切换说明.md](docs/UAMS_启动与环境切换说明.md)。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.14、FastAPI、SQLAlchemy 2、Alembic、Pydantic v2 |
| 前端 | Vue 3、TypeScript、Vite、Element Plus、Pinia、Vue Router |
| 数据库 | MySQL 8.4 LTS（InnoDB / utf8mb4） |
| 正式部署 | Nginx 静态站点 + `/api` 反向代理 + systemd FastAPI |

## 目录结构

```text
uams/
├── start.sh             统一启动与环境管理器
├── README.md            本文件
├── CLAUDE.md            项目开发规范
├── backend/             FastAPI 后端（app / alembic / tests / scripts）
├── frontend/            Vue 3 前端（src / public / 构建配置）
├── deploy/              Nginx、systemd 与前端发布配置
├── docs/                当前文档 + archive/ 历史报告
├── scripts/             MySQL 环境准备等运维脚本
├── logs/                运行日志（Git 忽略）
├── .run/                PID/FIFO 等运行文件（Git 忽略）
└── backend/uploads/     教学资料持久化目录（Git 忽略）
```

## 数据库

- 正式库：`uams`
- 隔离测试库：`uams_test`
- 恢复验证库：`uams_restore_20261027`
- Alembic head：以 `backend/alembic/versions/` 为准（当前 `e4f5a6b7c8d9`）

连接配置只来自 `backend/.env`（不提交 Git）。启动器只替换数据库名，并通过真实连接校验库名与版本。

## 文档

- [文档入口](docs/README.md)
- [启动说明](docs/STARTUP.md)
- [部署说明](docs/DEPLOYMENT.md)
- [开发规范](docs/DEVELOPMENT.md)
- [架构说明](docs/ARCHITECTURE.md)
- [数据库设计](docs/DATABASE.md)
- [API](docs/API.md)
- [用户操作手册](docs/UAMS_教务管理系统用户操作手册.md)

## 安全

- 不提交 `.env`、数据库密码、JWT 密钥、备份、日志或教学资料；
- 正式后端只监听 `127.0.0.1:8000`，由 Nginx 对外；
- 教学资料通过鉴权 API 下载，不作为 Nginx 公共静态文件暴露；
- 历史明文演示密码已从跟踪文件脱敏。
