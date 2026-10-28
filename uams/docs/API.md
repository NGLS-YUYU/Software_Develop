# 后端 API 文档

> 依据当前 FastAPI 路由实际代码整理（V3.2，2026-10-29 复核）。
> **119 个路径 / 169 个操作**（以 `/openapi.json` 为准）；未列出的接口不存在。
> 正式环境经 Nginx 80 访问：`http://<服务器IP>/api/v1/...`；开发/测试直连 `http://127.0.0.1:8000/api/v1/...`。

---

## 1. 通用约定

| 项 | 约定 |
|---|---|
| 前缀 | 所有业务 API 使用 `/api/v1/`（CLAUDE.md §13） |
| 认证 | `Authorization: Bearer <JWT>` |
| 分页参数 | `page`（≥1，默认 1）、`page_size`（1~200，默认 20）、`keyword`、`order_by`、`order_desc` |
| 分页响应 | `{ items, total, page, page_size, total_pages }` |
| 错误响应 | `{ code, message }`；参数校验失败为 `{ code: "VALIDATION_ERROR", message, errors[] }` |
| 交互式文档 | `/docs`（Swagger UI）、`/redoc`（ReDoc）—— 仅 `DEBUG=true` 时开放 |
| 健康检查 | `GET /health`（无前缀，不需认证） |

### 1.1 错误码

| 错误码 | HTTP | 含义 |
|---|---|---|
| `AUTH_INVALID_CREDENTIALS` | 401 | 用户名或密码错误 |
| `AUTH_ACCOUNT_LOCKED` | 423 | 账号锁定（连续失败达阈值） |
| `AUTH_ACCOUNT_DISABLED` | 403 | 账号停用或状态异常 |
| `AUTH_INVALID_TOKEN` | 401 | 令牌缺失/无效/过期 |
| `PERM_DENIED` | 403 | 权限不足或越权访问 |
| `RESOURCE_NOT_FOUND` | 404 | 资源不存在 |
| `RESOURCE_CONFLICT` | 409 | 冲突（唯一约束、引用保护、业务规则） |
| `INVALID_EMAIL` | 400 | 邮箱格式不合法（Service 层；Schema 层通常先返回 422） |
| `EMAIL_ALREADY_EXISTS` | 409 | 邮箱已被其他账号占用（FIX-001） |
| `VALIDATION_ERROR` | 422 | 请求参数校验失败 |
| `TEACHING_CLASS_FULL` | 409 | 教学班容量已满（TASK-012） |
| `TEACHING_CLASS_HAS_DATA` | 409 | 教学班存在选课或成绩数据，无法删除（TASK-012） |
| `TEACHING_CLASS_TERM_ENDED` | 409 | 学期已结束，教学班只读（TASK-012） |
| `TEACHING_CLASS_TEACHER_LOCKED` | 409 | 已有成绩提交/审核，无法更换教师（TASK-012） |
| `CAPACITY_BELOW_ENROLLED` | 409 | 容量不能小于已选人数（TASK-012） |
| `TEACHING_CLASS_COURSE_IMMUTABLE` | 409 | 教学班所属课程不可修改（TASK-012） |
| `TEACHING_CLASS_TERM_IMMUTABLE` | 409 | 教学班所属学期不可修改（TASK-012） |
| `TEACHING_SCHEDULE_TERM_ENDED` | 409 | 学期已结束，教学安排只读（TASK-013） |
| `TEACHING_SCHEDULE_TEACHER_CONFLICT` | 409 | 教师在该时段已有其他教学安排（TASK-013） |
| `TEACHING_SCHEDULE_CLASSROOM_CONFLICT` | 409 | 教室在该时段已被占用（TASK-013） |
| `TEACHING_SCHEDULE_CLASS_CONFLICT` | 409 | 教学班在该时段已有其他安排（TASK-013） |

> **邮箱字段（FIX-001）**：学生/教师/用户新增、编辑时，`email` 可省略；`null`、空字符串、纯空格统一保存为 `NULL`。非空邮箱必须符合格式且全局唯一（跨学生/教师/管理员共用 `users.email` 唯一约束）。重复返回 `EMAIL_ALREADY_EXISTS`（409），格式非法在请求模型层返回 422，Service 层直接调用返回 `INVALID_EMAIL`（400）。

---

## 2. 认证 `/api/v1/auth`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | `/auth/login` | 登录，返回 token、用户、角色、权限、首页路由 | 公开 |
| GET | `/auth/me` | 当前用户信息与权限 | 登录 |
| POST | `/auth/change-password` | 修改密码（204） | 登录 |
| POST | `/auth/logout` | 退出登录（204，前端丢弃 token） | 登录 |

**用户管理**（TASK-001）

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/users` | 用户列表（分页/按类型、状态筛选） | `user:read` |
| GET | `/users/{id}` | 用户详情 | `user:read` |
| POST | `/users` | 新建账号（默认按 user_type 分配角色） | `user:write` |
| PUT | `/users/{id}/password` | 重置密码（204，重置后解锁） | `user:write` |
| PUT | `/users/{id}/status` | 停用/启用账号（停用唯一管理员返回 409；不能停用自己） | `user:write` |

**管理员管理**（V3.0）

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/admins` | 管理员列表（含教师兼任账号） | `user:read` |
| POST | `/admins/{user_id}/grant` | 授予管理员角色（典型：教师兼任） | `user:write` |
| POST | `/admins/{user_id}/revoke` | 撤销管理员角色（不删账号、不动教学数据） | `user:write` |

