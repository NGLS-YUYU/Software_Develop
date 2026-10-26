# UAMS V3.1 全系统功能完整性审计报告

> 审计日期：2026-10-26
> 审计基线：`main` 分支，提交 `beb2105`（`不隔离`）
> 审计对象：UAMS 后端 API/Service/Model、前端页面与路由、数据库现状、`uams/docs/UAMS_教务管理系统用户操作手册.md` 第 12 章
> 审计方式：**只读审计**。本次未修改任何业务代码、数据库结构、系统配置或正式业务数据。
> 结论口径：只把“当前 `main` 代码能够证明的”内容写成结论；运行期未复现的项目单独标注。

---

## 0. 结论摘要

### 0.1 总体判断

1. 手册第 12 章列出的 **11 项问题，在 `main` 分支上全部仍然存在**，没有一项可以按“已修复”关闭。
2. 其中 4 项属于 **P0**：必修课预安排无前端入口、学生/教师档案邮箱异常导致 500、已审核成绩无更正流程、退课不校验选课时间窗口。
3. 除手册第 12 章外，本次另发现 **11 项**影响业务完整性、数据隔离或工程交付的问题（见第 4 章），合计 **22 项**发现。
4. 系统的主干闭环（组织机构 → 课程/培养方案 → 教学任务/教学班 → 排课 → 选修课选课 → 课表 → 成绩录入/审核 → 学生成绩/考试）在代码层面基本成立，但“必修课预安排”“成绩更正”“考试冲突检测”“业务审计日志”等关键环节仍不能由普通教务人员在前端独立完成。
5. 前端 `npm run build`（含 `vue-tsc -b`）通过；后端 `compileall` 通过；数据库连接可用，Alembic 位于 head `a5b7c9d1e2f3`。本次**未启动后端、未做浏览器端到端**，因此“可演示”结论均指代码路径与构建层面，答辩前仍应实际走一遍页面。

### 0.2 问题数量

| 优先级 | 数量 | 含义 |
|---|---:|---|
| P0 | 4 | 正式使用前必须修复；阻断核心业务闭环或造成明确数据正确性风险 |
| P1 | 9 | 应尽快修复；功能缺失/业务校验不完整/权限口径不一致 |
| P2 | 9 | 体验、展示、工程保障或非主干功能缺口 |
| **合计** | **22** | 不含纯文档措辞问题 |

### 0.3 最需要优先处理的 5 件事

1. **必修课预安排与教学班名单维护没有前端入口**（F-01 / F-12）：普通教务无法通过界面完成必修课名单，只能调接口或依赖种子数据。
2. **新增学生/教师时邮箱留空或重复会 500**（F-02）：连续录入无邮箱档案是常见操作，当前会失败且提示不直观。
3. **已审核成绩没有更正/撤销审核流程**（F-03）：成绩一旦通过，界面与 API 都没有合法更正路径，也没有变更历史。
4. **退课不校验选课时间窗口**（F-04）：选课窗口关闭但教学班仍为“选课中”时，学生仍可退课。
5. **默认学期由浏览器日期推断，而不是读取 ACTIVE 学期**（F-05）：教师成绩录入页没有学期选择器，学期不一致时可能直接“看不到教学班”。

---

## 1. 审计范围、基线与限制

### 1.1 Git 基线

| 项 | 结果 |
|---|---|
| 审计开始时所在分支 | `docs/user-manual`（工作区干净） |
| 目标分支 | `main` |
| `main` 与 `origin/main` | 一致，均为 `beb2105a0afacbc656d89ab3682662c7cf7533d2` |
| 审计执行分支 | `main`（已切换，未创建任何新分支、未创建 worktree） |
| 是否合并/变基/拣选其他分支 | 否 |
| 本次唯一纳入版本控制的写入 | 本审计报告文件 |

说明：

- 用户手册文件不在 `main` 上。本次从 `docs/user-manual` 分支的提交 `b3294ad` 只读读取 `uams/docs/UAMS_教务管理系统用户操作手册.md` 作为对照材料，**没有把手册或该分支的代码合入 `main`**。
- `docs/user-manual` 分支存在提交 `03e38c6`（`fix(selection): 修复选课开放但学生端无可选课程`），其中包含对选课可用列表的部分改进（补充学期 ACTIVE 条件、诊断摘要等），但**该提交不在 `main`**。因此本报告不把它计为“已修复”；它只能作为后续修复 F-06 时的参考。
- 本次审计的结论以 `main` 当前代码为准，不对手册本身的措辞做评价。

### 1.2 审计输入

| 类别 | 内容 |
|---|---|
| 后端 | `uams/backend/app/api/v1/*.py`、`services/*.py`、`models/*.py`、`schemas/*.py`、`core/*.py`、`alembic/versions/*` |
| 前端 | `uams/frontend/src/router/index.ts`、`api/index.ts`、`layouts/MainLayout.vue`、`views/{admin,teacher,student}/*.vue`、`composables/*.ts` |
| 数据库 | MySQL 8.4.11（本机 `uams` 库），只读查询 |
| 文档 | 用户操作手册第 12 章、`docs/API.md`、`docs/TESTING.md`、`CLAUDE.md` |
| 构建 | 前端 `npm run build`；后端 `python -m compileall`；`alembic current/heads` |

### 1.3 验证限制

- 后端服务未运行（`http://127.0.0.1:8000/health` 无响应），因此没有做真实 HTTP 登录、选课、成绩提交、考试排座等端到端验证。
- 数据库只做 `SELECT`，没有插入/更新/删除；因此“邮箱重复 500”“考试冲突”等需要构造异常数据的结论，依据是代码路径 + 手册已有的隔离库实测记录 + 只读数据核对。
- 当前库中只有 1 个独立管理员账号（`admin`，`user_type=ADMIN`），没有“教师兼任管理员”账号，因此 F-11 的双身份问题为代码与路由层验证，未做真实双身份登录复现。
- 本次没有自动化测试可运行。`docs/TESTING.md` 明确说明最终交付时已移除 `backend/tests/` 与端到端脚本。

---

## 2. 系统功能完整性矩阵

状态说明：

- **已实现**：数据库模型、后端 API/Service、前端入口、权限校验均存在，且代码路径自洽。
- **部分实现**：存在后端但缺前端入口，或前后端都有但业务校验/状态流转不完整。
- **未实现**：没有可用实现，或只有文档中的 planned 说明。
- **有缺陷**：功能存在，但已确认会导致错误结果、异常响应或权限/数据口径不一致。

### 2.1 业务链路矩阵

