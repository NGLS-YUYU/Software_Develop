# 测试规范与现状

> 记录当前测试实际情况（TASK-DOC-001，2026-09-17）。

---

## 1. 测试工具

| 项 | 说明 |
|---|---|
| 框架 | pytest 9.1.1 |
| HTTP 客户端 | `fastapi.testclient.TestClient`（基于 httpx） |
| 扩展 | pytest-asyncio 1.4.0（已安装，当前测试未使用异步用例） |
| 前端检查 | `vue-tsc --noEmit`（类型）+ `vite build`（构建） |

---

## 2. 当前测试现状

### 2.1 已有测试

```
backend/tests/
├── __init__.py
├── test_auth.py          # 认证与权限（17 个用例）
├── test_smoke.py         # 基础设施冒烟（4 个用例）
├── test_rbac.py          # 三类角色权限隔离（9 个用例）
├── test_models.py        # 模型字段完整性与约束（13 个用例）
├── test_score_service.py # 统一成绩计算服务（15 个用例）
├── test_gpa_ranking.py   # GPA 换算与班级/专业排名（16 个用例）
├── test_teacher_grade.py # 教师成绩录入与状态机（15 个用例）
├── test_grade_review.py  # 教务处成绩审核（18 个用例）
├── test_student_grade.py # 学生成绩查询（18 个用例）
└── test_teaching_class.py # 教学班基础管理（23 个用例）
```

**合计 148 个用例，全部通过。**

| 文件 | 覆盖内容 |
|---|---|
| `test_auth.py` | 密码哈希与校验、登录成功/失败、用户名枚举防护、登录失败锁定、账号停用、token 校验（缺失/伪造/有效）、`/me`、**角色权限隔离断言**、改密流程 |
| `test_smoke.py` | `/health` 连通性、五张 RBAC 表存在、表引擎与字符集合规、`CHECK` 约束实际生效 |
| `test_rbac.py` | admin/teacher/student 三类登录与首页路由、权限包含/排除断言、用户管理接口越权拒绝（TASK-001） |
| `test_models.py` | 五模型需求字段完整性、TASK-002 新增列/CHECK 约束落库、非法值被拒、理论/实践字段可空（TASK-002） |
| `test_score_service.py` | 32/48/64 课时总评、理论+实践合并、100/0 分边界、缺失/非法考核方式/越界异常、草稿容错（TASK-003） |
| `test_gpa_ranking.py` | 百分制→绩点、单课程贡献、学分加权 GPA、班级/专业排名、无成绩/无学分/零学分/空成绩异常、Grade 表未新增 GPA 字段（TASK-004） |
| `test_teacher_grade.py` | 教师我的课程、跨教师/跨学生越权防护、学生名单（含成绩状态）、草稿保存、非法成绩拒绝、32/48 课时与理论+实践录入、完整/不完整提交、SUBMITTED/APPROVED/REJECTED 状态流转（TASK-005） |
| `test_grade_review.py` | 待审核列表权限、审核通过/驳回、非法状态流转（APPROVED/DRAFT/REJECTED/NOT_ENTERED 禁止审核）、审核后教师联动、教师/学生越权防护、审核权限隔离（TASK-006） |
| `test_student_grade.py` | 学生查看本人 APPROVED 成绩、DRAFT/SUBMITTED/REJECTED/NOT_ENTERED 不可见、grade_id/student_id 越权防护、GPA 正确/加权/不及格计入/两位小数/不落库、班级/专业排名且与 RankingService 一致、教师/学生反向越权（TASK-007） |
| `test_teaching_class.py` | 教务处创建教学班（课程/教师/教师身份/唯一性校验）、教务/教师/学生数据权限隔离、教学班学生名单（含专业与行政班）、教务处添加/移除学生、同一学生多教学班、不同课程/学期教学班共存、TASK-005/006/007 回归（TASK-008） |

### 2.2 测试不足的部分 ⚠️

**8 个业务模块无任何自动化测试**：

| 模块 | 状态 | 风险 |
|---|---|---|
| organization（学院/专业/班级/教室） | ❌ 无测试 | 引用保护、唯一约束未回归 |
| person（学生/教师） | ❌ 无测试 | 账号联动创建、冗余字段同步未回归 |
| course（课程/先修/培养方案） | ❌ 无测试 | **环路检测**、权重校验未回归 |
| teaching（开课/排课） | ❌ 无测试 | **冲突检测**、单双周相容未回归 |
| selection（选课） | ❌ 无测试 | **并发防超卖**仅有手工压测，无回归测试 |
| grade（成绩） | ⚠️ 部分 | **总评计算已有单测**（TASK-003）；四态状态机、学分汇总仍未回归 |
| exam（考试） | ❌ 无测试 | 自动排座未回归 |
| misc（评价/公告/统计） | ❌ 无测试 | 评价匿名性未回归 |

