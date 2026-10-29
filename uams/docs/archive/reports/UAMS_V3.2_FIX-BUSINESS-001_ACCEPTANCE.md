# UAMS V3.2 FIX-BUSINESS-001 上线前验收与部署方案

> 日期：2026-10-29
> 代码基线：`75580e5`（本文档随后单独提交）
> 验收环境：`uams_test`（后端 8010 / Vite 5180 / Chrome CDP），**未连接或修改正式库 `uams`**
> 结论：四项业务修复的浏览器验收 **49/49 通过**；无数据库迁移；上线需按“前端优先”顺序切换，回滚必须前后端成对执行。

---

## 1. 验收结论

| 项目 | 结果 |
|---|---|
| 浏览器 E2E（真实 UI + Console + Network） | **49 项全部通过** |
| 后端回归 | 57 passed |
| 前端构建 / 单元测试 | 构建通过；2 passed |
| 批量删除覆盖 | 8 类，均有页面入口、API、Service 与业务约束 |
| 正式库身份完整性 | 活跃账号空姓名 **0**；初始管理员可用；无迁移 |
| 是否可上线 | 可以，在获得生产授权并完成备份后执行第 6 节 |

验收期间发现并修复的两个问题：

1. 学生导入模板电话列表头为「联系电话」，与「新增学生」表单的「手机」不一致 → 模板改为「手机」（解析仍兼容旧表头）。
2. E2E 初期选择器把多个下拉框选项混在一起、读取了错误的选中值节点 → 改为按当前可见下拉容器与 `.el-select__placeholder` 读取。

---

## 2. E2E 结果明细

执行：

```bash
cd uams/frontend
../backend/.venv/bin/python tests/e2e/prep_business_acceptance.py
python3 tests/e2e/test_business_acceptance.py
../backend/.venv/bin/python tests/e2e/cleanup_business_acceptance.py
```

| 分组 | 通过项 | 覆盖 |
|---|---:|---|
| LOGIN-1~11 | 11 | 缺姓名前端拦截、错误姓名/密码 401、初始 admin（`admin` 名与历史姓名）、教师/学生三字段登录、角色菜单、教师兼任管理员同账号登录 |
| UI-1~10 | 10 | 学生列加载、未选学院时专业/班级禁用、专业按学院过滤、班级按专业过滤、新增/编辑/删除无需 F5、编辑回显 |
| BATCH-1~6 | 6 | 学生/课程批量删除成功反馈、无 F5 消失、有选课学生与有教学任务课程被拒绝并保留 |
| SELECT-1~4 | 4 | 名单加载、勾选有成绩学生、批量移除被拒绝、名单仍保留 |
| TPL-1~8 | 8 | 学生/教师/课程/成绩模板下载成功且字段完整（学生模板含「手机」） |
| IMP-1~8 | 8 | 学生/教师/课程/成绩各一组合法与非法导入（1 成功 0 失败 / 0 成功 1 失败） |
| CONSOLE / NETWORK | 2 | 无未捕获异常或 `console.error`；无 HTTP 5xx |

> E2E 使用 Chrome/CDP 驱动真实页面；数据写入仅发生在 `uams_test`。测试栈在验收后已停止，临时课程/教学班/选课/成绩已清理。

---

## 3. 批量删除覆盖矩阵（8 类）

通用实现：`schemas/common.py` 的 `BatchDeleteRequest/BatchDeleteResult` + `services/base.py::batch_delete_each`。
逐条调用各模块单条删除方法，单条失败不影响其他条，HTTP 固定 200，失败返回 `{id, reason}`。