> **判定依据是角色，不是 `user_type`**：持有 `ACADEMIC_ADMIN` 角色即为管理员。
> - 教师兼任管理员时 `user_type` **保持 `TEACHER` 不变**，教学班、课表、成绩等归属完全不受影响；
> - 撤销只删除 `user_roles` 关联，账号与教学数据全部保留；
> - 令牌只携带 `sub`，角色每次请求重新解析，因此**撤销后旧会话在下一次请求即失效**；
> - 保护规则：不能撤销/停用唯一的管理员（409），不能撤销/停用当前登录账号自己（409）；
> - 审计：授权/撤销/启停会写入 `operation_logs`（`action` 为 `ADMIN_GRANT`/`ADMIN_REVOKE`/`ADMIN_ENABLE`/`ADMIN_DISABLE`，含操作人、目标与时间），
>   可通过 `GET /audit-logs?resource_type=user&resource_id=` 查询（`audit-logs` 本次新增 `resource_type`/`resource_id` 过滤参数）。

**请求示例**

```json
POST /api/v1/auth/login
{ "username": "20260001", "password": "20260001" }
```

**响应示例**

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 28800,
  "user": { "id": 3, "username": "20260001", "real_name": "钱伟", "user_type": "STUDENT", "status": "ACTIVE" },
  "roles": ["STUDENT"],
  "permissions": ["course:read", "selection:write", "..."],
  "home_route": "/student/dashboard"
}
```

---

## 3. 基础数据

### 3.1 学院 `/api/v1/colleges`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/colleges` | 列表（支持 `status`、`keyword`） | 登录 |
| GET | `/colleges/{college_id}` | 详情 | 登录 |
| POST | `/colleges` | 新增（201） | `college:write` |
| PUT | `/colleges/{college_id}` | 修改 | `college:write` |
| DELETE | `/colleges/{college_id}` | 删除（204，被引用时 409） | `college:write` |

### 3.2 专业 `/api/v1/majors`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/majors` | 列表（`college_id`、`status`、`keyword`） | 登录 |
| GET | `/majors/{major_id}` | 详情 | 登录 |
| POST | `/majors` | 新增 | `major:write` |
| PUT | `/majors/{major_id}` | 修改 | `major:write` |
| DELETE | `/majors/{major_id}` | 删除（有班级时 409） | `major:write` |

### 3.3 班级 `/api/v1/classes`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/classes` | 列表（`major_id`、`grade_year`） | 登录 |
| GET | `/classes/{class_id}` | 详情 | 登录 |
| POST | `/classes` | 新增 | `class:write` |
| PUT | `/classes/{class_id}` | 修改 | `class:write` |
| DELETE | `/classes/{class_id}` | 删除（有学生时 409） | `class:write` |

### 3.4 教室 `/api/v1/classrooms`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/classrooms` | 列表（`building`、`room_type`） | 登录 |
| GET | `/classrooms/{room_id}` | 详情 | 登录 |
| POST | `/classrooms` | 新增 | `classroom:write` |
| PUT | `/classrooms/{room_id}` | 修改 | `classroom:write` |
| DELETE | `/classrooms/{room_id}` | 删除（被排课占用时 409） | `classroom:write` |

---

## 4. 人员

### 4.1 学生 `/api/v1/students`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/students` | 列表（`class_id`、`major_id`、`college_id`、`academic_status`、`keyword`） | `student:read` |
| GET | `/students/me` | 我的学生档案 | 登录（学生） |
| GET | `/students/{student_id}` | 详情（学生仅可查本人） | 登录 + 对象级校验 |
| POST | `/students` | 新增（同时创建 users 账号并授 STUDENT 角色） | `student:write` |
| PUT | `/students/{student_id}` | 修改 | `student:write` |
| DELETE | `/students/{student_id}` | 删除（有选课记录时 409） | `student:write` |

> 新增学生时 `password` 留空则默认密码为学号。

### 4.2 教师 `/api/v1/teachers`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/teachers` | 列表（`college_id`、`title`、`keyword`） | `teacher:read` |
| GET | `/teachers/me` | 我的教师档案 | 登录（教师） |
| GET | `/teachers/{teacher_id}` | 详情 | `teacher:read` |
| POST | `/teachers` | 新增（同时创建账号并授 TEACHER 角色） | `teacher:write` |
| PUT | `/teachers/{teacher_id}` | 修改 | `teacher:write` |
| DELETE | `/teachers/{teacher_id}` | 删除（有教学班时 409） | `teacher:write` |

---

## 5. 课程与培养方案

### 5.1 课程 `/api/v1/courses`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/courses` | 列表（`college_id`、`course_type`、`status`） | 登录 |
| GET | `/courses/{course_id}` | 详情 | 登录 |
| POST | `/courses` | 新增 | `course:write` |
| PUT | `/courses/{course_id}` | 修改 | `course:write` |
| DELETE | `/courses/{course_id}` | 删除（有教学任务时 409） | `course:write` |
| GET | `/courses/{course_id}/prerequisites` | 先修课程列表 | 登录 |
| POST | `/courses/{course_id}/prerequisites` | 添加先修（**含环路检测**） | `course:write` |
| DELETE | `/courses/{course_id}/prerequisites/{row_id}` | 移除先修 | `course:write` |

> 成绩权重不通过课程维护：总评权重统一在 `ScoreService.WEIGHT_RULES` 中配置（FIX-008 已删除 `regular_weight`/`final_weight` 字段）。
> **FIX-009**：考核结构由 `total_hours`/`practice_hours` 经 `services/assessment.py` 唯一推导，`assessment_type` 仅作派生缓存，POST/PUT 时由后端重算、忽略客户端传入值；`theory_hours + practice_hours = total_hours` 由 Schema/Service/DB 三层强制，不满足直接 400；已存在提交/审核成绩的课程，PUT 修改学时将返回 409。

