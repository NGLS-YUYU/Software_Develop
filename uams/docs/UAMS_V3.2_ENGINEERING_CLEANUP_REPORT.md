# UAMS V3.2 工程清理与 Nginx 正式部署报告

> 执行日期：2026-10-29
> 分支：`main`
> 正式库：`uams`（head `e4f5a6b7c8d9`，未修改结构或业务数据）
> 当前服务：仍为 Vite + uvicorn 临时方式（正式 Nginx 切换尚未执行，原因见 §11）

---

## 0. 结论摘要

1. 已完成工程结构清理：历史报告归档、Vue 模板残留删除、重复上传目录确认并统一、空目录清理。
2. 已准备可执行的 Nginx、systemd 与前端原子发布配置，位于 `deploy/`。
3. `start.sh` 已升级：正式环境使用 Nginx + systemd 检查；测试/恢复环境保留 Vite；旧命令保留并区分语义。
4. 当前服务器 **Nginx 未安装**，且 `sudo -n` 不可用（需要交互式 sudo），因此系统级安装与正式切换**未执行**。
5. 现有 Vite + uvicorn 正式服务保持运行，未在新部署验证前关闭。
6. 前端构建、后端 44 项测试、Shell 语法、systemd unit 校验通过；19 个核心页面浏览器回归通过。
7. Nginx 配置因 Nginx 未安装，尚未执行 `nginx -t`，也未做 Nginx 下的浏览器验收。

---

## 1. 清理的文件及原因

| 文件/目录 | 处理 | 原因 |
|---|---|---|
| `frontend/src/assets/vite.svg` | 删除 | Vite 模板残留，全项目 0 引用 |
| `frontend/src/assets/vue.svg` | 删除 | 同上 |
| `frontend/src/assets/hero.png` | 删除 | 同上 |
| `backend/app/uploads/` | 删除（空目录） | 旧上传路径；无文件、数据库 `teaching_materials=0`；代码实际使用 `backend/uploads/materials` |
| `database/` | 删除（空目录） | 无文件、未被 Git 跟踪、无引用 |
| `docs/fixes/` | `git mv` → `docs/archive/fixes/` | 历史阶段修复记录，保留证据但不再作为当前指南 |
| `docs/UAMS_V3.1_*.md`（13 份） | `git mv` → `docs/archive/` | 历史审计/修复/部署/启动管理器/登录修复报告 |
| `docs/V0.2_*`、`docs/V2.0开发指南.md`、`docs/V2.1_FINAL_BASELINE.md`、`docs/DOCUMENTATION_UPDATE_REPORT.md` | `git mv` → `docs/archive/` | 历史阶段文档 |
| `backend/.pytest_cache`（未跟踪） | 未处理 | Git 已忽略，属于运行缓存 |

> 未删除任何 Alembic 迁移文件，未改写 Git 历史。

---

## 2. 保留的文件及原因

| 文件/目录 | 原因 |
|---|---|
| `docs/PRD.md`、`ARCHITECTURE.md`、`DATABASE.md`、`API.md`、`DEVELOPMENT.md`、`ROADMAP.md`、`TESTING.md`、`STARTUP.md`、`DEPLOYMENT.md` | 当前项目指南，继续使用 |
| `docs/UAMS_教务管理系统用户操作手册.md` | 当前用户操作手册 |
| `docs/UAMS_启动与环境切换说明.md` | 当前启动指南 |
| `docs/PRD.docx` | 原始需求档案 |
| `docs/archive/` | 历史审计与阶段报告，保留可追溯性 |
| `scripts/setup_mysql.sh` | 数据库环境准备脚本，仍有效 |
| `scripts/uninstall_docker.sh` | 一次性运维脚本，保留但不属于日常启动 |
| `backend/alembic/versions/*` | 历史迁移链，禁止删除 |
| `backend/uploads/materials/` | 唯一教学资料持久化目录（当前为空） |
| `frontend/public/favicon.svg`、`icons.svg` | 前端公共静态资源，保留 |
| `frontend/dist/` | 构建产物（Git 忽略），用于发布 |

