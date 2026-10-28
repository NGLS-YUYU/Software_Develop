# UAMS V3.1 PROD-001 正式数据库升级与运行报告

> 执行日期：2026-10-28
> 分支：`main`
> 正式库：MySQL `uams`
> 隔离库：`uams_test`（未清空、未覆盖）
> 恢复验证库：`uams_restore_20261027`（保持原状）
> 本报告提交：见 `main` 最新 Git 记录

---

## 0. 结论摘要

1. 正式库 `uams` 已从 `a5b7c9d1e2f3` 升级到当前 head `e4f5a6b7c8d9`。
2. 迁移仅新增 4 个可空字段/表结构，无删除、清空或重建正式业务数据的操作。
3. 迁移前已完成完整备份，`gzip -t` 与 SHA256 校验通过；备份文件位于正式库同机目录。
4. 迁移前后学生、教师、课程、教学班、选课、成绩、考试记录数量一致。
5. 后端日常运行配置已指向 `uams`；运行进程连接经 `SHOW PROCESSLIST` 确认为 `uams`。
6. 历史错误 `Unknown column 'course_selections.source'` 已解决，教学班名单等接口返回 200。
7. 管理员、教师、学生登录及核心 API、核心页面验收通过。
8. 未执行任何破坏性数据写入；正式库仅因登录验收新增了审计日志。

**最终结论：UAMS V3.1 正式数据库已完成升级，系统可以正常用于结课答辩演示。**

---

## 1. 执行前状态（真实核对）

| 项目 | 结果 |
|---|---|
| Git 分支 | `main` |
| 工作区 | 干净，无未提交修改 |
| 与远程 | `main...origin/main` 同步 |
| Alembic heads | 唯一 head：`e4f5a6b7c8d9` |
| 正式库当前版本 | `a5b7c9d1e2f3` |
| `course_selections.source` | 不存在 |
| 新表 `grade_change_logs` / `teaching_materials` / `schedule_adjustments` | 均不存在 |
| 部分迁移痕迹 | 未发现；`alembic_version` 单行 |
| 运行中的写入进程 | 无 |

迁移链完整、线性，无分支或重复 revision：

```
bc0a832224a4 (base)
  → 7d34560e8aba
  → ce5a2a2a3f11
  → d81e869930fb
  → a3f9c2e8b1d4
  → c4d8e2f6a9b1
  → d7e5a3f1c2b4
  → e1b7c4a9f3d2
  → e2a1b5c6d7e8
  → a5b7c9d1e2f3   ← 迁移前正式库
  → b1c2d3e4f5a6   ← add course_selections.source
  → c2d3e4f5a6b7   ← add grade_change_logs
  → d3e4f5a6b7c8   ← add teaching_materials
  → e4f5a6b7c8d9   ← add schedule_adjustments（head）
```

待执行迁移的操作类型：

| 迁移 | 操作 | 是否破坏现有数据 |
|---|---|---|
| `b1c2d3e4f5a6` | `course_selections` 新增可空 `source` + CHECK | 否，历史行保持 NULL |
| `c2d3e4f5a6b7` | 新建 `grade_change_logs` | 否 |
| `d3e4f5a6b7c8` | 新建 `teaching_materials` | 否 |
| `e4f5a6b7c8d9` | 新建 `schedule_adjustments` | 否 |

---

## 2. 迁移前备份

| 项目 | 内容 |
|---|---|
| 备份目录 | `/home/nglsyuyu/uams_backups/` |
| 文件 | `uams_20261028_232010.sql.gz` |
| 大小 | 11,568 bytes |
| SHA256 | `fb0602463322806eae30921f6d0949706851cbed89814aac2ca2b1a2930091ac` |
| 校验文件 | `uams_20261028_232010.sql.gz.sha256` |
| 基线数据 | `uams_20261028_232010_baseline.json` |
| 权限 | `600`，仅当前用户可读 |
| 工具 | `mysqldump 8.4.11` |
| 一致性参数 | `--single-transaction --quick --routines --triggers --events --no-tablespaces` |

验证结果：

- `gzip -t`：通过；
- `sha256sum -c`：通过；
- 转储尾部包含 `-- Dump completed`；
- 包含 30 个 `CREATE TABLE`，28 张有数据的表包含 `INSERT`；
- 备份文件未提交 Git。

