# UAMS V3.1 FIX-001 学生与教师邮箱异常治理报告

> 修复日期：2026-10-26
> 基线分支：`main`
> 相关报告：`docs/UAMS_V3.1_FUNCTION_GAP_AUDIT.md`（F-02）、`docs/UAMS_V3.1_PRECHECK_REPORT.md`（PC-01/PC-02）
> 修复代码提交：`f00d6dcac3b988f8731481d678e52c84fed5a806`
> 推送结果：已成功推送到 `origin/main`（`f00d6dc`）
> 本报告提交：见本次最终 Git 记录（`main` 最新提交）

---

## 0. 结论摘要

1. **根因已修复**：空字符串/纯空格邮箱现在在 Schema 与 Service 两层统一归一化为 `NULL`；非空邮箱统一校验格式；重复邮箱返回 `409 EMAIL_ALREADY_EXISTS`，不再触发未处理的 HTTP 500。
2. **学生、教师、管理员创建使用同一套邮箱逻辑**：`UserService`、`StudentService`、`TeacherService` 均经过同一规范化/唯一性检查；批量导入显式按“未填写”传 `NULL`。
3. **编辑邮箱可清空**：学生/教师更新时 `email=""`/纯空格会清空为 `NULL`；编辑为他人邮箱返回 409。
4. **事务安全**：`flush()` 阶段的唯一约束冲突会先 `rollback` 再返回业务异常；创建失败后不会留下孤立 `users` / `user_roles` / 档案记录。
5. **未改数据库结构**：保留 `users.email` 唯一索引，不新增迁移；历史 3 个异常邮箱和 4 个 `NULL` 邮箱均未修改。
6. **测试结果**：在隔离库 `uams_test` 执行 25 项后端/API 断言，**25 项通过、0 项失败**；前端 `npm run build` 通过；后端 `compileall` 通过；`alembic check` 无 schema 漂移。
7. **未做浏览器实测**：未启动浏览器逐页点击验证错误提示；前端构建通过，错误提示由现有 Axios 拦截器展示后端 `message`，但不能宣称浏览器端到端验收通过。

---

## 1. 原始缺陷根因

### 1.1 复现路径

1. 教务在“学生管理/教师管理”新增档案，邮箱留空。
2. 前端表单初始值为 `email: ''`，提交时没有转成 `null`。
3. 后端 `StudentCreate` / `TeacherCreate` 的 `email` 是普通 `str | None`，Pydantic 接受空字符串。
4. `StudentService.create_student()` / `TeacherService.create_teacher()` 把 `data.get("email")` 原样写入 `users.email`，随后 `self.db.flush()`。
5. `users.email` 有唯一索引：MySQL 允许多个 `NULL`，但不允许多个空字符串 `''`。
6. 第二个空邮箱或重复非空邮箱在 `flush()` 抛 `IntegrityError`；`BaseCrudService._commit()` 只捕获 `commit()` 阶段的 `IntegrityError`，没有捕获 `flush()`；`main.py` 也没有全局 `IntegrityError` 处理器，最终返回 500。

### 1.2 其他关联问题

- **编辑不能清空邮箱**：`StudentService.update_student()` / `TeacherService.update_teacher()` 用 `{k: v for k, v in data.items() if v is not None}` 过滤字段，显式提交 `email=None` 会被丢弃，无法把邮箱清空为 `NULL`。
- **错误信息不区分字段**：`_commit()` 只根据 `"duplicate"` 返回“已存在重复数据”，无法区分邮箱、登录名、学号、工号冲突。
- **管理员创建/批量导入未统一**：管理员 `UserService.create_user()` 直接写入 `email`；导入服务依赖同一模型，但没有统一的邮箱入口。
- **前端没有格式提示**：新增/编辑表单只限制 `maxlength=100`，没有邮箱格式校验；空字符串直接提交。

---

## 2. 修改的文件与关键逻辑

### 2.1 后端

