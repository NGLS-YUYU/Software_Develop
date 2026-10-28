# UAMS V3.1 FIX-002 必修课预安排与教学班学生名单管理报告

> 修复日期：2026-10-26
> 基线分支：`main`
> 相关报告：`docs/UAMS_V3.1_FUNCTION_GAP_AUDIT.md`（F-01/F-12）、`docs/UAMS_V3.1_PRECHECK_REPORT.md`（PC-05/PC-06/PC-07）、`docs/UAMS_V3.1_FIX-001_REPORT.md`
> 修复代码提交：`3230dcc506422145ab9e5431a4389661cba5806b`
> 代码推送：已成功推送到 `origin/main`（`3e12447..3230dcc`）
> 本报告提交：见本次最终 Git 记录（`main` 最新提交）
> **正式库迁移：未执行，等待确认（详见第 4 章）**

---

## 0. 结论摘要

1. 教务端「开课排课 → 教学班」新增「安排学生」入口，支持按**行政班/专业/学院**批量预安排，支持**预览 → 二次确认 → 单事务提交**。
2. 教学班名单支持查看学号、姓名、行政班、专业、**安排来源**、**安排时间**、状态，并支持手动添加/移除。
3. 后端预排与手动添加均校验：教学班有效、学期 ACTIVE、授课教师/排课存在、学生存在且在读、容量、同课程其他班、时间冲突；管理员权限不能绕过这些校验。
4. 批量安排采用「应用层部分成功 + 数据库单事务」策略：不符合条件的学生逐条返回原因；所有新增记录同一事务提交，提交失败整批回滚。
5. 新增 `course_selections.source` 字段区分学生自主选课/教务预安排/教务手动添加；历史行保持 `NULL`，显示“历史记录（未标记来源）”，不自动回填。
6. 隔离库 `uams_test` 执行 **36 项后端/API 断言，36 项通过、0 项失败**；前端 `npm run build` 通过；后端 `compileall` 通过；迁移在测试库完成 upgrade/downgrade/upgrade 往返验证。
7. **未完成浏览器三角色端到端验收**；未启动 Chrome 自动化（无 Playwright/Puppeteer），因此只完成 API 级三角色闭环验证，不能宣称浏览器端到端验收通过。
8. **正式库 `uams` 未执行迁移**，仍停留在 `a5b7c9d1e2f3`，没有 `course_selections.source` 列；正式数据未被修改。

---

## 1. 原始缺陷及根因

### 1.1 原始缺陷

F-01/F-12 审计结论：

- 后端已有 `assign-required`、添加学生、移除学生接口；
- 前端没有调用，普通教务无法通过界面完成必修课预安排；
- 后端预排缺少容量、学期、学籍、同课程、时间冲突校验；
- 教学班名单没有来源/安排时间，无法区分“教务预安排”和“学生自主选课”；
- 手动移除没有成绩保护。

PRECHECK 数据：

- `CS103` 必修教学班 0 人；
- `PUB101` 有教学任务但无教学班；
- 2 名学生没有任何选课记录；
- 以上正式数据未自动修改。

### 1.2 根因

1. **前端缺口**：`Teaching.vue` 教学班操作列只有排课/开放/编辑/删除；没有安排学生或名单管理入口。
2. **后端预排过于简化**：原 `assign_required()` 只校验课程类型和范围，循环创建记录，没有容量/学期/学籍/同课程/时间冲突检查；曾退课记录会被直接复用，无法保留“教务移除”的意图。
3. **无来源字段**：`course_selections` 只有 `status`/`selected_at`，无法区分学生自主选课与教务安排；历史数据也无法推断，不能虚构。
4. **手动名单管理校验不足**：原添加学生只校验容量；原移除学生不检查成绩。
5. **缺少操作日志**：批量安排/手动添加/移除没有写入 `operation_logs`。

---

## 2. 修改文件与功能说明

### 2.1 数据库与模型