---

## 3. 调整后的项目结构

```text
uams/
├── README.md                    项目入口
├── start.sh                     交互式启动/环境管理器
├── CLAUDE.md                    项目开发规范
├── backend/
│   ├── app/                     FastAPI 业务代码（api/services/models/schemas/...）
│   ├── alembic/                 数据库迁移（含全部历史版本）
│   ├── scripts/                 seed / 环境守卫 / 启动辅助
│   ├── tests/                   pytest（强制 uams_test）
│   ├── uploads/materials/       教学资料持久化目录（Git 忽略）
│   └── .env                     本机生产配置（Git 忽略）
├── frontend/
│   ├── src/                     Vue 源码（api/router/stores/views/...）
│   ├── public/                  公共静态资源
│   └── dist/                    生产构建产物（Git 忽略）
├── deploy/
│   ├── nginx/uams.conf          Nginx 站点配置
│   ├── systemd/uams-backend.service
│   ├── deploy-frontend.sh       前端原子发布
│   └── README.md                安装/验收/回滚
├── docs/
│   ├── README.md                文档入口
│   ├── *.md                     当前指南
│   └── archive/                 历史报告 + fixes/
├── scripts/                     MySQL 环境准备等运维脚本
├── logs/                        运行日志（Git 忽略）
└── .run/                        PID/FIFO（Git 忽略）
```

设计目标：源码、运行时数据、部署配置、当前文档与历史报告分离。

---

## 4. 重复上传目录处理

检查结果：

- `backend/app/uploads/materials/`：空，无文件；
- `backend/uploads/materials/`：空，无文件；
- 正式库 `teaching_materials`：0 行；
- 代码 `MATERIAL_DIR = backend/uploads/materials`，路径基于 `__file__` 绝对解析，不依赖启动工作目录；
- 下载/删除使用数据库 `file_path`，并做 `resolve().is_relative_to(MATERIAL_DIR)` 校验。

处理：

- 保留 `backend/uploads/materials/` 作为唯一持久化目录；
- 删除空的旧目录 `backend/app/uploads/`；
- 因无实际文件、无数据库记录，**无需迁移文件或修改业务数据**；
- 教学资料仍通过鉴权 API 下载，不进入 Nginx 公共目录。

---

## 5. Nginx 配置与部署路径（已准备，未安装）

| 项目 | 内容 |
|---|---|
| 仓库配置 | `deploy/nginx/uams.conf` |
| 目标路径 | `/etc/nginx/sites-available/uams` → `/etc/nginx/sites-enabled/uams` |
| 静态根 | `/var/www/uams/current`（软链到 `releases/<时间戳>`） |
| 对外端口 | 80（当前 80 空闲） |
| API 代理 | `location ^~ /api/` → `http://127.0.0.1:8000`，`proxy_pass` 末尾无 `/`，保留 `/api/v1/...` |
| SPA | `try_files $uri $uri/ /index.html` |
| 缓存 | `/assets/` 30 天 immutable；`index.html` no-store |
| 上传 | `client_max_body_size 20m`（后端限制 10MB） |
| 安全 | 拒绝点文件；不 alias 项目目录；不暴露 `.env`/`.git`/备份/uploads |

**状态**：Nginx 未安装，未执行 `nginx -t`，未写入 `/etc/nginx`。

---

## 6. systemd 服务（已准备，未安装）

| 项目 | 内容 |
|---|---|
| 仓库配置 | `deploy/systemd/uams-backend.service` |
| 目标路径 | `/etc/systemd/system/uams-backend.service` |
| 用户 | `nglsyuyu` |
| 工作目录 | `.../uams/backend` |
| 监听 | `127.0.0.1:8000`（仅回环） |
| 数据库校验 | `ExecStartPre=... env_guard.py check production`（库名 `uams` + head） |
| 启动 | `env_guard.py exec production -- .venv/bin/python -m uvicorn ...` |
| 重启 | `Restart=on-failure`、`RestartSec=3` |
| 停止 | `SIGINT`，`TimeoutStopSec=30` |
| 日志 | journald：`journalctl -u uams-backend -f` |