> 已通过**手工验证**但缺少自动化回归的机制：选课并发压测（20 线程抢 3 名额）、成绩闭环全流程、排课冲突、先修环路检测、跨角色权限隔离。

---

## 3. 运行测试

```bash
# 后端：全部测试
cd uams/backend && .venv/bin/python -m pytest tests/ -q

# 后端：单个文件 / 单个用例
.venv/bin/python -m pytest tests/test_auth.py -q
.venv/bin/python -m pytest tests/test_auth.py::test_login_success -v

# 后端：显示通过详情
.venv/bin/python -m pytest tests/ -v

# 前端：类型检查（注意用本地 vue-tsc，不要用 npx）
cd uams/frontend && node_modules/.bin/vue-tsc --noEmit

# 前端：生产构建（含类型检查）
npm run build
```

**测试前提**：MySQL 服务运行中，且数据库已完成迁移（`alembic upgrade head`）。`test_auth.py::test_admin_has_approve_permission` 依赖 `seed_rbac` 已执行。

---

## 4. 测试数据管理

`test_auth.py` 使用 **fixture 自建自清** 模式：

```python
@pytest.fixture
def student_user():
    # 先清理同名残留 -> 建用户 -> 授角色 -> yield id -> 测试后清理
```

避免污染开发数据。其余模块测试（V0.2 新增）建议沿用该模式。

---

## 5. 测试编写规范

### 5.1 覆盖维度（CLAUDE.md §29）

核心业务必须覆盖四类场景：

1. **正常场景** —— 业务流程走通
2. **异常场景** —— 非法输入、冲突、资源不存在
3. **权限场景** —— 越权访问被拒绝
4. **边界场景** —— 容量临界、时间边界、状态边界

### 5.2 示例：选课测试应覆盖

```
正常选课
重复选课          → 409
课程已满          → 409
时间冲突          → 409
先修课不满足      → 409
未开放选课        → 409
不在选课时间窗口  → 409
无权限（教师调用）→ 403
并发选课不超卖    → 实际记录数 ≤ 容量
```

### 5.3 断言原则

- **不得为了让测试通过而修改测试结果**（CLAUDE.md §27）
- 权限测试必须显式断言「不应拥有的权限」，而非只断言「拥有的权限」
- 数据库约束测试应实际尝试写入非法数据，确认被拒绝

---

## 6. V0.2 待补充测试

| 优先级 | 测试项 | 说明 |
|---|---|---|
| P1 | 选课并发测试 | 多线程抢容量，断言不超卖、计数一致 |
| P1 | 排课冲突测试 | 教室冲突、教师冲突、单双周相容 |
| ~~P1~~ ✅ | ~~成绩状态机测试~~ | **已在 TASK-005 完成**：`test_teacher_grade.py` 覆盖 DRAFT → SUBMITTED → APPROVED/REJECTED 全流转与非法流转 |
| ~~P1~~ ✅ | ~~成绩计算测试~~ | **已在 TASK-003 完成**：`test_score_service.py` 覆盖 32/48/64 课时、理论+实践合并、边界与异常 |
| P1 | 先修课环路测试 | A→B→C→A 被拒绝 |
| ~~P2~~ ✅ | ~~GPA 计算测试~~ | **已在 TASK-004 完成**：`test_gpa_ranking.py` 覆盖换算、加权、排名、异常 |
| ~~P2~~ ✅ | ~~排名测试~~ | **已在 TASK-004 完成**：班级/专业排名实时计算，不落库 |
| P2 | Excel 导入测试 | **属于 V0.2 业务开发阶段**（功能未实现） |

> ⚠️ 上述 GPA、排名、Excel 相关测试对应的功能**尚未实现**，需先完成 V0.2 业务开发，再补测试。本任务（TASK-DOC-001）只记录，不实现。

---

## 7. 相关文档

- [DEVELOPMENT.md](DEVELOPMENT.md) — 开发规范
- [API.md](API.md) — 接口清单
- [ROADMAP.md](ROADMAP.md) — 版本规划
- [V0.2_AUDIT.md](V0.2_AUDIT.md) — 审计详情
