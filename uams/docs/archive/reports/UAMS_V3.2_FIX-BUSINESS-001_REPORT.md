# UAMS V3.2 FIX-BUSINESS-001 修复报告

> 日期：2026-10-29
> 分支：`main`
> 测试库：`uams_test`（正式库 `uams` 未写入、未迁移）
> 说明：本报告承接上一会话遗留的未提交修改，只补齐缺失项，未重做已完成部分。

---

## 1. 任务完成情况

| 任务 | 状态 | 说明 |
|---|---|---|
| FIX-001 学生学院选择 | 已完成并验证 | 学院→专业→班级级联选择；后端校验学院/专业必须与班级一致 |
| FIX-002 批量删除 | 已完成并验证 | 学生、教师、课程、培养方案、教学任务、教学班、教学安排、教学班名单共 8 类；逐条校验、失败原因返回 |
| FIX-003 四类 Excel 导入模板 | 已完成并验证 | 模板字段与新增表单对齐；性别、学院、日期、邮箱、考核形式等；模板缺列保护 |
| FIX-004 三字段登录 | 已完成并验证 | 用户名 + 个人姓名 + 密码联合校验；初始 admin 兼容；教师兼任管理员复用账号 |

上一会话已完成：后端 Schema/Service/API 主体、前端页面改造、`tests/test_business_fixes.py` 初稿、4 个 E2E 脚本登录参数更新。

本次补齐：

1. 修复学生导入在缺少可选「登录名」列时的 `KeyError`（`import_students` 增加列存在性判断）；
2. 教师导入统一使用 `_TEACHER_REQUIRED` 常量；
3. 课程/培养方案表格补上 `type="selection"` 与 `@selection-change`（原按钮无选择列，永远不可用）；
4. 排课弹窗表格补上选择列；
5. 导入结果字段中文化补齐新列（入学年份、出生日期、邮箱、入职日期、考核形式、课程简介、状态）；
6. 学生层级校验测试改为构造“专业与班级不一致”，避免测试库只有一个学院时无法构造冲突；
7. 新增教师批量删除、名单批量移除（有成绩拒绝）、教师兼任管理员三组测试；
8. 同步 PRD.md / PRD.docx / API.md / 技术文档 / 用户手册 / TESTING.md。

---

## 2. FIX-001 学生学院选择

### 后端

- `schemas/person.py`：`StudentCreate` / `StudentUpdate` 增加可选 `college_id`、`major_id`（仅作一致性校验，不单独存储）。
- `services/person.py`：
  - 新增：班级不存在、班级未关联专业时 404；传入学院/专业与班级派生关系不一致时 409；
  - 编辑：更换班级时由新班级重算专业/学院并校验；未更换班级时同样校验；
  - 学院/专业始终以 `class.major` 为权威来源。

### 前端

- `views/admin/Students.vue`：新增/编辑弹窗增加「所属学院」「专业」级联下拉；换学院清空专业与班级，换专业清空班级；提交前要求三者齐全。
- 列表仍展示由班级派生的专业/学院。

### 验证

- 新增时专业与班级不一致 → 409，未创建账号/学生；
- 编辑时专业不一致 → 409；
- 正确层级 → 201，返回的 `college_id` 为班级所属学院。

---

## 3. FIX-002 批量删除

### 通用机制

- `schemas/common.py`：`BatchDeleteRequest`（1–100 条）、`BatchDeleteFailure`、`BatchDeleteResult`。
- `services/base.py`：`batch_delete_each()` 逐条调用模块自身的删除方法，捕获 `BizError` 与异常，汇总 `requested / deleted / failed`；单条失败不影响其他条。
- 所有批量端点固定返回 200，前端根据 `failed` 展示原因。

### 端点

