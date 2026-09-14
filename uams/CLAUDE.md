# 高校教务教学管理系统

项目名称：高校教务教学管理系统
英文名称：University Academic Affairs & Teaching Management System
项目简称：UAMS

这是一个面向高校教学管理场景的多角色 Web 应用系统。

项目主要用于课程设计、智能软件工程课程项目以及后续个人作品集展示。

---

# 1. 项目目标

系统面向三类核心用户：

1. 学生
2. 教师
3. 教务管理员

系统通过统一认证和 RBAC 权限模型实现不同角色的业务隔离。

核心业务：

* 用户认证
* 用户与角色管理
* 学生管理
* 教师管理
* 学院管理
* 专业管理
* 班级管理
* 课程管理
* 培养方案
* 开课管理
* 排课管理
* 在线选课
* 学生课表
* 考试管理
* 成绩管理
* 教学评价
* 通知公告
* 数据统计

---

# 2. 核心技术栈

## Backend

* Python 3.14.4
* FastAPI
* SQLAlchemy 2.x
* Alembic
* Pydantic v2
* PyMySQL
* Pytest

## Frontend

* Vue 3
* TypeScript
* Vite
* Element Plus
* Pinia
* Vue Router
* Axios

## Database

* MySQL 8.4 LTS
* InnoDB 存储引擎
* 字符集必须使用 utf8mb4

## Development

* Git
* GitHub
* Docker / Docker Compose
* Claude Code

---

# 3. 数据库规则

数据库是本项目最重要的基础设施之一。

必须使用 MySQL 8.4 LTS。

存储引擎必须使用 InnoDB，字符集必须使用 utf8mb4。

数据库连接采用：

SQLAlchemy
→ MySQL dialect
→ PyMySQL
→ MySQL 8.4

示例：

CREATE DATABASE uams
CHARACTER SET utf8mb4
COLLATE utf8mb4_0900_ai_ci;

实际命令必须根据当前 MySQL 版本进行验证。

---

# 4. MySQL 使用原则

优先使用：

* INT
* BIGINT
* VARCHAR
* TEXT
* BOOLEAN（MySQL 中为 TINYINT(1)）
* DATE
* DATETIME
* DECIMAL

谨慎使用：

* JSON 类型
* 生成列（Generated Column）
* 存储过程与触发器
* 事件调度器
* 全文索引
* 不必要的自定义数据库类型

MySQL 使用须知：

* 字符集必须 utf8mb4；旧的 utf8 实为 3 字节，存不下部分汉字和 emoji
* 金额、成绩、绩点必须用 DECIMAL，禁止用 FLOAT / DOUBLE
* VARCHAR 索引长度受限，建索引前确认前缀长度
* DDL 不参与事务回滚，迁移脚本需要考虑这一点
* 表名统一小写，避免跨平台大小写敏感性差异

不要为了炫技增加数据库高级特性。

---

# 5. 数据库设计原则

数据库设计必须满足：

* 第三范式为主要参考
* 避免明显数据冗余
* 核心业务表必须具有明确主键
* 重要业务字段必须有唯一约束
* 外键关系必须明确
* 高频查询字段建立合理索引
* 不允许通过字符串拼接方式构造 SQL
* 所有数据库操作优先使用 SQLAlchemy ORM
* 必须支持数据库迁移
* 数据库结构必须由 Alembic 管理

---

# 6. 推荐核心数据模型

核心实体至少包含：

users
roles
permissions

students
teachers

colleges
majors
classes

courses
course_prerequisites

curriculum_plans
curriculum_courses

teaching_tasks
teaching_classes

classrooms
schedules

course_selections

exams
exam_rooms

grades

evaluations

announcements

operation_logs

---

# 7. 核心业务关系

核心业务数据流：

学院
↓
专业
↓
培养方案
↓
课程
↓
教学任务
↓
教学班
↓
排课
↓
学生选课
↓
学生课表
↓
考试
↓
成绩
↓
学分统计
↓
毕业审核

教师关系：

教师
↓
教学任务
↓
教学班
↓
学生
↓
成绩

---

# 8. 用户权限模型

采用 RBAC。

核心关系：

User
↓
Role
↓
Permission

系统第一阶段角色：

STUDENT
TEACHER
ACADEMIC_ADMIN

未来可以扩展：

SYSTEM_ADMIN
COLLEGE_ADMIN
TEACHING_SECRETARY

但第一阶段不要提前实现所有角色。

---

# 9. 权限隔离原则

学生：

只能访问自己的：

* 个人信息
* 课表
* 选课
* 成绩
* 考试
* 培养方案
* 教学评价

教师：

只能访问：

* 自己授课的课程
* 自己课程对应的学生
* 自己负责的成绩
* 自己的教学资料
* 自己的课表

教务管理员：

可以管理全校教学业务数据。

任何 API 都必须进行后端权限验证。

