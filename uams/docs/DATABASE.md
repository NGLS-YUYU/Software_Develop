# UAMS 数据库设计

高校教务教学管理系统（UAMS）字段级数据库设计。

| 项目 | 值 |
|---|---|
| 数据库 | MySQL 8.4 LTS |
| 存储引擎 | InnoDB |
| 字符集 | utf8mb4 / utf8mb4_0900_ai_ci |
| 时区 | +08:00 |
| 迁移管理 | Alembic |
| 文档版本 | V1.0（2026-09-15） |

本文档是 `CLAUDE.md §5/§6` 与 `PRD §12` 的字段级落地。表结构变更必须先改本文档，再写 Alembic migration。

---

# 1. 通用约定

## 1.1 主键

所有业务表使用自增代理主键：

```sql
id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY
```

业务编号（学号、工号、课程代码）单独建 `UNIQUE` 索引，不做主键。理由：业务编号存在变更可能，作主键会导致外键连锁修改。

## 1.2 时间戳

所有表包含：

```sql
created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
```

## 1.3 状态字段

统一使用 `VARCHAR(20)` + `CHECK` 约束，全大写下划线命名：

```sql
status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
CONSTRAINT ck_xxx_status CHECK (status IN ('ACTIVE','INACTIVE'))
```

## 1.4 数值类型

| 用途 | 类型 | 说明 |
|---|---|---|
| 学分 | `DECIMAL(4,1)` | 如 3.5、2.0 |
| 成绩 | `DECIMAL(5,2)` | 0.00 ~ 100.00 |
| 绩点 | `DECIMAL(3,2)` | 0.00 ~ 5.00 |
| 学时 | `SMALLINT UNSIGNED` | 整数 |
| 人数/容量 | `SMALLINT UNSIGNED` | 整数 |

**禁止对成绩、学分、绩点使用 `FLOAT` / `DOUBLE`**（二进制浮点存在精度误差，会导致总评计算和学分统计出错）。

## 1.5 外键

全部显式声明，命名 `fk_<子表>_<父表>`。删除策略：

- 基础数据被引用（学院、专业、课程等）→ `ON DELETE RESTRICT`
- 从属明细（选课、成绩、考场等）→ `ON DELETE CASCADE`

## 1.6 命名

- 表名：小写复数下划线，如 `course_selections`
- 索引：`idx_<表>_<字段>`；唯一索引：`uk_<表>_<字段>`
- 布尔：`is_` 前缀，`TINYINT(1)`

## 1.7 学期标识

统一格式 `YYYY-YYYY-N`，如 `2026-2027-1`（第一学期）。用 `VARCHAR(16)`，全库一致。

---

# 2. ER 总览

```
users ──┬── user_roles ── roles ── role_permissions ── permissions
        ├── students ── classes ── majors ── colleges
        └── teachers ──────────────┘         │
                                             │
colleges ── majors ── curriculum_plans ── curriculum_courses ── courses
                                                                  │
                                                     course_prerequisites
                                                                  │
courses ── teaching_tasks ── teaching_classes ──┬── schedules ── classrooms
                    │              │            ├── course_selections ── students
                 teachers          │            ├── grades ── students
                                   │            ├── evaluations ── students
                                   └── exams ── exam_rooms ── classrooms

announcements     operation_logs
```

---

# 3. 认证与权限

## 3.1 users

统一账号表。学生、教师、教务共用，通过 `user_type` 区分并关联各自档案表。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK, AUTO_INCREMENT | |
| username | VARCHAR(50) | NOT NULL, UNIQUE | 登录名；学生为学号，教师为工号 |
| password_hash | VARCHAR(255) | NOT NULL | bcrypt 哈希，禁止明文 |
| real_name | VARCHAR(50) | NOT NULL | 真实姓名 |
| user_type | VARCHAR(20) | NOT NULL | STUDENT / TEACHER / ADMIN |
| email | VARCHAR(100) | NULL, UNIQUE | |
| phone | VARCHAR(20) | NULL | |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'ACTIVE' | ACTIVE / DISABLED / LOCKED |
| last_login_at | DATETIME | NULL | |
| failed_login_count | SMALLINT UNSIGNED | NOT NULL, DEFAULT 0 | 登录失败限制（CLAUDE.md §23） |
| locked_until | DATETIME | NULL | 锁定到期时间 |
| created_at / updated_at | DATETIME | NOT NULL | |

