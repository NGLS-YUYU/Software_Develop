# UAMS V3.1 交互式启动环境管理器报告

> 执行日期：2026-10-28
> 分支：`main`
> 基线：PROD-001 报告提交 `8ffc33e`
> 报告提交：见 `main` 最新 Git 记录
> 数据库迁移：**未执行**

---

## 0. 结论

1. 已实现统一入口 `./start.sh`：无参数进入交互菜单，选择正式/测试/恢复环境。
2. 支持 `--env production|testing|restore` 非交互启动，执行相同的安全检查。
3. 保留原有 `start` / `prod` / `stop` / `restart` / `status` 命令。
4. 不修改 `backend/.env`；使用 SQLAlchemy URL 解析后只替换数据库名，保留驱动、主机、端口、账号、密码和查询参数。
5. 启动前用真实 MySQL 连接执行 `SELECT DATABASE()`，并核对 `alembic_version` 与项目 head。
6. 环境与数据库不符、版本不符、连接失败、配置缺失、端口占用、重复启动均拒绝启动。
7. 前台模式支持 `Ctrl+C` 清理本次启动的前后端进程，未留下残留。
8. 正式环境 `uams` 与测试环境 `uams_test` 均已实际启动验证；恢复环境因版本落后被正确拒绝。
9. 已清理 Git 跟踪文件中的历史明文演示数据库密码（未修改真实数据库密码）。
10. 正式环境当前已在后台运行，系统可继续使用。

---

## 1. 修改文件清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `uams/start.sh` | 重写/扩展 | 交互菜单、`--env` 非交互、环境守卫调用、端口/重复启动检查、信号处理、孤儿进程清理；保留旧命令 |
| `uams/backend/scripts/env_guard.py` | 新增 | 读取 `.env`、URL 解析与数据库名替换、真实连接校验、Alembic 版本校验、`check`/`exec` 子命令 |
| `uams/backend/tests/test_env_guard.py` | 新增 | 8 项单元测试：模式映射、URL 重建、未知模式、配置缺失、身份不符、版本不符 |
| `uams/backend/app/core/config.py` | 安全修改 | 内置默认 `DATABASE_URL` 密码从明文改为 `CHANGE_ME` 占位符 |
| `uams/docs/V0.2_AUDIT.md` | 安全修改 | 历史明文演示密码脱敏为 `CHANGE_ME` |
| `uams/docs/fixes/FIX-007-REPORT.md` | 安全修改 | 同上（2 处） |
| `uams/docs/UAMS_启动与环境切换说明.md` | 新增 | 用户使用说明 |
| `uams/docs/UAMS_V3.1_STARTUP_MANAGER_REPORT.md` | 新增 | 本报告 |

未修改：`backend/.env`、数据库结构、正式业务数据、JWT 密钥、数据库账号权限。

---

## 2. 设计要点

### 2.1 环境映射

| 模式 | 数据库 |
|---|---|
| `production` | `uams` |
| `testing` | `uams_test` |
| `restore` | `uams_restore_20261027` |

映射集中在 `env_guard.py::MODE_DATABASES`，前后端启动均经过同一守卫。

### 2.2 不修改 `.env`

启动器从 `backend/.env` **只读**解析基础连接，使用 SQLAlchemy `make_url()` 与 `URL.set(database=...)`：

- 只替换数据库名；
- 驱动、用户名、密码、主机、端口、`charset` 等查询参数保持不变；
- 特殊字符密码由 SQLAlchemy 重新编码，不做字符串切割；
- 连接串只在子进程环境变量中传递，不打印到终端。

### 2.3 双重校验

1. `check`：`SELECT DATABASE()` 必须等于模式映射库名；
2. 查询 `alembic_version`，必须等于项目唯一 head；
3. `exec`：启动后端前再次执行同样校验，通过后才把 `DATABASE_URL` / `APP_ENV` 放入子进程并 `exec`。

即使外部环境变量被误设置，启动器也不会使用它作为基础连接；配置文件缺失时直接报错，不回退内置默认值。

### 2.4 进程管理

- 前台模式：捕获 `SIGINT`/`SIGTERM`，先 TERM，8 秒后必要时 KILL，且只针对本次启动的 PID；
- 任一子进程退出时停止另一个，避免只留下一半服务；
- 后台模式保留 `nohup` 行为；
- `stop` 仅停止 PID 文件记录且命令行匹配的进程；额外清理“工作目录属于本项目 + 命令含 uvicorn/vite”的旧版残留；
- 不按端口盲目杀进程，不终止来源不明进程。

---

## 3. 三种环境验证结果

### 3.1 正式环境（production）

```text
mode=production db=uams current=e4f5a6b7c8d9 head=e4f5a6b7c8d9 match=1
```

- 已用 `./start.sh start` 实际启动；
- 健康检查：`{"status":"ok","app":"UAMS","env":"production","database":"up"}`；
- 后端进程环境：`DATABASE_URL=...:3306/uams`、`APP_ENV=production`；
- 管理员登录后 `students total = 4`（正式库数据量），确认未连测试库；
- 局域网前端 200，`/api` 代理正常。

### 3.2 测试环境（testing）