| 业务域 | 子功能 | 数据库/模型 | 后端 API/Service | 前端入口 | 权限/数据隔离 | 状态 |
|---|---|---|---|---|---|---|
| 组织机构 | 学院 CRUD | `colleges` | `organization.py` | `admin/Organization.vue` | `college:*` | 已实现 |
| 组织机构 | 专业 CRUD | `majors` | `organization.py` | `admin/Organization.vue` | `major:*` | 已实现 |
| 组织机构 | 行政班 CRUD | `classes` | `organization.py` | `admin/Organization.vue` | `class:*` | 已实现 |
| 组织机构 | 教室 CRUD | `classrooms` | `organization.py` | `admin/Organization.vue` | `classroom:*` | 已实现 |
| 人员 | 学生档案 + 账号联动 | `students` + `users` | `person.py::StudentService` | `admin/Students.vue` | `student:*` | 已实现（邮箱异常见 F-02） |
| 人员 | 教师档案 + 账号联动 | `teachers` + `users` | `person.py::TeacherService` | `admin/Teachers.vue` | `teacher:*` | 已实现（邮箱异常见 F-02） |
| 人员 | 学生/教师 Excel 导出 | — | 无 | 无 | `student:export` / `grade:export` 已定义但未使用 | 未实现（F-17） |
| 学期 | 学期 CRUD | `academic_terms` | `terms.py` | `admin/Terms.vue` | `term:*` | 已实现 |
| 学期 | 激活/结束、单 ACTIVE 约束 | `academic_terms` | `term.py` | `admin/Terms.vue` | `term:write` | 已实现 |
| 学期 | 当前学期统一识别 | — | 无 `/terms/active` | 各页用 `currentSemester()` | — | 未实现（F-05） |
| 课程 | 课程库 CRUD、学时/考核推导 | `courses` | `course.py` | `admin/Courses.vue` | `course:*` | 已实现 |
| 课程 | 先修课程 + 环路检测 | `course_prerequisites` | `course.py` | `admin/Courses.vue` | `course:write` | 已实现 |
| 培养方案 | 方案 CRUD + 方案课程 | `curriculum_plans` / `curriculum_courses` | `course.py` | `admin/Curriculum.vue` | `curriculum:*` | 已实现（管理端） |
| 培养方案 | 学生端查看培养方案 | 同上 | 后端可读（`_read`） | 无学生页面 | 学生有 `curriculum:read` | 部分实现（F-20） |
| 教学任务 | 任务 CRUD | `teaching_tasks` | `teaching.py` | `admin/Teaching.vue` | `teaching:*` | 部分实现（F-08：无编辑） |
| 教学班 | 教学班 CRUD、容量、教师 | `teaching_classes` | `teaching.py` | `admin/Teaching.vue` | `teaching:*` | 已实现 |
| 教学班 | 开放/关闭选课前置校验 | `teaching_classes` | `teaching.py` | `admin/Teaching.vue` / `SelectionManage.vue` | `selection:manage` | 已实现（但编辑表单可绕过，见 F-12） |
| 排课 | 排课 CRUD、教室/教师/班级冲突 | `schedules` | `teaching.py::ScheduleService` | `admin/Teaching.vue` | `schedule:*` | 已实现 |
| 必修课 | 按行政班/专业/学院预安排 | `course_selections` | `selection.py::assign_required` | **无** | `selection:manage` | 部分实现（F-01） |
| 教学班名单 | 添加/移除学生 | `course_selections` | `teaching.py::add_student/remove_student` | **无** | `selection:manage` | 部分实现（F-01） |
| 选修课 | 可选课程列表 | `teaching_classes` | `selection.py::available_classes` | `student/Selection.vue` | `get_current_user` | 有缺陷（F-06） |
| 选课 | 学期/窗口/容量/冲突/先修/重复 | `course_selections` | `selection.py::select_course` | `student/Selection.vue` | `selection:write` | 已实现 |
| 退课 | 窗口/学期/成绩/必修校验 | `course_selections` | `selection.py::drop_course` | `student/Selection.vue` | `selection:write` | 有缺陷（F-04） |
| 选课窗口 | 窗口 CRUD | `selection_periods` | `selection.py` | `admin/SelectionManage.vue` | `selection:manage` | 已实现 |
| 教师教学 | 我的课程、学生名单 | `teaching_classes` / `course_selections` | `teaching.py` / `selection.py` | `teacher/MyCourses.vue` | 教师本人 | 已实现 |
| 教师教学 | 我的课表 | `schedules` | `teaching_schedule.py` | `teacher/Schedule.vue` | 教师本人 | 已实现 |
| 教师教学 | 成绩录入/草稿/提交/导入 | `grades` | `grade.py` / `imports.py` | `teacher/GradeEntry.vue` | 教师本人 | 已实现（学期默认见 F-05） |
| 教师教学 | 教学评价查看 | `evaluations` | `misc.py` | `teacher/Evaluation.vue` | 教师本人 | 已实现 |
| 成绩审核 | 待审核、通过、驳回 | `grades` | `grade.py` | `admin/GradeApproval.vue` | `grade:approve` | 已实现 |
| 成绩更正 | 已审核成绩撤销/更正/历史 | `grades` | **无** | **无** | — | 未实现（F-03） |
| 学生成绩 | 已审核成绩查询 | `grades` | `grade.py` | `student/Grades.vue` | 学生本人 | 已实现 |
| 学生成绩 | GPA/学分 | `grades` / `students` | `gpa_service.py` | `student/Grades.vue` | 学生本人 | 已实现 |
| 学生成绩 | 班级/专业排名 | `grades` | `ranking_service.py` / `/grades/my` | 首页有；成绩页写死“—” | 学生本人 | 有缺陷（F-14） |
| 考试 | 考试 CRUD | `exams` | `exam.py` | `admin/Exams.vue` | `exam:*` | 已实现（更新时间校验见 F-19） |
| 考试 | 考场添加/容量 | `exam_rooms` | `exam.py` | `admin/Exams.vue` | `exam:write` | 已实现 |
| 考试 | 考场删除/修改/监考设置 | `exam_rooms` | **无删除/修改 API** | **无** | — | 未实现/部分实现（F-16） |
| 考试 | 自动排座 | `exam_students` | `exam.py::assign_seats` | `admin/Exams.vue` | `exam:write` | 已实现 |
| 考试 | 发布、学生查询 | `exams` / `exam_students` | `exam.py` | `student/Exams.vue` | `exam:read` | 已实现 |
| 考试 | 时间/考场/学生考试冲突 | — | **无** | **无** | — | 未实现（F-07） |
| 教学评价 | 学生评价提交 | `evaluations` | `misc.py` | `student/Evaluation.vue` | 学生本人 | 已实现 |
| 教学评价 | 评价任务管理 | `evaluation_tasks` | `misc.py::create_task` | **无** | `evaluation:manage` | 部分实现（F-10） |
| 教学评价 | 教师评价统计 | `evaluations` | `misc.py` | `teacher/Evaluation.vue` | 教师本人 | 已实现 |
| 公告 | 公告 CRUD/发布/撤回 | `announcements` | `misc.py` | `admin/AnnouncementManage.vue` | `announcement:write` | 已实现（双身份过滤见 F-11） |
| 统计 | 概览/成绩分布/选课排行 | 多表 | `misc.py` | `admin/Statistics.vue` | `statistics:read` | 已实现 |
| 批量导入 | 学生/教师/课程/成绩 | 多表 | `imports.py` / `import_service.py` | `admin/ImportCenter.vue` | 对应 write 权限 | 已实现 |
| 导出 | 学生/成绩/课程/选课结果 | — | 无 | 无 | 权限码已定义 | 未实现（F-17） |
| RBAC | 三角色、权限校验 | `roles` / `permissions` / `user_roles` | `deps.py` | 路由/菜单 | 已实现 | 已实现 |
| 双身份 | 教师兼任管理员 | `user_roles` | `user.py` | `AdminManage.vue` | 角色判定 | 部分实现（F-11） |
| 会话 | 登录、锁定、JWT | `users` | `auth.py` | `Login.vue` | — | 已实现（JWT 无服务端吊销，已知限制） |
| 操作日志 | 日志写入 | `operation_logs` | 仅 `user.py` | — | — | 部分实现（F-09） |
| 操作日志 | 日志查询 | `operation_logs` | `misc.py::/audit-logs` | 仅管理员变更弹窗 | `audit:read` | 部分实现（F-15） |
| 教学资料 | 上传/下载 | — | 无 | 无 | — | 未实现（F-21） |
| 调停课 | 申请/审核 | — | 无 | 无 | — | 未实现（F-22） |
| 工程质量 | 自动化测试 | — | 无 `backend/tests/` | — | — | 未实现（F-18，文档说明已移除） |

### 2.2 已实现 / 部分实现 / 未实现清单

**已实现（可作为答辩展示主干）**

- 学院、专业、行政班、教室 CRUD 与引用保护。
- 学生/教师档案与账号联动、默认密码、RBAC 角色关联。
- 学期 CRUD、激活/结束、单 ACTIVE 约束。
- 课程库、学时守恒、考核方式推导、先修课程及环路检测。
- 培养方案与方案课程管理（管理端）。
- 教学任务、教学班、排课、教室/教师/教学班冲突检测。
- 选修课选课：学期 ACTIVE、教学班 OPEN、容量、重复选课、同课程其他班、时间冲突、先修课程、并发行锁。
- 选课窗口 CRUD、开放/关闭教学班选课。
- 教师我的课程/名单/课表、成绩草稿/提交/Excel 导入。
- 教务待审核成绩、通过、驳回。
- 学生已审核成绩、GPA、学分、班级/专业排名（后端）。
- 考试创建、考场添加、自动排座、发布、学生查询。
- 公告 CRUD/发布/撤回（独立管理员）。
- 数据统计、批量导入、管理员授权/撤销/停用/重置密码。
- 前端构建、后端编译、Alembic head 一致。

**部分实现（有后端或部分前端，但业务不完整）**

- 必修课预安排：后端有接口，前端无入口；后端缺容量/学期/冲突校验（F-01/F-12）。
- 教学任务编辑：后端有 `PUT`，前端无按钮（F-08）。
- 已审核成绩更正：后端无接口、无历史表（F-03）。
- 默认学期：前端推断，无统一 ACTIVE 读取（F-05）。
- 学生可选列表：未校验选课窗口、限定年级、学期 ACTIVE（F-06）。
- 退课：未校验选课窗口（F-04）。
- 考试冲突：无时间/考场/学生考试冲突检测（F-07）。
- 教师兼任管理员：路由与授权可用，但多处按 `user_type` 过滤（F-11）。
- 操作日志：仅管理员权限变更写入；前端只有变更记录弹窗（F-09/F-15）。
- 教学评价任务：后端可创建，前端无管理页（F-10）。
- 考场管理：可添加，不能删除/修改/设置监考（F-16）。
- 对象级数据隔离：部分读接口范围过宽（F-13）。
- 学生端培养方案：后端可读，前端无入口（F-20）。

**未实现**

- 已审核成绩撤销/更正与变更历史（F-03）。
- 考试时间/考场/学生考试冲突检测（F-07）。
- 通用操作日志前端独立查询页面（F-15）。
- Excel 导出（F-17）。
- 自动化测试（F-18）。
- 教学资料上传/下载（F-21）。
- 调停课申请/审核（F-22）。
- 学生端培养方案页面（F-20，后端有读接口，前端无入口）。

---

## 3. 手册第 12 章 11 项逐项复核

> 复核方法：逐项读当前 `main` 代码，不照抄手册结论。
> “状态”使用任务要求的六类：完全未实现 / 后端已实现、前端未实现 / 前后端均实现但业务不完整 / 数据展示缺陷 / 已修复 / 尚未验证。

### 3.1 汇总表

| 手册项 | 问题 | 复核状态 | 对应发现 | 优先级 |
|---|---|---|---|---|
| 12.1 | 学生“我的成绩”页排名固定显示“—” | 数据展示缺陷 | F-14 | P2 |
| 12.2 | 必修课预安排只有后端接口，没有前端入口 | 后端已实现、前端未实现 | F-01 / F-12 | P0 / P1 |
| 12.3 | 退课不校验选课时间窗口 | 前后端均实现但业务不完整 | F-04 | P0 |
| 12.4 | 默认学期按浏览器日期推断 | 前后端均实现但业务不完整 | F-05 | P1 |
| 12.5 | 可选列表不校验限定年级 | 前后端均实现但业务不完整 | F-06 | P1 |
| 12.6 | 已审核成绩没有更正入口 | 完全未实现 | F-03 | P0 |
| 12.7 | 通用操作日志只有后端接口，没有前端页面 | 后端已实现、前端未实现 | F-15 / F-09 | P2 / P1 |
| 12.8 | 教学任务没有前端编辑入口 | 后端已实现、前端未实现 | F-08 | P1 |
| 12.9 | 考试管理不检测时间/考场冲突 | 前后端均实现但业务不完整 | F-07 | P1 |
| 12.10 | 教师兼任管理员公告/数据过滤异常 | 前后端均实现但业务不完整 | F-11 | P1 |
| 12.11 | 邮箱留空或重复时新增档案 500 | 前后端均实现但业务不完整 | F-02 | P0 |