```sql
CONSTRAINT ck_users_type   CHECK (user_type IN ('STUDENT','TEACHER','ADMIN'))
CONSTRAINT ck_users_status CHECK (status IN ('ACTIVE','DISABLED','LOCKED'))
UNIQUE KEY uk_users_username (username)
UNIQUE KEY uk_users_email (email)
KEY idx_users_type_status (user_type, status)
```

## 3.2 roles

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| code | VARCHAR(30) | NOT NULL, UNIQUE | STUDENT / TEACHER / ACADEMIC_ADMIN |
| name | VARCHAR(50) | NOT NULL | 显示名 |
| description | VARCHAR(200) | NULL | |
| is_builtin | TINYINT(1) | NOT NULL, DEFAULT 0 | 内置角色不可删除 |
| created_at / updated_at | DATETIME | NOT NULL | |

第一阶段仅 3 个角色（CLAUDE.md §8），`SYSTEM_ADMIN` 等留待扩展。

## 3.3 permissions

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| code | VARCHAR(80) | NOT NULL, UNIQUE | 如 `course:create` |
| name | VARCHAR(80) | NOT NULL | |
| module | VARCHAR(40) | NOT NULL | 所属模块，用于分组 |
| description | VARCHAR(200) | NULL | |

权限码格式 `<资源>:<动作>`，动作取 `create` / `read` / `update` / `delete` / `approve` / `export`。

## 3.4 user_roles

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT UNSIGNED | PK |
| user_id | BIGINT UNSIGNED | NOT NULL, FK → users(id) ON DELETE CASCADE |
| role_id | BIGINT UNSIGNED | NOT NULL, FK → roles(id) ON DELETE CASCADE |
| created_at | DATETIME | NOT NULL |

```sql
UNIQUE KEY uk_user_roles (user_id, role_id)
```

## 3.5 role_permissions

结构同上，`role_id` + `permission_id`，唯一约束 `uk_role_permissions (role_id, permission_id)`。

---

# 4. 组织结构

## 4.1 colleges

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| code | VARCHAR(20) | NOT NULL, UNIQUE | 学院代码 |
| name | VARCHAR(100) | NOT NULL | 学院名称 |
| description | VARCHAR(500) | NULL | |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'ACTIVE' | ACTIVE / INACTIVE |
| created_at / updated_at | DATETIME | NOT NULL | |

## 4.2 majors

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| code | VARCHAR(20) | NOT NULL, UNIQUE | 专业代码 |
| name | VARCHAR(100) | NOT NULL | |
| college_id | BIGINT UNSIGNED | NOT NULL, FK → colleges(id) RESTRICT | |
| degree_type | VARCHAR(20) | NOT NULL | 学位类型：BACHELOR / MASTER |
| duration_years | TINYINT UNSIGNED | NOT NULL, DEFAULT 4 | 学制 |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'ACTIVE' | |

```sql
KEY idx_majors_college (college_id)
```

## 4.3 classes

行政班级。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| code | VARCHAR(30) | NOT NULL, UNIQUE | 班级代码 |
| name | VARCHAR(60) | NOT NULL | 如「计算机 2026-1 班」 |
| major_id | BIGINT UNSIGNED | NOT NULL, FK → majors(id) RESTRICT | |
| grade_year | SMALLINT UNSIGNED | NOT NULL | 入学年份，如 2026 |
| counselor_id | BIGINT UNSIGNED | NULL, FK → teachers(id) SET NULL | 辅导员 |
| student_count | SMALLINT UNSIGNED | NOT NULL, DEFAULT 0 | 冗余计数，选课/学籍变更时同步 |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'ACTIVE' | |

```sql
KEY idx_classes_major_grade (major_id, grade_year)
```

## 4.4 classrooms

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| code | VARCHAR(30) | NOT NULL, UNIQUE | 如 `A-301` |
| building | VARCHAR(50) | NOT NULL | 楼栋 |
| capacity | SMALLINT UNSIGNED | NOT NULL | 容纳人数 |
| room_type | VARCHAR(20) | NOT NULL, DEFAULT 'NORMAL' | NORMAL / LAB / MULTIMEDIA |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'ACTIVE' | ACTIVE / MAINTENANCE / DISABLED |

---

# 5. 人员档案

