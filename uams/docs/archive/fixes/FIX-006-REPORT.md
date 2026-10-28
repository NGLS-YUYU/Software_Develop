# FIX-006 实施报告：学期管理前端完整闭环

> 本文是**实施报告**；`FIX-006.md` 是原始工单，保持原样未改动。本次工单与该工单范围一致（学期管理前端闭环），无范围冲突。

状态：**COMPLETE**

---

## 1. 现状审计（§三，只读，改动前）

### 后端已有能力（全部复用，未改一行）

| 项 | 实际情况 |
|---|---|
| Model | `AcademicTerm`（表 `academic_terms`）：`id / name / academic_year(String 9) / semester(SmallInteger 1\|2) / start_date / end_date / status / created_at / updated_at` |
| 状态枚举 | `TermStatus.PLANNED / ACTIVE / ENDED`，**单向** `PLANNED → ACTIVE → ENDED` |
| CRUD | `GET /terms`（分页 + `academic_year` + `status` + `keyword`）、`GET /terms/{id}`、`POST /terms`、`PUT /terms/{id}`、`DELETE /terms/{id}` |
| activate | `POST /terms/{id}/activate` ✔ |
| end | `POST /terms/{id}/end` ✔ |
| **update** | **存在** → `PUT /terms/{id}`，故 **EDIT 为真实支持**，不是 `BACKEND_NOT_SUPPORTED` |
| 当前激活学期 | 没有 `is_current` 列、也没有 `/terms/current`；**就是 `status='ACTIVE'` 的那一行** |
| 单激活约束 | 有：`_ensure_single_active()`（激活、以及直接创建 ACTIVE 学期时校验），**不会自动降级**其它 ACTIVE 学期 |
| 日期校验 | 三层都有：Schema `check_dates`、Service `_check_dates`、DB `ck_terms_dates (end_date > start_date)` |
| 唯一约束 | `uk_terms_year_sem (academic_year, semester)` |
| 删除保护 | 该学期下有教学班 → 409 |
| 权限 | `term:read`（三角色都有）/ `term:write`（仅 ACADEMIC_ADMIN） |
| 测试 | `tests/test_academic_term.py` 已有 39 例 |

### 前端原缺失

| 项 | 情况 |
|---|---|
| `termApi` | **不存在**（`src/api/index.ts` 无任何 terms 调用） |
| `Term` 类型 | **不存在**（`src/types/index.ts` 只有其它实体的 `semester: string`） |
| 页面 / 路由 / 菜单 | **全无**（无 `/admin/terms`，教务端菜单无「学期管理」） |
| 残留学期逻辑 | `src/composables/useSemester.ts`：`currentSemester()` 按**系统时钟**推断 `"YYYY-YYYY-N"` 字符串，`semesterOptions()` 生成下拉项 |

### 关键发现：两套「学期」表示并存（§十五 报告项，不在本 FIX 范围）

- `academic_terms`：`(academic_year, semester 序号)` + `id`，有状态机；
- 教学班/选课/课表/成绩用的是**字符串** `semester`（如 `"2026-2027-1"`，`TeachingClass.semester`），教学班同时另有 `term_id` 外键；
- 前端 7 个页面（学生/教师首页、学生课表与成绩、教师我的课程、教务选课管理、成绩审核）通过 `useSemester()` **按系统时钟推断**当前学期，与数据库里的 `ACTIVE` 学期无关联。

→ 已按要求**未顺手重构**，列入 §12 后续待处理问题。

---

## 2. 本次修改

| 文件 | 内容 |
|---|---|
| `src/types/index.ts` | 新增 `Term` / `TermStatusValue`（字段与 `TermOut` 一一对应） |
| `src/api/index.ts` | 新增 `termApi`：`list / get / create / update / remove / activate / end` |
| `src/views/admin/Terms.vue` | **新增**学期管理页（列表 + 筛选 + 分页 + 新增/编辑弹窗 + 激活/结束/删除） |
| `src/router/index.ts` | 新增路由 `/admin/terms`（`meta.title = 学期管理`，随父路由 `roles: ['ADMIN']` 生效，菜单自动生成） |
| `tests/test_academic_term.py` | **补齐 6 例** FIX-006 用例（见 §9） |
| `scripts/e2e_fix006_api.py` | **新增**真实 HTTP + MySQL 验收脚本（40 项断言） |
| `scripts/e2e_fix006_browser.py` | **新增** Chrome 真实浏览器验收脚本（43 项断言） |
| `docs/API.md` §6.1、`docs/TESTING.md` | 补前端入口说明、测试计数与覆盖说明 |

