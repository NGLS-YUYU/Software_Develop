# 系统架构设计

> 依据当前代码实际情况整理（TASK-DOC-001，2026-09-17）。
> 技术栈与目录职责均以代码为准，见 [DATABASE.md](DATABASE.md)、[API.md](API.md)。

---

## 1. 总体架构

前后端分离的单体 Web 应用。

```
┌─────────────────────────────────────────────┐
│  Browser（PC Web，Chrome/Edge）              │
│  Vue 3 + TypeScript + Element Plus          │
│  Pinia（状态） + Vue Router（路由守卫）        │
└──────────────────┬──────────────────────────┘
                   │  Axios（/api/v1/*，开发期由 Vite 代理）
                   ▼
┌─────────────────────────────────────────────┐
│  FastAPI 应用（backend/app）                  │
│  ┌───────────────────────────────────────┐  │
│  │ api/v1/*.py     Router：HTTP 请求/响应  │  │
│  ├───────────────────────────────────────┤  │
│  │ api/deps.py     认证与权限依赖注入        │  │
│  ├───────────────────────────────────────┤  │
│  │ services/*.py   Service：业务逻辑        │  │
│  ├───────────────────────────────────────┤  │
│  │ repositories/   Repository：数据访问     │  │
│  ├───────────────────────────────────────┤  │
│  │ models/*.py     SQLAlchemy ORM 模型     │  │
│  │ schemas/*.py    Pydantic 校验与序列化    │  │
│  └───────────────────────────────────────┘  │
└──────────────────┬──────────────────────────┘
                   │  PyMySQL（SQLAlchemy 2.x dialect）
                   ▼
┌─────────────────────────────────────────────┐
│  MySQL 8.4 LTS（InnoDB / utf8mb4 / +08:00）  │
└─────────────────────────────────────────────┘
```

**分层约束**（CLAUDE.md §11）：`Router → Service → Repository/CRUD → SQLAlchemy → MySQL`。
禁止把大量业务逻辑写在 Router 中。

---

## 2. 后端结构

```
backend/
├── app/
│   ├── main.py               FastAPI 入口、CORS、异常处理器、路由挂载
│   ├── core/
│   │   ├── config.py         pydantic-settings 配置（读 .env）
│   │   ├── security.py       密码哈希（bcrypt）与 JWT（python-jose）
│   │   └── exceptions.py     统一业务异常与错误码
│   ├── db/
│   │   ├── base.py           DeclarativeBase + IdMixin + TimestampMixin
│   │   └── session.py        engine / SessionLocal / get_db 依赖
│   ├── models/               SQLAlchemy 模型（10 个模块文件）
│   ├── schemas/              Pydantic 请求/响应模型（6 个模块文件）
│   ├── repositories/         BaseRepository + UserRepository
│   ├── services/             BaseCrudService + 8 个业务 Service + ScoreService/GpaService/RankingService
│   ├── api/
│   │   ├── deps.py           get_current_user / RequireRoles / RequirePermissions
│   │   └── v1/               11 个路由模块 + __init__.py 汇总
│   └── utils/                预留（当前为空）
├── alembic/                  数据库迁移
├── tests/                    pytest 测试
└── scripts/                  种子数据与环境脚本
```

### 2.1 各层职责

| 层 | 目录 | 职责 | 禁止事项 |
|---|---|---|---|
| Router | `app/api/v1/` | 解析 HTTP 请求、调用 Service、返回响应 | 不写业务规则、不直接查库 |
| 依赖 | `app/api/deps.py` | 认证解析、角色/权限校验 | —— |
| Service | `app/services/` | 业务规则、事务边界、校验 | 不处理 HTTP 细节 |
| Repository | `app/repositories/` | 数据访问、查询封装 | 不含业务规则 |
| Model | `app/models/` | 表结构、关系、约束 | 不含业务逻辑（少量领域方法除外） |
| Schema | `app/schemas/` | 入参校验、出参序列化 | 不查库 |

### 2.2 模型模块划分

| 文件 | 表 |
|---|---|
| `models/user.py` | users |
| `models/role.py` | roles / permissions / user_roles / role_permissions |
| `models/organization.py` | colleges / majors / classes / classrooms |
| `models/person.py` | students / teachers |
| `models/course.py` | courses / course_prerequisites / curriculum_plans / curriculum_courses |
| `models/teaching.py` | teaching_tasks / teaching_classes / schedules |
| `models/selection.py` | course_selections / selection_periods |
| `models/grade.py` | grades（含总评与绩点计算） |
| `models/exam.py` | exams / exam_rooms / exam_students |
| `models/misc.py` | evaluation_tasks / evaluations / announcements / operation_logs |

> `models/__init__.py` 集中导入全部模型 —— **新增模型必须在此登记**，否则 Alembic autogenerate 会漏表。

### 2.3 路由模块划分

| 文件 | 前缀 | 说明 |
|---|---|---|
| `api/v1/auth.py` | `/auth` | 登录、当前用户、改密、退出 |
| `api/v1/user.py` | `/users` | 用户账号管理（列表/新建/重置密码/停用启用） |
| `api/v1/organization.py` | `/colleges` `/majors` `/classes` `/classrooms` | 基础数据 CRUD |
| `api/v1/person.py` | `/students` `/teachers` | 人员档案与账号联动 |
| `api/v1/course.py` | `/courses` `/curriculum-plans` | 课程、先修、培养方案 |
| `api/v1/teaching.py` | `/teaching-tasks` `/teaching-classes` | 开课、教学班、排课 |
| `api/v1/selection.py` | `/course-selections` `/selection-periods` | 选课、退课、选课窗口 |
| `api/v1/schedule.py` | `/schedules` | 课表（由选课+排课推导） |
| `api/v1/grade.py` | `/grades` | 成绩录入/提交/审核/统计 |
| `api/v1/exam.py` | `/exams` | 考试、考场、自动排座 |
| `api/v1/misc.py` | `/evaluations` `/announcements` `/statistics` `/audit-logs` | 评价、公告、统计、审计 |
| `api/v1/__init__.py` | —— | 汇总所有 v1 路由 |

