# UAMS V3.1 DEPLOY-002 解除恢复库阻塞并完成隔离验收报告

> 执行日期：2026-10-27
> 分支：`main`
> 正式库：`uams`，当前 Alembic 版本 `a5b7c9d1e2f3`（**未迁移**）
> 恢复库：`uams_restore_20261027`（隔离库，已迁移至 `b1c2d3e4f5a6`）
> 备份文件：`/home/nglsyuyu/uams_backups/uams_20261026_235014.sql.gz`
> **本阶段未对正式库 `uams` 执行迁移或写入；未修改 `uams_test`；未启动下一项 FIX 任务。**

---

## 0. 执行摘要

1. 用户已在 Ubuntu 终端完成 `uams_restore_20261027` 创建与库级授权；本次只读核验通过：
   - 恢复库存在，字符集 `utf8mb4` / 排序规则 `utf8mb4_0900_ai_ci`；
   - `uams_app@127.0.0.1` 拥有 `uams_restore_20261027.*` 的 `ALL PRIVILEGES`；
   - 正式库 `uams` 仍为 `a5b7c9d1e2f3`、无 `source` 列、数据未变；
   - `uams_test` 未被修改；
   - 备份 SHA256/gzip 校验通过。
2. 已用已校验备份恢复到 `uams_restore_20261027`，恢复耗时约 3.3 秒：
   - 30 张表、218 行、`alembic_version = a5b7c9d1e2f3`；
   - 无 `source` 列；
   - 逐表行数与备份基线完全一致。
3. 仅在恢复库执行 `alembic upgrade head`，耗时约 0.55 秒：
   - 版本 `b1c2d3e4f5a6`；
   - `course_selections.source` 存在且可空；
   - `ck_selection_source` 存在；
   - 原有 5 条选课记录保留，且 `source IS NULL`；
   - 30 表/218 行未丢失；`alembic check` 无漂移。
4. 在隔离环境启动新后端（`127.0.0.1:8000`，`APP_ENV=restore-verification`）和前端（`127.0.0.1:5173`），完成：
   - API 验收 10 项全部通过；
   - 真实浏览器（headless Chrome 155 + CDP，非 Playwright/Puppeteer）三角色 DOM 操作验收；
   - 管理员预览/提交/名单、重复安排、容量、时间冲突、历史来源显示；
   - 教师名单/课表；学生课表；教师/学生越权 403。
5. 发现并纠正一次运行配置事故：
   - 首次启动包装脚本未把 `DATABASE_URL` 传给 `os.execv`，进程实际连到正式库；
   - 健康检查返回 `env=production` 后立即停止，仅执行过 `GET /health`，**没有业务写入**；
   - 正式库计数/版本/`source` 状态未变；
   - 随后改用 `os.execve(env=...)`，并通过 `/proc/<pid>/environ` 确认目标为 `uams_restore_20261027`，`APP_ENV=restore-verification`。
6. **正式库迁移仍未执行，必须等待单独批准。**

---

## 1. 只读核验结果

### 1.1 恢复库与授权

| 项 | 结果 |
|---|---|
| 恢复库 | `uams_restore_20261027` 存在 |
| 字符集/排序规则 | `utf8mb4` / `utf8mb4_0900_ai_ci` |
| 授权前表数量 | 0（空库） |
| `uams_app` 授权 | `ALL PRIVILEGES ON uams_restore_20261027.*` |
| 全局权限 | 仍只有 `USAGE`；未新增全局 `PROCESS` |
| 正式库权限 | 未修改 |

### 1.2 正式库与测试库原状

| 库 | Alembic | 关键计数 | `source` 列 |
|---|---|---|---|
| `uams` | `a5b7c9d1e2f3` | users 8 / students 4 / teachers 3 / course_selections 5 / operation_logs 22 | 不存在 |
| `uams_test` | `b1c2d3e4f5a6` | users 26 / students 20 / teachers 5 / course_selections 80 / operation_logs 0 | 存在（此前已有） |

- 本次未对 `uams` 执行迁移/写入；
- 本次未对 `uams_test` 执行任何写入、清空或结构变更。

### 1.3 备份完整性

| 项 | 结果 |
|---|---|
| 文件 | `/home/nglsyuyu/uams_backups/uams_20261026_235014.sql.gz` |
| 大小 | 11,252 字节 |
| 权限 | 目录 700 / 文件 600 |
| SHA256 | `dc79dec0046f0e09e0235f000db87d0f83b63e12a32553b7f4cb8e404b850b46` |
| `sha256sum -c` | 通过 |
| `gzip -t` | 通过 |
| 是否在 Git 仓库 | 否 |

