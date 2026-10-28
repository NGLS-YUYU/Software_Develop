# UAMS 启动与环境切换说明

> 适用版本：UAMS V3.1（main）
> 启动入口：项目根目录 `./start.sh`

---

## 1. 快速开始

```bash
cd /home/nglsyuyu/Software_Develop/Software_Develop/uams
./start.sh
```

出现运行环境菜单：

```text
============================================
        UAMS V3.1 启动管理器
============================================

请选择运行环境：

  [1] 正式环境（Production）
      Nginx + FastAPI + uams

  [2] 测试环境（Testing）
      Vite + FastAPI + uams_test

  [3] 恢复验证环境（Restore）
      Vite + FastAPI + uams_restore_20261027

  [0] 退出

============================================
请输入选项：
```

选择后启动器会自动：

1. 检查后端虚拟环境、前端依赖与配置文件；
2. 检查是否已有 UAMS 在运行、端口是否被占用；
3. 用真实 MySQL 连接执行 `SELECT DATABASE()`；
4. 校验数据库名与所选环境一致；
5. 校验数据库 Alembic 版本与项目 head 一致；
6. 启动后端和前端；
7. 显示数据库、版本、本机/局域网地址。

**启动器不会修改 `backend/.env`，不会执行 Alembic 迁移，不会 seed、清库或导入数据。**

---

## 2. 运行环境与数据库绑定

| 选项 | 运行模式 | 数据库 | 启动方式 | `APP_ENV` |
|---|---|---|---|---|
| 1 | production | `uams` | Nginx + systemd | `production` |
| 2 | testing | `uams_test` | Vite + uvicorn | `testing` |
| 3 | restore | `uams_restore_20261027` | Vite + uvicorn | `restore` |

正式环境要求本机已安装 Nginx 与 `uams-backend.service`；未安装时启动器会拒绝启动并提示安装命令。
本地开发/临时演示可用 `./start.sh start`（Vite + uvicorn + `uams`）。

> 当前服务器（2026-10-29）Nginx 已安装并运行，但 UAMS 站点/systemd 服务尚未安装，且 80 由默认站点占用；
> 正式模式会拒绝启动。安装需 sudo，步骤见 [../deploy/README.md](../deploy/README.md)。

绑定关系写在 `backend/scripts/env_guard.py` 的 `MODE_DATABASES` 中，启动前会用实际连接核对：

- 实际库名与模式不符 → 拒绝启动；
- 数据库版本与项目 head 不一致 → 拒绝启动；
- 连接失败 / 配置缺失 → 拒绝启动；
- 不会静默回退到 `uams`。

---

## 3. 非交互启动

```bash
./start.sh --env production   # 正式环境（Nginx + systemd，不做 Vite 启动）
./start.sh --env testing      # 测试环境（Vite，前台）
./start.sh --env restore      # 恢复环境（Vite，前台）
```

`testing` / `restore` 执行与菜单模式相同的安全检查，并在前台运行：

- `Ctrl+C` 停止本次启动的后端和前端；
- 任一端异常退出时，启动器会停止另一端，避免残留进程。

参数只接受 `production`、`testing`、`restore`；其他值直接拒绝。

---

## 4. 兼容原有命令

```bash
./start.sh start            # 本地开发/临时模式：Vite + uvicorn + uams（后台）
./start.sh start prod       # 正式环境（Nginx + systemd 检查）
./start.sh prod             # 正式环境（Nginx + systemd 检查）
./start.sh restart          # 重启本地开发/临时服务；systemd 服务请用 sudo systemctl restart
./start.sh stop             # 停止本脚本启动的本地开发服务
./start.sh status           # 查看模式、实际数据库、版本、Nginx/systemd 状态
./start.sh --help           # 帮助
```

> 无参数运行 `./start.sh` 进入交互菜单；正式环境不再由 Vite 5173 提供。
> 正式部署安装、切换与回滚见 [../deploy/README.md](../deploy/README.md)。

---

## 5. 查看当前实际连接的数据库

推荐：

```bash
./start.sh status
```

输出示例：

```text
记录运行环境：正式环境（Production）（uams）
mode=production db=uams current=e4f5a6b7c8d9 head=e4f5a6b7c8d9 match=1
健康检查
{"status":"ok","app":"UAMS","env":"production","database":"up"}
```

也可以单独运行守卫（只读，不输出连接串/密码）：

```bash
cd backend
.venv/bin/python scripts/env_guard.py check production
.venv/bin/python scripts/env_guard.py check testing
.venv/bin/python scripts/env_guard.py check restore
```

---

## 6. 停止服务

