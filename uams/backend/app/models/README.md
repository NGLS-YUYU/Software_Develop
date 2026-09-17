# app/models —— ORM 模型层

## 作用

定义数据库表结构、字段约束、表间关系。对应 28 张业务表。

## 主要内容

| 文件 | 表 |
|---|---|
| `user.py` | users |
| `role.py` | roles / permissions / user_roles / role_permissions |
| `organization.py` | colleges / majors / classes / classrooms |
| `person.py` | students / teachers |
| `course.py` | courses / course_prerequisites / curriculum_plans / curriculum_courses |
| `teaching.py` | teaching_tasks / teaching_classes / schedules |
| `selection.py` | course_selections / selection_periods |
| `grade.py` | grades（含 `Grade.compute()` 总评与绩点计算） |
| `exam.py` | exams / exam_rooms / exam_students |
| `misc.py` | evaluation_tasks / evaluations / announcements / operation_logs |
| `__init__.py` | **集中导入全部模型** |

## 依赖关系

```
services / repositories  →  models  →  db/base（Base / IdMixin / TimestampMixin）
alembic/env.py           →  models/__init__.py（发现全部表以生成迁移）
```

## 开发注意事项

1. ⚠️ **新增模型必须在本目录 `__init__.py` 中导入登记**，否则 Alembic autogenerate 会静默漏表
2. 主键统一 `BIGINT UNSIGNED AUTO_INCREMENT`（用 `IdMixin`）
3. 时间戳统一 `created_at` / `updated_at`（用 `TimestampMixin`）
4. 状态字段用 `VARCHAR(20)` + `CheckConstraint`，取值用同文件中的常量类
5. 成绩、学分、绩点**必须用 `Numeric`**（DECIMAL），禁止 FLOAT/DOUBLE
6. 表参数统一 `mysql_engine=InnoDB` / `mysql_charset=utf8mb4`
7. 模型本身不写业务逻辑；`Grade.compute()` 属少量领域方法，可接受
8. 修改表结构后必须生成 migration，并同步更新 [docs/DATABASE.md](../../docs/DATABASE.md)

## 当前状态

- **已实现**：28 张表全部定义，与数据库零漂移
- **V0.2 待重新设计**：`grade.py`（实践/理论成绩拆分、GPA 细化、排名）

## 相关文档

- [docs/DATABASE.md](../../docs/DATABASE.md) — 字段级设计
- [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) — 模型模块划分