### 5.2 培养方案 `/api/v1/curriculum-plans`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/curriculum-plans` | 列表（`major_id`、`grade_year`） | 登录 |
| GET | `/curriculum-plans/{plan_id}` | 详情 | 登录 |
| POST | `/curriculum-plans` | 新增（同专业同年级唯一） | `curriculum:write` |
| PUT | `/curriculum-plans/{plan_id}` | 修改 | `curriculum:write` |
| DELETE | `/curriculum-plans/{plan_id}` | 删除 | `curriculum:write` |
| GET | `/curriculum-plans/{plan_id}/courses` | 方案课程列表 | 登录 |
| POST | `/curriculum-plans/{plan_id}/courses` | 添加课程 | `curriculum:write` |
| DELETE | `/curriculum-plans/{plan_id}/courses/{row_id}` | 移除课程 | `curriculum:write` |

---

## 6. 学期与开课排课

### 6.1 学期 `/api/v1/terms`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/terms` | 列表（`academic_year`、`status`、分页） | `term:read` |
| GET | `/terms/{term_id}` | 详情（含 `teaching_class_count`） | `term:read` |
| POST | `/terms` | 新增（201，默认 `PLANNED`） | `term:write` |
| PUT | `/terms/{term_id}` | 修改 | `term:write` |
| DELETE | `/terms/{term_id}` | 删除（有教学班时 409） | `term:write` |
| POST | `/terms/{term_id}/activate` | 激活（`PLANNED`→`ACTIVE`） | `term:write` |
| POST | `/terms/{term_id}/end` | 结束（`ACTIVE`→`ENDED`） | `term:write` |

**业务规则（TASK-011）**

- 唯一约束：同一 `(academic_year, semester)` 只能存在一个学期。
- 状态单向流转 `PLANNED → ACTIVE → ENDED`；`ENDED` 不可再改状态或重新激活，只有 `ACTIVE` 才能结束。
- 全系统最多一个 `ACTIVE` 学期；激活或直接创建 `ACTIVE` 学期时若已存在进行中学期则 409。
- 教学班通过 `term_id` 绑定学期（必填）；`ENDED` 学期不能创建新教学班。
- 学生选课仅允许在 `ACTIVE` 学期；`ENDED` 学期不可退课。
- 学生/教师仅 `term:read`（只读），仅 `ACADEMIC_ADMIN` 拥有 `term:write`。

> **前端入口（FIX-006）**：教务端 `/admin/terms`（菜单「学期管理」）已接入上述全部接口，支持列表/关键词与状态筛选/分页/新增/编辑/激活/结束/删除。激活与结束均带二次确认，页面状态一律取自 `/terms` 的返回结果（前端不维护「当前学期」，也不自行推断状态机）。教师/学生访问该路由由前端守卫挡到 `/403`，写接口仍由后端 403 兜底。

### 6.2 教学任务 `/api/v1/teaching-tasks`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/teaching-tasks` | 列表（`semester`、`course_id`、`college_id`） | `teaching:read` |
| POST | `/teaching-tasks` | 新增 | `teaching:write` |
| PUT | `/teaching-tasks/{task_id}` | 修改 | `teaching:write` |
| DELETE | `/teaching-tasks/{task_id}` | 删除（有教学班时 409） | `teaching:write` |

### 6.3 教学班 `/api/v1/teaching-classes`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/teaching-classes` | 列表（`semester`、`term_id`、`course_id`、`teacher_id`、`selection_status`，均在数据库层过滤） | 登录 |
| GET | `/teaching-classes/mine` | 我的授课课程（**教师身份取自 token**，不接受 `teacher_id`；支持 `semester`、`term_id`） | 登录（教师） |
| GET | `/teaching-classes/{class_id}` | 详情（含排课；返回 `term_id`、`term_name`、`term_status`、`name`） | 登录 |
| POST | `/teaching-classes` | 新增（`term_id`、`teacher_id` 必填，可选 `name`；`ENDED` 学期拒绝） | `teaching:write` |
| PUT | `/teaching-classes/{class_id}` | 修改（`code`/`name`/`teacher_id`/`capacity`/`selection_status`/`status`；`term_id`/`course_id` 不可变；换教师有 SUBMITTED/APPROVED 成绩时锁定；容量不得小于已选人数） | `teaching:write` |
| DELETE | `/teaching-classes/{class_id}` | 删除（有选课或成绩时 409 `TEACHING_CLASS_HAS_DATA`；`ENDED` 学期拒绝） | `teaching:write` |
| POST | `/teaching-classes/{class_id}/selection?open=true\|false` | 开放/关闭选课 | `selection:manage` |
| GET | `/teaching-classes/{class_id}/schedules` | 排课列表 | 登录 |
| POST | `/teaching-classes/{class_id}/schedules` | 添加排课（**冲突检测**） | `schedule:write` |
| PUT | `/teaching-classes/{class_id}/schedules/{schedule_id}` | 修改排课（重新检测冲突） | `schedule:write` |
| DELETE | `/teaching-classes/{class_id}/schedules/{schedule_id}` | 删除排课 | `schedule:write` |
| GET | `/teaching-classes/{class_id}/students` | 教学班学生名单（含 `selection_id`、专业、行政班、`status`、`source`/`source_label`、`selected_at`；教师仅限本人） | `selection:read` |
| POST | `/teaching-classes/{class_id}/students` | 教务手动添加学生（FIX-002：校验学期/学籍/容量/同课程/时间冲突，来源 `ADMIN_MANUAL`） | `selection:manage` |
| DELETE | `/teaching-classes/{class_id}/students/{student_id}` | 教务移除学生（FIX-002：已有成绩记录时 409） | `selection:manage` |
| POST | `/teaching-classes/{class_id}/assign-required?preview=true\|false` | 必修课预安排（FIX-002：`preview=true` 只预览不写库；按行政班/专业/学院，优先级 class_id>major_id>college_id） | `selection:manage` |
| GET | `/teaching-classes/{class_id}/selection-stats` | 选课统计（含计数一致性检查） | `selection:read` |