| 文件 | 变更 |
|---|---|
| `backend/app/models/selection.py` | 新增 `SelectionSource` 常量；`CourseSelection.source`（可空 `VARCHAR(20)`）；`ck_selection_source` 检查约束。 |
| `backend/alembic/versions/20261026_1200_b1c2d3e4f5a6_add_selection_source.py` | 新增迁移：添加 `source` 列与检查约束；**不回填历史数据**；downgrade 删除约束与列。 |

来源取值：

| 值 | 含义 |
|---|---|
| `STUDENT` | 学生自主选课 |
| `ADMIN_REQUIRED` | 教务批量预安排（必修/实践） |
| `ADMIN_MANUAL` | 教务手动添加 |
| `NULL` | 历史记录（未标记来源），不自动推断 |

### 2.2 后端 Service/API

| 文件 | 变更 |
|---|---|
| `backend/app/services/selection.py` | 新增预览/正式提交、范围校验、容量/学籍/同课程/时间冲突规划、部分成功结果、操作日志、`_commit()` 回滚；学生自主选课写入 `source=STUDENT`。 |
| `backend/app/services/teaching.py` | 手动添加：校验教师/排课、学期 ACTIVE、学籍、容量、同课程、时间冲突，写入 `source=ADMIN_MANUAL`；手动移除：校验成绩记录、写入操作日志、软删除。 |
| `backend/app/api/v1/selection.py` | `assign-required` 增加 `preview` 查询参数与完整响应模型；名单返回 `selection_id/status/source/source_label/selected_at`；手动添加/移除传入当前操作人。 |
| `docs/API.md` | 更新名单/预排接口说明、响应字段、来源与迁移说明。 |

**批量安排事务策略**：

- `preview=true`：只读计算，不写库；
- `preview=false`：按班级/专业/学院范围计算；可新增记录在同一事务所提交；
- 容量不足、冲突、学籍无效、同课程、曾移除等按业务规则跳过并逐条报告；
- 提交失败整批 rollback，不出现“部分落库但前端显示全部成功”。

**幂等与移除语义**：

- 已在本班：返回 `ALREADY_ASSIGNED`，不重复添加；
- 曾从本班移除（`DROPPED`）：返回 `PREVIOUSLY_REMOVED`，批量预排**不自动恢复**；
- 需要恢复时由教务在「当前名单」手动添加，并重新经过全部校验。

### 2.3 前端

| 文件 | 变更 |
|---|---|
| `frontend/src/components/ClassEnrollmentDialog.vue`（新增） | 批量安排 + 当前名单弹窗；预览统计、逐学生结果、二次确认；远程搜索学生、手动添加/移除；来源/时间展示。 |
| `frontend/src/views/admin/Teaching.vue` | 教学班操作列新增「安排学生」；接入弹窗；名单变更后刷新教学班人数。 |
| `frontend/src/api/index.ts` | 新增 `assignRequired`、`addStudent`、`removeStudent`；名单返回类型升级。 |
| `frontend/src/types/index.ts` | 新增 `ClassRosterStudent`、`RequiredAssignResult`、`RequiredAssignItem`；`Selection` 增加来源字段。 |
| `frontend/src/views/admin/SelectionManage.vue`、`teacher/MyCourses.vue` | 仅调整名单类型兼容 `class_name: null`，不改变原有行为。 |
| `frontend/components.d.ts` | 自动生成组件类型包含 `ClassEnrollmentDialog`。 |

### 2.4 用户手册

用户手册此前不在 `main` 上。本次从 `docs/user-manual` 分支同步手册并更新：

- 1.1 功能范围/1.2 名词解释；
- 4.8.3 教学班操作列与安排学生入口；
- 4.9.2 名单说明；
- 4.10 必修课预安排与教学班名单管理（完整重写）；
- 12.2 标记为“已修复 FIX-002”；
- 开学前检查清单。

---

## 3. 前后端实现情况

