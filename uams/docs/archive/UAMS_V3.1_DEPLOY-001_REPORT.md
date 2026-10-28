# UAMS V3.1 DEPLOY-001 正式数据库备份与隔离恢复验证报告

> 执行日期：2026-10-26
> 分支：`main`（检查前基线 `f93d04e`）
> 目标迁移：`b1c2d3e4f5a6`（`add course_selections.source`）
> 正式库：`uams`，当前 Alembic 版本 `a5b7c9d1e2f3`
> **执行状态：备份已完成并做结构与行数校验；隔离恢复/迁移验证因缺少 `CREATE DATABASE` 权限停止。未执行正式库迁移，未启动新版本后端，未修改正式数据或 `uams_test`。**

---

## 0. 执行摘要

1. 已确认正式库连接目标为 `uams`，当前版本 `a5b7c9d1e2f3`，无 `course_selections.source` 列。
2. 已确认检查时无 UAMS 后端进程、无 8000/5173 端口监听、无 UAMS systemd 服务、无用户 crontab。
3. 已创建**仓库外**完整逻辑备份：
   - `/home/nglsyuyu/uams_backups/uams_20261026_235014.sql.gz`
   - 大小 11,252 字节；SHA256 `dc79dec0046f0e09e0235f000db87d0f83b63e12a32553b7f4cb8e404b850b46`
   - 目录 700、文件 600；未提交到 Git。
4. 备份已通过：
   - `gzip -t`；
   - `sha256sum -c`；
   - 30 张表全部存在；
   - 30 个主键定义；
   - `ck_selection_status` 存在；
   - `course_selections` 5 条记录；
   - `alembic_version = a5b7c9d1e2f3`；
   - 逐表行数与备份前基线一致（合计 218 行）；
   - SQL 中没有 `CREATE DATABASE` / `USE uams`，可安全恢复到独立库。
5. **隔离恢复未执行**：当前 MySQL 账号 `uams_app` 只有 `uams` / `uams_test` 的库级权限，**没有 `CREATE DATABASE` 权限**；按任务要求已停止，未尝试提权，未修改 `uams_test`。
6. 因此以下项目**未执行**：
   - 创建 `uams_restore_YYYYMMDD`；
   - 恢复备份并核对恢复库；
   - 在恢复库执行 `alembic upgrade head`；
   - 新后端/前端三角色验证与浏览器验收。
7. **正式库仍为迁移前状态**：`users=8`、`students=4`、`teachers=3`、`course_selections=5`、`operation_logs=22`；`CS103` 仍 0 人、`PUB101` 仍无教学班、2 名学生仍无选课。

---

## 1. 正式环境检查

### 1.1 Git

| 项 | 结果 |
|---|---|
| 当前分支 | `main` |
| 工作区 | 干净 |
| 检查前 `main` | `f93d04eb9eec27697e5f5917691537be9c3c5127` |
| `origin/main` | 同 `main` |
| 新建分支/worktree/PR | 未创建 |
| 本次计划提交 | 仅本报告 |

### 1.2 数据库目标与版本

| 项 | 结果 |
|---|---|
| 连接目标 | `uams`（通过 `SELECT DATABASE()` 确认） |
| MySQL | 8.4.11 |
| Alembic 版本 | `a5b7c9d1e2f3` |
| `course_selections.source` | 不存在 |
| `course_selections` 行数 | 5（全部 `SELECTED`） |
| 表数量 | 30 |
| 数据量 | 约 1.72 MB、218 行 |
| 可见数据库 | `information_schema`、`performance_schema`、`uams`、`uams_test`；无 `uams_restore_*` |

### 1.3 运行服务与写入风险

| 检查项 | 结果 |
|---|---|
| UAMS 后端进程 | 未发现 |
| 8000 端口 | 无监听 |
| 5173 端口 | 无监听 |
| UAMS systemd service | 未发现 |
| 用户 crontab | 无 |
| 系统级 timers | 仅 sysstat/fwupd/logrotate/apt 等，与 UAMS 无关 |
| 备份前 `Threads_connected` | 1（仅当前检查连接） |
| 备份后 `Threads_connected` | 1 |
| 权威活动会话/事务检查 | 当前账号缺少 `PROCESS` 权限，无法执行 `SHOW FULL PROCESSLIST` / `INNODB_TRX`；需 DBA 复核 |

