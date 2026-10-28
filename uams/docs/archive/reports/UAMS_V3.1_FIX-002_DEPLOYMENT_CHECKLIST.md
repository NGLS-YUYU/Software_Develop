# UAMS V3.1 FIX-002 正式部署前检查与迁移准备清单

> 检查日期：2026-10-26
> 检查基线：`main` 分支，提交 `f93d04e`（FIX-002 报告提交）
> 目标迁移：`b1c2d3e4f5a6`（`add course_selections.source`）
> 当前正式库版本：`a5b7c9d1e2f3`
> **执行状态：未执行任何正式库迁移、写入或新版本后端启动。**
> **批准门：本清单完成后必须等待明确批准，才能执行正式迁移。**

---

## 0. 结论与批准门

### 0.1 当前结论

1. `main` 工作区干净，`main == origin/main == f93d04e`。
2. 正式库 `uams` 当前 Alembic 版本为 `a5b7c9d1e2f3`，**尚无** `course_selections.source` 列。
3. 新迁移 `b1c2d3e4f5a6` 的 `down_revision` 正确指向 `a5b7c9d1e2f3`；迁移只新增可空列 + CHECK 约束，不回填历史数据。
4. 正式库当前 5 条选课记录全部为 `SELECTED`；迁移后这些行的 `source` 将为 `NULL`，新代码会显示“历史记录（未标记来源）”，不会虚构来源。
5. 当前未发现旧后端进程、8000/5173 端口监听、UAMS systemd 服务或用户 crontab；系统级 systemd timers 与 UAMS 无关。
6. 正式库 30 张表、约 198 行、数据约 1.72 MB；磁盘可用约 145 GB；MySQL/mysqldump 8.4.11 可用。
7. 当前应用账号 `uams_app` 对 `uams.*` 有 `ALL PRIVILEGES`，可执行迁移/备份；但**没有全局 `PROCESS` 权限**，因此无法自行确认全部活动连接/事务，也无法自行创建恢复验证数据库，需要 DBA 协助。
8. 备份工具已做只读试跑：完整 `mysqldump` 到 `/dev/null` 成功；必须使用 `--no-tablespaces`，否则会因缺少 `PROCESS` 权限出现 tablespace 读取警告。
9. 旧版本（FIX-002 之前，`3e12447`）的模型不包含 `source` 字段；迁移后旧代码仍可忽略新列并读写（新列可空），可作为迁移后新后端失败时的临时回退版本，但不具备 FIX-002 新功能。
10. **新版本后端不能在本迁移之前连接正式库**：新模型会查询 `course_selections.source`，正式库缺列会报错。

### 0.2 Go / No-Go

| 条件 | 当前状态 | 是否满足 |
|---|---|---|
| 分支为 main 且工作区干净 | `f93d04e`，干净 | 是 |
| 正式库版本与迁移 down_revision 匹配 | `a5b7c9d1e2f3` | 是 |
| 迁移为可空、无回填、单 head | 是 | 是 |
| 旧后端已停止 | 是（未发现进程/端口） | 是 |
| 计划任务/外部写入已停止 | 用户 crontab 无、UAMS systemd 无；外部写入需 DBA 确认 | 部分（需 DBA 确认） |
| 正式库备份可执行 | 工具/权限试跑通过；备份目录权限需 DBA/管理员准备 | 部分 |
| 活动事务/连接可确认 | 应用账号缺 PROCESS，需 DBA | 待 DBA |
| 恢复验证数据库可创建 | 应用账号无 CREATE DATABASE，需 DBA | 待 DBA |
| 浏览器三角色验收 | 未执行，需在隔离环境准备 | 待执行 |
| **正式迁移批准** | **未批准** | **否** |

**结论：当前不具备直接执行正式迁移的最终条件；应先完成 DBA 配合、备份目录/恢复库准备和批准。**

---

## 1. 正式环境检查结果

### 1.1 Git 状态

| 项 | 结果 |
|---|---|
| 当前分支 | `main` |
| 工作区 | 干净 |
| `main` | `f93d04eb9eec27697e5f5917691537be9c3c5127` |
| `origin/main` | 同 `main` |
| 新建分支/worktree/PR | 未创建 |
| 本阶段计划提交 | 仅本文档 |