> 限制：当前 `uams_app` 账号无 `CREATE DATABASE` 权限，未做“恢复到临时库”的演练；备份一致性依赖 InnoDB `--single-transaction` 快照，完整性依赖 gzip/SHA256/转储完成标记。

---

## 3. 迁移执行

```bash
cd uams/backend
alembic current   # a5b7c9d1e2f3（连接 uams）
alembic upgrade head
```

实际输出：

```
Running upgrade a5b7c9d1e2f3 -> b1c2d3e4f5a6, add course_selections.source (FIX-002)
Running upgrade b1c2d3e4f5a6 -> c2d3e4f5a6b7, add grade change logs (F-03)
Running upgrade c2d3e4f5a6b7 -> d3e4f5a6b7c8, add teaching materials (F-21)
Running upgrade d3e4f5a6b7c8 -> e4f5a6b7c8d9, add schedule adjustments (F-22)
```

结果：退出码 0，`alembic current` 为 `e4f5a6b7c8d9 (head)`。

未使用 `stamp head`，未删除/重建数据库，未执行 `drop_all()`，未复制测试库数据，未手工补字段。

---

## 4. 迁移后完整性验证

| 检查 | 结果 |
|---|---|
| `alembic current` | `e4f5a6b7c8d9 (head)` |
| `alembic check` | `No new upgrade operations detected.` |
| `course_selections.source` | 存在 |
| `ck_selection_source` | 存在；历史 5 行全部为 NULL，满足约束 |
| `grade_change_logs` | 11 列，2 个外键，1 个 CHECK |
| `teaching_materials` | 9 列，2 个外键 |
| `schedule_adjustments` | 18 列，5 个外键，2 个 CHECK |
| 历史已审核成绩 | 4 条，可正常读取 |
| 历史选课来源 | 5 条均为 NULL（历史未标记，符合迁移设计） |

### 4.1 数据量对比

| 表 | 迁移前 | 迁移后（验收前） |
|---|---:|---:|
| users | 8 | 8 |
| students | 4 | 4 |
| teachers | 3 | 3 |
| courses | 5 | 5 |
| teaching_classes | 4 | 4 |
| course_selections | 5 | 5 |
| grades | 4 | 4 |
| exams | 2 | 2 |
| exam_rooms | 2 | 2 |
| operation_logs | 25 | 25 |
| evaluation_tasks | 1 | 1 |

验收后 `operation_logs` 变为 33，是本次管理员/教师/学生登录产生的审计日志（正常追加），业务表数量未变。

---

## 5. 正式运行配置

| 项目 | 结果 |
|---|---|
| `backend/.env` | `DATABASE_URL` 指向 `uams`；文件权限 `600`；已被 `.gitignore` 忽略 |
| 后端配置来源 | `app/core/config.py` 读取 `backend/.env` |
| 测试隔离 | `backend/tests/conftest.py` 强制覆盖为 `uams_test`，fixture 再次断言 `SELECT DATABASE()` |
| `os.execv` | 仓库内无任何 `os.execv` 使用；当前启动脚本通过 `nohup` 启动，继承 `.env` 配置 |
| 启动脚本 | `uams/start.sh`；不执行 seed、清库、导入或自动初始化 |
| Vite 代理 | `/api` → `http://127.0.0.1:8000`（可用 `UAMS_BACKEND_URL` 覆盖） |
| 运行进程数据库 | `SHOW PROCESSLIST` 中应用连接全部为 `uams` |
| 健康检查 | `{"status":"ok","app":"UAMS","env":"production","database":"up"}` |

正式运行地址：

- 本机前端：`http://127.0.0.1:5173`
- 局域网前端：`http://10.136.44.195:5173`
- 后端：`0.0.0.0:8000`

进程：

- 后端 PID：`16349`
- 前端 PID：`16364`
- 日志：`uams/logs/backend.log`、`uams/logs/frontend.log`

---

## 6. 功能验收

### 6.1 1054 错误

历史错误 `Unknown column 'course_selections.source'` 已解决：

- 管理员 `GET /api/v1/teaching-classes/1/students` → 200（2 条）
- 教师 `GET /api/v1/grades/teaching-classes/1/students` → 200（2 条）
- 教师 `GET /api/v1/grades/teaching-classes/1` → 200（2 条）
- 选课来源字段可正常读写；历史记录为 NULL 不影响读取