| # | 页面 | API | Service | 业务规则（拒绝条件） |
|---|---|---|---|---|
| 1 | 学生管理 `Students.vue` | `POST /students/batch-delete` | `StudentService.delete` | 存在任意 `course_selections` 记录；删除学生同时删除账号并回退班级人数 |
| 2 | 教师管理 `Teachers.vue` | `POST /teachers/batch-delete` | `TeacherService.delete` | 已被 `teaching_classes.teacher_id` 引用 |
| 3 | 课程管理 `Courses.vue` | `POST /courses/batch-delete` | `CourseService.delete` | 存在 `teaching_tasks` |
| 4 | 培养方案 `Curriculum.vue` | `POST /curriculum-plans/batch-delete` | `CurriculumService.delete` | 方案课程随方案处理；不做跨模块级联删除 |
| 5 | 开课排课·教学任务 `Teaching.vue` | `POST /teaching-tasks/batch-delete` | `TeachingTaskService.delete` | 任务下存在教学班 |
| 6 | 开课排课·教学班 `Teaching.vue` | `POST /teaching-classes/batch-delete` | `TeachingClassService.delete` | 存在 `SELECTED` 选课或任意成绩；`ENDED` 学期 |
| 7 | 开课排课·排课弹窗 `Teaching.vue` | `POST /teaching-schedules/batch-delete` | `ScheduleService.delete` | `ENDED` 学期只读；删除排课不影响教学班/选课 |
| 8 | 选课管理·名单弹窗 `SelectionManage.vue` | `POST /teaching-classes/{id}/students/batch-delete` | `batch_delete_each` + `TeachingClassService.remove_student` | 学期非 `ACTIVE`；无有效选课；存在任意成绩（含草稿）；软删除为 `DROPPED` 并写操作日志 |

前端统一入口：`composables/useCrudTable.ts` 的 `selectedRows / onSelectionChange / batchRemoveSelected`，含二次确认与部分失败提示。

### 3.1 “选课管理”边界说明

| 操作 | 入口 | 行为 | 拒绝条件 |
|---|---|---|---|
| 教学班学生名单批量移除 | 选课管理 → 名单弹窗 → 批量移除学生 | 教务调整：`SELECTED → DROPPED`，保留来源/时间，写日志 | 学期非 ACTIVE；无有效选课；**任意成绩**（含 DRAFT） |
| 管理员取消单个选课 | 同一弹窗的行内移除 / `DELETE /teaching-classes/{id}/students/{sid}` | 与批量移除同一个 Service，无独立的“管理员硬删除选课”接口 | 同上 |
| 学生自主退课 | 学生端 `DELETE /course-selections/{id}` | `SelectionService.drop_course` | 必修/公共必修/实践课；教学班非 OPEN；不在选课窗口；非草稿成绩 |

结论：

- 选课管理已完整覆盖“名单批量移除”和“管理员取消选课”，二者共用同一套规则，**不会物理删除选课或成绩**；
- 批量操作不会绕过规则：每条都调用 `remove_student`，已有成绩的拒绝在测试中已通过（SELECT-3）；
- 必修课约束保留在学生自主退课路径（`必修课不能由学生自主退选`）；教务名单移除是学校层面的调整通道，允许移除必修课学生，但一旦有成绩仍拒绝——符合 TASK-009 的分工；
- 系统没有“管理员直接删除关联成绩”的入口，批量删除也不会触发级联删除。

---

## 4. 三字段登录兼容性审查

### 4.1 契约变化

```json
// 旧：{ "username": "...", "password": "..." }
// 新：{ "username": "...", "real_name": "...", "password": "..." }
```

- `real_name` 为必填（1–50），与 `users.real_name` 精确匹配（去首尾空白）；
- 姓名或密码错误统一 401 `AUTH_INVALID_CREDENTIALS`，计入原有失败次数与 5 次/15 分钟锁定；
- 初始 `admin`：接受存储姓名，也接受字面量 `admin`；
- 教师兼任管理员：`user_roles` 增加角色，`user_type` 不变、账号与姓名不复制。

### 4.2 组合兼容矩阵

| 组合 | 登录 | 其他功能 | 结论 |
|---|---|---|---|
| 新前端 + 新后端 | 正常（三字段） | 全部可用 | **目标状态** |
| 旧前端 + 新后端 | **422 失败**（缺 `real_name`） | 无法进入系统 | **不可共存**，必须同窗口切换 |
| 新前端 + 旧后端 | 正常（旧后端忽略多余字段，仅校验用户名+密码） | 批量删除等新端点 404；学生学院字段被忽略 | **可短暂共存**，作为切换过渡态 |

因此切换顺序必须是 **先发布新前端，再启用新后端**：过渡期新前端仍可登录；反向顺序会让旧前端完全无法登录。

直接调用 API 的第三方客户端同样必须补 `real_name`，这是本次唯一的破坏性契约变更。

### 4.3 正式库只读核查（仅汇总，不输出姓名）

| 检查 | 结果 |
|---|---|
| `users.status=ACTIVE` 且姓名为空/纯空白 | **0** |
| 活跃管理员空姓名 | **0** |
| 活跃教师/学生空姓名 | **0 / 0** |
| 管理员账号数 | 1（初始 `admin`） |
| `admin` 的 `real_name` 是否为空 | 否（且不等于字面量 `admin`，两种输入均兼容） |
| 教师/学生档案与 `users` 关联缺失 | 0 / 0 |
| `alembic_version` | `e4f5a6b7c8d9`，与仓库 head 一致 |
| `env_guard check production` | `db=uams current=e4f5a6b7c8d9 head=e4f5a6b7c8d9 match=1` |