**教学班业务规则（TASK-012）**

- 创建要求 `Course`（经 task）、`AcademicTerm`、`Teacher` 均存在，`term.status != ENDED`；`teacher_id` 必填且须具备教师身份。
- `term_id` / `course_id` 创建后**不可修改**（提交即 409）。
- 更换教师：存在 `SUBMITTED` / `APPROVED` 成绩时 409 `TEACHING_CLASS_TEACHER_LOCKED`，并重新检测排课冲突。
- 容量：`capacity` 不得小于已选人数（`CAPACITY_BELOW_ENROLLED`）；学生选课与教务添加学生满员时 409 `TEACHING_CLASS_FULL`（`SELECT ... FOR UPDATE` 防超卖）。
- 删除仅限空教学班（无 `CourseSelection` 且无 `Grade`）；`ENDED` 学期不可增删改（`TEACHING_CLASS_TERM_ENDED`）。
- `GET /teaching-classes` 的 `term_id` / `course_id` / `teacher_id` 过滤在数据库查询层完成。

**排课冲突判定**（`services/teaching.py`）：同学期 + 同星期 + 节次区间重叠 + 周次区间重叠 + 单双周相容。检测**三类**冲突——教学班自身、教室、教师——分别返回 `TEACHING_SCHEDULE_CLASS_CONFLICT` / `TEACHING_SCHEDULE_CLASSROOM_CONFLICT` / `TEACHING_SCHEDULE_TEACHER_CONFLICT`。开放选课要求已分配教师且已排课。

### 6.4 教学安排 `/api/v1/teaching-schedules`（TASK-013）

复用既有 `Schedule` 模型（`schedules` 表）作为教学安排实体；一个教学班可有多条安排。权限复用 `schedule:read` / `schedule:write`（不新增权限码）。

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/teaching-schedules` | 列表（`term_id`、`teaching_class_id`、`teacher_id`、`weekday`、`classroom` 均在数据库层过滤，按星期/节次/周次排序） | `ACADEMIC_ADMIN` |
| GET | `/teaching-schedules/{schedule_id}` | 详情 | `ACADEMIC_ADMIN` |
| POST | `/teaching-schedules` | 新增（`teaching_class_id` + `classroom_id` + 星期/节次/周次/单双周；**自动检测三类冲突**） | `schedule:write` |
| PUT | `/teaching-schedules/{schedule_id}` | 修改（仅星期/节次/周次/教室；`teaching_class_id` 不可变） | `schedule:write` |
| DELETE | `/teaching-schedules/{schedule_id}` | 删除 | `schedule:write` |
| GET | `/teaching-schedules/mine` | 我的教学安排（教师，身份取自 token；过滤：`term_id` / `semester` / `week`） | 登录（教师） |
| GET | `/teaching-schedules/my` | 我的课程安排（学生，本人已选教学班；未选课返回空列表；过滤同上） | 登录（学生） |

**教学安排业务规则（TASK-013）**

- 学期生命周期：`PLANNED` / `ACTIVE` 可增删改查；`ENDED` 只读，增删改返回 409 `TEACHING_SCHEDULE_TERM_ENDED`。
- 冲突检测在数据库查询层完成（`ConflictChecker`），修改时排除自身（`id != 当前 id`）。
- 教室校验：必须存在、`ACTIVE`、且容量 ≥ 教学班容量。
- `teaching_class_id` 创建后不可修改（`ScheduleUpdate` 不接收该字段）。
- 响应富化：`teaching_class_code/name`、`course_code/name`、`teacher_name`、`term_name`、`classroom_code/building`。
- **前端数据源（FIX-007）**：教务排课页（列表/新增/修改/删除）、教师课表（`/mine`）、学生课表（`/my`）全部使用本组平铺接口；`semester`（字符串学期）与 `week`（第几周，含单双周判定，范围 1–30）为 FIX-007 新增的**可选**过滤参数，由服务端过滤，前端不再自行实现周次逻辑。

---

## 7. 选课

### 7.1 选课 `/api/v1/course-selections`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/course-selections/available?semester=...` | 可选教学班（学生，仅选修课 ELECTIVE） | 登录 |
| GET | `/course-selections/mine` | 我的选课（`semester`、`include_dropped`，含 `course_type`、`source`/`source_label`、教学班状态） | 登录 |
| GET | `/course-selections/window?semester=...` | 学生当前选课/退课窗口状态（FIX-003：`can_select`/`can_drop`/`reason_code`/`reason`/`window`/`open_windows`） | 登录（学生） |
| POST | `/course-selections` | 选课（201，身份取自 JWT，不接受 `student_id`） | `selection:write` |
| DELETE | `/course-selections/{selection_id}` | 退课（204） | `selection:write` |

**选课校验链**（`services/selection.py`，全部在单个事务内完成）：

1. `SELECT ... FOR UPDATE` 锁定教学班行（防超卖）
2. 教学班状态与选课开放状态
3. **课程类型**：仅 `ELECTIVE`/`PUBLIC_ELECTIVE` 可自主选择，必修课（`REQUIRED`/`PUBLIC_REQUIRED`/`PRACTICE`）拒绝
4. 选课时间窗口（`selection_periods`）
5. 重复选课 / 同学期同课程其他教学班
6. 容量（动态统计 `COUNT(CourseSelection)` ≥ `capacity` 时满员，`selected_count` 已不落库）
7. 时间冲突（与已选课程比对排课）
8. 先修课程（已审核且达最低分）