## 5.1 students

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| user_id | BIGINT UNSIGNED | NOT NULL, UNIQUE, FK → users(id) CASCADE | |
| student_no | VARCHAR(30) | NOT NULL, UNIQUE | 学号 |
| class_id | BIGINT UNSIGNED | NOT NULL, FK → classes(id) RESTRICT | |
| major_id | BIGINT UNSIGNED | NOT NULL, FK → majors(id) RESTRICT | 冗余，便于按专业统计 |
| college_id | BIGINT UNSIGNED | NOT NULL, FK → colleges(id) RESTRICT | 冗余，便于按学院统计 |
| gender | VARCHAR(10) | NOT NULL | MALE / FEMALE / UNKNOWN |
| birth_date | DATE | NULL | |
| enrollment_year | SMALLINT UNSIGNED | NOT NULL | 入学年份 |
| academic_status | VARCHAR(20) | NOT NULL, DEFAULT 'ENROLLED' | 学籍状态 |
| total_credits | DECIMAL(5,1) | NOT NULL, DEFAULT 0.0 | 已修总学分 |
| gpa | DECIMAL(3,2) | NULL | 平均绩点 |

```sql
CONSTRAINT ck_students_status CHECK (academic_status IN
  ('ENROLLED','SUSPENDED','GRADUATED','WITHDRAWN'))
KEY idx_students_class (class_id)
KEY idx_students_major (major_id)
KEY idx_students_college_year (college_id, enrollment_year)
```

> `major_id` / `college_id` 是**有意的冗余**。严格三范式下可经 `class → major → college` 推导，但学生列表、成绩统计、培养方案校验都高频按专业/学院过滤，三表 JOIN 代价明显。写入时由 Service 层保证与 `class_id` 一致。

## 5.2 teachers

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| user_id | BIGINT UNSIGNED | NOT NULL, UNIQUE, FK → users(id) CASCADE | |
| teacher_no | VARCHAR(30) | NOT NULL, UNIQUE | 工号 |
| college_id | BIGINT UNSIGNED | NOT NULL, FK → colleges(id) RESTRICT | |
| title | VARCHAR(20) | NULL | 职称 |
| gender | VARCHAR(10) | NOT NULL | |
| hire_date | DATE | NULL | |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'ACTIVE' | ACTIVE / LEAVE / RETIRED |

```sql
CONSTRAINT ck_teachers_title CHECK (title IS NULL OR title IN
  ('ASSISTANT','LECTURER','ASSOCIATE_PROFESSOR','PROFESSOR'))
KEY idx_teachers_college (college_id)
```

---

# 6. 课程与培养方案

## 6.1 courses

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| code | VARCHAR(30) | NOT NULL, UNIQUE | 课程代码 |
| name | VARCHAR(100) | NOT NULL | |
| college_id | BIGINT UNSIGNED | NOT NULL, FK → colleges(id) RESTRICT | 开课学院 |
| course_type | VARCHAR(20) | NOT NULL | 课程性质 |
| credits | DECIMAL(4,1) | NOT NULL | 学分 |
| total_hours | SMALLINT UNSIGNED | NOT NULL | 总学时 |
| theory_hours | SMALLINT UNSIGNED | NOT NULL, DEFAULT 0 | 理论学时 |
| practice_hours | SMALLINT UNSIGNED | NOT NULL, DEFAULT 0 | 实践学时 |
| exam_type | VARCHAR(20) | NOT NULL, DEFAULT 'EXAM' | EXAM 考试 / CHECK 考查 |
| regular_weight | DECIMAL(3,2) | NOT NULL, DEFAULT 0.40 | 平时成绩权重 |
| final_weight | DECIMAL(3,2) | NOT NULL, DEFAULT 0.60 | 期末成绩权重 |
| description | TEXT | NULL | |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'ACTIVE' | |

```sql
CONSTRAINT ck_courses_type CHECK (course_type IN
  ('REQUIRED','ELECTIVE','PUBLIC_REQUIRED','PUBLIC_ELECTIVE','PRACTICE'))
CONSTRAINT ck_courses_weight CHECK (regular_weight + final_weight = 1.00)
CONSTRAINT ck_courses_credits CHECK (credits > 0)
KEY idx_courses_college_type (college_id, course_type)
```

> 成绩权重放在课程上，由后端统一计算总评（CLAUDE.md §21：不得硬编码到前端）。`CHECK` 保证两项权重和恒为 1。