### 1.2 正式库版本与迁移链

| 项 | 结果 |
|---|---|
| 正式库 | `uams` |
| 当前版本 | `a5b7c9d1e2f3` |
| `alembic_version` 行数 | 1 |
| 新迁移 head | `b1c2d3e4f5a6` |
| 新迁移 down_revision | `a5b7c9d1e2f3`（正确） |
| 迁移链 | `a5b7c9d1e2f3 → b1c2d3e4f5a6 (head)` |
| 多 head | 无 |

### 1.3 迁移文件与约束

迁移文件：`backend/alembic/versions/20261026_1200_b1c2d3e4f5a6_add_selection_source.py`

| 项 | 内容 |
|---|---|
| 列 | `course_selections.source VARCHAR(20) NULL` |
| 默认值 | 无；历史行保持 `NULL` |
| CHECK | `ck_selection_source`：`source IS NULL OR source IN ('STUDENT','ADMIN_REQUIRED','ADMIN_MANUAL')` |
| 数据回填 | 无 |
| downgrade | 删除 CHECK 与列 |

正式库当前只存在 `ck_selection_status`；`uams_test` 已执行迁移，存在 `ck_selection_source`，可作为迁移成功样例。

### 1.4 历史数据兼容性

| 项 | 结果 |
|---|---|
| 正式库 `course_selections` 行数 | 5 |
| 正式库选课状态 | 全部 `SELECTED` |
| 正式库 `source` 列 | 不存在 |
| 迁移后预期 | 5 行 `source = NULL` |
| 新代码对 NULL 的处理 | `selection_source_label(None)` → “历史记录（未标记来源）” |
| 是否自动推断来源 | 否 |
| 是否修改历史业务行 | 否（只新增列） |

### 1.5 运行服务与写入任务

| 检查项 | 结果 |
|---|---|
| 后端进程（uvicorn/gunicorn/fastapi） | 未发现 |
| 8000 端口 | 无监听 |
| 5173 前端端口 | 无监听 |
| UAMS systemd service | 未发现 |
| 用户 crontab | 无 |
| systemd timers | 仅系统级 sysstat/fwupd/logrotate/apt 等，无 UAMS 任务 |
| 外部写入/定时导入 | 当前账号无法确认；需 DBA 用 `SHOW FULL PROCESSLIST` / `INNODB_TRX` 确认 |

### 1.6 容量、工具与权限

| 项 | 结果 |
|---|---|
| MySQL 版本 | 8.4.11 |
| 数据目录 | `/var/lib/mysql/` |
| 数据库大小 | 约 1.72 MB（30 表，约 198 行） |
| 磁盘可用 | 约 145 GB（根分区 23% 使用） |
| `mysql` 客户端 | 8.4.11 |
| `mysqldump` | 8.4.11 |
| 表引擎/字符集 | 30 表全部 InnoDB / utf8mb4 |
| routines/events/triggers | 0 / 0 / 0 |
| binlog | 开启，ROW，GTID OFF |
| 应用账号权限 | `ALL PRIVILEGES ON uams.*`、`ALL PRIVILEGES ON uams_test.*`；无全局 PROCESS |
| 备份试跑 | 完整 `mysqldump --no-tablespaces` 到 `/dev/null` 成功（exit 0，无 stderr） |
| 备份目录 | `/var/backups` 存在但当前用户不可写；`/home/nglsyuyu` 可写 |
| 恢复验证建库权限 | 应用账号无 `CREATE DATABASE`，需 DBA |

### 1.7 旧版/新版兼容性

| 版本 | 迁移前（a5b7） | 迁移后（b1c2） |
|---|---|---|
| 旧后端（`3e12447`，FIX-002 前） | 可运行 | 可运行；旧模型不含 `source`，新列可空，旧写入不提供 source → NULL |
| 新后端（`3230dcc`，FIX-002） | **不可运行**（缺 `source` 列） | 可运行 |
| 旧前端 | 可用（没有安排学生入口） | 可用；新字段不会破坏旧 API 消费方 |
| 新前端（FIX-002） | **禁止连接旧后端**：旧后端不识别 `preview`，预览可能直接执行写入 | 可用（必须配套新后端） |