| 模块 | 端点 | 权限 |
|---|---|---|
| 学生 | `POST /students/batch-delete` | `student:write` |
| 教师 | `POST /teachers/batch-delete` | `teacher:write` |
| 课程 | `POST /courses/batch-delete` | `course:write` |
| 培养方案 | `POST /curriculum-plans/batch-delete` | `curriculum:write` |
| 教学任务 | `POST /teaching-tasks/batch-delete` | `teaching:write` |
| 教学班 | `POST /teaching-classes/batch-delete` | `teaching:write` |
| 教学安排 | `POST /teaching-schedules/batch-delete` | `schedule:write` |
| 教学班名单 | `POST /teaching-classes/{id}/students/batch-delete` | `selection:manage` |

### 数据安全约束（复用单条删除）

- 学生：有选课记录时拒绝；
- 教师：有教学班时拒绝；
- 课程：有教学任务时拒绝；
- 教学任务：有教学班时拒绝；
- 教学班：有有效选课或成绩时拒绝；已结束学期拒绝；
- 教学班名单移除：已有成绩记录时拒绝；移除为软删除（`DROPPED`），保留来源与时间；
- 任何批量操作都不级联删除成绩、选课、教学任务等历史记录。

### 前端

- `useCrudTable` 增加 `selectedRows / batchDeleting / onSelectionChange / batchRemoveSelected`，统一确认框与部分失败提示；
- 学生、教师、课程、培养方案页面增加选择列与「批量删除」按钮；
- 开课排课页：教学任务、教学班、排课弹窗分别支持批量删除；
- 选课管理：名单弹窗支持勾选多名学生批量移除。

### 验证

- 学生（有选课）+ 临时学生：临时学生删除成功，受限学生失败并返回原因；
- 教师（有教学班）+ 临时教师：同上，临时教师账号同步删除；
- 课程（有教学任务）+ 临时课程：同上；
- 名单中“有成绩学生 + 不存在的学生”：全部失败，`deleted` 为空，不产生 `DROPPED` 记录；
- 空 `ids` → 422；无权限学生账号 → 403；重复提交已删除 ID → 明确失败原因。

---

## 4. FIX-003 四类 Excel 导入模板

### 字段对齐

| 模板 | 必填 | 选填 |
|---|---|---|
| 学生 | 学号、姓名、学院、专业、行政班 | 登录名、性别、出生日期、入学年份、邮箱、手机 |
| 教师 | 工号、姓名、学院 | 职称、性别、入职日期、邮箱、联系电话 |
| 课程 | 课程代码、课程名称、学院、学分、总学时、理论学时、实践学时、课程性质 | 考核形式、课程简介、状态 |
| 成绩 | 按教学班动态生成 | — |

### 后端

- `_STUDENT_HEADERS/_TEACHER_HEADERS/_COURSE_HEADERS` 扩展，并分别定义必填集合；
- 新增中文字段别名（性别、出生日期、入学年份、邮箱、入职日期、考核形式等）；
- 导入学生：性别翻译、出生日期解析、入学年份校验（留空取班级年级）、邮箱/手机写入；学院/专业传给 `create_student` 做层级校验；
- 导入教师：入职日期、邮箱写入；
- 导入课程：考核形式、课程简介、状态写入；
- 每行创建包在异常捕获中，单行失败返回原因，不影响其他行。

### 前端

- `ImportCenter.vue` 字段中文化补齐新列，三个 Tab 的操作提示同步更新。

### 验证

- 下载模板为合法 xlsx；
- 按模板导入学生（含性别“女”）成功 1 行，`gender=FEMALE`、`college_id` 正确；
- 非法性别“未知X”行失败，错误字段为 `gender`；
- 删除可选「登录名」列后仍可导入（修复 `KeyError`）。

---

## 5. FIX-004 三字段登录

### 规则

- 请求体：`{ username, real_name, password }`，三项均为必填；
- `username` 全局唯一（学号 / 工号 / 管理员登录名）；
- `real_name` 取自 `users.real_name`（学生/教师建档时写入），不是独立登录名；
- 姓名与密码同时校验，任一失败统一返回 `AUTH_INVALID_CREDENTIALS`（“用户名、姓名或密码错误”），并计入原有失败次数与 5 次/15 分钟锁定策略；
- 初始管理员 `admin`：接受姓名 `admin` 或历史显示名「系统管理员」，不修改历史资料；
- 其他管理员允许用户名与姓名不同；
- 教师兼任管理员：`POST /admins/{id}/grant` 只增加角色，不改 `user_type`、不复制账号，用户名与姓名保持教师本人。