### 6.2 管理员

| 检查 | 结果 |
|---|---|
| 登录（`admin`） | OK |
| 工作台 | 页面正常渲染 |
| 学生列表 | 200，4 条 |
| 教师列表 | 200，3 条 |
| 课程 | 200，5 条 |
| 教学班 | 200，4 条 |
| 教学班学生名单 | 200，2 条 |
| 必修课预安排只读预览 | 200；`matched=1, already_assigned=1, would_add=0`，未写库（选课仍为 5 条） |
| 选课窗口 | 页面正常；接口可读 |
| 成绩审核 | 页面正常；待审核 0 条，已审核 4 条 |
| 考试 / 评价 / 统计 | 页面正常；考试 2 场、评价任务 1 个 |

### 6.3 教师（`T001`）

| 检查 | 结果 |
|---|---|
| 登录 | OK |
| 我的课程 | 200，2 个教学班 |
| 教学班名单 | 200，2 人 |
| 课表 | 200，2 条 |
| 已有成绩 | 200，2 条 |
| 考试 | 200，2 场 |

### 6.4 学生（`20260001`）

| 检查 | 结果 |
|---|---|
| 登录 | OK |
| 个人信息 | 200 |
| 我的选课 | 200，3 条 |
| 可选课程 / 选课窗口 | 200；窗口状态可读 |
| 课表 | 200，3 条 |
| 成绩 / 绩点 / 排名 | 200，2 条成绩，含 GPA 与班级/专业排名 |
| 考试安排 | 200，2 场 |

### 6.5 浏览器页面验收

使用无头 Chrome 实际渲染，全部通过：

- 管理员：仪表盘、学生、教师、课程、开课排课、选课、成绩、考试、评价
- 教师：仪表盘、我的课程、成绩、课表
- 学生：仪表盘、个人信息、选课、课表、成绩、考试
- 页面未出现 `无权限`、`加载失败`、`Unknown column`、`1054`

---

## 7. 未验证项目

| 项目 | 说明 |
|---|---|
| 备份恢复到临时库演练 | `uams_app` 无 `CREATE DATABASE` 权限；未尝试提权 |
| 正式库写入类业务 | 按要求未新建/安排/删除真实业务记录；写入路径此前在 `uams_test` 验证 |
| 必修课预安排浏览器点击“预览” | 页面已渲染；只读预览通过同一后端接口验证，未在浏览器内点击提交 |
| 并发/压力测试 | 未做选课、成绩、调停课并发压测 |
| 视觉截图核对 | 以无头浏览器 DOM 文本与接口响应为准，未逐页人眼比对 |

---

## 8. 剩余风险

1. 正式库业务数据量较小（4 名学生、5 门课程、2 场考试）；教学资料、调停课、评价记录为空，相关页面会显示空列表。
2. 备份与正式库位于同一台机器；建议尽快复制到独立存储。
3. MySQL DDL 非事务性；本次迁移已完整成功，若未来回滚需使用备份恢复，不能依赖 `alembic downgrade` 单独保证数据安全。
4. 历史选课 `source=NULL` 属于预期；前端以“历史记录（未标记来源）”展示，新记录才会写入来源。
5. 审计日志会随登录和写操作持续增长，长期运行需考虑归档策略。

---

## 9. Git 与交付

| 项目 | 结果 |
|---|---|
| 分支 | `main` |
| 新建分支/worktree/PR | 否 |
| 强制推送/硬重置 | 否 |
| 代码修改 | 本次仅数据库迁移与部署验证，无业务代码修改 |
| 报告提交 | 见 `main` 最新 Git 记录 |
| 推送 | 已推送 `origin/main` |
| 提交内容 | 仅本报告；未提交 `.env`、备份、日志、数据库密码 |

---

## 10. 最终结论

**UAMS V3.1 正式数据库 `uams` 已完成从 `a5b7c9d1e2f3` 到 `e4f5a6b7c8d9` 的升级，结构一致性检查通过，历史业务数据未丢失，运行环境已指向正式库，管理员/教师/学生核心业务与页面验收通过。**

**系统可以正常用于结课答辩演示。**

> 报告结束。
> 本报告不包含数据库密码、JWT、备份内容或敏感个人数据。