---

## 2. 恢复结果

### 2.1 恢复执行

| 项 | 值 |
|---|---|
| 目标 | `uams_restore_20261027`（连接后 `SELECT DATABASE()` 再次确认） |
| 源文件 | 上述已校验备份 |
| 恢复方式 | `gunzip -c` → `mysql uams_restore_20261027`，未使用 `USE uams`/`CREATE DATABASE` |
| 耗时 | 约 3.3 秒 |
| 错误 | 无 |

### 2.2 恢复后核对（迁移前）

| 项 | 期望 | 实际 | 结果 |
|---|---:|---:|---|
| 表数量 | 30 | 30 | 一致 |
| 总行数 | 218 | 218 | 一致 |
| `alembic_version` | `a5b7c9d1e2f3` | `a5b7c9d1e2f3` | 一致 |
| `course_selections` | 5 行 | 5 行 | 一致 |
| `source` 列 | 不存在 | 不存在 | 一致 |
| 逐表行数差异 | 无 | 无 | 一致 |
| 缺失/多余表 | 无 | 无 | 一致 |

结论：备份可恢复，恢复库与备份快照一致。

---

## 3. 恢复库迁移结果

### 3.1 迁移前保护

- 只连接 `uams_restore_20261027`；
- 迁移前再次确认 `SELECT DATABASE()` 为恢复库；
- 迁移前版本 `a5b7c9d1e2f3`，`source` 不存在，5 条选课记录。

### 3.2 迁移

| 项 | 结果 |
|---|---|
| 命令 | `alembic upgrade head`（`DATABASE_URL` 指向恢复库） |
| 耗时 | 约 0.55 秒 |
| 输出 | `Running upgrade a5b7c9d1e2f3 -> b1c2d3e4f5a6` |
| 错误 | 无 |

### 3.3 迁移后核对

| 项 | 结果 |
|---|---|
| `alembic_version` | `b1c2d3e4f5a6` |
| `source` 列 | `varchar(20)`，可空 |
| `ck_selection_source` | 存在，允许 `NULL` / `STUDENT` / `ADMIN_REQUIRED` / `ADMIN_MANUAL` |
| 原有 5 条选课记录 | 全部保留 |
| `source IS NULL` | 5 / 5 |
| 表数量 | 30 |
| 总行数 | 218（迁移本身未增删业务行） |
| 逐表行数差异 | 无 |
| `alembic check` | `No new upgrade operations detected.` |

**迁移验证通过。**

---

## 4. API 验收

后端启动参数：

- 地址：`127.0.0.1:8000`
- `APP_ENV=restore-verification`
- `DATABASE_URL` 目标：`uams_restore_20261027`（通过 `/proc/<pid>/environ` 确认）
- 正式库计数/版本/`source` 未变

### 4.1 测试数据

在恢复库创建 `UAT002_` 前缀的隔离测试数据（不影响正式库）：

- 测试学院/专业/行政班；
- 3 名测试学生（`UAT002_S1`～`S3`）；
- 必修验收课/容量验收课/冲突验收课/选修课及对应教学班、排课；
- 其中 S3 已选一门周一 1-2 节选修课，用于时间冲突。

### 4.2 API 结果（10/10 通过）

| # | 用例 | 结果 |
|---:|---|---|
| 1 | 管理员预览必修课安排（3 人匹配、3 人将新增） | PASS |
| 2 | 预览不产生写入（DB 选课数保持 0） | PASS |
| 3 | 容量不足预览（2 新增 + 1 容量不足） | PASS |
| 4 | 容量不足正式提交仅新增 2 人 | PASS |
| 5 | 时间冲突预览（2 新增 + 1 冲突） | PASS |
| 6 | 时间冲突正式提交新增 2 人 | PASS |
| 7 | 选修课误调用必修预安排 → 409 | PASS |
| 8 | 教师越权调用 → 403 | PASS |
| 9 | 学生越权调用 → 403 | PASS |
| 10 | 历史名单来源显示为“历史记录（未标记来源）” | PASS |

补充 API 验证：

- 手动移除学生 → 204；
- 手动添加学生 → 201，来源 `ADMIN_MANUAL`；
- 已有成绩记录时移除 → 409；
- 操作日志包含 `REQUIRED_ASSIGN`、`ADMIN_ADD_STUDENT`、`ADMIN_REMOVE_STUDENT`；
- 恢复库中来源分布：`NULL=5`、`STUDENT=1`、`ADMIN_REQUIRED=2`、`ADMIN_MANUAL=1`。