退课限制（FIX-003 与选课统一）：仅本人、**必修课不可自主退选**、教学班 ACTIVE/OPEN、学期 ACTIVE、窗口 ACTIVE 且当前时间在起止范围内、限定年级匹配、已有成绩记录（非草稿）时不允许退课。

**统一窗口判断（FIX-003）**：`SelectionService.selection_window_status()` 同时用于选课、退课和学生端状态接口。多窗口重叠按并集处理：任一 ACTIVE、时间在范围内、年级适用的窗口开放即可；时间边界包含开始/结束时刻。状态与时间不一致时，以后端实际判断为准（例如 ACTIVE 但已过期 → 拒绝）。

### 7.2 必修课预安排（TASK-009 / FIX-002）

`POST /api/v1/teaching-classes/{class_id}/assign-required?preview=true|false`

请求体（范围优先级 `class_id` > `major_id` > `college_id`，至少指定其一）：

```json
{ "college_id": null, "major_id": null, "class_id": 3 }
```

- 仅 `ACADEMIC_ADMIN`（`selection:manage`）可调用；教师/学生返回 403。
- 只允许为必修课（`REQUIRED`/`PUBLIC_REQUIRED`/`PRACTICE`）教学班预排，选修课返回 409。
- 教学班必须 ACTIVE、学期 ACTIVE、已分配教师且至少一条排课；否则 409。
- `preview=true`：只返回预览，不写库；`preview=false`：在单个事务内提交所有可新增记录。
- 校验：容量、学籍（仅 ENROLLED）、同课程其他班、时间冲突；容量不足时按学生顺序部分新增，其余逐条报告 `CAPACITY_FULL`。
- 幂等：已在本班返回 `ALREADY_ASSIGNED`；曾移除返回 `PREVIOUSLY_REMOVED`，不自动恢复。
- 写库来源：`course_selections.source = ADMIN_REQUIRED`（历史行可为 NULL）。
- 响应（FIX-002 扩展）：
  ```json
  {
    "teaching_class_id": 1, "teaching_class_code": "...", "course_code": "...", "course_name": "...",
    "scope": {"class_id": 3},
    "matched": 10, "already_assigned": 2, "would_add": 6, "added": 0, "skipped": 2,
    "capacity": 40, "selected_count": 3, "selected_count_after": 9,
    "remaining": 37, "remaining_after": 31,
    "conflict_count": 1, "ineligible_count": 1,
    "reason_counts": {"INVALID_STATUS": 1, "TIME_CONFLICT": 1},
    "preview": true, "committed": false,
    "items": [{"student_id": 1, "student_no": "...", "student_name": "...", "class_name": "...", "major_name": "...", "action": "ADD", "reason_code": null, "reason": null}]
  }
  ```
- **数据库迁移**：FIX-002 新增 `course_selections.source`（可空 `VARCHAR(20)`，`ck_selection_source`）；历史数据不回填。正式环境执行迁移前需按变更流程确认。

### 7.3 选课时间窗口 `/api/v1/selection-periods`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/selection-periods` | 列表（`semester`） | 登录 |
| POST | `/selection-periods` | 新增 | `selection:manage` |
| PUT | `/selection-periods/{period_id}` | 修改 | `selection:manage` |

**FIX-003 字段与校验**：

- 响应新增 `time_state`（`OPEN`/`NOT_STARTED`/`EXPIRED`/`INACTIVE`）、`term_status` 与 `is_effective`；`is_effective` 同时要求时间开放且学期存在并 ACTIVE。管理员“实际状态”列使用该字段。
- `POST`/`PUT` 使用同一 `SelectionPeriodCreate` 校验：`end_time` 必须晚于 `start_time`，否则 422；`target_grade_year` 限制 1900–2200。
- 同一学期多个 ACTIVE 窗口重叠时，后端选课/退课按**并集**判断（任一适用窗口开放即可），不强制合并；管理员端会提示重叠。
- 状态不会随时间自动变化：`ACTIVE` 但时间已过时，`time_state=EXPIRED`，选课/退课仍会被拒绝。

---

## 8. 课表 `/api/v1/schedules`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/schedules/mine?semester=...&week=...` | 我的课表（学生=已选课表，教师=授课课表） | 登录 |
| GET | `/schedules/students/{student_id}` | 指定学生课表（学生仅可查本人） | 登录 + 对象级校验 |

> 课表由「选课记录 + 排课」实时推导，不单独建表。`week` 参数按单双周与周次区间过滤。
>
> **FIX-007 说明**：教师/学生课表页面已改为调用 `/teaching-schedules/mine|my`（TASK-013 平铺接口，同样支持 `semester`/`week` 过滤）。本组接口保留，供「教务/教师查看指定学生课表」等既有场景使用，未做修改。

---

## 9. 成绩 `/api/v1/grades`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/grades/mine` | 我的成绩（**仅 APPROVED**） | 登录（学生） |
| GET | `/grades/mine/summary` | 我的学分与绩点统计 | 登录（学生） |
| GET | `/grades/my` | 我的成绩（含实时 GPA 与班级/专业排名，TASK-007） | 登录（学生） |
| GET | `/grades/teaching-classes/{class_id}` | 教学班成绩单（教师仅限本人教学班） | `grade:read` |
| GET | `/grades/teaching-classes/{class_id}/students` | 课程学生名单（含成绩录入状态：未录入/草稿/待审核/已通过/已驳回，教师仅限本人） | `grade:read` |
| POST | `/grades/teaching-classes/{class_id}/init` | 生成成绩单（按已选学生，幂等） | `grade:write` |
| PUT | `/grades` | 批量录入/保存草稿 | `grade:write` |
| POST | `/grades/teaching-classes/{class_id}/submit` | 提交成绩（需全部录入完整） | `grade:submit` |
| GET | `/grades/pending` | 待审核成绩（`semester`） | `grade:approve` |
| POST | `/grades/approve` | 审核通过 | `grade:approve` |
| POST | `/grades/reject` | 驳回（需原因） | `grade:approve` |
| GET | `/grades/teaching-classes/{class_id}/statistics` | 成绩分布统计 | `grade:read` |