管理命令：

```bash
sudo systemctl status uams-backend
sudo systemctl restart uams-backend
journalctl -u uams-backend -f
```

**状态**：未安装、未启动；`systemd-analyze verify` 已检查 unit 文件（仅有其他无关 unit 的可执行位警告）。

---

## 7. 正式/测试环境启动方法

```bash
cd uams

./start.sh                     # 交互菜单
./start.sh --env production    # 正式：Nginx + systemd + uams（需先安装）
./start.sh --env testing       # 测试：Vite + uvicorn + uams_test
./start.sh --env restore       # 恢复：仅当版本等于 head 时允许
./start.sh start               # 本地开发/临时：Vite + uvicorn + uams（后台）
./start.sh status              # 模式、数据库、版本、Nginx/systemd 状态
./start.sh stop                # 停止本地开发服务
```

正式模式当前行为：

- 校验 `backend/.env`、实际库名 `uams`、Alembic head；
- 检查 Nginx、`uams-backend.service`、`/var/www/uams/current`；
- 缺少任一条件时拒绝启动并提示安装命令；
- 不会自动安装、不会自动迁移、不会启动 Vite 冒充正式环境。

---

## 8. 原始部署与新部署的区别

| 项目 | 原始（V3.1） | 目标（V3.2 正式） |
|---|---|---|
| 前端 | Vite dev/preview，5173/4173 | Nginx 80，静态构建 |
| 后端 | `start.sh` nohup 子进程，0.0.0.0:8000 | systemd，127.0.0.1:8000 |
| 对外端口 | 5173/8000 | 80（HTTPS 后续） |
| 进程管理 | PID/FIFO 文件 | systemd + journald |
| 发布 | 覆盖式构建 | `/var/www/uams/releases` 原子软链 |
| 数据库校验 | `start.sh` 环境守卫 | systemd `ExecStartPre` + `exec` 双重校验 |
| 日志 | 文件 + 前台前缀 | journald + Nginx 日志 |

当前实际：新部署配置已准备，但因系统权限未切换；现有服务仍是原始方式。

---

## 9. 测试结果

### 9.1 工程检查

| 检查 | 结果 |
|---|---|
| 前端 `npm run build`（删除模板资源后） | 通过 |
| 后端 `pytest -q` | **44 通过，0 失败** |
| 后端 `compileall app tests scripts` | 通过 |
| `bash -n start.sh deploy/deploy-frontend.sh` | 通过 |
| `systemd-analyze verify deploy/systemd/uams-backend.service` | 无 unit 错误 |
| `nginx -t` | **未执行**（Nginx 未安装） |

### 9.2 启动管理器

| 场景 | 结果 |
|---|---|
| `./start.sh status` | 正确显示“本地开发/临时模式”、`uams`、head、健康状态 |
| `./start.sh --env testing` | 启动 Vite + uvicorn，实时日志正常，Ctrl+C 后端口释放 |
| `./start.sh --env production`（Nginx 缺失） | 拒绝启动，提示需 sudo 安装 Nginx |
| `./start.sh stop` / `start` | 停止和恢复现有开发服务正常，正式库健康 |

### 9.3 浏览器回归（当前 Vite 临时正式服务）

管理员 9 页、教师 4 页、学生 6 页，共 **19 页全部 OK**：

- 管理员：仪表盘、学生、教师、课程、开课排课、选课、成绩、考试、评价；
- 教师：仪表盘、我的课程、成绩、课表；
- 学生：仪表盘、个人信息、选课、课表、成绩、考试；
- 未出现无权限、加载失败或 1054。

教学资料上传/下载/删除与权限由 `tests/test_v31_fixes.py::test_materials_flow` 在 `uams_test` 覆盖并通过。
Nginx 下的页面刷新、`/api` 代理与登录流程**尚未验证**（等待系统安装）。