结论：正式库无需补姓名数据；无账号因新规则被锁在门外；**无数据库结构变更，无需 Alembic 迁移**（`5b5c896..HEAD` 未修改 `alembic/` 与 `requirements.txt`）。

---

## 5. 当前正式环境记录（只读检查）

| 项目 | 当前值 |
|---|---|
| 旧代码基线 | `5b5c896` |
| 当前前端 release | `/var/www/uams/releases/20261029_031352`（`current`） |
| 上一 release | `/var/www/uams/releases/20261029_023646`（`previous`） |
| 当前 `index.html` SHA-256 | `e639ade301017de3eb27131edf305bbea0d501943103a81f7953141e8b2e1f7e` |
| Nginx | active，80 端口，`/` → `/var/www/uams/current`，`/api` → `127.0.0.1:8000` |
| MySQL | active，正式库 `uams` |
| `uams-backend.service` | enabled 但 **inactive（dead）**；因此当前 `GET /api/v1/terms/active` 返回 502 |
| 后端工作目录 | 本仓库 `uams/backend`，systemd 以 `env_guard exec production` 启动 |

> 上线前请确认这是预期的停机状态。若需要保持旧版可用，先 `sudo systemctl start uams-backend` 恢复旧后端，再按第 6 节执行。

---

## 6. 上线步骤（需生产授权后执行）

> 全程建议维护窗口。开始前确认：已授权、已备份、无人正在录入成绩。

### 6.1 记录基线

```bash
cd /home/nglsyuyu/Software_Develop/Software_Develop
git status --short --branch          # 必须干净
git rev-parse HEAD                   # 旧基线：5b5c896
readlink -f /var/www/uams/current    # 20261029_031352
readlink -f /var/www/uams/previous
sha256sum /var/www/uams/current/index.html
```

### 6.2 备份数据库

```bash
STAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p ~/uams-backups/$STAMP && chmod 700 ~/uams-backups/$STAMP

mysqldump --single-transaction --quick --routines --triggers \
  --default-character-set=utf8mb4 -h 127.0.0.1 -u uams_app -p uams \
  | gzip > ~/uams-backups/$STAMP/uams.sql.gz

gzip -t ~/uams-backups/$STAMP/uams.sql.gz && echo BACKUP_OK

# 结构与迁移版本单独留档
mysqldump --single-transaction --no-data -h 127.0.0.1 -u uams_app -p uams \
  > ~/uams-backups/$STAMP/uams_schema.sql

# 配置留档（不含明文输出）
cp uams/backend/.env ~/uams-backups/$STAMP/backend.env.bak
cp /etc/nginx/sites-available/uams ~/uams-backups/$STAMP/nginx-uams.conf
systemctl cat uams-backend > ~/uams-backups/$STAMP/uams-backend.service.txt
chmod 600 ~/uams-backups/$STAMP/*
```

备份文件不得放在数据库数据目录、Nginx 站点目录或 Git 仓库内。

### 6.3 代码与服务预检

```bash
cd /home/nglsyuyu/Software_Develop/Software_Develop
git fetch origin
git switch main
git pull --ff-only
git rev-parse HEAD                   # 应为本次验收提交

cd uams/backend
.venv/bin/python scripts/env_guard.py check production
# 期望：db=uams current=e4f5a6b7c8d9 head=e4f5a6b7c8d9 match=1
```

- **无需** `pip install`、**无需** `alembic upgrade`；
- 若 `match` 不为 1，停止上线并排查。

### 6.4 发布新前端（先）

```bash
cd /home/nglsyuyu/Software_Develop/Software_Develop/uams
bash deploy/deploy-frontend.sh
```

脚本会：构建 → 新建 `/var/www/uams/releases/<时间戳>` → 原子切换 `current` → `nginx -t`/reload → 校验首页；失败自动回滚 `current`。
此时后端若是旧版或未启动，`verify_api_proxy` 只告警不阻断，属预期。

### 6.5 启动/重启新后端（后）

```bash
sudo systemctl start uams-backend      # 当前为 inactive
# 若此前已 running，则用：sudo systemctl restart uams-backend
sudo systemctl status uams-backend --no-pager
```