## 6.2 course_prerequisites

先修课程关系。自引用多对多。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| course_id | BIGINT UNSIGNED | NOT NULL, FK → courses(id) CASCADE | 目标课程 |
| prerequisite_course_id | BIGINT UNSIGNED | NOT NULL, FK → courses(id) CASCADE | 先修课程 |
| min_score | DECIMAL(5,2) | NOT NULL, DEFAULT 60.00 | 先修最低成绩 |

```sql
UNIQUE KEY uk_course_prereq (course_id, prerequisite_course_id)
CONSTRAINT ck_course_prereq_self CHECK (course_id <> prerequisite_course_id)
```

> `CHECK` 只能挡住直接自引用。**环路（A→B→A）必须在 Service 层做图检测**，数据库无法约束。

## 6.3 curriculum_plans

专业培养方案。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| code | VARCHAR(30) | NOT NULL, UNIQUE | |
| name | VARCHAR(100) | NOT NULL | |
| major_id | BIGINT UNSIGNED | NOT NULL, FK → majors(id) RESTRICT | |
| grade_year | SMALLINT UNSIGNED | NOT NULL | 适用年级 |
| total_credits_required | DECIMAL(5,1) | NOT NULL | 毕业总学分要求 |
| required_credits | DECIMAL(5,1) | NOT NULL | 必修学分要求 |
| elective_credits | DECIMAL(5,1) | NOT NULL | 选修学分要求 |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'DRAFT' | DRAFT / PUBLISHED / ARCHIVED |

```sql
UNIQUE KEY uk_curriculum_major_year (major_id, grade_year)
```

## 6.4 curriculum_courses

方案—课程关系。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| plan_id | BIGINT UNSIGNED | NOT NULL, FK → curriculum_plans(id) CASCADE | |
| course_id | BIGINT UNSIGNED | NOT NULL, FK → courses(id) RESTRICT | |
| suggested_semester | TINYINT UNSIGNED | NOT NULL | 建议修读学期 1~8 |
| is_required | TINYINT(1) | NOT NULL, DEFAULT 1 | 是否必修 |

```sql
UNIQUE KEY uk_curriculum_courses (plan_id, course_id)
KEY idx_curriculum_courses_sem (plan_id, suggested_semester)
```

---

# 7. 开课与排课

## 7.1 teaching_tasks

教学任务：某学期要开某门课。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| semester | VARCHAR(16) | NOT NULL | 如 `2026-2027-1` |
| course_id | BIGINT UNSIGNED | NOT NULL, FK → courses(id) RESTRICT | |
| college_id | BIGINT UNSIGNED | NOT NULL, FK → colleges(id) RESTRICT | 承担学院 |
| planned_classes | SMALLINT UNSIGNED | NOT NULL, DEFAULT 1 | 计划开班数 |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'DRAFT' | |

```sql
UNIQUE KEY uk_teaching_tasks (semester, course_id, college_id)
CONSTRAINT ck_teaching_tasks_status CHECK (status IN
  ('DRAFT','CONFIRMED','CANCELLED'))
KEY idx_teaching_tasks_semester (semester)
```

## 7.2 teaching_classes

教学班：任务下的具体班级，是**选课、排课、成绩、考试的公共锚点**。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| code | VARCHAR(40) | NOT NULL, UNIQUE | 教学班号 |
| task_id | BIGINT UNSIGNED | NOT NULL, FK → teaching_tasks(id) CASCADE | |
| course_id | BIGINT UNSIGNED | NOT NULL, FK → courses(id) RESTRICT | 冗余，避免高频三表 JOIN |
| semester | VARCHAR(16) | NOT NULL | 冗余，同上 |
| teacher_id | BIGINT UNSIGNED | NULL, FK → teachers(id) RESTRICT | 授课教师，排课前可为空 |
| capacity | SMALLINT UNSIGNED | NOT NULL | 容量上限 |
| selected_count | SMALLINT UNSIGNED | NOT NULL, DEFAULT 0 | 已选人数 |
| selection_status | VARCHAR(20) | NOT NULL, DEFAULT 'CLOSED' | CLOSED / OPEN / FINISHED |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'ACTIVE' | ACTIVE / CANCELLED |