> 结论：在应用账号可见范围内**未观察到其他客户端连接**，且未发现 UAMS 后端/定时任务；但由于缺少 `PROCESS` 权限，不能宣称已经权威排除所有短时连接或并发 DDL。正式迁移前应由 DBA 再做一次会话/事务复核，并在维护窗口内重新执行一次最终备份。

### 1.4 备份权限、工具与空间

| 项 | 结果 |
|---|---|
| `mysqldump` | 8.4.11，可用 |
| `gzip` / `sha256sum` | 可用 |
| 应用账号权限 | `ALL PRIVILEGES ON uams.*`、`ALL PRIVILEGES ON uams_test.*`；无全局 `PROCESS` / `CREATE DATABASE` |
| 完整 dump 试跑 | 到 `/dev/null` 成功（exit 0，无 stderr） |
| 备份目录 | `/home/nglsyuyu/uams_backups`（仓库外，700） |
| 磁盘可用 | 约 145 GB |
| 数据库大小 | 约 1.72 MB |

---

## 2. 备份结果与校验

### 2.1 备份文件

| 项 | 值 |
|---|---|
| 备份时间戳 | `20261026_235014` |
| 文件 | `/home/nglsyuyu/uams_backups/uams_20261026_235014.sql.gz` |
| 文件大小 | 11,252 字节 |
| SHA256 | `dc79dec0046f0e09e0235f000db87d0f83b63e12a32553b7f4cb8e404b850b46` |
| 目录权限 | `700` |
| 文件权限 | `600` |
| 是否在 Git 仓库内 | 否 |
| 是否提交 Git | 否 |
| 基线 JSON | `/home/nglsyuyu/uams_backups/uams_20261026_235014_baseline.json` |
| 校验 JSON | `/home/nglsyuyu/uams_backups/uams_20261026_235014_verify.json` |

### 2.2 备份命令（实际使用）

使用 `--skip-extended-insert` 以便逐行统计并与基线行数比对；未使用 `--databases`，避免 dump 中出现 `USE uams` 而误恢复到正式库。

```bash
mysqldump \
  --single-transaction --quick --no-tablespaces \
  --routines --events --triggers --skip-comments \
  --skip-extended-insert \
  --default-character-set=utf8mb4 --set-gtid-purged=OFF \
  --host=127.0.0.1 --port=3306 --user=<backup-user> \
  uams \
  | gzip -9 > uams_20261026_235014.sql.gz
```

> 实际执行时凭据通过受保护的客户端配置/环境变量传入，未写入命令历史或本报告。

### 2.3 校验结果

| 校验项 | 结果 |
|---|---|
| `gzip -t` | 通过 |
| `sha256sum -c` | 通过 |
| 表数量（基线/备份） | 30 / 30 |
| 表名集合 | 完全一致，无缺失/多余 |
| `PRIMARY KEY` 定义 | 30 |
| `ck_selection_status` | 存在 |
| `course_selections` 备份行数 | 5 |
| `alembic_version` 备份值 | `a5b7c9d1e2f3`（一致） |
| 逐表行数对比 | 全部一致；合计 218 / 218 |
| `CREATE DATABASE` | 不存在 |
| `USE uams` | 不存在 |
| 备份耗时 | 约 0.08 秒 |

**结论**：备份文件结构完整、可解压、校验和匹配、表集合/行数/Alembic 版本与正式库基线一致，且不含跨库 `USE`/`CREATE DATABASE`。
**限制**：由于缺少 `PROCESS` 权限，不能权威确认备份期间绝对没有其他连接/DDL；建议在正式维护窗口由 DBA 复核后重新执行最终备份。

---

## 3. 隔离恢复测试：已停止

### 3.1 停止原因

```text
当前账号 uams_app 授权：
  ALL PRIVILEGES ON uams.*
  ALL PRIVILEGES ON uams_test.*
没有 CREATE DATABASE 权限。
```

- 按任务要求，未尝试创建数据库，也未尝试提权；
- `SHOW DATABASES` 中不存在 `uams_restore_*`；
- 未覆盖/清空 `uams` 或 `uams_test`；
- 未执行恢复、未在恢复库执行迁移、未启动新后端。

