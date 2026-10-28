# UAMS V3.1 FIX-003 选课与退课时间窗口一致性修复报告

> 修复日期：2026-10-27
> 基线分支：`main`（检查前 `ff83cb8`）
> 修复代码提交：`5d1284d8e905aefb0b8c8359b4cc76d27d16e57a`
> 代码推送：已成功推送到 `origin/main`（`ff83cb8..5d1284d`）
> 本报告提交：见本次最终 Git 记录（`main` 最新提交）
> 正式库：`uams` 仍为 `a5b7c9d1e2f3`，**未迁移、未修改**
> `uams_test`：未修改、未重置

---

## 0. 执行摘要

1. F-04 已修复：选课和退课现在共用同一个后端窗口判断，学期、窗口状态、当前时间、限定年级、教学班状态全部统一校验。
2. 退课新增了窗口校验：开始前、结束后、窗口非 ACTIVE、限定年级不匹配、学期非 ACTIVE、必修课、教学班关闭等均被明确拒绝。
3. 前端不再自行实现一套时间判断：学生端通过新的后端状态接口显示“能否选/退 + 原因”；管理员端显示后端计算的“实际状态”，并对重叠窗口提示。
4. 同一学期多个 ACTIVE 窗口重叠时采用**并集**规则（任一适用窗口开放即可），时间边界包含开始/结束时刻；没有修改数据库状态枚举。
5. 隔离库自动化测试：
   - FIX-003：**42 项通过，0 失败**；
   - FIX-001 回归：**25 项通过**；
   - FIX-002 回归：**36 项通过**。
6. 前端 `npm run build` 通过；后端 `compileall` 通过；`uams_test` 的 `alembic check` 无漂移。
7. 浏览器验收（headless Chrome + CDP，真实 DOM 操作）：**11 项通过**；未做人眼截图检查。
8. **无数据库结构变更、无迁移文件**；正式库未执行任何迁移或写入，`uams_test` 未修改。

---

## 1. F-04 原始问题与根因

### 1.1 原始问题

- `select_course()` 调用了 `_check_period_open()`，但 `drop_course()` **没有查询 `SelectionPeriod`**；
- 退课只校验教学班 `OPEN`、学期不是 `ENDED`、成绩非草稿，窗口关闭但教学班仍开放时仍可退课；
- 选课/退课/前端各自实现时间判断，容易不一致；
- 前端 `openPeriod` 只判断 ACTIVE + 起止时间，不判断限定年级和学期状态；
- 管理员窗口列表只显示人工维护的“状态”，没有显示“当前时间是否真正生效”；
- `SelectionPeriodCreate` 没有应用层 `end_time > start_time` 校验，非法时间依赖数据库约束，可能产生 500；
- 同一学期多个 ACTIVE 窗口重叠时没有明确规则。

### 1.2 根因

1. 选课与退课是两条独立校验路径，退课缺少窗口逻辑；
2. 窗口判断散落在 Service、前端 composable、页面 computed 中；
3. 窗口“状态”和“时间是否生效”混为一谈；
4. 缺少统一的窗口状态 DTO 与错误原因码；
5. 数据库/模型没有统一的年级+时间+学期判断入口。

---

## 2. 修复后的统一业务规则

### 2.1 选课与退课共同条件

以下条件必须全部满足：

1. 学期存在且状态为 **ACTIVE**；
2. 教学班存在且状态为 **ACTIVE**；
3. 教学班选课状态为 **OPEN**；
4. 至少存在一个窗口：`status=ACTIVE` 且 `start_time <= now <= end_time`；
5. 学生 `enrollment_year` 满足窗口 `target_grade_year`（`NULL` 表示全部年级）；
6. 学生本人/课程类型等业务条件满足。

退课额外条件：

- 必须选修课（必修/公共必修/实践由教务安排，学生不能自主退课）；
- 没有非草稿成绩；
- 教学班未关闭、未取消、学期未结束。