**复核结论：11 项均可在当前代码中复现其根因，未发现应标记为“已修复”的项。**
其中 12.5 在 `docs/user-manual` 分支的 `03e38c6` 中有部分改进（给可选列表增加学期 ACTIVE 条件、增加诊断接口），但该提交不在 `main`；即使合入，也仍未校验 `target_grade_year`，不能整体关闭 12.5。

### 3.2 12.1 学生“我的成绩”页排名固定显示“—”

**状态：数据展示缺陷**

证据：

- 前端 `frontend/src/views/student/Grades.vue:38-39` 只调用 `gradeApi.mine()` 和 `gradeApi.mySummary()`；没有调用返回排名的 `/grades/my`。
- 同文件 `frontend/src/views/student/Grades.vue:63-69` 的“班级排名”“专业排名”两个值直接写死为 `—`。
- 后端 `backend/app/api/v1/grade.py:164` 的 `GET /grades/my` 确实返回 `class_rank`、`major_rank`；`backend/app/services/grade.py:366-390` 用 `RankingService` 实时计算。
- 学生首页 `frontend/src/views/student/Dashboard.vue:59` 调用了 `gradeApi.my()`，并在 `:68-69` 使用排名，所以首页能显示，成绩页不能。

影响：学生无法在“我的成绩”页看到排名，只能回首页；两个页面数据源不一致，容易让答辩演示自相矛盾。

补充：`GradeSummary` 类型（`frontend/src/types/index.ts:324-330`）本身不含排名字段，说明成绩页当初就按“汇总接口”设计，未接入 `/grades/my`。

### 3.3 12.2 必修课预安排只有后端接口，没有前端入口

**状态：后端已实现、前端未实现（后端校验也不完整，见 F-12）**

证据：

- 后端存在：
  - `POST /api/v1/teaching-classes/{class_id}/assign-required`（`backend/app/api/v1/selection.py:247-263`，权限 `selection:manage`）；
  - `POST /api/v1/teaching-classes/{class_id}/students`（同文件 `:212-229`）；
  - `DELETE /api/v1/teaching-classes/{class_id}/students/{student_id}`（同文件 `:232-243`）。
- 服务层 `backend/app/services/selection.py:267-344` 实现按 `class_id > major_id > college_id` 预排；`backend/app/services/teaching.py:478-518` 实现添加/移除学生。
- 前端检索 `assign-required`、`assignRequired`、`addStudent`、`removeStudent`：**没有任何调用**。
- 前端 `frontend/src/views/admin/SelectionManage.vue:72` 只调用 `teachingApi.students(row.id)` 查看名单；`:248`、`:300` 的操作列只有“名单/开放/关闭”。
- 前端 `frontend/src/api/index.ts:144-176` 的 `teachingApi` 也没有 `assignRequired`、`addStudent`、`removeStudent` 方法。

影响：

- 普通教务人员无法通过界面完成必修课名单生成；必修课学生名单只能依赖后端接口、种子数据或数据运维。
- 由于学生端选课只允许选修课（`backend/app/services/selection.py:148-150`），必修课没有预排就没有学生，后续“教师名单 → 成绩录入 → 教务审核”链路在真实使用中会断。
- 手册的“临时办法：由技术人员确认名单生成方式”仍然成立。

后端校验缺口（F-12）：

- `assign_required()`（`backend/app/services/selection.py:267-344`）没有校验教学班容量、教学班状态、学期是否 ACTIVE、学生与已有课程的时间冲突；循环中直接创建选课记录，可能超出容量或排入已结束学期。
- 对比手工添加学生 `TeachingClassService.add_student()`（`backend/app/services/teaching.py:478-518`）有容量校验，说明预排路径与手工路径的规则不一致。
- 教学班编辑接口 `PUT /teaching-classes/{id}`（`backend/app/api/v1/teaching.py:217-227`）允许直接提交 `selection_status=OPEN`；服务层 `update_class()`（`backend/app/services/teaching.py:356-410`）没有复用 `open_selection()`（同文件 `:466-476`）的“必须有教师、必须有排课”校验。前端编辑弹窗也确实提供了选课状态下拉（`frontend/src/views/admin/Teaching.vue:652-658`），因此可以绕过开放选课的业务前置条件。

### 3.4 12.3 退课不校验选课时间窗口

**状态：前后端均实现但业务不完整**

证据：

- `backend/app/services/selection.py:225-263` 的 `drop_course()`：
  - 校验记录存在、属于本人、状态为 `SELECTED`；
  - 校验选修课（必修课不能自主退选）；
  - 校验教学班 `selection_status == "OPEN"`（`:244-245`）；
  - 校验学期不是 `ENDED`（`:248-249`）；
  - 校验没有非草稿成绩（`:252-259`）；
  - **没有查询 `SelectionPeriod`，没有调用 `_check_period_open()`**。
- 对比选课 `select_course()` 在 `:152` 调用了 `_check_period_open()`，其实现位于 `:83-92`，会校验 `SelectionPeriod.status`、起止时间、`target_grade_year`。

影响：管理员关闭选课窗口但忘记把教学班改成“未开放”时，学生仍可退课。手册的“关闭窗口时同时关闭教学班”只是操作规避，不是系统校验。

### 3.5 12.4 默认学期按浏览器日期推断

**状态：前后端均实现但业务不完整**

证据：

- `frontend/src/composables/useSemester.ts:7-15` 的 `currentSemester()` 按 `new Date()` 推断：9 月—次年 1 月为第一学期，2—8 月为第二学期。
- 直接使用 `currentSemester()` 且**没有学期选择器**的页面：
  - 教务工作台 `frontend/src/views/admin/Dashboard.vue:30`（选课排行）；
  - 学生首页 `frontend/src/views/student/Dashboard.vue:10,56,57`（课表、考试）；
  - 学生教学评价 `frontend/src/views/student/Evaluation.vue:29`；
  - 教师工作台 `frontend/src/views/teacher/Dashboard.vue:10,35,36`；
  - 教师成绩录入 `frontend/src/views/teacher/GradeEntry.vue:85`（只按 `currentSemester()` 加载教学班，页面没有学期下拉框）；
  - 顶栏学期 chip `frontend/src/layouts/MainLayout.vue:18`。
- 有学期选择器的页面（可手动纠正）：教务开课排课/选课管理/数据统计/考试管理；学生选课/课表/考试；教师我的课程/课表。
- 后端没有 `/terms/active` 或 `GET /terms/current` 接口；`backend/app/api/v1/terms.py` 只有列表/详情/CRUD/activate/end，列表支持 `status` 过滤但没有“当前”语义。

影响：学校实际 ACTIVE 学期与浏览器日期不一致（提前开学、补录、跨年、演示数据写死 2026-2027-1 等）时，无选择器的页面会默认到错误学期，表现为“学生看不到课程/考试”“教师看不到教学班/成绩单为空”。教师成绩录入页没有选择器，是影响最大的一个。

### 3.6 12.5 学生可选列表不校验“限定年级”

**状态：前后端均实现但业务不完整**

证据：

- `backend/app/services/selection.py:348-390` 的 `available_classes()` 只按：
  - `TeachingClass.semester == semester`；
  - `selection_status == "OPEN"`；
  - `status == "ACTIVE"`；
  - 课程性质为选修；
  - 排除已选教学班/已选课程；
  - 可选关键字过滤。
  它**没有查询 `SelectionPeriod`**，因此不校验窗口是否开放、是否在起止时间内、`target_grade_year` 是否匹配；也**没有要求学期为 ACTIVE**。
- 选课提交 `select_course()` 在 `:144-152` 校验学期 ACTIVE、教学班 OPEN，并调用 `_check_period_open()`；`SelectionPeriod.is_open_now()`（`backend/app/models/selection.py:103-109`）会校验限定年级。
- 前端 `frontend/src/views/student/Selection.vue:22-28` 的 `openPeriod` 只判断 `status === 'ACTIVE'` 和起止时间，不判断 `target_grade_year`；页面会显示“选课开放中”的绿色提示，即使当前学生不在限定年级。
- 前端可选卡片（同文件 `:146-229`）只按 `c.remaining <= 0` 禁用选课按钮，没有年级/窗口资格维度。

影响：

- 限定年级窗口下，不符合年级的学生会看到课程，点击后后端返回“当前不在选课时间内”，提示与页面状态矛盾。
- 非 ACTIVE 学期（PLANNED/ENDED）的教学班如果仍为 OPEN，也会出现在可选列表，但提交必然失败；这是比手册描述更广的“看得到但选不了”。
- `docs/user-manual` 的 `03e38c6` 已给 `available` 增加学期 ACTIVE 条件，但未合入 `main`，且仍未处理 `target_grade_year`。

### 3.7 12.6 已审核成绩没有更正入口

**状态：完全未实现**

证据：

- 教师侧 `backend/app/services/grade.py:157-201` 的 `save_scores()` 明确拒绝 `APPROVED`（`:170-171`）和 `SUBMITTED`（`:172-173`）。
- 教务侧 `backend/app/services/grade.py:295-324` 的 `approve()` / `reject()` 都要求记录状态为 `SUBMITTED`；没有 `unapprove()`、`correct()`、`reopen()` 之类方法。
- `backend/app/api/v1/grade.py` 的写接口只有：
  - `PUT /grades`（保存草稿，`save_scores` 拒绝已审核）；
  - `POST /grades/teaching-classes/{id}/submit`；
  - `POST /grades/approve`；
  - `POST /grades/reject`；
  - `DELETE /grades/{id}`（`delete_draft`，只允许 DRAFT，见 `backend/app/services/grade.py:203-225`）。