> **严禁混用前后端版本**：FIX-002 前端的「预览安排」依赖 `preview=true`；旧后端会忽略该参数并直接执行安排，可能误写数据。新前端必须与新后端一起发布。

**结论**：迁移后旧后端仍具备 schema 兼容性，可作为新后端故障时的临时回退；但旧后端没有 FIX-002 功能，且会继续产生 `source=NULL` 的安排记录。不能把“旧后端可运行”当作功能回滚。

### 1.8 正式数据保护状态

| 数据 | 状态 |
|---|---|
| `users` / `students` / `teachers` | 8 / 4 / 3，未修改 |
| `course_selections` | 5，未修改 |
| `operation_logs` | 22，未新增/删除 |
| `CS103` 零选课教学班 | 0 人，未自动补排 |
| `PUB101` 无教学班 | 未自动创建 |
| 2 名零选课学生 | 未自动安排 |

---

## 2. 备份与恢复方案

> 本阶段**未执行实际备份**；仅验证了工具/权限，并准备命令。执行备份属于待批准操作。

### 2.1 备份目标

- 保留：30 张表、全部数据、索引、约束、触发器/事件/例程（当前均为 0）、`alembic_version`；
- 备份文件带时间戳，放在**仓库外**；
- 备份目录权限 700，文件权限 600；
- 至少保留一份异地/另一磁盘副本；
- 备份过程只读，不清空、不删除、不修改正式数据。

### 2.2 推荐备份目录

| 方案 | 说明 |
|---|---|
| `/var/backups/uams/` | 由 DBA 创建，`root:root 700`；当前用户 `/var/backups` 不可写 |
| `/home/nglsyuyu/uams_backups/` | 用户可写；必须 `chmod 700`，且不在 Git 仓库内 |

### 2.3 备份命令（待批准后执行）

凭据不要写入命令行历史；使用 DBA 创建的 `/etc/uams/backup.cnf`（`[client]`，权限 600），或交互式输入。

```bash
set -euo pipefail
umask 077

TS=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/var/backups/uams
BACKUP_FILE="$BACKUP_DIR/uams_${TS}.sql.gz"

# 先记录基线
mysql --defaults-extra-file=/etc/uams/backup.cnf \
  -e "SELECT version_num FROM alembic_version; SELECT COUNT(*) AS selections FROM course_selections;" \
  uams > "$BACKUP_DIR/uams_${TS}_baseline.txt"

# 完整逻辑备份（InnoDB 一致性快照；--no-tablespaces 避免 PROCESS 权限问题）
mysqldump \
  --defaults-extra-file=/etc/uams/backup.cnf \
  --single-transaction --quick --no-tablespaces \
  --routines --events --triggers --skip-comments \
  --default-character-set=utf8mb4 --set-gtid-purged=OFF \
  uams \
  | gzip -9 > "$BACKUP_FILE"

gzip -t "$BACKUP_FILE"
sha256sum "$BACKUP_FILE" > "$BACKUP_FILE.sha256"
sha256sum -c "$BACKUP_FILE.sha256"
ls -lh "$BACKUP_FILE"
```

说明：

- **不要加 `--databases`**：该选项会在 dump 中写入 `CREATE DATABASE uams` / `USE uams`，恢复到 `uams_restore_*` 时会被 `USE uams` 拉回正式库，存在误写风险。单库 dump 直接写库名即可。
- `--single-transaction`：InnoDB 一致性快照；期间不要执行 DDL。
- `--no-tablespaces`：当前备份账号无 PROCESS 权限，必须加；否则会有 tablespace 读取警告（虽然 exit 0，但不应忽略）。
- `--routines --events --triggers`：当前对象为 0，但保留完整性；若权限不足，需 DBA 账号。
- `--set-gtid-purged=OFF`：当前 GTID OFF；避免 restore 时受 GTID 影响。
- 不要把备份文件提交到 Git，也不要放在项目目录内。

### 2.4 备份验证

```bash
gzip -t "$BACKUP_FILE"
sha256sum -c "$BACKUP_FILE.sha256"
# 检查备份中确实包含 alembic_version 与业务表
zcat "$BACKUP_FILE" | grep -m1 "CREATE TABLE \`alembic_version\`"
zcat "$BACKUP_FILE" | grep -m1 "CREATE TABLE \`course_selections\`"
```