### 2.2 时间与边界

- 使用应用服务器本地时间与 MySQL `DATETIME` 直接比较，**不做时区换算**；部署环境必须保持同一时区（当前项目原有约定）。
- 边界包含：`now == start_time` 和 `now == end_time` 均视为开放。
- 状态不会随时间自动变化：ACTIVE 但时间已过 → 实际拒绝，学生端显示“选课已结束”，管理员端实际状态显示“已过期”。

### 2.3 多窗口重叠

- 同一学期多个 ACTIVE 窗口重叠时，后端采用**并集**：任一“时间在范围内且年级适用”的窗口开放即可选/退。
- 学生端展示开始时间最晚的那个适用窗口，并返回 `open_windows` 列表；
- 管理员端提示“检测到 N 组 ACTIVE 窗口时间重叠”，建议合并，但不强制修改已有数据；
- 不同学期窗口严格按 `semester` 隔离，不会串用。

### 2.4 管理员窗口实际状态

- 后端 `time_state`：`OPEN` / `NOT_STARTED` / `EXPIRED` / `INACTIVE`；
- `is_effective` 同时要求“时间开放 + 学期存在且 ACTIVE”；
- 管理员端“实际状态”列显示：生效中 / 已过期 / 未开始 / 未激活 / 学期不存在 / 学期PLANNED 等；
- 因此窗口“状态=进行中”但时间已过、或学期不存在时，管理员能直接看到不一致。

### 2.5 学生端交互

- 新增 `GET /api/v1/course-selections/window?semester=...`，返回 `can_select`、`can_drop`、`reason_code`、`reason`、`window`、`open_windows`；
- 学生端不再自行计算窗口；直接使用后端状态显示横幅和按钮可用性；
- 不可选/不可退时显示具体原因；必修课退课按钮禁用并提示“必修课由教务安排，不能自主退课”；
- 操作成功后重新加载可选列表、我的选课和窗口状态；
- 后端仍然是最终裁判，直接调用 API 无法绕过。

### 2.6 权限边界

- 学生自主退课：`selection:write` + 本人记录 + 必修/成绩/窗口校验；
- 管理员维护教学班名单：继续使用 FIX-002 的 `selection:manage` 手动添加/移除接口，不套用学生退课窗口规则；
- 两类操作没有混用权限：管理员维护名单不会被“学生窗口关闭/必修课”误拦截。

---

## 3. 修改文件与功能

### 3.1 后端

| 文件 | 变更 |
|---|---|
| `backend/app/services/selection.py` | 新增 `selection_window_status()`：统一学期/窗口/年级/时间判断；新增 `_check_selection_window()`；`select_course()` 和 `drop_course()` 统一调用；退课增加教学班 ACTIVE/OPEN、学期、窗口、年级、必修、成绩校验；支持时间边界与多窗口并集。 |
| `backend/app/api/v1/selection.py` | 新增 `GET /course-selections/window`；`SelectionPeriodCreate` 增加 `end_time > start_time` 校验；`SelectionPeriodOut` 增加 `time_state`、`term_status`、`is_effective`；`SelectionOut` 增加教学班状态/选课状态，供前端准确禁用退课。 |
| `docs/API.md` | 更新选课/退课/窗口接口说明，记录 FIX-003 规则。 |

### 3.2 前端

| 文件 | 变更 |
|---|---|
| `frontend/src/types/index.ts` | 新增 `SelectionWindowStatus`、`SelectionWindowInfo`；`SelectionPeriod` 增加实际状态字段；`Selection` 增加课程类型/教学班状态。 |
| `frontend/src/api/index.ts` | 新增 `selectionApi.windowStatus()`。 |
| `frontend/src/views/student/Selection.vue` | 使用后端窗口状态；显示开放/不可操作原因；选课/退课按钮按后端状态和课程类型禁用；必修课退课提示；操作后刷新。 |
| `frontend/src/views/admin/SelectionManage.vue` | “实际状态”列（含学期状态）；重叠窗口提示；开始/结束时间前端预校验。 |
| `docs/UAMS_教务管理系统用户操作手册.md` | 4.9.1/4.9.2 更新选课/退课规则、实际状态、重叠规则；12.3 标记“已修复 FIX-003”。 |