不能仅依靠前端隐藏菜单实现权限控制。

---

# 10. 后端架构

后端使用 FastAPI。

推荐结构：

backend/
├── app/
│   ├── main.py
│   ├── core/
│   ├── api/
│   ├── models/
│   ├── schemas/
│   ├── services/
│   ├── repositories/
│   ├── crud/
│   ├── db/
│   └── utils/
│
├── tests/
├── alembic/
└── requirements.txt

推荐业务模块：

auth
users
students
teachers
colleges
majors
classes
courses
curriculum
teaching
schedules
selections
exams
grades
evaluations
announcements
statistics
audit

---

# 11. 分层原则

后端采用：

Router
↓
Service
↓
Repository / CRUD
↓
SQLAlchemy
↓
MySQL

Router：

负责 HTTP 请求和响应。

Service：

负责业务逻辑。

Repository：

负责数据库访问。

Model：

负责数据库模型。

Schema：

负责 API 数据验证。

禁止把大量业务逻辑直接写在 Router 中。

---

# 12. API 设计原则

API 使用 REST 风格。

例如：

GET
/api/v1/courses

POST
/api/v1/courses

GET
/api/v1/courses/{id}

PUT
/api/v1/courses/{id}

DELETE
/api/v1/courses/{id}

特殊业务动作可以使用：

POST
/api/v1/course-selections

POST
/api/v1/grades/{id}/submit

POST
/api/v1/grades/{id}/approve

---

# 13. API 版本管理

所有业务 API 使用：

/api/v1/

不要直接使用：

/api/

未来升级到 v2 时保持兼容。

---

# 14. 前端架构

前端使用：

Vue 3
+
TypeScript
+
Vite
+
Element Plus
+
Pinia
+
Vue Router
+
Axios

推荐结构：

frontend/
├── src/
│   ├── api/
│   ├── assets/
│   ├── components/
│   ├── layouts/
│   ├── router/
│   ├── stores/
│   ├── types/
│   ├── utils/
│   ├── views/
│   └── App.vue
│
└── main.ts

---

# 15. 前端角色路由

登录后根据用户角色跳转：

学生：

/student/dashboard

教师：

/teacher/dashboard

教务：

/admin/dashboard

前端菜单必须根据角色动态生成。

但前端权限控制不能代替后端权限控制。

---

# 16. 页面设计原则

界面要求：

* 简洁
* 清晰
* PC 优先
* 高校教务系统风格
* 表格和表单优先
* 不追求复杂动画
* 不追求花哨视觉效果

教务端优先采用：

后台管理系统布局。

学生端优先采用：

信息门户 + 数据卡片 + 业务页面。

教师端优先采用：

教学工作台 + 课程管理页面。

---

# 17. 核心业务流程

## 学生选课

学生登录
↓
查看可选课程
↓
选择课程
↓
后端检查：

* 是否在选课时间
* 是否已有课程
* 是否课程容量已满
* 是否存在时间冲突
* 是否满足先修课程
* 是否满足选课资格

↓
创建选课记录
↓
更新课程容量
↓
生成课表

---

# 18. 成绩业务

教师：

进入课程
↓
查看学生名单
↓
录入成绩
↓
保存草稿
↓
提交成绩

教务：

审核成绩
↓
通过 / 驳回

学生：

查询已发布成绩

已审核成绩不得由普通教师直接修改。

---

# 19. 事务规则

以下业务必须考虑数据库事务：

* 学生选课
* 学生退课
* 成绩提交
* 成绩审核
* 考试安排
* 关键数据批量导入

例如选课：

检查容量
+
创建选课记录
+
更新已选人数

必须保证原子性。

避免出现：

课程人数更新成功，但是选课记录没有创建成功。

---

# 20. 并发控制

选课属于可能出现并发操作的业务。

不能只在前端判断课程剩余人数。

后端必须最终再次验证。

需要根据 MySQL / InnoDB 支持情况设计：

* 行级锁（SELECT ... FOR UPDATE）
* 事务（InnoDB 默认隔离级别为 REPEATABLE READ）
* 唯一约束

具体实现必须经过数据库验证。

---

# 21. 成绩计算

不要把成绩计算规则硬编码到前端。

例如：

# 总评

平时成绩 × 40%
+
期末成绩 × 60%

权重应该属于课程考核规则的一部分。

后端统一计算。

---

# 22. 数据导入导出

教务系统需要支持：

Excel 导入：

* 学生
* 教师
* 课程
* 成绩

Excel 导出：

* 学生名单
* 成绩
* 课程
* 选课结果

Python 可使用：

pandas
openpyxl

---

# 23. 安全规则

必须实现：

* 密码哈希
* JWT 或安全 Session 认证
* RBAC
* API 权限控制
* 参数验证
* SQL 注入防护
* CORS 合理配置
* 登录失败限制
* 操作日志

