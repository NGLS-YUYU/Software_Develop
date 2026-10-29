# 测试与验收说明

> 文档版本：V3.2（2026-10-29）
> 适用代码：UAMS main 分支，Alembic head `e4f5a6b7c8d9`
> 说明：自动化测试覆盖核心回归与部分接口，**不等于全功能、全权限组合或高并发覆盖**。

---

## 1. 测试环境与隔离

- 自动化测试连接 **`uams_test`**，由 `backend/tests/conftest.py` 强制覆盖 `DATABASE_URL`；
- 测试 fixture 再次断言 `SELECT DATABASE() == 'uams_test'`；
- 测试产生的审计日志在会话结束时清理；
- 正式库 `uams` 不参与自动化测试写入；
- 测试数据使用临时账号/记录并在用例内清理。

```bash
cd backend
.venv/bin/pytest -q
```

---

## 2. 后端自动化测试（57 项）

| 文件 | 收集数 | 覆盖 |
|---|---:|---|
| `tests/test_core_regressions.py` | 6 | 隔离库目标、邮箱规范化、成绩快照、考试时长、成绩历史表、未知学期窗口 |
| `tests/test_v31_fixes.py` | 24 | 成绩撤销/更正/历史、ACTIVE 学期、考试冲突/考场、教学任务、教学班开放校验、评价任务、审计、双身份、数据隔离、排名、导出、培养方案、资料、调停课、登录相关对象校验 |
| `tests/test_login_errors.py` | 9 | 登录成功、错误密码/未知账号统一响应、停用、锁定（5 次/剩余秒数）、空值校验、强制 500；**新增**姓名错误拒绝、缺少姓名为 422、初始 admin 姓名兼容 |
| `tests/test_env_guard.py` | 8 | 模式映射、URL 只改库名、特殊字符密码、未知模式、配置缺失、库名不符、版本不符 |
| `tests/test_business_fixes.py` | 10 | FIX-BUSINESS-001：学生学院/专业层级校验、学生/教师/课程批量删除（含关联保护）、教学班名单批量移除（有成绩拒绝）、批量删除空列表 422、导入模板字段与性别校验、三字段登录、教师兼任管理员复用账号与姓名 |
| `frontend/tests/latest.test.mjs` | 2 | 最近请求守卫（`npm run test:unit`） |

**最近结果：57 passed，0 failed。**

```bash
cd backend
.venv/bin/pytest -q
# 57 passed
```

---

## 3. 构建与静态检查

| 检查 | 命令 | 最近结果 |
|---|---|---|
| 前端类型与构建 | `cd frontend && npm run build` | 通过（存在 >500kB chunk 提示，不影响构建） |
| 后端编译 | `cd backend && .venv/bin/python -m compileall -q app tests scripts` | 通过 |
| 启动器语法 | `bash -n start.sh deploy/*.sh` | 通过 |
| systemd unit | `systemd-analyze verify deploy/systemd/uams-backend.service` | 通过（无 UAMS unit 错误） |
| Nginx 配置（临时前缀） | `nginx -t -c /tmp/...` | 通过；正式 `sudo nginx -t` 需 root |
| 数据库版本 | `alembic current` | `e4f5a6b7c8d9 (head)` |

---

## 4. 正式环境验收（非破坏性）

| 项目 | 方法 | 结果 |
|---|---|---|
| Nginx 首页 | `curl --noproxy '*' http://127.0.0.1/` | 200，UAMS 页面 |
| SPA 子路由 | `/admin/students` 直接访问 | 200，返回入口 HTML |
| 静态资源 | 首页 `/assets/*.js` | 200 |
| API 代理 | `/api/v1/terms/active` 未登录 | 401（代理生效） |
| 后端健康 | `http://127.0.0.1:8000/health` | `database: up` |
| systemd | `systemctl is-active uams-backend` | active |
| Nginx | `systemctl is-active nginx` | active |
| 数据库 | `alembic current` | head |

### 4.1 三角色浏览器

在正式环境（Nginx 80）或当前开发临时环境执行无头浏览器页面检查：

- 管理员：仪表盘、学生、教师、课程、开课排课、选课、成绩、考试、评价等；
- 教师：仪表盘、我的课程、成绩、课表；
- 学生：仪表盘、个人信息、选课、课表、成绩、考试。

最近一次页面回归：**19 个页面通过**（Vite 临时服务；正式 Nginx 下的完整三角色浏览器验收以交付时实际执行记录为准）。

### 4.2 登录错误与发布回滚

- 登录：错误密码、未知账号、停用、锁定、断网、500、空值、失败重试、成功跳转，共 12 个浏览器场景通过（`uams_test`）；
- 发布脚本：隔离目录 + 临时 Nginx + 代理环境验证构建、原子切换、首页/API 校验、reload 失败回滚、首次失败保留 current；
- Nginx 临时实例：首页/子路由/API/静态资源/点文件拒绝均符合预期。

---

### 4.3 前端写入后数据同步回归

问题：写入成功后页面可能显示旧数据。修复后新增：