### 3.2 所需最小授权（建议由 DBA 执行）

不授予全局 `CREATE` 也可以完成：由 DBA 创建恢复库，并仅给该库授权。

```sql
CREATE DATABASE uams_restore_20261027
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

GRANT ALL PRIVILEGES ON uams_restore_20261027.*
  TO 'uams_app'@'127.0.0.1';
```

如需让应用账号自行查看全部会话/事务，可临时授予：

```sql
GRANT PROCESS ON *.* TO 'uams_app'@'127.0.0.1';
```

恢复/迁移验证完成后，由 DBA 删除恢复库（或先确认库名不是 `uams`/`uams_test` 再删除）。

### 3.3 待执行的恢复验证步骤（未执行）

1. DBA 创建 `uams_restore_YYYYMMDD`，不要覆盖 `uams` / `uams_test`；
2. 恢复备份：
   ```bash
   gunzip -c /home/nglsyuyu/uams_backups/uams_20261026_235014.sql.gz \
     | mysql --host=127.0.0.1 --user=<restore-user> uams_restore_YYYYMMDD
   ```
3. 核对恢复库：
   - 30 张表、218 行；
   - `alembic_version = a5b7c9d1e2f3`；
   - `course_selections` 5 行，无 `source` 列；
   - 关键约束/索引存在；
4. 仅在恢复库执行：
   ```bash
   cd uams/backend
   DATABASE_URL="mysql+pymysql://.../uams_restore_YYYYMMDD?charset=utf8mb4" \
     .venv/bin/alembic upgrade head
   ```
5. 验证：
   - Alembic 版本 `b1c2d3e4f5a6`；
   - `source` 列存在且可空；
   - `ck_selection_source` 存在；
   - 原有 5 条选课记录仍在，且 `source IS NULL`；
   - 行数/表结构/关键约束无丢失；
6. 在恢复库上验证新后端/前端与历史 NULL 来源兼容性；
7. 完成后由 DBA 删除恢复库，保留验证记录。

**以上步骤本次均未执行。**

---

## 4. 迁移与兼容性验证：未执行

由于恢复库未创建，以下项目未执行：

- `alembic upgrade head` 在恢复库上的执行；
- 迁移耗时与错误记录；
- 新后端连接迁移后数据库的启动验证；
- 选课查询、管理员名单、必修课预览/提交、教师名单、学生课表等 API/浏览器验证；
- 历史来源“历史记录（未标记来源）”的页面显示验证。

代码层兼容性结论（静态）：

- 旧后端 `3e12447` 的模型不含 `source`；迁移后新列可空，旧代码仍可读写，旧写入会产生 `source=NULL`；
- 新后端 `3230dcc` 在迁移前不能连接正式库（缺 `source` 列）；
- 新前端必须与新后端一起发布；旧后端会忽略 `preview` 参数，预览可能直接执行写入，严禁混用。

---

## 5. 浏览器三角色验收：未执行

未执行原因：

- 恢复库未创建；
- 不能在正式库写入测试数据；
- 当前环境无 Playwright/Puppeteer 自动化依赖；
- 未启动新后端。

待恢复库和授权完成后，按 `UAMS_V3.1_FIX-002_DEPLOYMENT_CHECKLIST.md` 第 5 章执行管理员/教师/学生三角色浏览器验收；测试写入仅限隔离恢复库，不使用正式库 `CS103`、`PUB101` 或 2 名零选课学生做写测试。

---

## 6. 风险与阻塞项