**状态机**

```
DRAFT ──提交──> SUBMITTED ──通过──> APPROVED（学生可见）
                    │
                    └──驳回──> REJECTED ──教师修改──> SUBMITTED
```

- 总评由后端统一计算：`ScoreService.compute` 按课程 `total_hours` 经 `profile_for` 推导考核方式后取 `WEIGHT_RULES` 权重（`32`→平时0.2/期末0.8 无期中；`48`/`64`→平时0.2/期中0.3/期末0.5），期中/期末的理论+实践拆分先取平均；考核结构由后端下发，前端不得反推
- 成绩模型闭环（DATABASE.md §9.3）：教师录入原始成绩（平时/期中/期末的理论与实践中可选拆分 + 理论补考/实践补考），系统计算并回写 `theory_total_score`（理论总评）、`practice_total_score`（实践总评）、`total_score`（成绩总评）、`grade_point`、`is_passed`；前端只读展示计算结果
- **FIX-009 §七/§八**：实践拆分由课程 `practice_hours` 决定——`practice_hours > 0` 必须分别录入理论/实践（只填一侧或只填合并字段均 400），`practice_hours = 0` 禁止任何实践成绩字段；课程属性由后端下发（`has_practice`/`has_midterm`）
- 补考规则：只允许对应期末分项 < 60 时录入（否则 400 `SCORE_CALC_ERROR`）；补考成绩替换对应期末分项重算；补考通过（≥60）的一侧总评按 60 封顶；结果仍由成绩总评 ≥ 60 判定
- 前端传入的 `total_score` 等计算字段被忽略
- `APPROVED` 后教师不可直接修改
- 审核通过后自动重算学生 `total_credits` 与 `gpa`
- 待审核列表（`GET /grades/pending`）同时返回 `teaching_class_code`（教学班）与 `teacher_name`（教师），供教务审核时核对（TASK-006）
- `GET /grades/my` 返回 `{ items, gpa, class_rank, major_rank }`：`items` 为 `GradeOut`（含 `assessment_type`、`has_midterm`、`has_practice`、`course_total_hours`、`course_theory_hours`、`course_practice_hours`、全部原始成绩与计算字段），`gpa` 与排名由 GpaService / RankingService 实时计算，**不落库**；无有效成绩时三者返回 `null`（TASK-007）
- 绩点单一来源：`Grade.grade_point`、GpaService（`/grades/my` 与 `/grades/mine/summary`）、RankingService 全部经 `models/grade.GRADE_POINT_TABLE` 的 `score_to_point()` 换算，口径一致

---

## 10. 考试 `/api/v1/exams`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/exams` | 列表（`semester`、`status`） | `exam:read` |
| GET | `/exams/mine` | 我的考试（**仅 PUBLISHED**，含考场与座位号） | 登录（学生） |
| POST | `/exams` | 创建考试 | `exam:write` |
| PUT | `/exams/{exam_id}` | 修改 | `exam:write` |
| DELETE | `/exams/{exam_id}` | 删除 | `exam:write` |
| POST | `/exams/{exam_id}/rooms` | 添加考场（容量不得超过教室容量） | `exam:write` |
| POST | `/exams/{exam_id}/assign` | 自动分配考场座位 | `exam:write` |
| POST | `/exams/{exam_id}/publish` | 发布考试（需已设考场） | `exam:write` |

---

## 11. 教学评价 `/api/v1/evaluations`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/evaluations/tasks` | 评价任务列表（`semester`） | 登录 |
| POST | `/evaluations/tasks` | 创建评价任务 | `evaluation:manage` |
| GET | `/evaluations/pending?task_id=...` | 我待评价的课程 | 登录（学生） |
| POST | `/evaluations` | 提交评价 | `evaluation:write` |
| GET | `/evaluations/statistics` | 评价统计（`task_id`、`teaching_class_id`） | `evaluation:read` |

> **匿名性**：统计接口只返回聚合分数与评语文本，**绝不下发 `student_id`**。教师仅能查看自己的评价。
> 提交评价需在开放期内、且本人已选该教学班。

---

## 12. 通知公告 `/api/v1/announcements`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/announcements` | 列表（非教务仅见已发布且面向本角色的） | 登录 |
| POST | `/announcements` | 发布公告 | `announcement:write` |
| PUT | `/announcements/{ann_id}` | 修改/发布/撤回 | `announcement:write` |
| DELETE | `/announcements/{ann_id}` | 删除 | `announcement:write` |

---

## 13. 数据统计 `/api/v1/statistics`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/statistics/overview` | 教务工作台概览（学院/专业/班级/学生/教师/课程/教学班/选课/待审成绩） | `statistics:read` |
| GET | `/statistics/grade-distribution` | 全校成绩分布（`semester`） | `statistics:read` |
| GET | `/statistics/selection-ranking` | 课程选课热度排行（`semester`、`limit`） | `statistics:read` |

---

## 14. 审计日志 `/api/v1/audit-logs`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/audit-logs` | 操作日志列表（`action`、`user_id`） | `audit:read` |