启动后立即检查：

```bash
curl -s http://127.0.0.1:8000/health
# 期望：{"status":"ok","env":"production","database":"up",...}
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1/api/v1/terms/active
# 期望：401（未登录）或 200；不得为 502/500
```

### 6.6 上线验收

1. 浏览器无痕窗口打开 `http://<站点>/`：
   - `admin` + 姓名（字面量 `admin` 或右上角显示名）+ 密码 → `/admin/dashboard`；
   - 教师账号 + 本人姓名 + 密码 → `/teacher/dashboard`，无教务菜单；
   - 学生账号 + 本人姓名 + 密码 → `/student/dashboard`。
2. 教务 → 学生管理：新增时学院→专业→班级级联可用；保存后列表无需 F5 即出现。
3. 勾选 2 条记录 → 批量删除 → 确认 → 成功提示；对有选课的学生单独批量删除应提示失败且数据保留。
4. 批量导入：四类模板可下载；学生模板含「手机」列。
5. DevTools：Console 无红色异常；Network 中登录与业务接口无 5xx。

### 6.7 健康检查清单

```bash
systemctl is-active uams-backend nginx mysql
ss -ltnp | grep -E ':80 |:8000 '
curl -s http://127.0.0.1:8000/health
curl -s -o /dev/null -w 'home=%{http_code}\n' http://127.0.0.1/
mysql -h 127.0.0.1 -u uams_app -p -N -e \
  "SELECT version_num FROM uams.alembic_version; SELECT 1;"
journalctl -u uams-backend -n 100 --no-pager
sudo tail -n 50 /var/log/nginx/error.log
```

期望：三个服务 active；80/8000 监听；`env=production` 且 `database=up`；首页 200；Alembic `e4f5a6b7c8d9`。

---

## 7. 回滚方案

### 7.1 触发条件

- 登录接口 5xx/422 比例异常；
- 前端白屏、资源 404；
- 批量删除/导入出现非预期数据变更；
- 健康检查持续失败超过 5 分钟。

### 7.2 联合回滚顺序

> **先回滚后端，再回滚前端**。新前端可以兼容旧后端；旧前端不能兼容新后端。

```bash
# 1) 后端回到旧基线（工作区必须干净；不要使用 git reset --hard）
cd /home/nglsyuyu/Software_Develop/Software_Develop
git switch --detach 5b5c896
sudo systemctl restart uams-backend
curl -s http://127.0.0.1:8000/health

# 2) 前端指回旧 release（原子切换）
sudo ln -sfn /var/www/uams/releases/20261029_031352 /var/www/uams/current
sudo systemctl reload nginx
curl -s --noproxy '*' http://127.0.0.1/ | grep -q '<div id="app"></div>' && echo HOME_OK
```

说明：

- `deploy-frontend.sh` 每次发布都会把旧 `current` 写入 `/var/www/uams/previous`；也可用 `readlink -f /var/www/uams/previous` 确认后切换；
- 回滚后如需继续开发：`cd repo && git switch main`（此时 main 仍是新代码，勿在 detach 状态下提交）；
- **禁止**只回滚前端而保留新后端：旧前端无法通过三字段校验。

### 7.3 数据库回滚

本次**没有迁移**，正常回滚不需要动数据库。仅在确认数据被破坏且获得明确授权时：

```bash
# 最后手段：会覆盖当前数据，必须先停服务并再次备份现状
sudo systemctl stop uams-backend
mysql -h 127.0.0.1 -u uams_app -p -e "DROP DATABASE uams; CREATE DATABASE uams CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"
zcat ~/uams-backups/<STAMP>/uams.sql.gz | mysql -h 127.0.0.1 -u uams_app -p uams
sudo systemctl start uams-backend
```

### 7.4 回滚后验证

- `/health` 为 `env=production database=up`；
- 首页 200 且为新/旧 release 的预期 hash；
- 旧前端（或旧 API 客户端）可以登录；
- `operation_logs` 中回滚窗口内的写操作可追溯。

---

## 8. 本次未执行的生产动作

- 未启动/重启 `uams-backend`；
- 未发布前端、未切换 `/var/www/uams/current`、未 reload Nginx；
- 未执行任何 Alembic 迁移；
- 未修改正式库 `uams` 的任何数据；
- 未修改任何正式账号密码；
- 未关机。

以上动作需获得明确生产授权后，按第 6、7 节执行。