---

## 5. 浏览器三角色验收

### 5.1 工具与真实性

- 使用 **headless Chrome 155 + Chrome DevTools Protocol（CDP）**，执行真实 DOM 点击/输入，不是用 API 冒充浏览器测试；
- 未使用 Playwright/Puppeteer（环境未安装）；
- 未做人眼视觉/截图检查；验收证据为页面 DOM 文本和 DB 结果；
- 所有写入仅发生在 `uams_restore_20261027`。

### 5.2 管理员

| 步骤 | 结果 |
|---|---|
| 登录 `admin` | 进入 `/admin/dashboard` |
| 进入 `/admin/teaching` | 看到 `UAT002_REQ-T` 教学班及「安排学生」按钮 |
| 打开「安排学生」 | 弹窗含「批量安排」「当前名单」两个 Tab |
| 选择行政班 `UAT002验收班` | 成功 |
| 点击「预览安排」 | 显示匹配 3、已安排 0、将新增 3、跳过 0、容量 0/3；预览后 DB 仍为 0 |
| 点击「确认安排」→ 二次确认 | 成功后 DB 为 3 条，来源 `ADMIN_REQUIRED` |
| 「当前名单」 | 显示 UAT002_S1/S2/S3、行政班、专业、来源“教务批量预安排”、安排时间、状态“已安排” |
| 重复预览 | 显示匹配 3、已安排 3、将新增 0 |
| 容量不足预览 | 显示“容量不足 1”，逐条原因“教学班剩余容量不足” |
| 时间冲突预览 | 显示“时间冲突 1”，逐条原因“与 UAT002_ELEC-T 时间冲突” |
| 历史名单（CS101） | 来源显示“历史记录（未标记来源）”，时间为原选课时间 |
| 手动移除/添加/成绩保护 | 已通过 API 验证（见 4.2） |

### 5.3 教师

| 步骤 | 结果 |
|---|---|
| 登录 `T001` | 进入 `/teacher/dashboard` |
| `/teacher/courses` | 看到 `UAT002_REQ-T`，选课人数 3/3 |
| 打开「学生名单」 | 显示 UAT002_S1/S2/S3 |
| `/teacher/schedule` | 显示 `UAT002必修验收课`（周一 3-4 节 A-303） |
| 直接访问 `/admin/teaching` | 跳转 `/403`，权限隔离正常 |

### 5.4 学生

| 步骤 | 结果 |
|---|---|
| 登录 `UAT002_S1` | 进入 `/student/dashboard` |
| `/student/schedule` | 显示 `UAT002必修验收课`、A-303、周一 3-4 节、1-16 周 |
| 学生端无需再次选课 | 已由教务安排，课表直接显示 |

### 5.5 负向与权限

- 教师/学生调用分配接口 → 403（API）；
- 教师访问教务页面 → `/403`（浏览器）；
- 选修课使用必修预安排 → 409（API）；
- 重复安排 → 不再新增（浏览器/API）；
- 容量不足 → 部分新增 + 逐条原因（API/浏览器预览）；
- 时间冲突 → 跳过 + 原因（API/浏览器预览）；
- 已有成绩移除 → 409（API）。

---

## 6. 正式库与 `uams_test` 保护

### 6.1 正式库 `uams`

| 项 | 结果 |
|---|---|
| Alembic | `a5b7c9d1e2f3`（未迁移） |
| `source` 列 | 不存在 |
| users/students/teachers | 8 / 4 / 3 |
| course_selections / operation_logs | 5 / 22 |
| 数据/结构 | 未修改 |
| 新后端连接 | 仅事故中的一次 `GET /health`，无业务写入；随后已停止并纠正 |

### 6.2 `uams_test`

| 项 | 结果 |
|---|---|
| Alembic | `b1c2d3e4f5a6`（此前已有） |
| 计数 | users 26 / students 20 / teachers 5 / course_selections 80 / operation_logs 0 |
| 本次写入 | 无 |
| 清空/结构变更 | 无 |

### 6.3 恢复库

- `uams_restore_20261027` 保留，版本 `b1c2d3e4f5a6`；
- 迁移前备份快照验证为 30 表/218 行；
- 之后为验收新增 `UAT002_` 测试数据（恢复库当前 users 11、students 7、course_selections 9、operation_logs 27），不影响正式库；
- 恢复库仍保留，供后续审查；未执行 `DROP DATABASE`。