- `frontend/src/views/teacher/GradeEntry.vue:317-319` 明确提示“成绩已审核通过，不可直接修改。如需更正请联系教务”；但教务端 `frontend/src/views/admin/GradeApproval.vue:28` 只查询 `gradeApi.pending()`（即 `SUBMITTED`），页面没有已审核成绩列表、撤销通过或更正按钮。
- 数据库 `grades` 表只有 `approved_by` / `approved_at` / `reject_reason` 等字段（`backend/app/models/grade.py:190-202`），没有成绩变更历史表；`operation_logs` 也没有成绩更正的写入点（见 F-09）。

影响：已通过成绩的错误只能由技术人员直接改库，无法保留“谁在何时因何原因改了什么”的审计链。对教务系统这是数据正确性与合规风险，不是普通体验问题。

### 3.8 12.7 通用操作日志只有后端接口，没有前端独立查询页面

**状态：后端已实现、前端未实现（且日志覆盖不足，见 F-09）**

证据：

- 后端 `GET /api/v1/audit-logs` 位于 `backend/app/api/v1/misc.py:453-478`，支持 `action`、`user_id`、`resource_type`、`resource_id` 过滤，权限 `audit:read`。
- 前端 `frontend/src/api/index.ts:240-241` 有 `adminApi.auditLogs()`。
- 唯一调用点是 `frontend/src/views/admin/AdminManage.vue:206-210`，固定传 `resource_type: 'user'`、`resource_id: 当前管理员`，用于“变更记录”弹窗。
- `frontend/src/router/index.ts:124-222` 没有任何“操作日志”路由；菜单由路由表生成（`MainLayout.vue:35-46`），因此也没有菜单。
- 日志写入点只有 `backend/app/services/user.py:202-217` 的 `_log()`，记录 `ADMIN_GRANT` / `ADMIN_REVOKE` / `ADMIN_ENABLE` / `ADMIN_DISABLE`。`backend/app/api/v1/auth.py:63-68` 的 `logout()` docstring 说“预留此接口是为了记录退出操作日志”，但方法体只 `return None`，没有写日志。

只读数据库核对：`operation_logs` 共 22 条，按 `action` 分组为 `ADMIN_GRANT 7`、`ADMIN_REVOKE 12`、`ADMIN_DISABLE 1`、`ADMIN_ENABLE 1`、`LOGIN 1`。其中 `LOGIN` 在**当前代码中找不到写入路径**，疑为历史数据或人工测试残留；这不能作为“登录已记日志”的证据。

影响：无法通过界面查询学生、课程、选课、成绩、考试、导入等业务操作；即使查到了，当前系统也没有为这些操作写日志。

### 3.9 12.8 教学任务没有前端编辑入口

**状态：后端已实现、前端未实现**

证据：

- 后端 `PUT /api/v1/teaching-tasks/{task_id}` 位于 `backend/app/api/v1/teaching.py:122-132`，权限 `teaching:write`。
- 后端 `TeachingTaskUpdate` 只允许改 `planned_classes`、`status`（`backend/app/schemas/teaching.py:16-18`）；`semester`、`course_id`、`college_id` 不可改。
- 前端 `frontend/src/api/index.ts:148-149` 有 `updateTask()`，但全前端检索 `updateTask` **只有定义、没有调用**。
- 前端 `frontend/src/views/admin/Teaching.vue:545` 和 `:582` 的教学任务表格/卡片操作列只有“删除”；没有“编辑”按钮或编辑弹窗。
- 任务删除受引用保护：`backend/app/services/teaching.py:208-215` 在任务下已有教学班时拒绝删除。因此任务一旦建了教学班，既不能编辑也不能删除，只能改库。

影响：修改计划开班数或任务状态只能删除重建；已有教学班时无法操作。手册的“临时办法”仍然成立。

### 3.10 12.9 考试管理不自动检测考试时间/考场冲突

**状态：前后端均实现但业务不完整**

证据：

- `backend/app/api/v1/exam.py:185-205` 的 `create_exam()` 只校验教学班存在、同教学班同类型考试唯一；时间只由 `ExamCreate.check_time()`（`:32-36`）校验 `end_time > start_time`。
- `backend/app/api/v1/exam.py:239-264` 的 `add_room()` 只校验教室存在、容量不超过教室容量、同一考试不重复添加同一教室；**没有查询其他考试在同一教室/同一时间的占用，也没有查询与上课排课的冲突**。
- `backend/app/api/v1/exam.py:208-222` 的 `update_exam()` 只做 `setattr`，没有重新校验时间顺序、考场冲突、考试状态与考场存在性。
- `backend/app/api/v1/exam.py:268-318` 的 `assign_seats()` 只按教学班已选学生顺序排座，没有校验同一学生同一天同一时段是否已有其他考试（学生考试冲突）。
- 前端 `frontend/src/views/admin/Exams.vue:302-338` 的考场弹窗只有“添加考场”和列表，没有冲突提示；表单也没有冲突预检。

影响：可能排出同一教室同一时间的多场考试、考试与上课冲突、同一学生同时参加两场考试；只能由教务人工核对。

### 3.11 12.10 教师兼任管理员时公告权限/数据过滤异常

**状态：前后端均实现但业务不完整**

证据（公告）：

- `backend/app/api/v1/misc.py:288-308` 的 `list_anns()` 用 `current.user_type != UserType.ADMIN` 判断是否过滤；`:296-301` 对非 ADMIN 只返回 `PUBLISHED` 且 `target_type in ("ALL", "STUDENT"/"TEACHER")`。
- 教师兼任管理员的 `user_type` 仍是 `TEACHER`，因此即使拥有 `ACADEMIC_ADMIN` 角色，也会被当作普通教师过滤：看不到 `DRAFT`、`WITHDRAWN`，也看不到 `target_type=STUDENT` 的公告。
- 更关键的是，公告创建接口 `AnnCreate`（`backend/app/api/v1/misc.py:253-257`）**没有 `status` 字段**，新建公告一律落为模型默认的 `DRAFT`（`backend/app/models/misc.py:134-137`）。前端 `AnnouncementManage.vue:12` 虽然表单里有 `status: 'DRAFT'`，但后端会忽略；教师兼任管理员创建后刷新列表，草稿不可见，容易误判“发布失败”。

证据（不止公告）：

- 教学班名单 `backend/app/api/v1/selection.py:170-200` 在 `current.user_type == UserType.TEACHER` 时强制 `tc.teacher_id == 本人教师 id`；教师兼任管理员在教务端查看其他教学班名单会被 403。
- 成绩单/名单/统计 `backend/app/api/v1/grade.py:189-218`、`:317-325` 同样按 `user_type == TEACHER` 强制“本人授课教学班”，教师兼任管理员在教务端查看其他班成绩会被 403。
- 评价统计 `backend/app/api/v1/misc.py:200-222` 在 `user_type == TEACHER` 时只统计本人评价，教师兼任管理员无法看全校。
- 前端路由明确允许双身份进入教务端：`frontend/src/router/index.ts:127-128` 使用 `roles: ['ADMIN','ACADEMIC_ADMIN']`；`frontend/src/stores/auth.ts:38-44` 的 `identities` 把角色并入访问身份；`MainLayout.vue:142-144` 提供“切换到教务控制台”。因此这是前端已经承诺、后端未完全兑现的能力。

影响：教师兼任管理员可以进入教务端，但公告草稿/学生公告、其他班名单、其他班成绩、全校评价统计等会异常缺失或 403。权限判定口径应统一为“权限码/角色”，`user_type` 只用于“教师本人数据”场景。

### 3.12 12.11 邮箱留空或重复时新增档案 500

**状态：前后端均实现但业务不完整**

证据：

- 前端新增学生表单初始值 `email: ''`（`frontend/src/views/admin/Students.vue:21`），新增教师同理（`frontend/src/views/admin/Teachers.vue:14`）；提交走 `useCrudTable.save()`（`frontend/src/composables/useCrudTable.ts:73-93`），没有把空字符串转成 `null`。
- 后端 `StudentCreate.email` / `TeacherCreate.email` 是 `str | None`（`backend/app/schemas/person.py:18`、`:69`），Pydantic 接受 `""`，不会自动转 `None`。
- `StudentService.create_student()`（`backend/app/services/person.py:70-80`）和 `TeacherService.create_teacher()`（同文件 `:179-188`）把 `data.get("email")` 原样写入 `User.email`，随后 `self.db.flush()` 写用户。
- `users.email` 有唯一约束（`backend/app/models/user.py:66-68`）。MySQL 唯一索引允许多个 `NULL`，但**不允许多个空字符串 `''`**；第二个空邮箱或重复非空邮箱会在 `flush()` 抛 `IntegrityError`。
- `BaseCrudService._commit()`（`backend/app/services/base.py:126-138`）只捕获 `commit()` 阶段的 `IntegrityError`；创建路径的冲突发生在 `flush()`，没有被捕获，也没有全局 `IntegrityError` 处理器（`backend/app/main.py:31-56` 只处理 `HTTPException` 和 `RequestValidationError`），因此返回 500。
- 手册 12.11 记录隔离库实测：第一个空邮箱学号 `99000001` 返回 201，第二个 `99000002` 返回 500；第一个 `duplicate@example.com` 返回 201，第二个同学号段返回 500。本次只读核对当前 `uams` 库：`email=''` 的用户 0 个，`email IS NULL` 4 个，说明现有数据尚未触发；但代码路径仍然存在。

影响：连续录入多个没有邮箱的学生/教师，或误填重复邮箱时，保存失败且提示为 500，不是“邮箱已存在”的友好 409。

---

## 4. 手册之外的新增发现

### 4.1 F-09 业务操作日志覆盖严重不足（P1）