密码绝对不能明文存储。

.env 中保存：

DATABASE_URL
JWT_SECRET
其他敏感配置

禁止把真实密码提交到 Git。

---

# 24. 日志

系统需要区分：

应用日志
操作日志
错误日志

操作日志记录：

用户
时间
IP
操作类型
目标资源
操作结果

例如：

“教务管理员审核学生张三成绩”。

---

# 25. Git 规范

使用 Git 管理全部源代码。

分支：

main
develop
feature/*

示例：

feature/student-course-selection
feature/teacher-grade-entry
feature/admin-course-management

Commit 使用：

feat:
fix:
refactor:
docs:
test:
chore:

示例：

feat: add student course selection

---

# 26. Claude Code 开发原则

Claude Code 每次开始开发前必须：

1. 阅读 CLAUDE.md
2. 查看当前 Git 状态
3. 阅读相关模块代码
4. 确认当前数据库结构
5. 确认现有 API
6. 不随意重构无关模块

修改代码前必须理解已有结构。

---

# 27. 禁止事项

Claude Code 禁止：

* 删除已有业务代码后重新实现
* 未经说明大规模重构
* 随意更换技术栈
* 随意更换数据库
* 使用 SQLite 替代 MySQL
* 使用 PostgreSQL 替代 MySQL
* 使用 MariaDB 替代 MySQL
* 创建不必要的数据库扩展
* 将数据库密码提交到 Git
* 删除 Alembic 历史迁移
* 修改 API 返回格式而不说明
* 破坏已有功能
* 为了通过测试直接修改测试结果

---

# 28. 数据库规则

数据库必须保持：

MySQL 8.4 LTS

绝对禁止为了“开发方便”切换：

SQLite
PostgreSQL
MariaDB

本地开发环境也应尽量使用与正式环境一致的 MySQL。

---

# 29. 测试要求

每个核心模块都需要测试。

至少测试：

认证
权限
学生
教师
课程
选课
成绩
考试

核心业务必须测试：

正常场景
异常场景
权限场景
边界场景

例如选课：

正常选课
重复选课
课程已满
时间冲突
未开放选课
无权限选课

---

# 30. 数据初始化

项目需要提供开发测试数据。

至少创建：

1 个学院
2 个专业
2 个班级
5 个教师
20 个学生
10 门课程
若干教学任务
若干排课
若干选课记录
若干考试
若干成绩

并提供：

scripts/seed.py

用于初始化演示数据。

---

# 31. 开发顺序

严格遵循：

基础设施
↓
数据库
↓
认证
↓
RBAC
↓
基础数据
↓
课程
↓
教学任务
↓
排课
↓
学生选课
↓
课表
↓
成绩
↓
考试
↓
评价
↓
统计
↓
优化

不要跳过数据库和权限直接开发大量前端页面。

---

# 32. 开发方法

采用“小步迭代”。

每次只完成一个明确任务。

流程：

读取现有代码
↓
分析
↓
设计
↓
实现
↓
运行测试
↓
修复问题
↓
更新文档
↓
Git commit

---

# 33. 完成任务的标准

一个任务只有同时满足：

代码完成
+
数据库迁移完成
+
API完成
+
权限完成
+
测试完成
+
前端页面完成
+
基本手工验证完成

才认为真正完成。

---

# 34. 文档要求

以下文档必须维护：

docs/
├── PRD.md
├── ARCHITECTURE.md
├── DATABASE.md
├── API.md
├── DEVELOPMENT.md
├── ROADMAP.md
└── TESTING.md

重要架构变化必须同步更新文档。

---

# 35. 当前项目开发目标

第一阶段目标：

完成一个真正可以演示的高校核心教务系统。

必须形成完整业务闭环：

教务创建课程
↓
教务创建教学任务
↓
安排教师
↓
安排时间和教室
↓
开放选课
↓
学生选课
↓
生成课表
↓
教师查看学生
↓
教师录入成绩
↓
教务审核
↓
学生查询成绩
↓
教务安排考试
↓
学生查询考试

---

# 36. AI 开发原则

Claude Code 的职责不是盲目生成代码。

每次开发优先保证：

正确性

>

数据完整性

>

业务逻辑

>

安全性

>

可维护性

>

性能

>

视觉效果

不要为了“看起来高级”牺牲稳定性。

---

# 37. 当需求不明确时

优先：

1. 查看 PRD
2. 查看架构文档
3. 查看数据库设计
4. 查看当前实现
5. 根据现有项目约定做最小改动

不要自行创造新的业务规则。

---

# 38. 项目最终原则

这是一个真实业务逻辑驱动的高校教务系统。

不是简单 CRUD Demo。

所有核心功能都必须围绕：

学生
教师
课程
教学任务
选课
课表
考试
成绩

建立数据关系。

优先保证业务闭环完整。

EOF