---

## 7. 运行配置事故与纠正

| 项 | 说明 |
|---|---|
| 事故 | 首次启动包装脚本创建了 `env` 字典，但使用了 `os.execv()`（不接收 env），子进程实际继承原环境，连接了正式库 |
| 发现 | `/health` 返回 `env=production`，与预期 `restore-verification` 不符 |
| 处理 | 立即 kill 进程；仅发生过 `GET /health`，没有业务写请求 |
| 正式库影响 | 计数/版本/`source` 均未变；无新增日志/选课/成绩 |
| 纠正 | 改用 `os.execve(..., env)`；通过 `/proc/<pid>/environ` 确认 `DATABASE_URL` 指向 `uams_restore_20261027`，`APP_ENV=restore-verification` |
| 后续约束 | 任何新后端启动前，必须同时核对 `APP_ENV` 和进程 `DATABASE_URL` 目标；本次已按此执行 |

> 该事故已如实记录，不作为“正式库无连接”的宣称；准确表述是“曾建立正式库连接，但未执行任何业务写入，正式库状态未变”。

---

## 8. 备份安全与第二份副本方案

- 原备份完整性再次验证：SHA256/gzip 均通过；未覆盖、未修改、未提交 Git。
- 当前主机只有根分区（`/dev/nvme0n1p6`），未发现独立的第二块数据盘或已挂载备份卷。
- 建议的第二份独立副本方案（未执行）：
  1. 通过 `scp`/`rsync` 复制到另一台受控主机；
  2. 或复制到加密外置存储/受控对象存储；
  3. 复制后执行 `sha256sum` 对比；
  4. 副本权限 600、目录 700，不放入 Git 仓库；
  5. 保留至少一份离线/异地副本，并记录保留周期。
- 原备份路径与 SHA 见 1.3；不要覆盖。

---

## 9. 风险与未完成项

| 项 | 状态 |
|---|---|
| 正式库迁移 `b1c2d3e4f5a6` | **未执行，等待单独批准** |
| 恢复库迁移验证 | 已完成 |
| 三角色 API 验收 | 已完成（10/10） |
| 浏览器三角色验收 | 已完成（headless Chrome + CDP；无人眼/截图） |
| 正式库维护窗口最终备份 | 未执行 |
| 第二份独立备份副本 | 未执行（仅方案） |
| 恢复库测试数据清理 | 未清理（保留供审查） |
| 正式库历史数据补排（CS103/PUB101/2 名学生） | 未自动处理，需教务通过新界面确认 |
| 正式迁移后的生产浏览器验收 | 未执行；本次验收在隔离恢复库完成 |

---

## 10. 正式升级前置条件

- [ ] 正式库迁移单独批准；
- [ ] 维护窗口内由 DBA 复核活动会话/长事务；
- [ ] 重新执行并验证最终正式库备份（不要只依赖本报告中的旧备份）；
- [ ] 确认恢复库验收结果（本报告）可作为预演依据；
- [ ] 确认正式库迁移后不启动旧后端/新前端混用；
- [ ] 迁移后按检查清单做只读冒烟与三角色人工浏览器验收（正式环境）；
- [ ] 明确失败恢复负责人和旧版本程序产物。

---

## 11. Git 与交付

| 项 | 结果 |
|---|---|
| 分支 | `main` |
| 检查前基线 | `ff0d3de` |
| 本次提交 | 仅本报告 |
| 是否新建分支/worktree/PR | 否 |
| 是否 force push/reset | 否 |
| 正式库 | 未迁移、未写入、未删除 |
| `uams_test` | 未修改、未清空 |
| 恢复库 | 保留 `uams_restore_20261027` |

---

## 12. 结论

- 备份恢复、迁移预演、历史 NULL 兼容、CHECK 约束、三角色 API 与真实浏览器 DOM 验收均已完成；
- 恢复库 `uams_restore_20261027` 现有 30 表、`b1c2d3e4f5a6`、`source` 列与 CHECK 约束，5 条历史选课 `source=NULL`；
- 正式库 `uams` 仍为迁移前状态，`uams_test` 未被修改；
- 曾发生一次误连正式库的启动配置事故，仅 `GET /health`，无业务写入，已停止并纠正；
- **正式库迁移继续等待单独批准。**

> 报告结束。
> 本报告不包含数据库密码、连接密钥、JWT 或备份文件内容；测试数据均在隔离恢复库中。