```text
mode=testing db=uams_test current=e4f5a6b7c8d9 head=e4f5a6b7c8d9 match=1
```

- 已用 `./start.sh --env testing` 实际启动；
- 健康检查 `env=testing`；
- 管理员登录后 `students total = 20`，确认连接 `uams_test`；
- 发送 `SIGINT` 后启动器退出码 130，8000/5173 均已释放，无 uvicorn/vite 残留。

### 3.3 恢复环境（restore）

```text
mode=restore db=uams_restore_20261027 current=b1c2d3e4f5a6 head=e4f5a6b7c8d9 match=0
```

- 版本落后 head，启动器按设计拒绝启动（退出码 3）；
- 未自动迁移、未修改恢复库；
- 如需使用，必须先单独申请迁移 `uams_restore_20261027`。

---

## 4. 安全检查结果

| 测试 | 结果 |
|---|---|
| 菜单未知选项 `9` | 拒绝，退出码 1 |
| 非交互非法参数 `--env staging` | 拒绝，退出码 1 |
| 正式库身份校验 | `uams`，通过 |
| 测试库身份校验 | `uams_test`，通过 |
| 恢复库版本不一致 | 拒绝，退出码 3 |
| 配置文件缺失（`UAMS_ENV_FILE` 指向不存在文件） | 拒绝，退出码 1，无回退 |
| 数据库连接失败（错误端口） | 拒绝，退出码 4 |
| 环境与库名不一致 | 单元测试覆盖，退出码 5 |
| 端口 8000 被其他程序占用 | 拒绝启动；占用进程仍存活（未被杀死） |
| 已在运行时重复启动 | 拒绝，提示先 `./start.sh stop` |
| `Ctrl+C` 前台停止 | 退出码 130；端口释放；无残留进程 |
| URL 只改库名 | 单元测试覆盖：驱动/账号/密码/主机/端口/查询参数全部保持 |
| Git 跟踪文件明文密码扫描 | 0 命中（数据库密码、JWT） |

---

## 5. 自动化与构建

| 检查 | 结果 |
|---|---|
| 后端 `python -m compileall app scripts tests` | 通过 |
| 后端 `pytest -q` | **38 通过，0 失败**（原 30 + 新增 8） |
| 前端 `npm run build`（含 vue-tsc） | 通过 |
| `bash -n start.sh` | 通过 |
| `./start.sh --help` / `status` | 正常 |
| 正式库只读验收 | 健康检查、管理员登录、学生数量核对通过 |

新增测试不连接正式库；数据库相关测试仍由 `tests/conftest.py` 强制 `uams_test`。

---

## 6. 使用方式

```bash
cd /home/nglsyuyu/Software_Develop/Software_Develop/uams

./start.sh                     # 交互菜单（前台，Ctrl+C 停止）
./start.sh --env production    # 正式环境
./start.sh --env testing       # 测试环境
./start.sh --env restore       # 恢复环境（当前会因版本落后被拒绝）
./start.sh start               # 后台启动正式环境（兼容旧用法）
./start.sh stop                # 停止
./start.sh status              # 查看环境、实际数据库、版本、健康状态
```

详细说明见 `docs/UAMS_启动与环境切换说明.md`。

---

## 7. 未验证项目与剩余风险

| 项目 | 说明 |
|---|---|
| 恢复环境实际启动 | 恢复库版本 `b1c2d3e4f5a6` 落后 head，按设计拒绝；未迁移 |
| 数据库连接密码错误场景 | 仅验证错误端口/连接拒绝；未使用错误密码测试，避免触发账号锁定策略 |
| 多用户同时执行启动器 | 通过 PID 文件与端口检查降低风险，但未做并发启动压测 |
| 生产模式前端（vite preview） | 旧 `prod` 分支保留并复用启动逻辑，本次未实际构建预览验收 |
| 系统级进程守护 | 未接入 systemd；当前后台启动仍依赖 `nohup` |
| 恢复库后续迁移 | 必须单独申请；启动器不会自动执行 |

其他风险：

- `uams_restore_20261027` 版本落后，不能直接用于演示；
- 前端日志曾达到 133MB，已加入 20MB 自动轮转，但历史 `.log.1` 仍占用磁盘；
- 生产环境当前以本机后台进程运行，不是 systemd 托管；机器重启后需重新执行 `./start.sh start`。

---

## 8. Git 与交付

| 项目 | 结果 |
|---|---|
| 分支 | `main` |
| 新建分支/worktree/PR | 否 |
| 强制推送/硬重置 | 否 |
| 提交内容 | 启动器、环境守卫、单元测试、文档、安全脱敏 |
| 未提交 | `.env`、密码、JWT、备份、日志、`.run/` |
| 推送 | 已推送 `origin/main`（详见最终 Git 记录） |

---

## 9. 最终结论

**用户只需执行 `./start.sh`，选择运行环境，即可完成安全检查并启动 UAMS；无需再手动修改 `.env`。**

**正式环境（`uams`）已完成实际启动验证并保持运行，可继续用于演示。**

> 报告结束。
> 本报告不包含数据库密码、JWT、连接串或敏感个人数据。