---

## 4. 数据库结构变化

**无。**

- 未新增字段、表、索引或迁移文件；
- 未修改 `uams` 或 `uams_test` 结构；
- 正式库仍为 `a5b7c9d1e2f3`，无 `course_selections.source`（FIX-002 迁移仍未应用到正式库）；
- 测试写入仅发生在 `uams_test` 和 `uams_restore_20261027` 隔离环境。

---

## 5. 测试结果

### 5.1 FIX-003 自动化测试（42 项全部通过）

测试库：`uams_test`（版本 `b1c2d3e4f5a6`）；测试数据前缀 `FIX003_`；测试后清理并恢复基线。

| # | 用例 | 结果 |
|---:|---|---|
| 1 | 正常窗口内选课 | PASS |
| 2 | 正常窗口内退课 | PASS |
| 3 | 窗口开始前选课/退课 | PASS（409；原因 NOT_STARTED） |
| 4 | 窗口结束后选课/退课 | PASS（409；原因 EXPIRED） |
| 5 | 窗口状态 PENDING / ACTIVE / CLOSED | PASS（PENDING/CLOSED → NO_ACTIVE_PERIOD；ACTIVE 正常） |
| 6 | 学期状态 PLANNED / ACTIVE / ENDED | PASS（PLANNED/ENDED → TERM_NOT_ACTIVE） |
| 7 | 限定年级匹配 / 不匹配 | PASS（不匹配 → GRADE_MISMATCH） |
| 8 | 多窗口重叠 | PASS（并集开放；`open_windows` 返回多个） |
| 9 | 不同学期窗口隔离 | PASS（不存在学期 → TERM_NOT_FOUND，不串用） |
| 10 | 必修课学生自行退课 | PASS（409） |
| 11 | 管理员维护必修课名单 | PASS（添加 201、移除 204） |
| 12 | 直接调用 API 绕过前端 | PASS（所有负向均通过 API 直接验证） |
| 13 | 窗口边界时刻 | PASS（开始/结束时刻可操作；前后 1 秒不可操作） |
| 14 | 选课/退课后的数据一致性 | PASS（记录 SELECTED→DROPPED；人数/状态正确） |

补充覆盖：

- 窗口 `end_time <= start_time` → 422；
- 管理员窗口 `time_state`：OPEN / NOT_STARTED / INACTIVE；
- 多窗口并集与 `open_windows`；
- 学期 PLANNED/ENDED；
- 必修课/成绩/教学班状态。

**FIX-003 汇总：42 通过，0 失败。**

### 5.2 回归测试

| 测试 | 结果 |
|---|---|
| FIX-001 邮箱治理 | 25 通过，0 失败 |
| FIX-002 必修课预安排/名单 | 36 通过，0 失败 |
| 前端 `npm run build`（含 `vue-tsc -b`） | 通过 |
| 后端 `compileall` | 通过 |
| `uams_test` `alembic check` | `No new upgrade operations detected.` |

### 5.3 浏览器验收（隔离环境）

环境：`uams_restore_20261027`（`b1c2d3e4f5a6`），新后端 `127.0.0.1:8000`（`APP_ENV=fix003-browser`），前端 `127.0.0.1:5173`，headless Chrome 155 + CDP。