### 前端

- 登录页新增「个人姓名」输入框，三字段均必填；
- 错误文案、401 兜底、校验提示同步更新；
- 4 个 E2E 脚本的登录辅助函数补充 `real_name`。

### 验证

- 缺少姓名 → 422 `VALIDATION_ERROR`；
- 姓名错误 → 401 `AUTH_INVALID_CREDENTIALS`；
- `admin` + `admin` / `admin` + `系统管理员` → 200；
- 教师 T001 授予管理员后：同一账号/姓名/密码仍可登录，`/auth/me` 含 `ACADEMIC_ADMIN`，`user_type` 仍为 `TEACHER`；撤销后恢复。

---

## 6. 测试结果

| 项目 | 命令 | 结果 |
|---|---|---|
| 后端全量 | `cd backend && .venv/bin/pytest -q` | **57 passed** |
| 新增业务测试 | `pytest tests/test_business_fixes.py -q` | 10 passed |
| 登录测试 | `pytest tests/test_login_errors.py -q` | 9 passed |
| 前端构建/类型 | `cd frontend && npm run build` | 通过 |
| 前端单测 | `npm run test:unit` | 2 passed |

浏览器 E2E：已在隔离栈（`uams_test` 后端 8010、Vite 5180、Chrome/CDP）执行 `test_business_acceptance.py`，49 项全部通过（含 Console/Network 检查）。详见 `UAMS_V3.2_FIX-BUSINESS-001_ACCEPTANCE.md`。

测试中发现并修复的问题：

1. `import_students` 在模板缺少可选「登录名」列时 `KeyError` → 增加列存在性判断；
2. 学生层级测试依赖“第二个学院”，测试库只有一个学院时无法构造冲突 → 改为构造“专业与班级不一致”，并在存在第二学院时额外验证学院冲突；
3. 课程/培养方案/排课表格缺少选择列，批量按钮不可用 → 补齐选择列与事件。

---

## 7. 文档同步

| 文档 | 更新内容 |
|---|---|
| `docs/PRD.md` | FR-001/003/131/132、FR-143~145；文档控制新增 V3.2 (FIX-BUSINESS-001) |
| `docs/PRD.docx` | 由 PRD.md 重新生成（A4、封面、目录域、页码、表格） |
| `docs/API.md` | 三字段登录说明、8 个批量删除端点与响应约定、导入模板字段表 |
| `docs/UAMS_系统技术文档.md` | 认证流程、登录 curl、安全表、Service 说明 |
| `docs/UAMS_教务管理系统用户操作手册.md` | 登录步骤、学生级联选择、各模块批量删除、导入模板列、登录故障排查 |
| `docs/TESTING.md` | 测试数量与 FIX-BUSINESS-001 验证记录 |

---

## 8. 安全与部署边界

- 仅修改 `main` 分支工作区，未创建分支/worktree/PR；
- 未执行 `git reset`、`git checkout --`、`git clean`，保留全部既有修改；
- 未连接或修改正式库 `uams`，未执行任何生产迁移；
- 未重启 Nginx/systemd，未发布正式前后端；
- 未修改任何正式用户密码；
- 批量删除不改变单条删除的业务约束，历史记录无级联删除。

## 9. 已知限制

- 批量删除为逐条提交，部分成功是设计行为；失败项需人工处理后再次提交；
- 批量删除单次上限 100 条；
- 学生/教师的“学院、专业”为班级派生字段，API 传入仅用于校验，不能独立指定；
- 三字段登录使所有旧客户端必须补充 `real_name`，属预期破坏性变更，已在 API 与手册中说明；
- 浏览器 E2E 已在隔离环境执行通过（49 项）。