```sql
CONSTRAINT ck_teaching_classes_sel CHECK (selection_status IN
  ('CLOSED','OPEN','FINISHED'))
CONSTRAINT ck_teaching_classes_cap CHECK (capacity > 0)
CONSTRAINT ck_teaching_classes_cnt CHECK (selected_count >= 0)
KEY idx_tc_semester_course (semester, course_id)
KEY idx_tc_teacher (teacher_id)
KEY idx_tc_selection (selection_status, semester)
```

> `selected_count` 是冗余计数，必须与 `course_selections` 实际行数一致。选课/退课**必须在同一事务内**更新两者（CLAUDE.md §19），并用 `SELECT ... FOR UPDATE` 锁住本行防超卖（§20）。

## 7.3 schedules

排课。一个教学班可有多条（如周二 1-2 节 + 周四 3-4 节）。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| teaching_class_id | BIGINT UNSIGNED | NOT NULL, FK → teaching_classes(id) CASCADE | |
| classroom_id | BIGINT UNSIGNED | NOT NULL, FK → classrooms(id) RESTRICT | |
| day_of_week | TINYINT UNSIGNED | NOT NULL | 1=周一 … 7=周日 |
| start_period | TINYINT UNSIGNED | NOT NULL | 起始节次 |
| end_period | TINYINT UNSIGNED | NOT NULL | 结束节次 |
| start_week | TINYINT UNSIGNED | NOT NULL | 起始周 |
| end_week | TINYINT UNSIGNED | NOT NULL | 结束周 |
| week_type | VARCHAR(10) | NOT NULL, DEFAULT 'ALL' | ALL / ODD / EVEN |
| semester | VARCHAR(16) | NOT NULL | 冗余，冲突检测用 |

```sql
CONSTRAINT ck_schedules_day    CHECK (day_of_week BETWEEN 1 AND 7)
CONSTRAINT ck_schedules_period CHECK (start_period >= 1 AND end_period >= start_period)
CONSTRAINT ck_schedules_week   CHECK (start_week >= 1 AND end_week >= start_week)
CONSTRAINT ck_schedules_wtype  CHECK (week_type IN ('ALL','ODD','EVEN'))
KEY idx_schedules_tc (teaching_class_id)
KEY idx_schedules_conflict (semester, day_of_week, classroom_id)
KEY idx_schedules_time (semester, day_of_week, start_period, end_period)
```

### 冲突判定

两条排课冲突，当且仅当**同时**满足：

1. 同学期
2. `day_of_week` 相同
3. 节次区间重叠：`a.start_period <= b.end_period AND b.start_period <= a.end_period`
4. 周次区间重叠：`a.start_week <= b.end_week AND b.start_week <= a.end_week`
5. 单双周相容：任一为 `ALL`，或两者 `week_type` 相同

需检测三类冲突：**教室**冲突、**教师**冲突、**学生**冲突（选课时校验）。

> 这个判定无法用唯一约束表达，必须在 Service 层实现。排课与选课都要调用同一套判定逻辑，避免两处规则不一致。

---

# 8. 选课

## 8.1 course_selections

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| student_id | BIGINT UNSIGNED | NOT NULL, FK → students(id) CASCADE | |
| teaching_class_id | BIGINT UNSIGNED | NOT NULL, FK → teaching_classes(id) CASCADE | |
| course_id | BIGINT UNSIGNED | NOT NULL, FK → courses(id) RESTRICT | 冗余 |
| semester | VARCHAR(16) | NOT NULL | 冗余 |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'SELECTED' | SELECTED / DROPPED |
| selected_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |
| dropped_at | DATETIME | NULL | |

```sql
UNIQUE KEY uk_selection (student_id, teaching_class_id)
CONSTRAINT ck_selection_status CHECK (status IN ('SELECTED','DROPPED'))
KEY idx_selection_student_sem (student_id, semester)
KEY idx_selection_tc (teaching_class_id, status)
```

> `uk_selection` 是防重复选课的**最后一道防线**（PRD §15）。并发下应用层判断可能失效，唯一约束由数据库保证。退课用 `status='DROPPED'` 软删除而非物理删除，保留操作痕迹；重选同一教学班时复用该行。

## 8.2 选课事务

```
BEGIN;
  SELECT ... FROM teaching_classes WHERE id = ? FOR UPDATE;   -- 行锁
  -- 校验：选课开放 / 容量未满 / 未重复 / 无时间冲突 / 先修满足 / 资格符合
  INSERT INTO course_selections ...;
  UPDATE teaching_classes SET selected_count = selected_count + 1 WHERE id = ?;
COMMIT;
```