### 2.5 恢复验证（隔离环境，DBA 执行）

应用账号没有 `CREATE DATABASE` 权限，需 DBA 创建恢复库；不要在正式库上直接恢复。

```bash
TS=...   # 备份时间戳
RESTORE_DB="uams_restore_${TS}"

mysql --defaults-extra-file=/etc/uams/backup.cnf \
  -e "CREATE DATABASE \`${RESTORE_DB}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"

gunzip -c "/var/backups/uams/uams_${TS}.sql.gz" \
  | mysql --defaults-extra-file=/etc/uams/backup.cnf "$RESTORE_DB"

# 验证恢复库
mysql --defaults-extra-file=/etc/uams/backup.cnf "$RESTORE_DB" -e "
  SELECT version_num FROM alembic_version;
  SELECT COUNT(*) FROM course_selections;
  SHOW COLUMNS FROM course_selections LIKE 'source';
"
```

预期：

- `version_num = a5b7c9d1e2f3`；
- `course_selections` 行数与正式库一致；
- `SHOW COLUMNS ... source` 为空（恢复的是迁移前备份）。

**迁移预演（推荐）**：在恢复库上执行新迁移，验证真实数据副本：

```bash
cd uams/backend
DATABASE_URL="mysql+pymysql://<restore-user>:<restore-password>@127.0.0.1:3306/${RESTORE_DB}?charset=utf8mb4" \
  .venv/bin/alembic upgrade head
DATABASE_URL="...${RESTORE_DB}..." .venv/bin/alembic current
```

预期：`b1c2d3e4f5a6 (head)`；`source` 列存在；CHECK `ck_selection_source` 存在；5 行 `source IS NULL`；业务行数不变。验证完成后由 DBA 删除恢复库（删除前确认不是正式库）。

### 2.6 MySQL DDL 非事务性风险

- Alembic 环境提示 `Will assume non-transactional DDL`；MySQL DDL 不跟随事务回滚。
- 本迁移包含两个 DDL：`ADD COLUMN` 与 `ADD CHECK CONSTRAINT`。
- 如果第一条成功、第二条失败：列可能已存在，但 `alembic_version` 未推进；此时**不要直接启动新后端**，也不要盲目重复执行迁移。
- 恢复策略：
  1. 首选：从已验证备份恢复（或切到已验证恢复库）；
  2. 次选：由 DBA 在确认无数据风险后手工清理半完成 DDL，再重新评估；
  3. **不允许把 `alembic downgrade` 当作唯一恢复手段**；它本身也是 DDL，也可能失败。
- 迁移前必须完成备份验证，并保留旧版本程序产物（`3e12447`）以便临时回退。

---

## 3. 升级流程（仅制定，未执行）

> 以下所有步骤均待批准后执行；当前阶段不执行任何一步中的生产变更。

### 步骤 1：停止正式后端及相关写入任务

```bash
# 当前已确认无进程；执行时仍需再确认
ps -ef | grep -E "uvicorn|gunicorn|fastapi" | grep -v grep
ss -ltnp | grep -E ":8000|:5173"
# 如使用 systemd/start.sh，按实际方式停止
```

- 确认 8000/5173 无监听；
- 停止任何导入脚本、定时任务、外部调用方；
- 由 DBA 用 `SHOW FULL PROCESSLIST` / `INNODB_TRX` 确认无活跃写入；
- 记录停止时间与操作人。

### 步骤 2：执行并验证正式库备份

- 按第 2 章执行 `mysqldump`；
- 验证 `gzip -t`、`sha256sum -c`；
- 记录备份文件路径、大小、校验和、基线版本/行数；
- 将备份复制到第二份存储（异地/另一磁盘），确认可读。

### 步骤 3：再次确认当前数据库版本

```sql
SELECT version_num FROM alembic_version;          -- 期望 a5b7c9d1e2f3
SHOW COLUMNS FROM course_selections LIKE 'source'; -- 期望空
SELECT COUNT(*) FROM course_selections;            -- 期望 5
```

### 步骤 4：执行迁移