| ID | 风险/阻塞 | 等级 | 状态/缓解 |
|---|---|---|---|
| B1 | 当前账号无 `CREATE DATABASE`，无法创建恢复库 | **阻塞** | 需 DBA 创建并由 DBA 授权；不得提权 |
| B2 | 当前账号无 `PROCESS`，无法权威确认活动会话/事务 | **阻塞（正式迁移前）** | DBA 执行 `SHOW FULL PROCESSLIST` / `INNODB_TRX` |
| R1 | 备份期间可能存在的短时连接/DDL未被权威排除 | 中 | 维护窗口由 DBA 复核后重新做最终备份 |
| R2 | MySQL DDL 非事务，迁移可能半完成 | 高 | 恢复库预演 + 备份恢复优先；不以 downgrade 为唯一手段 |
| R3 | 新后端在迁移前连接正式库会失败 | 高 | 迁移完成并验证前不启动新后端 |
| R4 | 新前端连接旧后端可能导致预览直接写入 | 高 | 前后端必须同版本发布 |
| R5 | 恢复验证尚未执行，无法确认真实备份可恢复 | **阻塞** | DBA 建恢复库后执行并记录 |
| R6 | 正式库 CS103/PUB101/2 名零选课学生仍为业务缺口 | 高（业务） | 部署后由教务通过新界面确认，不自动补排 |
| R7 | 浏览器三角色未验证 | 中 | 恢复库 + 新后端上人工验收 |
| R8 | 备份文件未做异地副本 | 中 | 复制到第二存储并校验 |
| R9 | 正式迁移尚未批准 | **阻塞** | 等待明确批准 |

---

## 7. 正式升级前置条件

以下条件全部满足后，才可申请正式迁移：

- [ ] DBA 创建独立恢复库 `uams_restore_YYYYMMDD`（不覆盖 `uams` / `uams_test`）；
- [ ] DBA 授予 `uams_app` 对该恢复库的库级权限（或提供专用恢复账号）；
- [ ] DBA 用 `SHOW FULL PROCESSLIST` / `INNODB_TRX` 确认无活动写入/长事务；
- [ ] 在恢复库成功恢复备份，核对 30 表/218 行/`a5b7c9d1e2f3`；
- [ ] 在恢复库执行 `alembic upgrade head`，验证 `b1c2d3e4f5a6`、`source`、`ck_selection_source`、5 条历史记录 `source=NULL`；
- [ ] 在恢复库完成管理员/教师/学生三接口验证；
- [ ] 完成浏览器三角色验收（管理员安排、教师名单/课表、学生课表、负向场景）；
- [ ] 维护窗口内 DBA 复核无并发 DDL/写入后，重新执行并验证最终备份；
- [ ] 明确批准正式库迁移 `b1c2d3e4f5a6`；
- [ ] 准备回退程序产物（旧版本 `3e12447`）及恢复负责人。

---

## 8. 本次执行/未执行清单

### 已执行（只读/仓库外备份）

- 确认目标数据库为 `uams`；
- 检查版本、表结构、行数、约束、容量；
- 检查后端进程/端口/systemd/crontab；
- 检查账号权限、工具、磁盘；
- 备份前/后观察 `Threads_connected=1`；
- 创建仓库外完整逻辑备份（文件 600、目录 700）；
- gzip/SHA256/表集合/行数/Alembic 版本/SQL 结构校验；
- 确认正式库关键计数未变。

### 未执行

- 未创建 `uams_restore_*`；
- 未恢复备份；
- 未在恢复库执行迁移；
- 未执行正式库迁移；
- 未启动新后端/前端；
- 未修改正式库数据/结构；
- 未修改或清空 `uams_test`；
- 未做浏览器三角色验收；
- 未复制异地备份（建议后续执行）。

---

## 9. Git 与交付

| 项 | 结果 |
|---|---|
| 分支 | `main` |
| 检查前基线 | `f93d04e` |
| 本次提交 | 仅本报告 |
| 是否新建分支/worktree/PR | 否 |
| 是否 force push/reset | 否 |
| 正式库 | 未迁移、未写入、未删除 |
| 备份文件 | 仓库外，未提交 |

---

## 10. 结论

- **备份已完成并通过结构与行数校验**，文件位于仓库外，权限受限，未提交 Git。
- **隔离恢复/迁移验证被 `CREATE DATABASE` 权限阻塞**，按任务要求已停止，未提权、未修改 `uams_test`、未执行正式迁移。
- 正式库仍处于迁移前状态；新后端不能连接正式库；新前端不能与旧后端混用。
- 下一步需要 DBA 创建恢复库并授权，完成恢复、迁移预演和三角色验收后，再申请正式迁移批准。

> 报告结束。
> 本报告不包含数据库密码、连接密钥、个人敏感数据或备份文件内容。