必须保证原子性，避免「人数更新成功但选课记录未创建」（CLAUDE.md §19）。

## 8.3 selection_periods

选课时间窗口。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| semester | VARCHAR(16) | NOT NULL | |
| name | VARCHAR(50) | NOT NULL | 如「2026-2027-1 正选」 |
| start_time | DATETIME | NOT NULL | |
| end_time | DATETIME | NOT NULL | |
| target_grade_year | SMALLINT UNSIGNED | NULL | 限定年级，NULL 为全部 |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'PENDING' | PENDING / ACTIVE / CLOSED |

```sql
CONSTRAINT ck_selection_period_time CHECK (end_time > start_time)
KEY idx_selection_period (semester, status)
```

---

# 9. 成绩

## 9.1 grades

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| student_id | BIGINT UNSIGNED | NOT NULL, FK → students(id) CASCADE | |
| teaching_class_id | BIGINT UNSIGNED | NOT NULL, FK → teaching_classes(id) CASCADE | |
| course_id | BIGINT UNSIGNED | NOT NULL, FK → courses(id) RESTRICT | 冗余 |
| semester | VARCHAR(16) | NOT NULL | 冗余 |
| regular_score | DECIMAL(5,2) | NULL | 平时成绩 |
| final_score | DECIMAL(5,2) | NULL | 期末成绩 |
| total_score | DECIMAL(5,2) | NULL | 总评，后端按课程权重计算 |
| grade_point | DECIMAL(3,2) | NULL | 绩点 |
| credits | DECIMAL(4,1) | NOT NULL | 学分快照 |
| is_passed | TINYINT(1) | NULL | 是否及格 |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'DRAFT' | 见下 |
| submitted_by | BIGINT UNSIGNED | NULL, FK → teachers(id) SET NULL | |
| submitted_at | DATETIME | NULL | |
| approved_by | BIGINT UNSIGNED | NULL, FK → users(id) SET NULL | |
| approved_at | DATETIME | NULL | |
| reject_reason | VARCHAR(500) | NULL | 驳回原因 |

```sql
UNIQUE KEY uk_grades (student_id, teaching_class_id)
CONSTRAINT ck_grades_status CHECK (status IN
  ('DRAFT','SUBMITTED','APPROVED','REJECTED'))
CONSTRAINT ck_grades_regular CHECK (regular_score IS NULL OR regular_score BETWEEN 0 AND 100)
CONSTRAINT ck_grades_final   CHECK (final_score   IS NULL OR final_score   BETWEEN 0 AND 100)
CONSTRAINT ck_grades_total   CHECK (total_score   IS NULL OR total_score   BETWEEN 0 AND 100)
KEY idx_grades_student_sem (student_id, semester)
KEY idx_grades_tc_status (teaching_class_id, status)
```

> `credits` 存快照而非每次 JOIN 取当前值。课程学分调整后，历史成绩仍应反映修读当时的学分，否则学分统计会随课程改动而漂移。

## 9.2 状态流转

```
DRAFT ──提交──> SUBMITTED ──通过──> APPROVED（对学生可见）
                    │
                    └──驳回──> REJECTED ──教师修改──> SUBMITTED
```

规则（CLAUDE.md §18、PRD §15）：

- `APPROVED` 后普通教师不可直接修改
- 学生只能查询 `APPROVED` 的成绩
- 每次状态变更写入 `operation_logs`

## 9.3 总评与绩点

总评由后端按课程权重计算：

```
total_score = regular_score × courses.regular_weight
            + final_score   × courses.final_weight
```

绩点换算（4.0 制，可配置）：

| 百分制 | 绩点 |
|---|---|
| 90–100 | 4.0 |
| 85–89 | 3.7 |
| 80–84 | 3.3 |
| 75–79 | 3.0 |
| 70–74 | 2.7 |
| 65–69 | 2.3 |
| 60–64 | 1.0 |
| < 60 | 0.0 |

---

# 10. 考试