| # | 场景 | 结果 |
|---:|---|---|
| 1 | 学生登录并进入在线选课 | PASS |
| 2 | 学生端显示“选课开放中”及截止时间 | PASS |
| 3 | 学生端显示可选选修课 | PASS |
| 4 | 浏览器内选课成功，我的选课出现该课程 | PASS |
| 5 | 必修课退课按钮禁用并显示“必修课由教务安排” | PASS |
| 6 | 浏览器内退课成功，我的选课移除该课程 | PASS |
| 7 | 关闭窗口后学生端显示“选课已结束” | PASS |
| 8 | 关闭窗口后选课按钮禁用 | PASS |
| 9 | 管理员登录并进入选课管理 | PASS |
| 10 | 管理员“实际状态”列显示“生效中/已过期” | PASS |
| 11 | 管理员端显示“1 组 ACTIVE 窗口时间重叠”提示 | PASS |

**浏览器汇总：11 通过，0 失败。** 使用真实 DOM 点击/输入，不是 API 冒充；但未做人眼截图/视觉检查。

补充说明：

- 浏览器验收使用恢复库中已有的 `UAT002_` 测试数据；测试期间将窗口 649 临时设为 CLOSED，结束后已恢复 ACTIVE；
- `UAT002_S1` 的选修课记录在浏览器内退课后为 `DROPPED`（隔离库测试数据，不影响正式库）；
- 正式库 `uams` 与 `uams_test` 未被修改。

---

## 6. 数据保护状态

| 库 | 状态 |
|---|---|
| `uams` | 版本 `a5b7c9d1e2f3`；无 `source`；users 8 / students 4 / teachers 3 / selections 5 / logs 22；未修改 |
| `uams_test` | 版本 `b1c2d3e4f5a6`；users 26 / students 20 / teachers 5 / selections 80 / logs 0 / selection_periods 1；测试后基线恢复，无 `FIX003_` 残留 |
| `uams_restore_20261027` | 版本 `b1c2d3e4f5a6`；窗口 649 已恢复 ACTIVE；仅保留既有 UAT002 测试数据 |

---

## 7. 未验证项目

| 项目 | 原因 |
|---|---|
| 人眼浏览器视觉/截图检查 | 使用 headless Chrome + CDP 做 DOM 验收，未做人眼视觉核对 |
| 正式库迁移后浏览器验收 | 正式库未迁移，按任务要求未执行 |
| 真实并发选课/退课压测 | 未做并发压力测试；沿用教学班行锁与动态计数 |
| 跨时区/夏令时 | 项目使用本地时间与 MySQL DATETIME 直接比较，未测试跨时区部署 |
| 长时间运行后的窗口边界漂移 | 未做长时间时钟漂移测试 |
| 浏览器自动化脚本入仓 | 临时脚本未提交；项目当前无持久化浏览器测试套件 |

---

## 8. Git 与交付

| 项 | 结果 |
|---|---|
| 分支 | `main` |
| 检查前基线 | `ff83cb8` |
| 修复代码提交 | `5d1284d8e905aefb0b8c8359b4cc76d27d16e57a` |
| 提交主题 | `fix: unify course selection and drop window checks` |
| 代码推送 | `git push origin main` 成功（`ff83cb8..5d1284d`） |
| 报告提交 | 见本次最终 Git 记录（`main` 最新提交） |
| 是否新建分支/worktree/PR | 否 |
| 是否 force push/reset | 否 |
| 正式库迁移 | 未执行 |

---

## 9. 结论

F-04 已修复：

- 选课和退课共用同一套后端窗口规则；
- 学期、窗口状态、当前时间、限定年级、教学班状态、必修/成绩全部统一校验；
- 学生端显示真实可操作状态与原因，管理员端显示实际生效状态和重叠提示；
- 直接 API 调用不能绕过；
- 42 项 FIX-003 测试、25 项 FIX-001 回归、36 项 FIX-002 回归、11 项浏览器验收全部通过；
- 无数据库结构变更，正式库未修改。

**FIX-003 完成，停止；不自动开始 FIX-004，不执行正式数据库迁移。**

> 报告结束。
> 本报告不包含数据库密码、连接密钥、JWT 或个人敏感数据。