| 文件 | 变更 |
|---|---|
| `backend/app/core/email.py`（新增） | 统一 `normalize_email()`：`None`/`""`/纯空格 -> `None`；`strip()` 后校验长度（≤100）和格式；非法值抛 `ValueError`。 |
| `backend/app/schemas/email.py`（新增） | `EmailField = Annotated[Optional[str], BeforeValidator(normalize_email)]`，在请求模型入口统一归一化。 |
| `backend/app/schemas/person.py` | `StudentCreate/Update`、`TeacherCreate/Update` 的 `email` 改用 `EmailField`。 |
| `backend/app/schemas/user.py` | `UserCreate.email` 改用 `EmailField`。 |
| `backend/app/core/exceptions.py` | 新增 `INVALID_EMAIL`（400）与 `EMAIL_ALREADY_EXISTS`（409）。 |
| `backend/app/services/email.py`（新增） | `normalize_email_or_error()` 把 `ValueError` 转为 400；`ensure_email_available()` 做写库前唯一性预检查（支持排除当前用户）。 |
| `backend/app/services/integrity.py`（新增） | `conflict_from_integrity_error()` 按索引名区分 `users.email` / `users.username` / `students.student_no` / `teachers.teacher_no`；`flush_or_conflict()` 在 flush 失败时先 rollback。 |
| `backend/app/services/base.py` | `_commit()` 复用统一 IntegrityError 映射；未知错误继续抛出，不一律当作邮箱重复。 |
| `backend/app/services/person.py` | 学生/教师创建：规范化邮箱、预检查、写入规范化值；`flush_or_conflict` + 外层 rollback。更新：允许显式清空 `email`，更新前排除当前用户检查唯一性。 |
| `backend/app/services/user.py` | 管理员创建账号：同一套邮箱规范化/唯一性检查；flush 冲突 rollback；任何后续异常回滚，避免孤立账号。 |
| `backend/app/services/import_service.py` | 学生/教师导入显式传入 `email=None`，保证“模板无邮箱列”时落库为 `NULL`。 |
| `docs/API.md` | 增加 `INVALID_EMAIL`、`EMAIL_ALREADY_EXISTS` 错误码与邮箱字段说明。 |

关键行为：

- **空值**：`None`、`""`、`"   "` -> `None` -> 数据库 `NULL`。
- **格式**：要求常见 `local@domain.tld` 形式（本地部分/域名标签/TLD 至少 2 个字母），长度 ≤100。
- **唯一性**：学生、教师、管理员共用 `users.email` 唯一约束；预检查 + 数据库唯一索引 + flush/commit 双重兜底。
- **错误码**：
  - 请求模型层非法格式：`422 VALIDATION_ERROR`（`email: 邮箱格式不正确`）；
  - Service 层非法格式：`400 INVALID_EMAIL`；
  - 重复邮箱：`409 EMAIL_ALREADY_EXISTS`；
  - 登录名/学号/工号重复：仍返回 `RESOURCE_CONFLICT`，消息分别提示对应字段。
- **事务**：flush 冲突 `rollback`；创建流程外层 `except Exception: rollback`；更新走 `_commit()` 的回滚路径。
- **历史数据**：未修改任何历史邮箱；3 个无 `@` 邮箱、4 个 `NULL` 邮箱保持原样。

### 2.2 前端

| 文件 | 变更 |
|---|---|
| `frontend/src/utils/email.ts`（新增） | `normalizeEmailInput()` 把 `undefined`/空/空格转为 `null`；`isValidEmail()` 做前端格式提示（最终以后端为准）。 |
| `frontend/src/views/admin/Students.vue` | 提交前归一化 `email`；非法格式 `ElMessage.warning('邮箱格式不正确')` 并阻止提交；新增 `save()` 包装 `payload()` 的可空返回值。 |
| `frontend/src/views/admin/Teachers.vue` | 同上，与学生端行为一致。 |

说明：

- 管理员创建账号页面当前没有邮箱输入框，创建时按“未填写”处理；后端 `UserCreate` 仍统一支持并校验 `email`。
- 前端只做提示，不代替后端校验；后端是唯一裁判。

---

## 3. 测试用例及结果

### 3.1 测试环境