> 说明：V3.1 F-09 起，已认证的写操作与登录成功/失败会写入操作日志；查询接口需要 `audit:read`。

---

## 15. 批量导入 `/api/v1/imports`

教务管理员（`ACADEMIC_ADMIN`）可导入学生 / 教师 / 课程 / 成绩；教师（`TEACHER`）可导入**本人授课教学班**的成绩（对象级校验在 `ImportService` 内完成，越权行返回错误明细）；`STUDENT` 一律 403。权限复用现有 `student:write` / `teacher:write` / `course:write` / `grade:write`。文件仅支持 `.xlsx`（openpyxl），单文件上限 10MB。

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/imports/templates/students` | 下载学生导入模板 | `student:write` |
| GET | `/imports/templates/teachers` | 下载教师导入模板 | `teacher:write` |
| GET | `/imports/templates/courses` | 下载课程导入模板 | `course:write` |
| GET | `/imports/templates/grades?teaching_class_id=` | 下载成绩导入模板（**按教学班 + 课程考核结构动态生成**，`teaching_class_id` 必填） | `grade:write` |
| POST | `/imports/students` | 批量导入学生 | `student:write` |
| POST | `/imports/teachers` | 批量导入教师 | `teacher:write` |
| POST | `/imports/courses` | 批量导入课程 | `course:write` |
| POST | `/imports/grades` | 批量导入成绩 | `grade:write` |

**模板（FIX-005）**

- 首行是**中文字段名**，同时兼容旧的英文字段名（`student_no` 等），既有调用方不受影响；取值也支持中文（职称 `教授/副教授/讲师/助教`、性别 `男/女/未知`、课程性质 `专业必修/…`）。
- 模板包含第 2 个工作表「填写说明」，逐条说明必填项与常见错误；说明不放在数据行，避免被当成数据解析。
- **成绩模板按 `teaching_class_id` 动态生成**：学号 / 姓名 / 班级 / 课程代码 / 课程名称 / 教学班 由系统带出（灰底，教师不用填），成绩列由 `AssessmentProfile` 决定：

| 课程 | 成绩列 |
|---|---|
| ≤32 学时、无实践 | 平时成绩、期末成绩 |
| ≤32 学时、有实践 | 平时成绩、期末理论、期末实践 |
| >32 学时、无实践 | 平时成绩、期中成绩、期末成绩 |
| >32 学时、有实践 | 平时成绩、期中理论、期中实践、期末理论、期末实践 |

  另有补考列（理论补考；实践课加实践补考）。**模板只负责录入原始成绩，不计算总评/绩点**——导入后由 `ScoreService` 统一计算。

**导入结果**（无论成功与否均返回 200，部分成功策略）

```json
{"total": 100, "success": 96, "failed": 4,
 "errors": [{"row": 3, "field": "student_no", "message": "学号已存在"}]}
```

- 校验规则（每行取首个错误）：字段非空 → 学院/专业/行政班存在且层级匹配 → 学号/登录名/工号/课程编号不重复（含文件内重复）→ 课程性质/职称/性别合法 → 学分与学时范围合法 → **理论+实践=总学时** → 成绩 0-100 且理论/实践成对填写 → 实践成绩与课程 `practice_hours` 匹配（FIX-009）→ 补考只允许对应期末分项 < 60 时填写 → 教师只能导入本人授课教学班。
- 学生导入复用 `StudentService.create_student`（`username` 缺省取学号；`enrollment_year` 取行政班 `grade_year`）。
- 教师导入复用 `TeacherService.create_teacher`（`teacher_no` 即登录名，初始密码 = 工号）。
- 课程导入复用 `CourseService.create`，**不会**自动创建学院；考核方式由 `total_hours` 推导，**不接受也不允许手填**。
- 成绩导入复用 `GradeService.import_scores` → `ScoreService.compute_for_draft` 统一计算，**一律保存为 DRAFT**；`SUBMITTED` / `APPROVED` 不可覆盖，`DRAFT` / `REJECTED` 可更新，未录入（NOT_ENTERED）可新建。**不写 GPA / 排名**。

### 15.1 成绩草稿删除 `/api/v1/grades/{grade_id}`

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| DELETE | `/grades/{grade_id}` | 删除成绩草稿，成功 204 | `grade:write`（教师仅限本人教学班） |

- **只有 `DRAFT` 允许删除**；`SUBMITTED` / `APPROVED` / `REJECTED` 一律 409（草稿与正式成绩共用 `grades` 表，删除严格依赖状态判断，不按 id 直删）。
- 教师删除他人教学班的草稿返回 403；教务可删除任意草稿。

---

## 16. 原计划接口的当前状态

| 接口 | 当前状态 |
|---|---|
| Excel 导出 | 已实现：学生/课程/已审核成绩/选课结果 |
| 教学资料 | 已实现：上传/列表/下载/删除，按教学班鉴权 |
| 调停课申请 | 已实现：申请/审批/驳回，批准后原子改排课 |
| 学生端培养方案查询 | 已实现：学生查看本专业培养方案 |

---

## 17. 权限码清单（42 项）

| 模块 | 权限码 |
|---|---|
| 基础数据 | `college:read/write`、`major:read/write`、`class:read/write`、`classroom:read/write` |
| 人员 | `student:read/write/export`、`teacher:read/write` |
| 用户 | `user:read/write` |
| 课程 | `course:read/write`、`curriculum:read/write` |
| 开课排课 | `teaching:read/write`、`schedule:read/write` |
| 学期 | `term:read/write` |
| 选课 | `selection:read/write/manage` |
| 成绩 | `grade:read/write/submit/approve/export` |
| 考试 | `exam:read/write` |
| 评价 | `evaluation:read/write/manage` |
| 公告 | `announcement:read/write` |
| 统计审计 | `statistics:read`、`audit:read` |

**角色权限分配**（`scripts/seed_rbac.py`）

| 角色 | 权限数 | 范围 |
|---|---|---|
| `STUDENT` | 11 | 课程查看、培养方案、课表、选课、成绩查看、考试、评价、公告、学期查看 |
| `TEACHER` | 13 | 课程/班级/学生查看、教学任务、课表、选课查看、成绩录入与提交、考试、评价、公告、学期查看 |
| `ACADEMIC_ADMIN` | 42 | 全部权限 |

---

## 18. V3.2 接口补充（按实际 OpenAPI）

以下为 V3.1/V3.2 新增或增强的主要接口组，完整参数以 `/openapi.json` 为准。

### 18.1 学期与教学班

| 方法 | 路径 | 说明 | 权限/对象 |
|---|---|---|---|
| GET | `/terms/active` | 当前唯一 ACTIVE 学期 | `term:read` |
| GET | `/teaching-classes/mine` | 教师本人授课课程 | 教师本人 |
| GET/PUT/DELETE | `/teaching-classes/{id}` | 教学班详情/编辑/删除 | `teaching:read/write` + 对象 |
| POST | `/teaching-classes/{id}/selection` | 开放/关闭选课（校验教师/排课） | `teaching:write` |
| GET/POST | `/teaching-classes/{id}/students` | 名单查询/添加 | `selection:manage` |
| DELETE | `/teaching-classes/{id}/students/{student_id}` | 移除学生（有成绩拒绝） | `selection:manage` |
| POST | `/teaching-classes/{id}/assign-required?preview=` | 必修课预安排/只读预览 | `selection:manage` |
| GET/POST | `/teaching-classes/{id}/schedules` | 排课查询/新增 | `teaching:*` |
| PUT/DELETE | `/teaching-classes/{id}/schedules/{sid}` | 修改/删除排课（冲突检测） | `teaching:write` |

### 18.2 选课

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/course-selections/window?semester=` | 学生选课/退课窗口状态与原因 |
| GET | `/course-selections/available?semester=` | 可选课程（窗口/年级/ACTIVE 校验） |
| GET | `/course-selections/mine?semester=` | 本人选课 |
| POST | `/course-selections` | 选课 |
| DELETE | `/course-selections/{id}` | 退课 |