| 能力 | 后端 | 前端 | 状态 |
|---|---|---|---|
| 按行政班批量安排 | `assign_required(dry_run/preview)` | 范围选择 + 预览 + 确认 | 已实现 |
| 按专业批量安排 | 同上 | 同上 | 已实现 |
| 按学院批量安排 | 同上 | 同上 | 已实现 |
| 预览统计/逐学生原因 | 完整响应 | 统计卡 + 预览表 | 已实现 |
| 二次确认 | API 只区分 preview/commit | `ElMessageBox.confirm` | 已实现 |
| 容量校验 | 锁教学班行 + 动态统计 | 显示剩余容量/容量不足原因 | 已实现 |
| 学籍校验 | `academic_status == ENROLLED` | 结果表显示原因 | 已实现 |
| 同课程其他班 | 查询并跳过 | 结果表显示原因 | 已实现 |
| 时间冲突 | `ConflictChecker.student_conflict` | 结果表显示原因 | 已实现 |
| 学期/教学班有效 | ACTIVE + 教师/排课存在 | 错误由拦截器提示 | 已实现 |
| 权限 | `selection:manage` | 仅管理员端入口 | 已实现 |
| 幂等 | 已安排/曾移除分类 | 结果表显示 | 已实现 |
| 名单来源/时间 | `source`/`selected_at` | 名单列 | 已实现 |
| 手动添加 | 完整校验 + 操作日志 | 搜索 + 添加 | 已实现 |
| 手动移除 | 成绩保护 + 操作日志 | 确认 + 移除 | 已实现 |
| 教师名单 | 名单接口返回来源/时间 | 现有「我的课程」名单 | 已实现（API 级） |
| 学生课表 | 选课记录生效 | 现有「我的课表」 | 已实现（API 级） |
| 人数统计 | 动态 COUNT | 教学班列表刷新 | 已实现 |

---

## 4. 数据库结构变化与迁移状态

### 4.1 变化

```sql
ALTER TABLE course_selections
  ADD COLUMN source VARCHAR(20) NULL
  COMMENT '来源：STUDENT/ADMIN_REQUIRED/ADMIN_MANUAL；NULL 为历史未标记';

ALTER TABLE course_selections
  ADD CONSTRAINT ck_selection_source
  CHECK (source IS NULL OR source IN ('STUDENT','ADMIN_REQUIRED','ADMIN_MANUAL'));
```

- 可空，不设默认值；现有 5 条正式选课记录的 `source` 均为 `NULL`，无需回填；
- 只影响 `course_selections`，不改学生/教师/成绩/学期表；
- 不影响既有成绩、学分、绩点、排名逻辑；
- 迁移版本：`b1c2d3e4f5a6`，down_revision `a5b7c9d1e2f3`。

### 4.2 兼容性

- MySQL 8.4.11；`source` 为可空列，历史数据天然满足 `NULL` 分支；
- 需要在正式库执行 `alembic upgrade head` 后，新代码才能读取该列；
- 在隔离库 `uams_test` 已执行 `upgrade → downgrade → upgrade` 往返验证；
- `alembic check` 在隔离库返回 `No new upgrade operations detected.`。

### 4.3 正式库状态（重要）

| 项 | 正式库 `uams` |
|---|---|
| Alembic 当前版本 | `a5b7c9d1e2f3`（**未升级**） |
| `course_selections.source` | **不存在** |
| 数据 | 未修改：`users=8`、`students=4`、`teachers=3`、`course_selections=5`、`operation_logs=22` |
| `CS103` 零选课 | 仍为 0（未自动补排） |
| `PUB101` | 仍无教学班（未自动创建） |
| 2 名零选课学生 | 未自动安排 |
| 操作日志 | 未新增/未删除 |

> **在正式库执行迁移前，不要用新版本后端连接正式库。** 新代码会查询 `course_selections.source`，正式库缺少该列会导致查询失败。正式迁移需按变更流程确认后执行 `alembic upgrade head`。

---

## 5. 测试用例与结果

### 5.1 测试环境