| 项 | 值 |
|---|---|
| 测试数据库 | `uams_test`（项目既有隔离测试库，与正式库 `uams` 分离） |
| 数据库版本 | MySQL 8.4.11 |
| 测试方式 | FastAPI `TestClient` + 直接 Service/SQL 校验 |
| 测试脚本 | 临时脚本 `/tmp/fix001_email_tests.py`（未纳入 Git） |
| 测试数据前缀 | `FIX001_`，测试结束全部清理 |
| 正式库 `uams` | **未执行任何写入**；测试前后 `users=8`、`students=4`、`teachers=3`、`operation_logs=22` 不变 |
| 隔离库清理 | 测试后 `FIX001_` 用户/学生/教师均为 0；行数恢复 `users=26`、`students=20`、`teachers=5`、`user_roles=26` |

> 说明：当前 MySQL 应用账号只有 `uams` / `uams_test` 权限，没有 `CREATE DATABASE` 权限，因此使用项目既有隔离库 `uams_test`，没有新建第三个库；未触碰正式库 `uams`。

### 3.2 必测用例结果

| # | 测试用例 | 结果 | 证据/说明 |
|---:|---|---|---|
| 1 | 连续创建两个邮箱留空的学生 | PASS | 两次均 201，响应 `email=null` |
| 2 | 连续创建两个邮箱留空的教师 | PASS | 两次均 201，响应 `email=null` |
| 3 | 输入纯空格邮箱 | PASS | 学生/教师均归一化为 `NULL`，201 |
| 4 | 输入非法邮箱 | PASS | 请求模型返回 422，非 500 |
| 5 | 创建重复邮箱的用户 | PASS | 409 `EMAIL_ALREADY_EXISTS`，消息“邮箱已存在，请更换邮箱” |
| 6 | 编辑邮箱为空 | PASS | 先设置邮箱，再提交 `email=""`，响应 `email=null` |
| 7 | 编辑邮箱为已有用户的邮箱 | PASS | 409 `EMAIL_ALREADY_EXISTS` |
| 8 | 不同角色之间的邮箱唯一性 | PASS | 教师使用学生已有邮箱返回 409 |
| 9 | 创建失败后的数据库事务回滚 | PASS | 绕过预检查模拟 flush 冲突，返回 409；失败后无孤立 `users` / `students` |
| 10 | 已有账号、档案和角色关联保持正常 | PASS | 测试前后行数一致；管理员账号角色、既有学生档案/角色关联不变 |
| 11 | 批量导入时空邮箱处理正确 | PASS | 学生/教师导入各 1 条成功，落库邮箱为 `NULL` |
| 12 | 前端正常显示明确的错误提示 | **未验证（浏览器）** | 前端构建通过；Axios 拦截器会显示后端 `message`，但未启动浏览器点击验证 |

### 3.3 额外测试与断言（13 项）

| # | 测试用例 | 结果 |
|---:|---|---|
| 13 | 大小写不同的重复邮箱 | PASS：仍返回 409 `EMAIL_ALREADY_EXISTS`（数据库排序规则大小写不敏感） |
| 14 | 管理员创建空邮箱账号 | PASS：201，`email=null` |
| 15 | 管理员创建重复邮箱账号 | PASS：409 `EMAIL_ALREADY_EXISTS` |
| 16 | 学号重复提示学号而非邮箱 | PASS：“学号已存在” |
| 17 | 工号重复提示工号而非邮箱 | PASS：“工号已存在” |
| 18 | 登录名重复提示登录名而非邮箱 | PASS：“登录名已存在” |
| 19 | flush 阶段邮箱冲突返回业务错误 | PASS：409，非 500 |
| 20 | 失败后无孤立 `users` 记录 | PASS |
| 21 | 失败后无孤立 `students` 记录 | PASS |
| 22 | 学生批量导入空邮箱 | PASS：`success=1`，`email=NULL` |
| 23 | 教师批量导入空邮箱 | PASS：`success=1`，`email=NULL` |
| 24 | 测试后基础表行数恢复基线 | PASS：`26/20/5/26 -> 26/20/5/26` |
| 25 | 既有管理员/学生角色关联不变 | PASS |

**测试汇总：25 项通过，0 项失败。**
唯一未完成的是浏览器端提示实测（第 12 项）；不能宣称浏览器端到端验收通过。

### 3.4 构建与静态检查