### 18.3 成绩

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/grades/my` | 学生成绩 + GPA + 班级/专业排名 |
| GET | `/grades/approved` | 已审核成绩（教务） |
| GET | `/grades/{id}/history` | 成绩变更历史 |
| POST | `/grades/{id}/unapprove` | 撤销审核（APPROVED→REJECTED） |
| POST | `/grades/{id}/correct` | 直接更正已审核成绩（写快照） |
| POST | `/grades/approve` / `/grades/reject` | 批量审核/驳回 |
| POST | `/grades/teaching-classes/{id}/init` | 生成成绩单（幂等） |
| GET | `/grades/teaching-classes/{id}/students` | 名单 + 录入状态 |
| GET | `/grades/teaching-classes/{id}/statistics` | 成绩分布 |

### 18.4 考试

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/exams` | 考试列表/创建（冲突检测） |
| PUT/DELETE | `/exams/{id}` | 修改/删除 |
| POST | `/exams/{id}/rooms` | 添加考场 |
| PUT/DELETE | `/exams/{id}/rooms/{rid}` | 修改/删除考场（容量/监考/已排座保护） |
| POST | `/exams/{id}/assign` | 自动分配座位 |
| POST | `/exams/{id}/publish` | 发布考试 |
| GET | `/exams/mine` | 学生本人考试与座位 |

### 18.5 评价、资料、调停课

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/evaluations/tasks` | 评价任务列表/创建 |
| PUT | `/evaluations/tasks/{id}` | 修改评价任务（时间校验） |
| POST | `/evaluations` | 学生提交评价（学期/选课/一次校验） |
| GET | `/evaluations/statistics` | 评价统计 |
| GET/POST | `/materials` | 资料列表/上传（≤10MB，类型白名单） |
| GET | `/materials/my` | 我可查看的资料 |
| GET | `/materials/{id}/download` | 鉴权下载 |
| DELETE | `/materials/{id}` | 删除（教师本人/管理员） |
| GET/POST | `/schedule-adjustments` | 调停课列表/提交 |
| GET | `/schedule-adjustments/mine` | 我的申请 |
| POST | `/schedule-adjustments/{id}/approve` / `reject` | 审批（行锁，原子改排课） |

### 18.6 导入导出与审计

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/imports/templates/{students,teachers,courses,grades}` | 导入模板 |
| POST | `/imports/{students,teachers,courses,grades}` | 批量导入 |
| GET | `/exports/students|courses|grades|selections` | xlsx 导出 |
| GET | `/audit-logs` | 操作日志（`audit:read`，可按 action/user/resource 过滤） |

### 18.7 错误码补充

| 错误码 | HTTP | 说明 |
|---|---:|---|
| `AUTH_ACCOUNT_LOCKED` | 423 | 含 `retry_after_seconds`、`locked_until` |
| `AUTH_ACCOUNT_DISABLED` | 403 | 停用 |
| `VALIDATION_ERROR` | 422 | `errors[]` |
| `TEACHING_CLASS_*` / `CAPACITY_*` / `TEACHING_SCHEDULE_*` | 409 | 教学班/排课业务冲突 |

## 19. 相关文档

- [ARCHITECTURE.md](ARCHITECTURE.md) — 分层与模块结构
- [DATABASE.md](DATABASE.md) — 表结构与字段
- [TESTING.md](TESTING.md) — API 测试方式