| 启动方式 | 停止方式 |
|---|---|---|
| 正式环境（Nginx + systemd） | `sudo systemctl stop uams-backend`；Nginx 视是否需要保留其他站点 |
| `./start.sh` / `--env testing|restore`（前台） | `Ctrl+C` |
| `./start.sh start`（后台本地开发） | `./start.sh stop` |

`stop` 只停止：

1. `.run/backend.pid`、`.run/frontend.pid` 记录且命令行匹配 UAMS 的进程；
2. 工作目录属于本项目、命令含 `uvicorn app.main:app` 或 `vite` 的残留进程（用于清理旧版 npx 子进程）。

不会按端口盲目杀进程；来源不明的进程只会提示，不会终止。

---

## 7. 常见失败原因

| 提示 | 原因 | 处理 |
|---|---|---|
| 未找到数据库配置文件 | `backend/.env` 缺失，或 `UAMS_ENV_FILE` 指向不存在文件 | 复制 `backend/.env.example` 为 `backend/.env` 并填写真实连接 |
| 数据库连接失败 | MySQL 未启动、账号/密码错误、主机端口错误 | 检查 MySQL 与 `.env`；启动器不会回退其他库 |
| 数据库版本不匹配 | 目标库未升级到项目 head | **先单独申请并执行迁移**，启动器不会自动迁移 |
| 数据库身份不符 | 环境映射与实际连接库不一致 | 检查 `.env` 与模式；禁止绕过 |
| 检测到 UAMS 已在运行 | `.run/*.pid` 指向存活进程 | 先 `./start.sh stop` |
| 端口 8000 / 5173 已被占用 | 其他程序占用 | 正式环境检查 80/8000；开发/测试检查 8000/5173；停止占用程序或使用 `UAMS_*_PORT` 覆盖 |
| 正式环境提示 Nginx 未安装 | 系统级依赖缺失 | 按 deploy/README.md 使用 sudo 安装 |
| 正式环境提示 systemd 服务未安装 | 未部署 `uams-backend.service` | 按 deploy/README.md 安装并 `daemon-reload` |
| 无效选项 / 无效的 --env 参数 | 输入不在允许范围 | 重新运行并选择 1/2/3 或使用允许的模式名 |

日志：

- **正式环境**：`journalctl -u uams-backend -f`；Nginx 日志在 `/var/log/nginx/`。
- **前台模式**（`./start.sh --env testing|restore`）：终端实时显示后端/前端输出，并带前缀：
  - `[Backend]`：Uvicorn 启动、HTTP 请求、FastAPI 异常、SQLAlchemy 错误；
  - `[Frontend]`：Vite 启动、编译错误、代理输出。
  同一份内容同时追加到日志文件，便于事后排查。
- **后台模式**（`./start.sh start`）：终端不输出，日志写入文件：
  - `uams/logs/backend.log`
  - `uams/logs/frontend.log`
  - `uams/logs/frontend-build.log`（生产前端构建）

日志超过 20MB 时会在下次启动自动轮转为 `*.log.1`。

---

## 8. 数据库版本不匹配时的处理

启动器**不会**自动执行 `alembic upgrade head`。处理流程：

1. 先确认目标库（正式/测试/恢复）与当前版本；
2. 单独提交迁移申请并获得明确批准；
3. 使用对应数据库连接执行迁移（注意不要误连正式库）；
4. 迁移完成后重新运行 `./start.sh`。

当前状态（2026-10-28）：

| 数据库 | 版本 |
|---|---|
| `uams` | `e4f5a6b7c8d9`（head） |
| `uams_test` | `e4f5a6b7c8d9`（head） |
| `uams_restore_20261027` | `b1c2d3e4f5a6`（低于 head，启动器会拒绝启动） |

如需使用恢复验证环境，必须先单独申请迁移该库。

---

## 9. 可覆盖的环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `UAMS_BACKEND_HOST` | `0.0.0.0` | 后端监听地址 |
| `UAMS_BACKEND_PORT` | `8000` | 后端端口 |
| `UAMS_FRONTEND_HOST` | `0.0.0.0` | 前端监听地址 |
| `UAMS_FRONTEND_PORT` | `5173` | 仅开发/测试 Vite 端口 |
| `UAMS_BACKEND_URL` | `http://127.0.0.1:8000` | Vite `/api` 代理目标 |
| `UAMS_ENV_FILE` | `backend/.env` | 仅供测试/排障指定配置文件，不改变数据库密码 |

启动器不读取、也不打印数据库密码；连接串只在子进程环境变量中传递。

---

## 10. 安全约定

- 不修改 `backend/.env`；
- 不把数据库密码写入脚本或 Git；
- 不把连接串打印到终端；
- 不自动迁移、不自动 seed、不清空数据库；
- 测试仍由 `backend/tests/conftest.py` 强制连接 `uams_test`；
- `.env`、`.run/`、`logs/`、备份目录均不提交 Git。