### 9.4 数据保护

- 正式库 `uams`：未执行结构变更或业务写入；head `e4f5a6b7c8d9`；
- `uams_test`：仅自动化测试使用，测试清理；
- 正式库健康检查 `database: up`；
- 未在正式库制造错误登录或写入测试记录。

---

## 10. 回滚方法

```bash
# 1) 停用新后端
sudo systemctl stop uams-backend && sudo systemctl disable uams-backend

# 2) 恢复 Nginx 配置（安装前的备份）
sudo rm -f /etc/nginx/sites-enabled/uams
sudo mv /etc/nginx/sites-enabled/default.disabled.<STAMP> /etc/nginx/sites-enabled/default 2>/dev/null || true
# 或整目录恢复：sudo rm -rf /etc/nginx && sudo mv /etc/nginx.backup.<STAMP> /etc/nginx
sudo nginx -t && sudo systemctl reload nginx

# 3) 前端回退到上一个 release
sudo ln -sfn /var/www/uams/releases/<上一个版本> /var/www/uams/current

# 4) 恢复原临时服务
./start.sh start
```

---

## 11. 尚未完成 / 需要人工授权的步骤

当前环境：

```text
sudo -n true → 需要交互式认证
nginx → 未安装
80/443 → 空闲
systemd user instance → running，Linger=no
```

需要用户在终端执行（不会自动提权）：

```bash
sudo apt update && sudo apt install -y nginx rsync
sudo cp deploy/nginx/uams.conf /etc/nginx/sites-available/uams
sudo ln -sfn /etc/nginx/sites-available/uams /etc/nginx/sites-enabled/uams
sudo cp deploy/systemd/uams-backend.service /etc/systemd/system/uams-backend.service
sudo systemctl daemon-reload

# 先停当前开发服务，释放 8000
./start.sh stop

# 部署前端（构建 + 原子发布）
bash deploy/deploy-frontend.sh

# 启动正式后端与 Nginx
sudo systemctl enable --now uams-backend.service
sudo systemctl enable --now nginx
sudo nginx -t && sudo systemctl reload nginx

# 验收
./start.sh --env production
```

安装后需补做：

- `nginx -t` 与 Nginx 下三角色浏览器验收；
- 子路由直接刷新、`/api` 代理、登录/上传下载；
- 记录最终 Nginx/systemd 配置与发布软链；
- 视需要配置 HTTPS。

---

## 12. 剩余风险

1. 正式环境尚未切换到 Nginx；当前仍依赖 Vite 5173 和 nohup 后端，机器重启后需手动 `./start.sh start`。
2. Nginx 配置未经 `nginx -t` 与实际代理验证。
3. 默认站点可能与 `server_name _` 冲突，安装时需按 deploy/README 备份并停用默认站点。
4. 暂无 HTTPS；正式对外应补充证书与 HSTS。
5. 前端日志目录曾累积约 128MB，已启用 20MB 轮转；历史日志可手动归档。
6. 正式数据库备份仍需按 PROD-001 方案定期执行。

---

## 13. Git 与推送

| 项目 | 结果 |
|---|---|
| 分支 | `main` |
| 新建分支/worktree/PR | 否 |
| 强制推送/硬重置 | 否 |
| 提交内容 | 工程清理、文档归档与更新、部署配置、start.sh 升级、本报告 |
| 未提交 | `.env`、密码、JWT、日志、PID、上传资料、备份 |
| 推送 | 见 `main` 最新 Git 记录（已推送 `origin/main`） |

---

## 14. 最终结论

工程清理、文档归档、部署配置与启动器升级已完成；**正式 Nginx + systemd 切换因缺少 sudo 授权尚未执行**，现有系统继续以 Vite + uvicorn 临时方式正常提供，正式库与业务数据未受影响。

完成系统级授权后，按 `deploy/README.md` 执行安装与验收，即可完成正式切换。

> 报告结束。
> 本报告不包含数据库密码、JWT、Token 或敏感个人数据。