| 项 | 命令 | 结果 |
|---|---|---|
| 后端编译 | `python -m compileall app` | 通过 |
| 前端构建 | `npm run build`（含 `vue-tsc -b`） | 通过；仅 chunk 体积提示 |
| 隔离库 schema | `alembic check`（`DATABASE_URL` 指向 `uams_test`） | `No new upgrade operations detected.` |
| 正式库 | 只读计数 | `users=8`、`students=4`、`teachers=3`、`operation_logs=22`，与修复前一致 |

---

## 4. 数据库兼容性

| 项 | 结论 |
|---|---|
| 是否需要迁移 | **不需要**。未修改模型字段、索引或表结构。 |
| `users.email` 唯一索引 | 保留；MySQL 唯一索引允许多个 `NULL`，空字符串在应用层统一转 `NULL`。 |
| 历史数据 | 4 个 `NULL` 邮箱、3 个无 `@` 邮箱均未修改；历史账号/档案/角色不受影响。 |
| MySQL 版本 | 8.4.11，符合项目要求；`uams_test` 当前 Alembic head 为 `a5b7c9d1e2f3`，`alembic check` 无漂移。 |
| 并发 | 预检查之后仍有数据库唯一索引兜底；flush/commit 冲突都映射为 409 并回滚。未做真实并发压测。 |
| 回滚 | 仅回滚当前事务；不删除历史数据；不回滚/重置数据库。 |

风险说明：

- 如果未来新增“邮箱归一化唯一索引”（例如对 `LOWER(TRIM(email))` 建唯一索引），必须先清理 3 个无 `@` 历史邮箱；本次**没有**新增该索引。
- 前端只做格式提示；如果前端绕过，后端仍会独立校验。
- 批量导入模板目前不含邮箱列，因此导入统一落 `NULL`；若未来模板增加邮箱列，应复用 `normalize_email_or_error()` 并在导入错误明细中返回 `email` 字段错误。

---

## 5. 未验证项目

| 项目 | 原因 |
|---|---|
| 浏览器端新增/编辑邮箱提示 | 未启动前端/浏览器；只做了前端构建和 Axios 拦截器代码检查 |
| 真实并发请求下的邮箱竞争 | 未做并发压测；通过 patch 预检查模拟了 flush 阶段唯一约束冲突 |
| 邮件发送/可达性 | 本任务只处理存储与校验，不涉及邮件发送 |
| 全量 pytest 套件 | 项目最终交付已移除 `backend/tests/`（见 `docs/TESTING.md`），当前无 pytest 套件可运行 |
| 生产环境验收 | 仅在 `uams_test` 隔离库验证，未在正式库写入 |
| 历史 3 个异常邮箱的真实性 | 属于历史数据；按要求不自动修正，需教务人工确认 |
| 前端响应式/交互细节 | 未做浏览器回归；仅 `npm run build` 通过 |

---

## 6. Git 与交付

| 项 | 结果 |
|---|---|
| 分支 | `main` |
| 修复代码提交 | `f00d6dcac3b988f8731481d678e52c84fed5a806` |
| 修复代码提交主题 | `fix: normalize and validate optional user emails` |
| 代码提交推送 | `git push origin main` 成功（`ccc7b9c..f00d6dc`） |
| 报告提交 | 见本次最终 Git 记录（`main` 最新提交） |
| 是否新建分支/worktree/PR | 否 |
| 是否 force push / reset --hard | 否 |
| 正式库 | 未写入、未重置、未删除 |
| 提交范围 | 修复代码 + `docs/API.md`；报告单独提交；未提交临时测试脚本 |

---

## 7. 结论

F-02 的根因已从三个层面同时处理：

1. **输入层**：Pydantic `EmailField` 把空/空格转 `NULL`，非法格式返回 422；
2. **Service 层**：统一规范化、写前唯一性检查、显式支持清空；
3. **数据库层**：保留唯一索引，flush/commit 的 `IntegrityError` 映射为明确的 409 并回滚，不再返回未处理的 500。

学生、教师、管理员创建与批量导入已统一到同一套邮箱逻辑；现有账号、角色、学生/教师档案关联未被破坏。唯一未完成的是浏览器端提示实测，报告已如实标注，不宣称端到端验收通过。

---

> 报告结束。
> 本次修复未修改正式库数据、未修改数据库结构；所有测试写入均发生在隔离库 `uams_test` 并已清理。