| 项 | 值 |
|---|---|
| 测试库 | `uams_test`（隔离库，与正式库 `uams` 分离） |
| 迁移 | 已升级到 `b1c2d3e4f5a6` |
| 测试方式 | FastAPI `TestClient` + 直接 SQL 校验 |
| 测试脚本 | 临时脚本 `/tmp/fix002_assignment_tests.py`（未纳入 Git） |
| 测试数据 | `FIX002_` 前缀；测试后清理，基线行数恢复 |
| 正式库 | 未写入、未迁移、未删除 |

### 5.2 业务验收用例（17 项）

| # | 用例 | 结果 | 说明 |
|---:|---|---|---|
| 1 | 按行政班安排必修课 | PASS | 4 人匹配、3 人新增、1 人学籍无效跳过 |
| 2 | 按专业安排必修课 | PASS | 6 人匹配、5 人新增、1 人学籍无效跳过 |
| 3 | 按学院安排必修课 | PASS | 9 人匹配、8 人新增、1 人学籍无效跳过 |
| 4 | 重复执行批量安排 | PASS | 已安排 3 人、新增 0 人；幂等 |
| 5 | 教学班容量不足 | PASS | 容量 2、4 人匹配：新增 2、跳过 2（容量 1 + 学籍 1）；无超容 |
| 6 | 学生课表时间冲突 | PASS | 冲突学生跳过，原因 `TIME_CONFLICT` |
| 7 | 学生已有相同课程 | PASS | 同课程其他班学生跳过，原因 `SAME_COURSE_OTHER_CLASS` |
| 8 | 学生学籍无效 | PASS | 休学学生跳过，原因 `INVALID_STATUS` |
| 9 | 选修课误调用必修预安排 | PASS | 409，提示不是必修/实践课程 |
| 10 | 非管理员越权调用 | PASS | 教师 403、学生 403 |
| 11 | 手动添加学生 | PASS | 201，来源 `ADMIN_MANUAL` |
| 12 | 手动移除学生 | PASS | 204，软删除 `DROPPED` |
| 13 | 已有成绩时禁止危险移除 | PASS | 草稿成绩存在时 409 |
| 14 | 教师名单正确显示 | PASS | 教师 token 查看本人教学班名单，含来源/时间 |
| 15 | 学生课表正确显示 | PASS | 学生 token 查 `/teaching-schedules/my`，包含被安排教学班 |
| 16 | 选课人数统计正确 | PASS | `selection-stats.selected` 与名单一致 |
| 17 | 批量部分失败/事务回滚 | PASS | 容量部分成功逐条报告；模拟提交失败后整批回滚为 0 |

### 5.3 其他断言（19 项）

包括：

- 预览不写库；
- 批量来源 `ADMIN_REQUIRED`；
- 手动来源 `ADMIN_MANUAL`；
- 批量/添加/移除操作日志写入；
- 手动重复添加 409；
- 手动添加无效学籍 409；
- 手动添加时间冲突 409；
- 手动添加超容量 409；
- 教师课表正常显示；
- 测试后基线行数恢复；
- 迁移 upgrade/downgrade/upgrade 往返；
- 前端构建、后端编译、`alembic check` 等。

**测试汇总：36 项通过，0 项失败。**

### 5.4 构建与静态检查

| 项 | 命令 | 结果 |
|---|---|---|
| 后端编译 | `python -m compileall app` | 通过 |
| 前端构建 | `npm run build`（含 `vue-tsc -b`） | 通过；仅 chunk 体积提示 |
| 隔离库迁移 | `alembic upgrade head` | 成功 |
| 迁移回滚 | `alembic downgrade -1` + `upgrade head` | 成功 |
| 隔离库 schema | `alembic check` | `No new upgrade operations detected.` |
| 正式库 | 只读计数/版本检查 | 未变；无 `source` 列 |

---

## 6. 三角色业务闭环验收结果

### 6.1 API 级验证（已完成）