- `operation_logs` 模型（`backend/app/models/misc.py:142-179`）字段齐全：用户、用户名快照、动作、模块、资源、详情、IP、UA、结果、时间。
- 但当前代码中唯一写入点是 `backend/app/services/user.py:202-217` 的 `_log()`，只覆盖管理员授予/撤销/启停。
- 登录成功/失败、退出、学生/教师/课程/教学班/排课的增删改、选课/退课、成绩提交/审核/驳回、考试发布、批量导入等**均未写操作日志**。
- `backend/app/api/v1/auth.py:63-68` 的退出接口 docstring 声称“为了记录退出操作日志”，但方法体没有写日志；登录 `backend/app/services/auth.py:52-90` 也没有写日志。
- 只读库核对：22 条日志中 21 条为 `ADMIN_*`，1 条 `LOGIN` 无对应代码路径（疑为历史数据）。

影响：CLAUDE.md §23/§24 要求的操作日志无法作为业务审计依据；发生成绩争议、误删、越权时无法追溯。

### 4.2 F-10 教学评价任务无前端管理页面（P1）

- 后端 `POST /api/v1/evaluations/tasks`（`backend/app/api/v1/misc.py:82-96`）支持创建评价任务，权限 `evaluation:manage`，但前端 `evaluationApi.createTask()`（`frontend/src/api/index.ts:317-318`）**没有任何调用点**。
- `frontend/src/router/index.ts` 没有教务端“教学评价任务”路由；学生端 `student/Evaluation.vue:29` 只能读取已有任务。
- 演示库中的评价任务来自 `backend/scripts/seed_demo.py:464` 的种子数据，不是教务通过界面创建的。

影响：新学期/新评价周期无法由教务在界面开启评价；只能改库或重新跑种子脚本。学生评价、教师统计因此依赖预置任务。

### 4.3 F-12 教学班/预排后端校验缺口（P1）

除 3.3 已列的 `assign_required()` 缺容量/学期/冲突校验外：

- `PUT /teaching-classes/{id}` 允许直接写 `selection_status`（`backend/app/schemas/teaching.py:44-53`），服务层 `update_class()`（`backend/app/services/teaching.py:356-410`）没有复用 `open_selection()`（`:466-476`）的“必须有教师、必须有排课”校验。前端编辑弹窗确实提供选课状态下拉（`frontend/src/views/admin/Teaching.vue:652-658`），因此可以绕过开放选课的前置条件。
- `remove_student()`（`backend/app/services/teaching.py:520-535`）不检查该生是否已有成绩；教务可把已有成绩的学生从教学班移除，成绩仍留在 `grades` 表，造成名单与成绩不一致。
- `assign_required()` 不做事务分段/结果明细，失败时只返回 409，无法告诉教务哪些学生因容量/冲突被跳过。

影响：预排/名单维护可能产生超容、空教师/空排课却开放选课、名单与成绩不一致等数据问题。

### 4.4 F-13 对象级数据隔离不足（P1）

以下接口只做“已登录”校验，没有按角色/对象收紧：

- `GET /api/v1/teaching-classes`（`backend/app/api/v1/teaching.py:148-176`）与 `GET /teaching-classes/{id}`（同文件 `:195-199`）使用 `_read = Depends(get_current_user)`（`:32`），学生也能列出全校教学班、已选人数与排课。
- `GET /api/v1/schedules/students/{student_id}`（`backend/app/api/v1/schedule.py:130-158`）只禁止学生查他人，**教师可查任意学生课表**，没有限制“本人授课教学班的学生”。
- `GET /api/v1/exams`（`backend/app/api/v1/exam.py:112-135`）使用 `exam:read`；学生角色拥有该权限（`backend/scripts/seed_rbac.py:93`），因此学生可通过 API 看到全校考试（包括 `DRAFT`），而前端只使用 `/exams/mine`。
- `GET /api/v1/students/{id}`（`backend/app/api/v1/person.py:99-108`）只限制学生只能看自己；教师可看任意学生档案，未限制为其授课学生。
- `GET /api/v1/teachers/{id}`（`backend/app/api/v1/person.py:174-181`）只要求登录，任意学生可看任意教师档案。

影响：与 CLAUDE.md §9“教师只能访问自己授课课程对应的学生；学生只能访问自己的信息/课表/成绩/考试”不完全一致。前端没有暴露这些路径，但后端 API 是最终边界，属于越权读取风险。

### 4.5 F-16 考试考场无法删除/修改、监考教师无法在界面设置（P2）

- 后端 `backend/app/api/v1/exam.py` 只有 `POST /exams/{id}/rooms`（`:238-264`），没有 `DELETE /exams/{id}/rooms/{room_id}`、`PUT /exams/{id}/rooms/{room_id}`。
- `ExamRoomCreate` 有 `invigilator_id`（`:76-79`），但前端 `frontend/src/views/admin/Exams.vue:20` 的 `roomForm` 只有 `classroom_id`、`capacity`，没有监考教师选择；后端 `_room_out`（`:87-91`）也没有返回监考教师姓名。
- 前端考场弹窗（`Exams.vue:302-338`）只有添加和列表，没有删除/修改按钮。

影响：考场选错或容量填错只能删除整场考试重建；监考教师无法通过界面维护。

### 4.6 F-17 Excel 导出缺失（P2）

- CLAUDE.md §22 要求学生名单、成绩、课程、选课结果的 Excel 导出；后端权限码 `student:export`、`grade:export` 已在 `backend/scripts/seed_rbac.py:35`、`:63` 定义。
- 后端没有任何导出 endpoint；`docs/API.md:519` 明确把 Excel 导出列为“V0.2 planned”，`docs/API.md:521-523` 还把教学资料、调停课、学生端培养方案列为 planned。
- 前端只有 `ImportCenter.vue` 的模板下载和上传，没有导出按钮；`studentApi` / `gradeApi` 没有 export 方法。

影响：教务无法从界面导出名单/成绩/课程/选课结果，只能查库或自行写脚本；对正式教务使用是明显缺口。

### 4.7 F-18 自动化测试缺失（P2）

- `docs/TESTING.md:3-8` 明确说明最终交付时移除了 `backend/tests/` 与端到端脚本；`backend/tests/` 目录不存在。
- 当前 `requirements.txt` 也没有把 `pytest` 作为运行依赖（虽然虚拟环境可能残留测试库）。
- 本次只能做前端构建、后端编译、只读数据库核对，无法执行回归用例。

影响：任何修复都缺少自动化回归保护；选课并发、成绩状态机、权限边界等高风险逻辑只能靠人工验证。

### 4.8 F-19 修改考试缺少应用层校验，可能 500（P2）

- `ExamUpdate`（`backend/app/api/v1/exam.py:39-44`）没有 `model_validator`；`update_exam()`（`:208-222`）直接把非空字段 `setattr` 后 `commit()`。
- 数据库有 `CheckConstraint("end_time > start_time")`（`backend/app/models/exam.py:47`）。如果管理员把结束时间改到开始时间之前，`commit()` 抛 `IntegrityError`，`exam.py` 没有捕获，`main.py` 也没有全局 `IntegrityError` 处理器，返回 500。
- `update_exam()` 允许直接把 `status` 改为 `PUBLISHED`，绕过 `publish()`（`:323-335`）的“必须已设置考场”校验。
- `duration_minutes` 与 `start_time`/`end_time` 的时长没有一致性校验。

影响：考试时间编辑可能 500；可能发布无考场考试；考试时长字段可能与实际时间不一致。

### 4.9 F-20 学生端培养方案只有后端读接口（P2）

- 后端 `GET /curriculum-plans`、`GET /curriculum-plans/{id}`、`GET /curriculum-plans/{id}/courses` 使用 `_read = Depends(get_current_user)`（`backend/app/api/v1/course.py:150-176`、`:204-221`），学生角色也有 `curriculum:read`（`backend/scripts/seed_rbac.py:85`）。
- 前端 `frontend/src/router/index.ts` 的学生端只有首页/信息/课表/选课/成绩/考试/评价/公告，没有培养方案页面；`docs/API.md:521` 也把“学生端培养方案查询”列为 planned。

影响：学生端无法查看培养方案；后端接口存在但未形成业务入口。

### 4.10 F-21 教学资料上传/下载未实现（P2）

- `docs/API.md:520` 明确列为 `V0.2+ planned`；代码中没有教学资料模型、API 或前端页面。
- CLAUDE.md §29 的“教学资料”属于教师侧扩展，不属于本次主干闭环，但对“完整教务系统”宣称有影响。

### 4.11 F-22 调停课申请/审核未实现（P2）

- `docs/API.md:521` 明确列为 `V0.2+ planned`；代码中没有调课/停课/补课申请模型、状态机、API 或页面。
- 当前排课只能由教务直接增删改，没有教师发起、教务审核的流程。

---

## 5. P0 / P1 / P2 优先级划分

### 5.1 P0（4 项）

| ID | 问题 | 主要证据 | 为什么是 P0 |
|---|---|---|---|
| F-01 | 必修课预安排/教学班名单维护无前端入口 | `selection.py:247-263`、`selection.py:212-243`；前端无调用 | 普通教务无法完成必修课名单，主干闭环断裂 |
| F-02 | 新增学生/教师空/重复邮箱 500 | `person.py:70-80`、`:179-188`；`base.py:126-138`；前端 `email: ''` | 常见录入操作直接失败，且错误不可理解 |
| F-03 | 已审核成绩无更正流程 | `grade.py:295-324`；`GradeApproval.vue:28`；无历史表 | 成绩错误只能改库，破坏数据正确性与审计 |
| F-04 | 退课不校验选课时间窗口 | `selection.py:225-263`（无 `SelectionPeriod`） | 违反选课窗口规则，可能产生非预期退课 |

### 5.2 P1（9 项）