---

## 3. 前端结构

```
frontend/
├── vite.config.ts        别名 @ → src，/api 代理到 :8000，Element Plus 按需导入
├── tsconfig.app.json     路径别名与编译选项
└── src/
    ├── main.ts           应用入口：Pinia、Router、Element Plus、图标注册
    ├── App.vue           根组件（仅 router-view）
    ├── api/
    │   ├── request.ts    Axios 实例、Token 注入、统一错误处理、page_size 夹取
    │   └── index.ts      按业务模块组织的 API 调用
    ├── types/index.ts    与后端 Schema 对应的 TypeScript 类型
    ├── stores/auth.ts    认证状态（token / user / roles / permissions）
    ├── router/index.ts   路由表与角色守卫
    ├── layouts/          MainLayout.vue（侧边菜单 + 顶栏，按角色动态生成）
    ├── components/       ScheduleGrid.vue（周课表网格）
    ├── composables/      useCrudTable.ts（分页表格通用逻辑）、useSemester.ts
    ├── assets/           main.css
    └── views/            28 个页面
```

### 3.1 页面清单（28 个）

| 端 | 数量 | 页面 |
|---|---|---|
| 公共 | 3 | `Login.vue`、`common/Forbidden.vue`、`common/NotFound.vue`；另 `common/Announcements.vue` 供学生/教师共用 |
| 学生端 | 7 | Dashboard、Profile、Schedule、Selection、Grades、Exams、Evaluation |
| 教师端 | 5 | Dashboard、MyCourses、Schedule、GradeEntry、Evaluation |
| 教务端 | 12 | Dashboard、Organization、Students、Teachers、Courses、Curriculum、Teaching、SelectionManage、GradeApproval、Exams、AnnouncementManage、Statistics |

### 3.2 认证与权限流

```
登录 → POST /api/v1/auth/login
     ← access_token + user + roles + permissions + home_route
     ↓
Pinia auth store 持久化 token 与 user（localStorage）
     ↓
路由守卫 router/index.ts
     ├─ 未登录 → 跳 /login
     ├─ 已登录但 permissions 为空（刷新页面）→ GET /auth/me 重新拉取
     └─ 路由 meta.roles 与 user.user_type 不符 → 跳 /403
     ↓
MainLayout 依据当前路由子树动态生成侧边菜单
```

> **前端权限仅用于体验**（菜单展示、路由拦截），后端 API 独立校验（CLAUDE.md §9 / §15）。
> `roles` 与 `permissions` 不落 localStorage，每次刷新从 `/auth/me` 重新获取。

### 3.3 状态管理

仅一个 Pinia store：`stores/auth.ts`。
其余页面数据通过 `api/index.ts` 直接获取，未做全局缓存，列表状态由 `useCrudTable` 组合式函数在组件内维护。

---

## 4. 关键业务机制

| 机制 | 实现位置 | 说明 |
|---|---|---|
| 事务边界 | `services/*.py` | Service 方法内 `commit`，失败整体回滚 |
| 选课防超卖 | `services/selection.py` | `SELECT ... FOR UPDATE` 行级锁 + `uk_selection` 唯一约束兜底 |
| 排课冲突检测 | `services/teaching.py` → `ConflictChecker` | 教室/教师/学生三类冲突，含单双周相容判定 |
| 先修课环路检测 | `services/course.py` | 图遍历，`CHECK` 只能挡直接自引用 |
| 总评与绩点 | `services/score_service.py` → `ScoreService` | 按 `course.assessment_type` 读取 `WEIGHT_RULES`，理论+实践先平均，不接受前端传入 |
| 学分与 GPA 汇总 | `services/grade.py` → `_refresh_student_credits()` | 审核通过后重算，仅统计及格成绩 |
| GPA 与排名 | `services/gpa_service.py` / `ranking_service.py` | GPA 实时计算不落库；班级/专业排名按 GPA 降序（TASK-004） |
| 登录失败锁定 | `services/auth.py` | 连续失败达阈值后锁定账号 |
| 二级冗余同步 | `services/person.py` 等 | 学生 → 班级 → 专业 → 学院 写入时保持一致 |

---

## 5. 数据库迁移

```
Alembic（backend/alembic/）
├── env.py          从 app.core.config 读 DATABASE_URL；导入 app.models 以发现全部表
└── versions/
    ├── 20260915_0114_bc0a832224a4_create_rbac_tables.py
    └── 20260915_0128_7d34560e8aba_create_business_tables.py
```

- 连接串**不在 `alembic.ini`** 中维护，统一由 `env.py` 从配置读取，避免两处漂移。
- `alembic.ini` 的 `file_template` 带时间戳前缀，便于按顺序阅读。
- 禁止手工改库替代迁移；禁止删除已提交的历史迁移（CLAUDE.md §27）。

---

## 6. 相关文档

- [PRD.md](PRD.md) — 业务需求
- [DATABASE.md](DATABASE.md) — 表结构与字段级设计
- [API.md](API.md) — 接口清单
- [DEVELOPMENT.md](DEVELOPMENT.md) — 开发规范
- [CLAUDE.md](../CLAUDE.md) — 项目规范（最高依据）