## 10.1 exams

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| teaching_class_id | BIGINT UNSIGNED | NOT NULL, FK → teaching_classes(id) CASCADE | |
| course_id | BIGINT UNSIGNED | NOT NULL, FK → courses(id) RESTRICT | 冗余 |
| semester | VARCHAR(16) | NOT NULL | 冗余 |
| exam_type | VARCHAR(20) | NOT NULL, DEFAULT 'FINAL' | FINAL / MAKEUP / RETAKE |
| exam_date | DATE | NOT NULL | |
| start_time | TIME | NOT NULL | |
| end_time | TIME | NOT NULL | |
| duration_minutes | SMALLINT UNSIGNED | NOT NULL | |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'DRAFT' | DRAFT / PUBLISHED / FINISHED |

```sql
CONSTRAINT ck_exams_type CHECK (exam_type IN ('FINAL','MAKEUP','RETAKE'))
CONSTRAINT ck_exams_time CHECK (end_time > start_time)
KEY idx_exams_date (exam_date, start_time)
KEY idx_exams_tc (teaching_class_id)
```

## 10.2 exam_rooms

考场安排。一场考试可分多个考场。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| exam_id | BIGINT UNSIGNED | NOT NULL, FK → exams(id) CASCADE | |
| classroom_id | BIGINT UNSIGNED | NOT NULL, FK → classrooms(id) RESTRICT | |
| capacity | SMALLINT UNSIGNED | NOT NULL | 本考场容量 |
| assigned_count | SMALLINT UNSIGNED | NOT NULL, DEFAULT 0 | 已安排人数 |
| invigilator_id | BIGINT UNSIGNED | NULL, FK → teachers(id) SET NULL | 监考教师 |

```sql
UNIQUE KEY uk_exam_rooms (exam_id, classroom_id)
```

## 10.3 exam_students

学生—考场分配。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| exam_room_id | BIGINT UNSIGNED | NOT NULL, FK → exam_rooms(id) CASCADE | |
| student_id | BIGINT UNSIGNED | NOT NULL, FK → students(id) CASCADE | |
| seat_no | SMALLINT UNSIGNED | NULL | 座位号 |

```sql
UNIQUE KEY uk_exam_students (exam_room_id, student_id)
KEY idx_exam_students_student (student_id)
```

---

# 11. 评价与公告

## 11.1 evaluation_tasks

评价任务。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| name | VARCHAR(100) | NOT NULL | |
| semester | VARCHAR(16) | NOT NULL | |
| start_time | DATETIME | NOT NULL | |
| end_time | DATETIME | NOT NULL | |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'PENDING' | PENDING / ACTIVE / CLOSED |

## 11.2 evaluations

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| task_id | BIGINT UNSIGNED | NOT NULL, FK → evaluation_tasks(id) CASCADE | |
| student_id | BIGINT UNSIGNED | NOT NULL, FK → students(id) CASCADE | |
| teaching_class_id | BIGINT UNSIGNED | NOT NULL, FK → teaching_classes(id) CASCADE | |
| teacher_id | BIGINT UNSIGNED | NOT NULL, FK → teachers(id) RESTRICT | |
| score | DECIMAL(5,2) | NOT NULL | 评分 |
| comment | TEXT | NULL | 文字评价 |
| submitted_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

```sql
UNIQUE KEY uk_evaluations (task_id, student_id, teaching_class_id)
KEY idx_evaluations_teacher (teacher_id)
```

> 教师端与统计只能看到**聚合结果**，不能反查具体学生（PRD §8.8）。该隔离由 API 层保证——表中保留 `student_id` 是为了防重复提交，查询时不得下发。

## 11.3 announcements

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| title | VARCHAR(200) | NOT NULL | |
| content | TEXT | NOT NULL | |
| target_type | VARCHAR(20) | NOT NULL, DEFAULT 'ALL' | ALL / STUDENT / TEACHER |
| publisher_id | BIGINT UNSIGNED | NOT NULL, FK → users(id) RESTRICT | |
| is_top | TINYINT(1) | NOT NULL, DEFAULT 0 | 是否置顶 |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'DRAFT' | DRAFT / PUBLISHED / WITHDRAWN |
| published_at | DATETIME | NULL | |

```sql
KEY idx_announcements_pub (status, target_type, published_at)
```

---

# 12. 审计

## 12.1 operation_logs