| ID | 问题 | 影响 |
|---|---|---|
| F-05 | 默认学期按浏览器日期推断，无 ACTIVE 学期 API | 学期不一致时多个页面空白/错学期；成绩录入页无选择器 |
| F-06 | 可选列表不校验窗口/限定年级/学期 ACTIVE | 学生看到课程但选不了；跨学期展示 |
| F-07 | 考试无时间/考场/学生考试冲突检测 | 教室/学生时间冲突，需人工核对 |
| F-08 | 教学任务无前端编辑 | 只能删除重建；有教学班时无法删除 |
| F-09 | 业务操作日志覆盖不足 | 无法追溯选课/成绩/导入等关键操作 |
| F-10 | 教学评价任务无前端管理 | 新评价周期无法由教务开启 |
| F-11 | 教师兼任管理员多处按 `user_type` 过滤 | 公告、名单、成绩、评价统计异常或 403 |
| F-12 | 教学班/预排后端校验缺口 | 超容、空教师/空排课开放选课、名单与成绩不一致 |
| F-13 | 对象级数据隔离不足 | 学生可读全校教学班/考试，教师可查任意学生课表/档案 |

### 5.3 P2（9 项）

| ID | 问题 | 影响 |
|---|---|---|
| F-14 | 学生成绩页排名固定“—” | 展示不完整，首页/成绩页不一致 |
| F-15 | 通用操作日志无独立前端页面 | 无法查询管理员变更之外的日志 |
| F-16 | 考场不能删除/修改、监考不能设置 | 只能删考试重建 |
| F-17 | Excel 导出缺失 | 名单/成绩/课程/选课结果无法导出 |
| F-18 | 自动化测试缺失 | 无回归保护 |
| F-19 | 修改考试缺应用层校验 | 可能 500、发布无考场考试、时长不一致 |
| F-20 | 学生端培养方案无前端入口 | 后端可读但学生看不到 |
| F-21 | 教学资料上传/下载未实现 | 教师资料无法管理 |
| F-22 | 调停课申请/审核未实现 | 无教师申请-教务审核流程 |

---

## 6. 推荐的分阶段修复任务与验收标准

> 原则：先修 P0 的数据正确性/主干闭环，再修 P1 的业务校验与权限口径，最后补 P2 的展示与工程保障。每个任务都应独立提交、附迁移（如涉及）、更新 `docs/API.md` 与手册。

### 6.1 阶段一：P0（正式使用/答辩前必须完成）

#### T0-1 必修课预安排与教学班名单维护前端闭环（F-01、F-12）

范围：

- 在教务端“选课管理”或“开课排课”增加“预安排”入口，支持按行政班/专业/学院选择范围；展示 `matched / assigned / skipped` 明细。
- 增加“添加学生”“移除学生”操作；移除已产生成绩的学生必须二次确认并说明后果，或直接拒绝。
- 后端 `assign_required()` 增加：学期 ACTIVE、教学班 ACTIVE、容量、重复/已退课复用、时间冲突；失败时返回可定位的明细，不产生部分写入。
- 教学班编辑接口禁止直接写 `selection_status=OPEN`；开放选课统一走 `open_selection()` 校验。

验收标准：

1. 教务不调用接口、不依赖种子数据，能在界面上完成一个必修课教学班的预安排。
2. 预排人数达到容量上限时，系统明确提示并**不超容**；已结束学期不能预排。
3. 添加/移除学生后，教师“我的课程 → 名单”和学生课表同步变化。
4. 已有非草稿成绩的学生不能被移除（或按明确的产品规则处理），不出现名单与成绩不一致。
5. 未分配教师/未排课的教学班不能通过任何前端表单直接变为“选课中”。

#### T0-2 学生/教师档案邮箱异常治理（F-02）

范围：

- 前端：空字符串邮箱统一转 `null` 后提交；增加邮箱格式校验。
- 后端：`StudentCreate` / `TeacherCreate` / `UserCreate` 增加 `field_validator`，把 `""` 转 `None`；创建/更新前检查邮箱唯一性；`flush()` 阶段的 `IntegrityError` 捕获并转换为 409。
- 可选：增加局部唯一索引/约束说明；MySQL 唯一索引已允许多个 `NULL`，无需改表。

验收标准：

1. 连续创建两个邮箱为空的学生/教师均成功（落库 `NULL`），不返回 500。
2. 使用相同非空邮箱创建第二个档案返回 409，提示“邮箱已存在”，不是 500。
3. 编辑档案把邮箱改为已存在值返回 409；清空邮箱可保存为 `NULL`。
4. 现有 `NULL` 邮箱数据不受影响，无需数据回填。

#### T0-3 已审核成绩更正流程（F-03）

范围：

- 增加“撤销审核/更正”接口（例如 `POST /grades/{id}/unapprove` 或 `POST /grades/{id}/correct`），权限 `grade:approve`，必须填写更正原因。
- 状态流转建议：`APPROVED → REJECTED`（教师可改后重新提交）或 `APPROVED → DRAFT`（仅教务代改），二选一并写入文档。
- 新增成绩变更历史（推荐新表 `grade_change_logs`，字段：grade_id、old/new 分数/状态、操作人、原因、时间、IP）；若暂不建表，至少写入 `operation_logs` 并保证不可静默覆盖。
- 前端教务端增加“已审核成绩”查询与“更正”入口；教师端在成绩被撤销后恢复可编辑。

验收标准：

1. 教务可对一条 `APPROVED` 成绩发起更正，必须填写原因；成功后教师可重新编辑并提交，学生最终看到新成绩。
2. 每次更正都有一条不可篡改的历史记录，包含操作人、时间、原因、改前/改后值。
3. 普通教师、学生不能调用更正接口（403）；未审核成绩不能走更正流程。
4. 更正过程中学生端不会看到中间态（按产品规则明确“更正期间是否隐藏”）。

#### T0-4 选课/退课时间窗口一致性（F-04、F-06）

范围：

- `drop_course()` 增加 `_check_period_open(student, semester)`；同时校验学期 ACTIVE。
- `available_classes()` 与 `select_course()` 共用同一组“可选条件”：学期 ACTIVE、教学班 ACTIVE/OPEN、课程为选修、选课窗口对当前学生开放（含 `target_grade_year`）。
- 前端 `openPeriod` 增加 `target_grade_year` 判断；不可选时给出“不在你的选课年级/窗口”提示，而不是绿色“选课开放中”。

验收标准：

1. 选课窗口关闭（无 ACTIVE 窗口或不在起止时间）时，退课返回 409，不能退课。
2. 不符合限定年级的学生看不到该窗口下的课程；直接调用选课接口返回明确 409。
3. PLANNED/ENDED 学期的教学班不出现在可选列表。
4. 正常窗口内选课/退课不受影响；并发选课仍不超卖。

### 6.2 阶段二：P1（主干业务完善）

#### T1-1 当前学期统一读取（F-05）

- 增加 `GET /api/v1/terms/active`（无 ACTIVE 时返回 404/空并给前端明确提示），或复用 `GET /terms?status=ACTIVE`。
- 前端新增 `useActiveTerm()`，优先读取后端 ACTIVE 学期；无 ACTIVE 时回退到 `currentSemester()` 并显示提示。
- 替换无选择器页面的 `currentSemester()`：教务/学生/教师工作台、学生评价、教师成绩录入、顶栏学期 chip；教师成绩录入增加学期下拉框。
- 验收：切换数据库 ACTIVE 学期后，所有默认页面同步变化；无 ACTIVE 学期时页面不崩溃、提示清晰。

#### T1-2 考试冲突检测与考场管理（F-07、F-16、F-19）

- 创建/修改考试、添加/修改考场时，检测：
  - 同一教室同一日期时间重叠的其他考试；
  - 同一监考教师同一时间重叠；
  - 同一学生同一时间已有其他考试（按已选教学班/座位分配）；
  - 考试时间与上课排课冲突（按学期、星期、节次、周次）。
- 增加 `DELETE /exams/{id}/rooms/{room_id}`、`PUT /exams/{id}/rooms/{room_id}`；发布后限制修改规则写入文档。
- `ExamUpdate` 增加 `end_time > start_time`、`duration_minutes` 与时间差一致、发布必须有考场的校验。
- 验收：冲突安排返回 409 并指出冲突对象；合法安排通过；修改时间不再 500；可删除/修改考场；监考教师可在界面设置。

#### T1-3 教学任务编辑入口（F-08）

- 前端教学任务表格/卡片增加“编辑”，弹窗只允许改 `planned_classes`、`status`。
- 后端更新时校验任务存在、`planned_classes` 不小于已建教学班数（或给出明确警告），并写操作日志。
- 验收：任务计划开班数/状态可修改并持久化；有教学班时也可修改；无需删除重建。

#### T1-4 操作日志覆盖与查询页面（F-09、F-15）

- 增加统一审计服务/中间件，至少覆盖：登录成功/失败/退出、学生/教师/课程/教学班/排课增删改、选课/退课、成绩保存/提交/审核/驳回、考试发布、批量导入、管理员授权/撤销/启停。
- 记录用户、时间、IP、UA、动作、模块、资源类型/ID、结果、失败原因；禁止记录密码/令牌。
- 前端新增“操作日志”菜单/页面，支持按模块、动作、操作人、资源、时间范围过滤；保留现有管理员变更记录弹窗或合并。
- 验收：上述关键操作各产生一条日志；页面可按条件查询；无敏感信息；日志失败不影响主业务（或按明确策略处理）。

#### T1-5 教学评价任务管理（F-10）

- 教务端新增“教学评价任务”页面：列表、创建、激活、关闭；校验时间窗口、学期、名称。
- 学生端/教师端复用现有任务读取与统计接口。
- 验收：教务可在界面为当前学期创建并激活评价任务；学生能看到待评价课程；教师能看到统计；关闭后不能提交。