```bash
cd uams/backend
DATABASE_URL="mysql+pymysql://<migration-user>:<password>@127.0.0.1:3306/uams?charset=utf8mb4" \
  .venv/bin/alembic upgrade b1c2d3e4f5a6

DATABASE_URL="..." .venv/bin/alembic current
```

建议使用 DBA/迁移账号；若使用现有 `uams_app`，其 `ALL PRIVILEGES ON uams.*` 足够，但权限偏大。

### 步骤 5：检查字段、约束、历史记录、版本

```sql
SELECT version_num FROM alembic_version;            -- 期望 b1c2d3e4f5a6
SHOW COLUMNS FROM course_selections LIKE 'source';  -- 期望 varchar(20), NULL
SELECT CONSTRAINT_NAME, CHECK_CLAUSE
FROM information_schema.TABLE_CONSTRAINTS tc
JOIN information_schema.CHECK_CONSTRAINTS cc
  ON cc.CONSTRAINT_SCHEMA=tc.CONSTRAINT_SCHEMA AND cc.CONSTRAINT_NAME=tc.CONSTRAINT_NAME
WHERE tc.TABLE_SCHEMA='uams' AND tc.TABLE_NAME='course_selections';  -- 期望 ck_selection_source
SELECT COUNT(*) AS total, SUM(source IS NULL) AS null_source
FROM course_selections;                              -- 期望 5/5
SELECT COUNT(*) FROM users;                          -- 期望 8
SELECT COUNT(*) FROM students;                       -- 期望 4
SELECT COUNT(*) FROM teachers;                       -- 期望 3
SELECT COUNT(*) FROM operation_logs;                 -- 期望 22
```

同时确认：

- `CS103` 仍 0 人、`PUB101` 仍无教学班、2 名学生仍无选课（本阶段不自动补排）；
- `alembic check` 在正式库应无 schema 漂移（模型已包含 source）。

### 步骤 6：启动与新结构匹配的后端

- 仅在步骤 5 全部通过后启动 `3230dcc` 版本后端；
- 启动后检查 `/health`（`status: ok`、`database: up`）；
- 观察启动日志是否有 `Unknown column 'source'` 或 SQL 错误；
- 检查 8000 端口监听。

### 步骤 7：验证管理员、教师、学生相关接口

**正式库只做只读冒烟**（不得用 `CS103`/`PUB101`/2 名零选课学生做写测试）：

- 管理员登录、进入开课排课、查看教学班列表、打开「安排学生」弹窗、做一次**预览**（preview=true，不写库）；
- 教师登录、查看本人教学班名单/课表；
- 学生登录、查看本人课表；
- 检查名单来源为“历史记录（未标记来源）”（迁移后既有 5 条记录）、时间字段；
- 确认无 500、无 SQL 错误。

**完整写验收**放到隔离恢复库（第 2.5 节升级后的副本）执行，不在正式库创建/移除学生。

### 步骤 8：失败时停止并恢复

- 任何步骤失败，立即停止，不启动新后端；
- 按第 4 章判断迁移处于哪个阶段；
- 优先使用备份恢复；不要盲目 `downgrade`。

---

## 4. 失败恢复方案

### 4.1 情况 A：迁移尚未执行或第一条 DDL 前失败

- 版本仍为 `a5b7c9d1e2f3`，无 `source` 列；
- 停止操作，保留日志；旧后端可继续运行；
- 修复原因（权限/连接/磁盘）后重新走备份与迁移流程。

### 4.2 情况 B：列已添加，但 CHECK 约束或版本推进失败

- **不要启动新后端**；不要重复执行 `upgrade`；
- DBA 检查 `SHOW CREATE TABLE course_selections`、`information_schema`、`alembic_version`；
- 首选：从备份恢复（正式库或恢复到新库后切换）；
- 次选：DBA 确认无数据风险后手工删除半完成列/约束，再重新评估；
- 禁止仅依赖 `alembic downgrade`。

### 4.3 情况 C：迁移成功，但新后端启动/功能失败

- 新后端不得继续对外服务；
- 旧后端（`3e12447`）在 schema 上兼容新列（可空、旧模型忽略），可作为临时回退，但无 FIX-002 功能；
- 若旧后端也不可用，使用备份恢复；
- 修复后重新验证；不要在有用户写入的正式库上反复试错。