CLAUDE.md §24 要求记录：用户、时间、IP、操作类型、目标资源、结果。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK | |
| user_id | BIGINT UNSIGNED | NULL, FK → users(id) SET NULL | 登录失败时可能为空 |
| username | VARCHAR(50) | NULL | 冗余快照，用户删除后仍可追溯 |
| action | VARCHAR(50) | NOT NULL | 如 `GRADE_APPROVE` |
| module | VARCHAR(40) | NOT NULL | |
| resource_type | VARCHAR(40) | NULL | 目标资源类型 |
| resource_id | BIGINT UNSIGNED | NULL | 目标资源 ID |
| detail | VARCHAR(500) | NULL | 如「审核学生张三成绩」 |
| ip_address | VARCHAR(45) | NULL | 兼容 IPv6 |
| user_agent | VARCHAR(300) | NULL | |
| result | VARCHAR(20) | NOT NULL | SUCCESS / FAILURE |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

```sql
KEY idx_oplogs_user_time (user_id, created_at)
KEY idx_oplogs_action_time (action, created_at)
KEY idx_oplogs_resource (resource_type, resource_id)
```

> **禁止记录密码、令牌等敏感信息**（CLAUDE.md §24）。

---

# 13. 索引与性能

## 13.1 高频查询

| 场景 | 支撑索引 |
|---|---|
| 学生查本学期课表 | `idx_selection_student_sem` → `idx_schedules_tc` |
| 教师查授课班级 | `idx_tc_teacher` |
| 可选课程列表 | `idx_tc_selection` |
| 教师录入成绩名单 | `idx_grades_tc_status` |
| 学生查成绩 | `idx_grades_student_sem` |
| 教室冲突检测 | `idx_schedules_conflict` |
| 待审核成绩 | `idx_grades_tc_status` |

## 13.2 N+1 规避

课表、成绩单、学生名单等一对多查询必须用 `selectinload` / `joinedload` 预加载（PRD §14）。

## 13.3 冗余字段一览

| 表 | 冗余字段 | 理由 | 一致性保证 |
|---|---|---|---|
| students | major_id, college_id | 避免三表 JOIN | Service 层写入时同步 |
| teaching_classes | course_id, semester | 高频过滤 | 创建时从 task 带入 |
| course_selections | course_id, semester | 高频过滤 | 创建时从 teaching_class 带入 |
| grades | course_id, semester, credits | 统计 + 历史快照 | 创建时带入，此后不随课程变动 |
| teaching_classes | selected_count | 避免每次 COUNT | **事务内**与选课记录同步 |
| classes | student_count | 避免每次 COUNT | 学籍变更时同步 |

> 这些是有意识的反范式。CLAUDE.md §5 要求「第三范式为主要参考」「避免明显数据冗余」——此处冗余均有明确性能或业务理由，并在上表登记一致性责任方。不得随意新增未登记的冗余字段。

---

# 14. 迁移策略

- 所有结构变更必须通过 Alembic migration（CLAUDE.md §5、PRD §12.4）
- 禁止手工改库替代迁移
- 禁止删除已提交的历史迁移（CLAUDE.md §27）
- 迁移必须可重复执行（PRD §18.4）

## 14.1 建表顺序

外键依赖决定顺序：

```
1. colleges, classrooms, permissions, roles
2. majors
3. users
4. teachers
5. classes            （依赖 teachers.counselor_id）
6. students
7. user_roles, role_permissions
8. courses
9. course_prerequisites, curriculum_plans
10. curriculum_courses
11. teaching_tasks
12. teaching_classes
13. schedules, selection_periods, evaluation_tasks
14. course_selections, grades, exams
15. exam_rooms, evaluations
16. exam_students
17. announcements, operation_logs
```

> `classes` ⇄ `teachers` 存在循环引用（班级有辅导员，教师属学院）。因 `counselor_id` 可为 NULL，按上述顺序建表即可，无需延迟约束。

---

# 15. 初始化数据

按 CLAUDE.md §30，`scripts/seed.py` 至少生成：

| 实体 | 数量 |
|---|---|
| 学院 | 1 |
| 专业 | 2 |
| 班级 | 2 |
| 教师 | 5 |
| 学生 | 20 |
| 课程 | 10 |
| 教学任务 / 教学班 / 排课 / 选课 / 考试 / 成绩 | 若干 |

另需内置 3 个角色（`STUDENT` / `TEACHER` / `ACADEMIC_ADMIN`）及对应权限。

种子数据必须可重复执行（幂等），不得产生重复记录。