**后端未做任何修改**（`app/models/term.py`、`app/services/term.py`、`app/api/v1/terms.py` 零改动）——既有实现完整且已通过验收。

---

## 3. 学期列表（§六/§七）

- 真实 API：`GET /api/v1/terms`（分页 + `keyword` + `status` + `academic_year`）。
- 页面列：学期名称 / 学年 / 学期（第一|第二学期）/ 开始日期 / 结束日期 / 教学班数 / 状态 / 操作。
- 筛选与分页**全部走后端**：关键词（名称与学年）、状态下拉（未开始/进行中/已结束）、`el-pagination` 直接绑定后端 `total`。前端**没有**拉全量再本地切片的假分页。
- 顶部显示「当前激活学期：X」——取自同一次 `GET /terms` 中 `status === 'ACTIVE'` 的行，**不做任何本地推断**。

## 4. 新增学期（§八）

弹窗表单字段与后端 `TermCreate` 一致：`name / academic_year / semester / start_date / end_date`（`status` 不由表单提交，新建一律 PLANNED）。

前端基础校验：必填、结束日期必须晚于开始日期；后端 `TermCreate.check_dates` + `Service._check_dates` + DB CHECK 仍是最终裁判。

真实结果（HTTP E2E）：`POST /terms` → **201**，`MySQL` 新增 `id=6165`，`status=PLANNED`，起止日期落库正确；重复 `(academic_year, semester)` → **409**；结束日期早于开始日期 → **422**。

## 5. 激活学期（§十/§十一）

- 按钮仅在 `status === 'PLANNED'` 时出现；点击 → `ElMessageBox` 二次确认（文案含学期名称）→ `POST /terms/{id}/activate` → 重新拉取列表。
- 前端不维护「当前学期」：激活后页面顶部提示与行内状态都来自服务端返回。
- 真实结果：单激活约束下激活 → 后端 **409**「已存在进行中的学期，不能同时激活多个学期」，页面显示该提示且 MySQL 状态**未变**；把演示学期临时降级后再激活 → **200 ACTIVE**，MySQL 同步，刷新页面显示「进行中」。

## 6. 结束学期（§十二）

- 按钮仅在 `status === 'ACTIVE'` 时出现；二次确认后 `POST /terms/{id}/end` → 刷新。
- 真实结果：**200 ENDED**，MySQL 同步，刷新后显示「已结束」；再次结束 → **409**「只有进行中的学期才能结束」；已结束学期不可再激活 → **409**「已结束的学期不能激活」。

## 7. 权限（§十七）

| 角色 | 前端路由 `/admin/terms` | 菜单 | 读接口 | 写接口（增/改/删/激活/结束） |
|---|---|---|---|---|
| ACADEMIC_ADMIN | 可进入 | 显示「学期管理」 | 200 | 正常 |
| TEACHER | **跳转 `/403`** | 不显示 | 200（`term:read`，既有设计） | **403** |
| STUDENT | **跳转 `/403`** | 不显示 | 200（`term:read`，既有设计） | **403** |
| 未登录 | — | — | **401** | 401 |

> 说明：`GET /terms` 对教师/学生开放是**后端既有且已测试的设计**（学生课表、成绩需要学期信息）。本 FIX 只做前端路由/菜单拦截，并验证写接口 403 —— 未修改该设计。

## 8. MySQL 实测（§十八）

| Case | 操作 | MySQL 结果 |
|---|---|---|
| 1 读取 | 列表 | 读到 `2026-2027学年第一学期`，`status=ACTIVE`，与库一致 |
| 2 新增 | `POST /terms` | 新行 `2999-3000 / 第1学期 / PLANNED`，起止日期正确 |
| 3 激活 | `POST activate` | `status: PLANNED → ACTIVE`；同时校验单激活规则 |
| 4 结束 | `POST end` | `status: ACTIVE → ENDED` |
| 5 非法 | 重复结束 / 已结束激活 / 重复学年学期 / 非法日期 | 409 / 409 / 409 / 422，**库中状态均未变** |
| 清理 | `DELETE` | 204，E2E 学期行已删除；演示学期已还原为 `ACTIVE` |

验收后数据库回到与开始前**完全一致**的状态（`academic_terms` 仅 1 行，`ACTIVE`）。

## 9. 自动化测试（§二十）