### 4.4 情况 D：数据异常/不确定

- 停止所有写入；
- 从备份恢复到**新的恢复库**，验证行数/版本/约束；
- 由 DBA 确认后再决定切库/恢复；
- 不要直接 `DROP DATABASE uams`；
- 任何恢复操作前再备份当前状态（即使当前状态异常），保留证据。

### 4.5 回退版本与数据说明

- 旧版本程序：`3e12447`（FIX-002 之前）；
- 旧模型不读取 `source`，迁移后可运行；
- 旧程序创建的新选课记录 `source=NULL`，显示为历史来源；
- 回退不会删除已迁移列；如要彻底回退 schema，必须使用经过验证的备份/恢复，不可把 `downgrade` 当作唯一方案。

---

## 5. 三角色浏览器验收准备（隔离环境优先）

> 目前没有 Playwright/Puppeteer 等浏览器自动化依赖；Chrome 二进制存在。建议在隔离恢复库/`uams_test` 上人工浏览器验证，禁止在正式库写入测试数据。

### 5.1 环境准备

- 使用正式库备份恢复出的隔离库 `uams_restore_<TS>`，并在其上执行 `alembic upgrade head`；
- 或使用已迁移的 `uams_test`；
- 启动后端指向隔离库（不要指向 `uams`）；
- 启动前端或使用构建产物；
- 准备管理员、教师、学生测试账号；测试数据使用专用前缀（如 `UAT002_`），测试后清理；
- **不要使用正式库的 `CS103`、`PUB101` 或 2 名零选课学生做写测试。**

### 5.2 管理员步骤

1. 登录管理员，进入「开课排课 → 教学班」；
2. 选择一个**必修/实践课程**、已分配教师、已排课的教学班；
3. 点击「安排学生」；
4. 「批量安排」选择行政班/专业/学院；
5. 点击「预览安排」，核对：
   - 匹配学生、已安排、将新增、跳过；
   - 剩余容量；
   - 冲突/不符合条件人数；
   - 逐学生原因；
6. 点击「确认安排」，在二次确认框确认；
7. 打开「当前名单」核对学号、姓名、行政班、专业、来源、安排时间；
8. 再执行一次相同范围，确认“已安排”增加、“新增”为 0（幂等）；
9. 测试容量不足、时间冲突、已选同课程、学籍无效等跳过原因；
10. 手动添加一个有效学生，再重复添加（应 409）、添加无效/冲突学生（应 409）；
11. 手动移除该学生；如已有成绩记录，确认移除被拒绝；
12. 打开教学班列表，确认已选人数/剩余容量刷新。

### 5.3 教师步骤

1. 登录授课教师；
2. 进入「我的课程」，选择对应教学班；
3. 打开名单，确认能看到被安排学生；
4. 进入「我的课表」，确认该教学班排课显示正常。

### 5.4 学生步骤

1. 登录被安排的学生；
2. 进入「我的课表」，确认被安排的必修课显示；
3. 确认学生端不需要再次自主选课；
4. 抽查一门选修课，确认原有学生自主选课规则未被破坏。

### 5.5 负向验收

| 场景 | 预期 |
|---|---|
| 教师/学生调用分配接口 | 403 |
| 选修课教学班使用批量预安排 | 409，提示不是必修/实践 |
| 教学班未分配教师/未排课 | 409，提示尚未分配教师/安排上课时间 |
| 学期非 ACTIVE | 409 |
| 容量不足 | 部分新增 + 逐条 `CAPACITY_FULL` |
| 时间冲突 | 跳过并显示 `TIME_CONFLICT` |
| 已选同课程其他班 | 跳过并显示 `SAME_COURSE_OTHER_CLASS` |
| 已移除学生重复预排 | 跳过并显示 `PREVIOUSLY_REMOVED`，不自动恢复 |
| 已有成绩移除 | 409，提示已有成绩记录 |
| 非管理员手动添加/移除 | 403 |

### 5.6 浏览器验收记录

- 记录浏览器版本、操作人、时间、环境（隔离库名）、测试账号（脱敏）、截图（不含敏感信息）；
- 若无法完成浏览器验收，明确标记“未验证”，不得宣称端到端通过。

---