#### T1-6 双身份权限口径统一（F-11）

- 所有“管理员操作”按权限码/角色判断，不按 `user_type`；`user_type` 仅用于判断“教师本人/学生本人”的数据范围。
- 具体至少改：公告列表、教学班名单、成绩单/名单/统计、评价统计。
- 前端双身份切换保留；在教务端调用管理员接口时不受教师本人限制。
- 验收：教师兼任管理员在教务端能看公告草稿/学生公告、其他班名单/成绩、全校评价统计；普通教师仍只能看本人授课数据；学生仍只能看本人数据。

#### T1-7 对象级数据隔离加固（F-13）

- `GET /teaching-classes` / `{id}`：学生仅返回自己已选/可选教学班，或改为管理端权限；教师仅返回本人授课 + 可选公开课程目录。
- `GET /schedules/students/{student_id}`：教师仅能查本人授课教学班的学生；教务可查全部；学生仅本人。
- `GET /exams`：学生只返回 `PUBLISHED` 且本人已选教学班的考试；教师只返回本人授课教学班；教务全部。
- `GET /students/{id}`：教师仅能查本人授课教学班学生；`GET /teachers/{id}` 明确公开字段或限制角色。
- 验收：越权读取返回 403 或空集；正常教务/教师/学生页面无回归；补充接口级测试。

#### T1-8 预排/名单业务校验补齐（F-12）

- 已包含在 T0-1；若分阶段实施，至少先补容量、学期 ACTIVE、教学班 ACTIVE、时间冲突、移除有成绩学生保护。
- 验收：同 T0-1 第 2—4 条。

### 6.3 阶段三：P2（体验、导出、工程保障）

#### T2-1 学生成绩页排名展示（F-14）

- `Grades.vue` 改为调用 `/grades/my`（或让 `/grades/mine/summary` 返回排名），复用首页同源数据；概览显示 `class_rank` / `major_rank`，无成绩时显示“—”。
- 验收：学生成绩页与首页排名一致；无成绩时不报错；切换学期/全部学期行为明确。

#### T2-2 Excel 导出（F-17）

- 后端增加学生名单、成绩、课程、选课结果导出 endpoint（`student:export` / `grade:export` / `course:read` / `selection:read`），使用 openpyxl；前端在对应页面增加导出按钮。
- 验收：导出文件可被 Excel 打开；字段、筛选条件与页面一致；权限不足 403。

#### T2-3 自动化测试与质量门禁（F-18）

- 恢复最小回归集：认证/RBAC、选课（正常/重复/满员/冲突/未开放/无资格）、成绩状态机、考试冲突、邮箱重复、学期单 ACTIVE、双身份。
- CI 或本地脚本执行 `pytest` + `npm run build`。
- 验收：核心用例全部通过；修复回归有测试覆盖；测试数据与正式库隔离。

#### T2-4 学生端培养方案、教学资料、调停课（F-20、F-21、F-22）

- 学生端增加培养方案查看页（复用 `curriculum-plans` 读接口）。
- 教学资料：新增模型/API/教师上传页面。
- 调停课：新增申请单模型、教师提交、教务审核、排课联动。
- 验收：各自形成完整的前后端入口与权限；不影响现有主干流程。

---

## 7. 对现有业务及数据的潜在影响

> 本次审计本身没有修改任何数据。以下评估针对“如果按第 6 章实施修复”可能产生的影响。

| 修复项 | 业务影响 | 数据影响 | 风险控制 |
|---|---|---|---|
| T0-1 预排/名单 | 教务操作方式变化；预排可能被容量/学期校验拒绝 | 新增/复用 `course_selections`；不改表结构 | 先只读统计现有超容教学班；提供 skipped 明细；事务提交 |
| T0-2 邮箱 | 空邮箱可正常保存；重复邮箱变为 409 | 现有 `NULL` 邮箱不受影响；`''` 规范为 `NULL` | 迁移前统计 `email=''`（当前为 0）；不要改已有 `NULL` |
| T0-3 成绩更正 | 新增教务更正动作；教师可重新编辑 | 需新增成绩变更历史表（推荐）或写 `operation_logs`；不改 `grades` 既有字段 | 先做只读备份/导出；状态机与权限写文档；更正必须填原因 |
| T0-4 选课/退课 | 关闭窗口后退课会被拒绝；可选列表可能变短 | 不改表结构 | 提前通知学生/教务；先核对现有窗口与教学班状态 |
| T1-1 ACTIVE 学期 | 页面默认学期可能变化 | 只读接口，无数据变更 | 无 ACTIVE 时回退并提示；不要写死学期 |
| T1-2 考试冲突 | 冲突安排会被拒绝；考场可删除/修改 | 新增校验不改表；如需索引需迁移 | 先只读扫描现有考试冲突；发布后修改规则需明确 |
| T1-3 任务编辑 | 计划开班数/状态可改 | 无表结构变化 | 限制不小于已建教学班数或明确警告 |
| T1-4 日志 | 关键操作留痕 | `operation_logs` 行数增长；建议加保留策略/索引 | 不记录敏感信息；日志失败不阻断主业务（或明确策略） |
| T1-5 评价任务 | 教务可创建/关闭评价 | 新增 `evaluation_tasks` 行 | 时间窗口校验；关闭后禁止提交 |
| T1-6 双身份 | 教师兼任管理员权限扩大（符合角色预期） | 无数据变更 | 用权限码统一判定；补越权测试 |
| T1-7 数据隔离 | 部分列表/详情返回范围变小 | 无数据变更 | 先梳理前端依赖；补 403/空集提示 |
| T2-2 导出 | 新增导出能力 | 只读，无数据变更 | 控制导出权限与日志；注意个人信息 |
| T2-3 测试 | 无业务影响 | 测试库隔离 | 不在正式库跑写测试 |

特别提醒：

- 任何涉及状态机的修复（成绩更正、考试发布、选课窗口）都应先明确“允许的状态迁移表”，不要只改前端按钮。
- 任何“收紧校验”的修复都可能让此前能保存的数据无法再保存；上线前应做一次只读扫描（例如超容教学班、冲突考试、已通过成绩缺历史等），把存量问题列成迁移/人工处理清单。

---

## 8. 已验证、未验证项目及原因

### 8.1 已验证

| 项目 | 方式 | 结果 |
|---|---|---|
| Git 基线 | `git status` / `git branch` / `git rev-parse` | 审计在 `main` 进行；`main == origin/main == beb2105`；工作区干净 |
| 手册 11 项 | 逐项读代码 + 交叉核对前端调用 | 11 项根因均存在；无“已修复”项 |
| F-02 邮箱根因 | 读 `person.py`、`base.py`、`user.py`、前端表单；结合手册隔离库实测记录 | `flush()` 阶段 `IntegrityError` 未捕获；前端提交 `""` |
| F-03 成绩更正 | 读 `grade.py` 全部写接口与状态判断 | 无撤销/更正接口；无历史表 |
| F-04/F-06 选课窗口 | 读 `selection.py` 全部校验路径 | 退课无 `SelectionPeriod`；可选列表无窗口/年级/ACTIVE |
| F-07 考试冲突 | 读 `exam.py` 全部写接口 | 无跨考试/考场/学生/排课冲突查询 |
| F-08 任务编辑 | 前端检索 `updateTask` | 只有 API 定义，无调用 |
| F-09 日志覆盖 | 全后端检索 `OperationLog` 写入点 | 仅 `user.py::_log()`；登录/退出/业务无写入 |
| F-10 评价任务 | 前端检索 `evaluationApi.createTask` | 无调用；无教务路由 |
| F-11 双身份 | 读 `misc.py`、`selection.py`、`grade.py` 的 `user_type` 分支 + 路由/身份代码 | 公告、名单、成绩、评价统计存在按 `user_type` 过滤 |
| F-13 数据隔离 | 读 `teaching.py`、`schedule.py`、`exam.py`、`person.py` 的依赖与过滤 | 多个读接口只要求登录 |
| 数据库现状 | 只读脚本查询表计数、学期、角色、权限、选课窗口、公告、日志、考试 | 连接 `uams` 库成功；1 个 ACTIVE 学期；3 角色/42 权限；22 条日志 |
| 前端构建 | `npm run build`（含 `vue-tsc -b`） | 通过；仅有 chunk 体积提示 |
| 后端编译 | `python -m compileall app` | 通过 |
| Alembic | `alembic current` / `heads` | `a5b7c9d1e2f3 (head)`，无多 head |
| 文档声明 | `docs/API.md`、`docs/TESTING.md` | 导出/资料/调停课/学生培养方案为 planned；测试已移除 |

### 8.2 未验证

| 项目 | 原因 | 备注 |
|---|---|---|
| 真实 HTTP 端到端 | 后端未运行（`/health` 无响应） | 答辩前应启动前后端，用演示账号走一遍 |
| 浏览器交互/响应式 | 本次未启动浏览器 | 前端构建通过不等于页面行为全部正确 |
| F-02 在当前库复现 500 | 审计约束禁止写入正式库 | 手册已有隔离库实测；本次只读核对现有 `email` 数据 |
| F-07 冲突实际拒绝 | 未构造冲突考试/排课数据（禁止写入） | 代码路径明确；建议在测试库构造 |
| F-11 双身份实际 403/缺失 | 当前库只有 1 个独立管理员，无教师兼任账号 | 代码与路由证据明确；建议在测试库授权后复现 |
| 并发选课/超卖 | 未做压测/并发请求 | 代码有 `FOR UPDATE` + 唯一约束，但未实测 |
| 数据库迁移执行 | 本次未执行迁移（只读） | 当前已在 head；修复涉及新表时需在测试库验证 |
| 性能/容量 | 未做数据量与响应时间测试 | 与功能审计分开评估 |
| 自动化回归 | `backend/tests/` 不存在 | `docs/TESTING.md` 说明已移除 |