| 项 | 结果 |
|---|---|
| `pytest` 全量 | **405 passed**（原 399 + 新增 6） |
| `test_academic_term.py` | **45 passed**（原 39 + 6） |
| `vue-tsc --noEmit` | **0 错误** |
| `npm run build` | **0 错误** |

**新增 6 例（补齐，未删除/未放宽任何旧断言）**：

1. `test_student_cannot_write_terms` — 学生写权限矩阵（增/改/删/激活/结束全 403，只读 200）
2. `test_teacher_cannot_end_term` — 教师结束 403（补齐教师侧矩阵）
3. `test_list_keyword_search` — 关键词命中 `name` 与 `academic_year`，未命中返回空
4. `test_list_status_filter_with_pagination` — 状态筛选 + 后端分页（`total_pages`、跨页并集）
5. `test_update_payload_without_status_keeps_status` — 前端编辑载荷不带 `status` 时状态不被重置
6. `test_full_term_lifecycle_via_frontend_endpoints` — 页面真实调用序列：列表→新增→激活→幂等激活→结束→重复结束 409→已结束不可激活 409

## 10. 真实浏览器（§二十/§二十三）

`scripts/e2e_fix006_browser.py`（Chrome + CDP，真实点击/真实弹窗/真实刷新）：**43/43 通过**。

覆盖：管理员表单登录 → 菜单出现「学期管理」→ 列表读到真实学期（状态「进行中」）→ 关键词筛选（无匹配→空状态、清空→恢复，均由后端过滤）→ 新增弹窗填表（含日期）→ 列表出现且 MySQL 有行 → **刷新页面仍在** → 单激活约束下激活被拒且提示明确 → 降级演示学期后激活成功（MySQL ACTIVE、刷新显示「进行中」、顶部「当前激活学期」同步）→ 结束成功（MySQL ENDED、刷新显示「已结束」、**按钮消失**）→ 重复结束/已结束激活后端 409 → 教师/学生访问被挡到 `/403` 且菜单不显示、写接口 403 → 删除 E2E 学期并确认清理。

---

## 11. 四层证据区分（§二十二）

| 层级 | 结论 |
|---|---|
| 【代码存在】 | `Term` 类型、`termApi`、`Terms.vue`、路由与菜单、2 个 E2E 脚本 |
| 【自动化测试通过】 | 后端 405 passed（含 6 例新增）；`vue-tsc` 0 错误；`build` 0 错误 |
| 【真实 HTTP/API 验证通过】 | `e2e_fix006_api.py` **40/40**：真实 HTTP 打到运行中的服务，每步回查 MySQL |
| 【真实浏览器操作通过】 | `e2e_fix006_browser.py` **43/43**：Chrome 真实点击、二次确认、关键词筛选、刷新后状态正确 |

---

## 12. BLOCKED

**NONE。**

## 13. 已知问题（只记录，不扩展到其他 FIX）

1. **「当前学期」存在两套表示**：`academic_terms`（实体 + 状态机）与各业务表上的 `semester` 字符串；前端 7 个页面用 `useSemester()` **按系统时钟**推断学期，与数据库中的 `ACTIVE` 学期无关联（例如 10 月推断 `2026-2027-1`，恰与演示数据一致，但二者并无联动）。属 §十五 明确要求「只记录、不顺手重构」的后续待处理问题。
2. **`activate` 对已 ACTIVE 学期是幂等的（200）**：后端不报错，「已激活不再显示激活按钮」由前端按状态处理（本页已如此实现）。这是既有后端行为，未修改。
3. **E2E 脚本的 CDP 客户端在 `e2e_fix005_browser.py` 与 `e2e_fix006_browser.py` 中各有一份**（约 110 行重复）。为遵守本次工单「不顺手重构其他模块」，未抽公共模块，也未改动 FIX-005 脚本。建议后续单独做一次测试工具去重。
4. **E2E 测试装置需要临时降级演示学期**：因「全系统最多一个 ACTIVE」且 `ENDED` 不可逆，脚本用 ORM 把演示学期在测试期间降级为 `PLANNED` 并在 `finally` 中还原（与 `tests/test_academic_term.py::_set_seed_active` 同一手法）。**被验证的操作本身全部走真实 API**；脚本结束时已确认演示数据还原。

## 14. Git

```
fix(FIX-006): 学期管理前端闭环
```

## 15. 最终状态

**COMPLETE** —— 页面 → API → Service → MySQL → 页面 全链路已由真实浏览器与真实 HTTP+MySQL 双向验证，且验收后数据库状态与验收前完全一致。
