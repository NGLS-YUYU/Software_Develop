# 测试规范与现状

> 记录当前测试实际情况（TASK-DOC-001，2026-09-17；TASK-011 更新，2026-09-18；TASK-012 更新，2026-09-18；TASK-013 更新，2026-09-18；FIX-008/009/005 更新，2026-09-20；FIX-006 更新，2026-10-08；FIX-007 更新，2026-10-08）。
>
> 新增的真实链路 E2E 脚本（不依赖测试客户端，直连运行中的服务）：
> - `backend/scripts/e2e_fix005_import.py` —— 真实 HTTP + 真实 Excel + 真实 MySQL（28 项断言）
> - `backend/scripts/e2e_fix005_browser.py` —— Chrome + CDP 真实浏览器操作（32 项断言）
> - `backend/scripts/e2e_fix006_api.py` —— 学期管理真实 HTTP + MySQL 逐项回查（40 项断言）
> - `backend/scripts/e2e_fix006_browser.py` —— 学期管理 Chrome 真实浏览器操作（43 项断言）
> - `backend/scripts/e2e_fix007_schedule.py` —— 排课真实 HTTP + MySQL（37 项断言）
> - `backend/scripts/e2e_fix007_lan.py` —— 局域网地址下的 Chrome 真实浏览器 + 网络请求审计（25 项断言）

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
├── test_score_service.py # 统一成绩计算服务（30 个用例）
├── test_score_consistency.py # 成绩权重一致性 + 全库成绩重算核对（14 个用例）
├── test_gpa_ranking.py   # GPA 换算与班级/专业排名（16 个用例）
├── test_teacher_grade.py # 教师成绩录入与状态机（19 个用例）
├── test_grade_review.py  # 教务处成绩审核（18 个用例）
├── test_student_grade.py # 学生成绩查询（20 个用例）
├── test_teaching_class.py # 教学班基础管理 + 开课计划规则（44 个用例）
├── test_selection.py     # 必修课预安排 + 选修课自主选课 + 容量并发（30 个用例）
├── test_teaching_schedule.py # 教学安排与课表管理（42 个用例）
├── test_academic_term.py # 学期管理与教学班学期绑定（45 个用例）
├── test_fix009_assessment.py # 学时守恒 + 考核结构推导 + 教学班继承（10 个用例）
├── test_fix005_import.py # 批量导入闭环 + 成绩模板动态列 + 草稿删除（35 个用例）
└── test_import.py        # 基础数据 Excel 批量导入（43 个用例）
```

**合计 409 个用例，全部通过。**

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
| `test_teaching_class.py` | 教务处创建教学班（课程/教师/教师身份/唯一性校验）、教务/教师/学生数据权限隔离、教学班学生名单（含专业与行政班）、教务处添加/移除学生、同一学生多教学班、不同课程/学期教学班共存、同一学期内编号唯一且跨学期可复用（TASK-011）、TASK-005/006/007 回归（TASK-008）；**TASK-012**：`name` 字段、`teacher_id` 必填、已结束学期增删改拒绝、`term_id`/`course_id` 不可变、换教师（无成绩可换/SUBMITTED/APPROVED 锁定）、容量不得小于已选人数、删除（空班可删/有选课/有成绩拒绝）、教务添加学生容量边界、按 `course_id`/`teacher_id` DB 层过滤 |
| `test_selection.py` | 必修课预排（学院/专业/行政班范围、幂等、选修课不可预排、教师/学生不可预排）、选修课自主选课/退课、必修课不可自主选择/退选、重复/同课程多教学班/越权防护、可选列表只含选修课且排除已选、退选不删成绩、非 ACTIVE 学期不可选课与 ENDED 学期不可退课（TASK-011）、TASK-005/006/007/008 回归（TASK-009）；**TASK-012**：教学班满员选课拒绝（`TEACHING_CLASS_FULL`）、并发选课不超卖（4 线程抢 2 名额，计数一致） |
| `test_teaching_schedule.py` | 教学安排增删改查、参数校验（星期/节次/周次/单双周/教室）、三类冲突（教师/教室/教学班自身，分别 `TEACHING_SCHEDULE_TEACHER_CONFLICT`/`TEACHING_SCHEDULE_CLASSROOM_CONFLICT`/`TEACHING_SCHEDULE_CLASS_CONFLICT`）、学期生命周期（PLANNED/ACTIVE 可操作、ENDED 只读 `TEACHING_SCHEDULE_TERM_ENDED`）、修改排除自身、教室容量校验、教务全量列表与 4 个过滤条件（teaching_class/teacher/weekday/classroom）及排序、角色权限隔离（教师/学生写 403、教务列表/详情仅 ACADEMIC_ADMIN）、教师 `/mine`（含 term 过滤）、学生 `/my`（含 term 过滤、未选课空列表）（TASK-013） |
| `test_fix007` 增量（并入 `test_teaching_schedule.py`） | 教师/学生课表接口新增的可选过滤参数：`semester` 过滤（含跨学期排除）、`week` 过滤（周次区间 + 单双周）、越界周次 422（FIX-007） |
| `test_academic_term.py` | 学期增删改查、状态单向流转 PLANNED→ACTIVE→ENDED、单激活约束、(学年,学期) 唯一、日期校验、删除引用保护、教学班 `term_id` 必填与已结束学期不可开课、按学期过滤、`term:read`/`term:write` 权限隔离（TASK-011） |
| `test_fix006` 增量（并入 `test_academic_term.py`） | 学生写权限矩阵（增/改/删/激活/结束全部 403，只读 200）、教师结束 403、关键词检索（名称/学年）、状态筛选 + 后端分页、编辑载荷不带 `status` 时状态不被重置、一条完整生命周期（列表→新增→激活→幂等激活→结束→重复结束 409→已结束不可激活 409）（FIX-006） |
| `test_import.py` | 学生/课程/成绩 Excel 批量导入、三种模板下载、`.xlsx` 格式校验、字段缺失/编号与登录名重复/学院/专业/行政班层级校验、课程类型/考核方式/学分校验、成绩 0-100 范围与理论/实践成对校验、DRAFT/REJECTED 可覆盖而 SUBMITTED/APPROVED 禁止覆盖、成绩复用 ScoreService 计算（32/48/64 课时与理论+实践）、不写 GPA/排名、教师/学生越权 403、错误行号（TASK-010） |
| `test_fix005_import.py` | 教师批量导入（中文取值翻译/去重/权限）、成绩模板按 AssessmentProfile 动态生成（32/48/64 × 实践/非实践四态）、真实 Excel 往返（下载模板→填写→上传→查库核对总评）、非法成绩/不存在学生/不属于教学班、重复导入覆盖草稿、草稿删除（DRAFT 204；SUBMITTED/APPROVED/REJECTED 409；越权 403）、教师只能导入本人教学班、英文表头兼容（FIX-005） |
| `test_fix009_assessment.py` | 理论+实践=总学时（Schema/Service）、考核结构由总学时推导且忽略存量 assessment_type、教学班继承课程考核结构、已出分课程禁止改学时（FIX-009） |
| `test_score_consistency.py` | 32 学时权重回归（62.20 而非旧口径 68.40）、GPA/排名同源、成绩导入走统一规则、死字段移除、**全库成绩按 WEIGHT_RULES 重算核对**（FIX-008） |

### 2.2 测试不足的部分 ⚠️

**8 个业务模块无任何自动化测试**：

| 模块 | 状态 | 风险 |
|---|---|---|
| organization（学院/专业/班级/教室） | ❌ 无测试 | 引用保护、唯一约束未回归 |
| person（学生/教师） | ❌ 无测试 | 账号联动创建、冗余字段同步未回归 |
| course（课程/先修/培养方案） | ❌ 无测试 | **环路检测**、权重校验未回归 |
| teaching（开课/排课） | ✅ 已测试 | **教学安排冲突检测、单双周相容、学期生命周期**已于 TASK-013 补回归（`test_teaching_schedule.py` 38 用例） |
| selection（选课） | ⚠️ 部分 | 必修课预排/选修课选退课已有测试（TASK-009）；**并发防超卖**已于 TASK-012 补回归测试（4 线程抢 2 名额，断言不超卖且计数一致） |
| grade（成绩） | ⚠️ 部分 | **总评计算已有单测**（TASK-003）；四态状态机、学分汇总仍未回归 |
| exam（考试） | ❌ 无测试 | 自动排座未回归 |
| misc（评价/公告/统计） | ❌ 无测试 | 评价匿名性未回归 |

> 已通过**手工验证**但缺少自动化回归的机制：成绩闭环全流程、排课冲突、先修环路检测、跨角色权限隔离。

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
| ~~P1~~ ✅ | ~~选课并发测试~~ | **已在 TASK-012 完成**：`test_selection.py::test_concurrent_selection_no_oversell` 多线程抢容量，断言不超卖、计数一致 |
| P1 | ~~排课冲突测试~~ | **已在 TASK-013 完成**：`test_teaching_schedule.py` 覆盖教师/教室/教学班自身三类冲突与单双周相容 |
| ~~P1~~ ✅ | ~~成绩状态机测试~~ | **已在 TASK-005 完成**：`test_teacher_grade.py` 覆盖 DRAFT → SUBMITTED → APPROVED/REJECTED 全流转与非法流转 |
| ~~P1~~ ✅ | ~~成绩计算测试~~ | **已在 TASK-003 完成**：`test_score_service.py` 覆盖 32/48/64 课时、理论+实践合并、边界与异常 |
| P1 | 先修课环路测试 | A→B→C→A 被拒绝 |
| ~~P2~~ ✅ | ~~GPA 计算测试~~ | **已在 TASK-004 完成**：`test_gpa_ranking.py` 覆盖换算、加权、排名、异常 |
| ~~P2~~ ✅ | ~~排名测试~~ | **已在 TASK-004 完成**：班级/专业排名实时计算，不落库 |
| ~~P2~~ ✅ | ~~Excel 导入测试~~ | **已在 TASK-010 完成**：`test_import.py` 覆盖学生/课程/成绩导入、模板下载、格式与业务校验、成绩状态限制、ScoreService 复用、不写 GPA/排名 |

> ⚠️ 上述 GPA、排名测试对应的功能**已实现**（TASK-004）。Excel **导入**已于 TASK-010 实现并补测试；Excel **导出**仍未实现，留待后续任务。

---

## 7. 相关文档

- [DEVELOPMENT.md](DEVELOPMENT.md) — 开发规范
- [API.md](API.md) — 接口清单
- [ROADMAP.md](ROADMAP.md) — 版本规划
- [V0.2_AUDIT.md](V0.2_AUDIT.md) — 审计详情