---

## 9. 课程结课答辩中的可展示能力与不可宣称完成的功能

> 前提：本次只做了静态代码审计、构建和只读数据库核对，**没有实际启动系统走浏览器**。以下“可展示”指代码路径、页面入口和演示数据均具备；答辩前仍应实际走一遍。

### 9.1 可以真实展示的功能（建议演示顺序）

1. **三角色登录与 RBAC**：`admin` / 教师 / 学生登录，进入各自工作台；教师兼任管理员可切换教务控制台（授权/撤销可在管理员管理页演示）。
2. **组织机构**：学院、专业、行政班、教室的增删改查与引用保护。
3. **学生/教师管理**：新增档案自动创建登录账号并授予角色；列表筛选、编辑、停用/启用。
4. **学期管理**：创建学期、激活、结束；系统保证最多一个 ACTIVE。
5. **课程与培养方案**：课程学时守恒、考核方式推导、先修课程环路检测；培养方案课程维护。
6. **教学任务/教学班/排课**：创建任务、教学班、分配教师、排课；演示教室/教师/教学班冲突被拒绝。
7. **选修课选课**：教务创建选修课教学班 → 开放选课 → 学生选课（容量、重复、同课程其他班、时间冲突、先修校验）→ 学生课表生成。
8. **教师教学**：我的课程/名单、我的课表、成绩录入（草稿/提交）、Excel 成绩导入。
9. **教务成绩审核**：待审核列表、整班通过/驳回；学生端只看到已通过成绩。
10. **学生成绩**：成绩明细、GPA、学分；首页显示班级/专业排名。
11. **考试管理**：创建考试、添加考场、自动排座、发布；学生查看考试安排与考场/座位。
12. **公告/统计/导入**：公告发布与撤回；数据统计；学生/教师/课程/成绩 Excel 导入。
13. **管理员管理**：管理员列表、创建独立管理员、从教师授予管理员、撤销、重置密码、停用/启用、管理员变更记录。

### 9.2 尚不能宣称“完整完成”的功能

| 功能 | 原因 | 答辩表述建议 |
|---|---|---|
| 必修课预安排 | 后端有接口，前端无入口；后端缺容量/学期校验 | “必修课名单目前由接口/种子数据生成，前端预排页面尚未完成” |
| 已审核成绩更正 | 无接口、无页面、无历史 | “已通过成绩目前不可在界面更正，需后续增加撤销审核/更正流程” |
| 业务操作日志 | 仅管理员权限变更写入；无独立页面 | “管理员变更记录可查；选课/成绩等业务日志尚未覆盖” |
| 考试冲突检测 | 无时间/考场/学生考试冲突 | “考试安排目前需人工核对，系统尚未自动检测冲突” |
| 教学任务编辑 | 后端有 `PUT`，前端无入口 | “任务目前只能删除重建；编辑入口待补” |
| 教学评价任务管理 | 后端可创建，前端无页面 | “评价任务目前依赖预置/接口创建，教务端管理页待补” |
| 教师兼任管理员全功能 | 公告草稿/学生公告、其他班名单/成绩/评价统计受 `user_type` 过滤 | “双身份登录与授权已支持，但部分教务功能仍在按账号类别过滤” |
| 学生成绩页排名 | 页面写死“—” | “首页可看排名，成绩页排名展示待补” |
| Excel 导出 | 未实现 | “当前只支持导入；导出为后续计划” |
| 学生端培养方案 | 后端可读，前端无入口 | “学生端培养方案页面尚未实现” |
| 教学资料/调停课 | 未实现 | “属于后续版本范围” |
| 自动化测试 | 已移除 | “当前依赖构建与人工验收，无自动化回归套件” |

### 9.3 答辩前建议的最小验证脚本

1. 启动 MySQL、后端、前端；`/health` 返回 `database: up`。
2. 用独立管理员登录，创建/确认一个 ACTIVE 学期与选课窗口。
3. 在“开课排课”创建教学任务 → 教学班 → 分配教师 → 排课 → 开放选课。
4. 用学生账号选课 → 查看课表 → 退课（在窗口内）。
5. 用教师账号查看名单 → 录入成绩 → 提交；用教务账号审核通过；学生查看成绩。
6. 创建考试 → 添加考场 → 排座 → 发布；学生查看考试/考场。
7. 发布一条公告；用学生/教师账号查看。
8. 导出/截图关键页面，作为答辩材料；对 9.2 中列出的功能，明确说明“未完成/后续计划”，不要现场演示不存在入口的功能。

---

## 10. 附录

### 10.1 关键代码位置索引

| 主题 | 文件:行 |
|---|---|
| 选课窗口校验 | `backend/app/services/selection.py:83-92` |
| 选课主流程 | `backend/app/services/selection.py:120-223` |
| 退课 | `backend/app/services/selection.py:225-263` |
| 必修课预排 | `backend/app/services/selection.py:267-344` |
| 可选课程 | `backend/app/services/selection.py:348-390` |
| 预排/名单 API | `backend/app/api/v1/selection.py:212-263` |
| 教学班/排课服务 | `backend/app/services/teaching.py:356-476` |
| 添加/移除学生 | `backend/app/services/teaching.py:478-535` |
| 排课冲突检测 | `backend/app/services/teaching.py:85-180`、`:593-615` |
| 成绩状态机 | `backend/app/services/grade.py:157-225`、`:267-324` |
| 学生成绩总览/排名 | `backend/app/services/grade.py:366-390` |
| 成绩 API | `backend/app/api/v1/grade.py:148-325` |
| 考试 API | `backend/app/api/v1/exam.py:112-335` |
| 考试模型约束 | `backend/app/models/exam.py:42-51` |
| 公告列表过滤 | `backend/app/api/v1/misc.py:288-308` |
| 评价统计过滤 | `backend/app/api/v1/misc.py:200-246` |
| 审计日志 API | `backend/app/api/v1/misc.py:453-478` |
| 审计日志写入 | `backend/app/services/user.py:202-217` |
| 学生/教师创建 | `backend/app/services/person.py:50-97`、`:168-201` |
| 通用提交异常处理 | `backend/app/services/base.py:126-138` |
| 用户邮箱唯一约束 | `backend/app/models/user.py:66-68` |
| 前端学期推断 | `frontend/src/composables/useSemester.ts:7-15` |
| 教师成绩录入学期 | `frontend/src/views/teacher/GradeEntry.vue:80-86` |
| 学生成绩页排名 | `frontend/src/views/student/Grades.vue:38-39`、`:63-69` |
| 教学任务表格 | `frontend/src/views/admin/Teaching.vue:538-585` |
| 选课管理名单 | `frontend/src/views/admin/SelectionManage.vue:72`、`:248`、`:300` |
| 成绩审核页 | `frontend/src/views/admin/GradeApproval.vue:28` |
| 管理员变更记录 | `frontend/src/views/admin/AdminManage.vue:206-210` |
| 双身份路由/身份 | `frontend/src/router/index.ts:127-128`、`frontend/src/stores/auth.ts:38-44` |
| 未实现接口清单 | `docs/API.md:515-523` |
| 测试移除说明 | `docs/TESTING.md:3-8` |

### 10.2 本次只读数据库核对结果（摘要）

| 项 | 值 |
|---|---|
| 数据库 | `uams` |
| 用户/学生/教师 | 8 / 4 / 3 |
| 学期 | 1 个：`2026-2027-1`，状态 `ACTIVE` |
| 角色/权限 | 3 / 42 |
| 课程/教学任务/教学班 | 5 / 5 / 4 |
| 选课记录/选课窗口 | 5 / 3 |
| 成绩/考试/考场 | 4 / 2 / 2 |
| 评价任务/评价 | 1 / 0 |
| 公告 | 3（均 PUBLISHED） |
| 操作日志 | 22（`ADMIN_*` 21，`LOGIN` 1） |
| 邮箱为空字符串/`NULL` | 0 / 4 |
| Alembic | `a5b7c9d1e2f3 (head)` |
| 前端构建 | 通过 |
| 后端编译 | 通过 |

### 10.3 本次审计未做的事

- 未修改任何业务代码、数据库结构、系统配置或正式业务数据。
- 未创建任何分支、worktree、合并或 cherry-pick。
- 未启动后端/前端服务，未做浏览器端到端。
- 未在正式库写入测试数据；涉及异常复现的结论均标注了代码证据与手册历史实测来源。
- 未把本报告之外的任何文件纳入提交。

---

## 11. 结论

UAMS 在当前 `main` 基线上已经具备一个可演示的教务系统主干：组织机构、课程、教学班、排课、选修课选课、课表、成绩录入/审核、学生成绩、考试、公告、统计和批量导入均有完整的前后端入口。

但它还不能被宣称为“所有教务业务均可由普通教务人员在前端独立完成”：

- **必修课预安排**没有前端入口，后端预排也缺容量/学期校验；
- **已审核成绩更正**完全没有实现；
- **退课窗口、可选课程资格、默认学期**存在业务校验不一致；
- **考试冲突检测、业务操作日志、教学评价任务管理、导出**等关键能力缺失；
- **教师兼任管理员**的权限口径仍混用 `user_type` 与角色，部分教务功能不可用；
- **对象级数据隔离**在若干读接口上偏宽。

建议按第 6 章先修 4 个 P0，再处理 9 个 P1，最后补 9 个 P2；修复过程中保持小步提交、先只读盘点存量数据、每项补验收用例。报告完成后的下一步应是制定修复排期，而不是直接在正式库上改数据。

---

> 报告结束。
> 本报告基于 `main @ beb2105` 的代码、只读数据库核对与构建结果；运行时端到端验证需在启动服务后另行执行。