## 6. 风险清单

| ID | 风险 | 等级 | 缓解 |
|---|---|---|---|
| R1 | 新后端在迁移前连接正式库会因缺 `source` 列失败 | 高 | 迁移完成并验证前不启动新后端 |
| R2 | MySQL DDL 非事务，列/约束/版本可能半完成 | 高 | 完整备份 + 恢复库预演 + 失败时恢复，不盲目 downgrade |
| R3 | 应用账号无 PROCESS，无法确认全部活动连接/事务 | 中 | DBA 执行 `SHOW FULL PROCESSLIST`/`INNODB_TRX` |
| R4 | 应用账号无 CREATE DATABASE，无法自行建恢复库 | 中 | DBA 创建 `uams_restore_<TS>` |
| R5 | `/var/backups` 当前用户不可写 | 中 | DBA 建 `/var/backups/uams`（700）或用户目录（700） |
| R6 | 外部写入/定时任务未完全确认 | 中 | 维护窗口 + DBA 连接检查 + 停止调用方 |
| R7 | 历史 `source` 为 NULL，来源无法自动判断 | 低 | 显示“历史记录（未标记来源）”，不虚构 |
| R8 | 旧后端回退后无 FIX-002 功能，且新写入 source 为 NULL | 中 | 仅作为临时回退；修复后重新部署新版本 |
| R9 | 无浏览器自动化，三角色 UI 未实测 | 中 | 隔离环境人工浏览器验收；记录未验证项 |
| R10 | 正式库 CS103/PUB101/2 名零选课学生仍是业务缺口 | 高（业务） | 部署后由教务通过新界面确认，不自动补排 |
| R11 | 备份/恢复未在正式库演练 | 中 | 用正式库备份恢复到 DBA 创建的隔离库，执行迁移预演 |

---

## 7. 待批准操作（本阶段一律未执行）

请逐项确认后再执行：

- [ ] 批准执行正式库迁移 `b1c2d3e4f5a6`。
- [ ] 指定维护窗口，并确认可停止所有后端/写入任务。
- [ ] 提供 DBA/备份账号，具备 `PROCESS`（查看活动事务）、`CREATE DATABASE`（恢复验证库）及备份权限；或授权 DBA 代为执行。
- [ ] 确认备份目录（`/var/backups/uams` 或用户目录）与保留周期、异地副本。
- [ ] 确认正式库没有外部写入方（其他系统/脚本/定时任务）。
- [ ] 确认恢复验证库命名与删除责任人。
- [ ] 批准在隔离恢复库执行迁移预演。
- [ ] 批准浏览器三角色验收环境与测试账号。
- [ ] 确认失败时接受“备份恢复优先、downgrade 不作为唯一手段”的恢复策略。

**在上述批准完成前，不执行迁移、不启动新后端、不写入正式库。**

---

## 8. 本次检查执行/未执行清单

### 已执行（只读）

- Git 状态/分支/远程差异；
- 正式库 Alembic 版本、表结构、行数、约束、容量；
- 迁移文件/down_revision/CHECK 约束阅读；
- 旧/新模型 source 兼容性检查；
- 进程/端口/systemd/crontab 检查；
- 磁盘/工具/账号权限检查；
- `mysqldump --no-data` 与完整 dump 到 `/dev/null` 的只读试跑；
- 现有正式数据保护状态核对。

### 未执行

- 未执行正式库迁移；
- 未执行正式库备份文件写入（仅 dump 到 `/dev/null` 试跑）；
- 未创建恢复库；
- 未启动新后端；
- 未修改正式库数据/结构/配置；
- 未执行浏览器三角色验收；
- 未修改计划任务或系统服务。

---

## 9. Git 与交付

| 项 | 结果 |
|---|---|
| 分支 | `main` |
| 检查基线 | `f93d04e` |
| 本阶段提交 | 仅本清单文档 |
| 是否新建分支/worktree/PR | 否 |
| 是否 force push/reset | 否 |
| 正式库 | 未迁移、未写入、未删除 |

> 本文档提交后立即停止；等待明确批准后再执行正式数据库迁移。

---

> 文档结束。
> 本清单只做准备，不构成迁移执行记录；所有生产变更必须经批准并在备份验证后执行。