| 类型 | 位置/命令 | 覆盖 |
|---|---|---|
| 单元测试 | `cd frontend && npm run test:unit` | `createLatestGuard` 竞态守卫（2 项） |
| E2E | `python3 tests/e2e/test_student_crud.py` | 新增/修改/删除/重复失败保留 |
| E2E | `python3 tests/e2e/test_multi_page_refresh.py` | 课程、教学班、学期、公告、选课/退课、成绩审核 |
| E2E | `python3 tests/e2e/test_materials_refresh.py` | 资料上传/删除 |
| E2E | `python3 tests/e2e/test_grade_entry_refresh.py` | 成绩保存/提交 |

E2E 环境：`uams_test` 后端 8010、Vite 5180、Chrome/CDP；脚本强制检查 `/health.env=testing`，临时数据自清理。详细说明见 `frontend/tests/e2e/README.md`。

最近结果：单元测试 2 通过；四组 E2E 全部通过（REF-001/002/003/004/005/007/008/009/010/011/012/013/014），REF-006 验证了学期编辑刷新与“已有 ACTIVE 时激活被拒绝”，REF-015 验证了新增跨页可见，REF-016 由守卫单测覆盖。

**未验证**：多浏览器矩阵、WebSocket/跨用户实时推送、复杂筛选与翻页组合、正式库写入（禁止）。

### 4.4 表单标签关联修复（Chrome Issues）

问题：Chrome DevTools Issues 报 `Incorrect use of <label for=FORM_ELEMENT>`。

根因：Element Plus `el-form-item` 会自动把 `label for` 指向单个注册控件的 id；`el-radio-group` / `el-slider` 的根节点是 `div`，其 id 不是可标注表单元素，因此产生无效关联。

修复（应用层，未改 node_modules）：

- 新增 `src/directives/controlId.ts`，为复合控件内部第一个真实 `input` 分配 id；
- 7 个 `el-radio-group`（学生/教师性别、课程考核方式、学期序号、考试类型、公告面向对象、学院状态）与 1 个 `el-slider`（学生评价评分）的 FormItem `for` 指向该 input；
- 单输入控件（input/select/date-picker/input-number/textarea/switch）保持原有关联。

验证：

- `npm run build` 通过；
- DOM 扫描：已检查页面的 `label[for]` 均指向 `INPUT/TEXTAREA`，无 `DIV`/不存在目标；
- 学生表单 E2E（新增/编辑/删除/失败）通过；
- 多页面 E2E（课程/教学班/学期/公告/选课/成绩审核）通过；
- 点击性别分组标签已验证聚焦首个 radio（`activeElement` 为 `student-gender|radio`）。

未验证/未执行：未直接读取 DevTools Issues 面板（使用等价 DOM 规则检查）；最新前端构建尚未发布到正式站点。

### FIX-BUSINESS-001 验证（2026-10-29）

| 项目 | 方法 | 结果 |
|---|---|---|
| 后端全量 | `cd backend && .venv/bin/pytest -q`（隔离库 `uams_test`） | 57 passed |
| 学生学院/专业层级 | 新增/编辑时传入与班级不一致的学院或专业 | 409，未写库 |
| 批量删除安全性 | 学生（有选课）、教师（有教学班）、课程（有教学任务）、名单学生（有成绩）混入可删除项 | 可删项成功、受限项失败并返回原因；历史记录不变 |
| 四类导入模板 | 下载模板、按模板导入学生（含性别）、非法性别 | 模板列与新增表单一致；成功 1 行 / 非法行返回 `gender` 字段错误 |
| 三字段登录 | 缺姓名、错误姓名、正确三字段、初始 admin 兼容名、教师兼任管理员 | 422 / 401 / 200 / 200 / 200；兼任后 `user_type` 仍为 TEACHER |
| 前端 | `npm run build`、`npm run test:unit` | 构建通过；单测 2 passed |

## 5. 未覆盖范围

- 全页面 × 全权限组合；
- 高并发选课/退课/调停课审批；
- 长时间稳定性与内存泄漏；
- 跨浏览器矩阵（仅 Chrome/Chromium 系）；
- 生产数据库故障注入与容灾演练；
- 第三方安全测评/渗透测试；
- 大规模数据量下的查询性能。

这些项目在正式大规模使用前应单独设计测试与验收方案。

---

## 6. 历史验收记录

历史 FIX/部署报告保留在归档中，代表当时代码状态：

- [archive/fixes/](archive/fixes/) — FIX-001～009、V3.1 FIX/登录修复
- [archive/reports/](archive/reports/) — DEPLOY/PROD/阶段报告
- [archive/audits/](archive/audits/) — 审计与预检

当前测试以本文件与 `backend/tests/` 为准。

---

## 7. 相关文档

- [DEPLOYMENT.md](DEPLOYMENT.md)
- [DEVELOPMENT.md](DEVELOPMENT.md)
- [UAMS_系统技术文档.md](UAMS_系统技术文档.md)
- [README.md](../README.md)