| 角色 | 操作 | 结果 |
|---|---|---|
| 教务管理员 | 创建测试教学班/排课/课程（隔离库） | 成功 |
| 教务管理员 | 按行政班/专业/学院预览、正式安排 | 成功；逐条原因正确 |
| 教务管理员 | 手动添加/移除学生 | 成功；容量/冲突/成绩保护生效 |
| 教务管理员 | 查看人数统计 | 成功，与名单一致 |
| 教师 | 查看本人教学班名单 | 成功，含来源/安排时间 |
| 教师 | 查看本人课表 | 成功，包含该教学班排课 |
| 学生 | 查看本人课表 | 成功，包含被安排必修课 |
| 学生/教师 | 调用管理员预排接口 | 403，权限隔离正确 |

### 6.2 浏览器端（未完成）

- **未完成浏览器三角色端到端验收**；
- 环境有 Chrome 二进制，但没有 Playwright/Puppeteer 等自动化依赖，未启动浏览器逐页点击；
- 前端构建通过，但“页面实际渲染、按钮点击、错误提示、响应式布局”未在浏览器中验证；
- 因此不能宣称完整端到端验收通过；答辩/上线前应由人工使用管理员、教师、学生三个账号实际走一遍。

---

## 7. 已知限制与未完成项目

| 项目 | 说明 |
|---|---|
| 正式库迁移未执行 | 正式库仍为 `a5b7c9d1e2f3`；需确认后执行 `alembic upgrade head`，否则新后端无法连接正式库 |
| 浏览器 E2E 未验证 | 无 Playwright/Puppeteer；仅 API 级三角色验证 |
| 历史来源不回填 | 既有 `course_selections.source` 为 `NULL`，显示“历史记录（未标记来源）”；不自动推断 |
| 预排预览未分页 | 大范围（如全院）会返回全部逐学生项，数据量大时响应体较大；后续可按需分页/截断 |
| 部分成功策略 | 容量不足时按 `student_no` 顺序尽量安排，剩余逐条报告；没有可配置优先级 |
| 曾移除不自动恢复 | 批量预排不会恢复已移除学生；需手动添加，这是有意的业务语义 |
| 无独立安排历史表 | 来源字段只保留当前值；重复添加会更新来源，历史变更依赖 `operation_logs` |
| 无缓存失效机制 | 当前页面按进入/刷新重新请求，没有共享缓存；教师/学生页面需刷新或重新进入 |
| 正式历史数据未补排 | `CS103`、`PUB101`、2 名零选课学生保持原状，需教务通过新界面确认后处理 |
| 自动化测试未入仓 | 项目 `docs/TESTING.md` 说明最终交付移除了 `backend/tests`；本次使用临时脚本 |
| 并发压测未执行 | 使用教学班行锁 + 动态计数防超容；未做真实并发压力测试 |

---

## 8. Git 与交付

| 项 | 结果 |
|---|---|
| 分支 | `main` |
| 修复代码提交 | `3230dcc506422145ab9e5431a4389661cba5806b` |
| 提交主题 | `feat: add required-course assignment and roster management` |
| 代码推送 | `git push origin main` 成功（`3e12447..3230dcc`） |
| 报告提交 | 见本次最终 Git 记录（`main` 最新提交） |
| 是否新建分支/worktree/PR | 否 |
| 是否 force push / reset --hard | 否 |
| 正式库 | 未迁移、未写入、未删除 |
| 提交范围 | 代码、迁移、前端组件、API 文档、用户手册；报告单独提交 |

---

## 9. 结论

FIX-002 已把「创建必修课教学班 → 排课 → 教务批量安排学生 → 教师查看名单/课表 → 学生查看课表」的主链路打通：

- 前端有明确的「安排学生」入口，支持预览与二次确认；
- 后端不再绕过容量、时间、学籍、同课程等校验；
- 名单有来源与时间，支持手动添加/移除，并阻止已有成绩的危险移除；
- 批量安排采用单事务提交 + 逐条业务原因，幂等且可追溯；
- 隔离库 36 项测试全部通过。

**但正式库迁移尚未执行，且浏览器端三角色验收尚未完成。** 在完成迁移确认和人工浏览器验收前，不能宣称 FIX-002 已在正式环境完整交付。

---

> 报告结束。
> 本次修复未修改正式库数据；所有写入均在隔离库 `uams_test`，测试数据已清理；正式库迁移等待确认。
