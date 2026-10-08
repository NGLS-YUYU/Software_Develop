# FIX-007 实施报告：部署优化 + 排课前端联调收尾

> 本文是**实施报告**；`FIX-007.md`（若存在）为原始工单，未改动。

状态：**COMPLETE**（局域网验收的「另一台物理设备」一项受限，见 §11/§12）

---

## 1. 现状审计（§三，只读，改动前）

### 排课

| 问题 | 结论 |
|---|---|
| 1. 后端排课 API | **三组并存**：① `/teaching-schedules`（TASK-013 平铺：GET 5 过滤 / POST / GET `/{id}` / PUT / DELETE / `mine` / `my`）② `/teaching-classes/{id}/schedules`（旧嵌套：GET/POST/PUT/DELETE）③ `/schedules/mine`、`/schedules/students/{id}`（课表视图，带 `semester`+`week`） |
| 2. TASK-013 新增 | 整组 `/teaching-schedules`（含三类冲突检测、平铺过滤、教师 `/mine`、学生 `/my`） |
| 3. 前端实际调用 | 教务页 → **旧嵌套** `teachingApi.schedules/addSchedule/removeSchedule`；教师/学生课表 → `/schedules/mine` |
| 4. 仍用旧嵌套的页面 | `admin/Teaching.vue`（排课管理） |
| 5. 支持新增 | 有（嵌套 POST），**但无修改入口** |
| 6. 支持修改 | **前端无入口**（后端嵌套 PUT 存在） |
| 7. 支持删除 | 有（嵌套 DELETE，无二次确认） |
| 8. 教师课表 API | `/schedules/mine`（**不是** TASK-013 的 `/mine`） |
| 9. 学生课表 API | `/schedules/mine`（同上） |
| 10. 冲突检测归属 | **后端**（`ConflictChecker`，数据库层判定）；前端仅展示 409 错误 |
| 11. 对象级权限 | 已有（`/mine`、`/my` 身份取自 token；`/teaching-schedules` 列表要求 `ACADEMIC_ADMIN`） |
| 12. 前端硬编码排课数据 | **无**（教室/教师/教学班下拉均来自 API） |

### 部署

| 问题 | 结论 |
|---|---|
| 1. 后端启动 | `uvicorn app.main:app --host 127.0.0.1 --port 8000`（**仅回环**） |
| 2. 前端启动 | `npm run dev`（vite） |
| 3. Vite `server.host` | **已是 `0.0.0.0`** |
| 4. API proxy | `/api` → `http://127.0.0.1:8000`（**服务端代理**，浏览器只见同源 `/api`） |
| 5. 生产 build 托管 | 无方案（`preview` 未配置 host/proxy） |
| 6. 启动脚本 | **不存在** `start.sh` / `deploy.sh`（仅有 `scripts/setup_mysql.sh`） |
| 7. `.env` 使用情况 | **仓库内没有 `.env`**，全部走 `config.py` 内置默认值 |
| 8. 默认口令 / 密钥 | ⚠️ **存在**：`config.py` 内置 `uams_app:888888` 与 `JWT_SECRET="CHANGE_ME_IN_ENV"`（详见 §12） |
| 9. CORS | 有，默认仅 `localhost:5173` / `127.0.0.1:5173` |
| 10. LAN 所需端口 | 前端 5173（prod 4173）、后端 8000；MySQL 3306 **不暴露** |

---

## 2. 本次修改

| 文件 | 内容 |
|---|---|
| `backend/app/services/teaching.py` | `mine_for_teacher` / `mine_for_student` 新增**可选** `semester`、`week` 过滤；新增模块级 `_in_week()`（与旧课表接口同一判定） |
| `backend/app/api/v1/teaching_schedule.py` | `/teaching-schedules/mine`、`/my` 新增可选查询参数 `semester`（1–30 之外的 `week` 由 Schema 拒绝） |
| `frontend/src/api/index.ts` | `scheduleApi` 重写：教务 `list/get/create/update/remove` 走平铺接口，`mine`/`my` 指向 TASK-013 |
| `frontend/src/types/index.ts` | `Schedule` 补齐 `ScheduleOut` 字段（教学班/课程/教师/学期/楼栋） |
| `frontend/src/components/ScheduleGrid.vue` | 数据源类型 `ScheduleItem` → `Schedule`（网格自身已计算星期名，无需 `day_name`） |
| `frontend/src/views/admin/Teaching.vue` | 排课弹窗改用平铺接口；**新增「编辑」入口**（PUT）、删除二次确认、节次/周次前端预校验 |
| `frontend/src/views/teacher/Schedule.vue`、`student/Schedule.vue` | 课表改用 `/teaching-schedules/mine` / `/my` |
| `frontend/src/views/teacher/Dashboard.vue`、`student/Dashboard.vue` | 同上；并把「今日课程」时间线的 `:key` 由旧类型字段 `schedule_id` 修正为 `id`（`vue-tsc -b` 在构建时发现，`vue-tsc --noEmit` 未报出） |
| `frontend/vite.config.ts` | 新增 `preview` 配置（`host: 0.0.0.0` + 同源代理），抽出 `apiProxy` 常量 |
| `uams/start.sh` | **新增**统一启动脚本（环境检查 / 数据库检查 / 启停 / 健康检查 / 打印 LAN 地址） |
| `backend/.env.example` | 补 LAN 部署说明与密钥生成方法 |
| `.gitignore` | 新增 `.run/`（脚本 PID 目录） |
| `tests/test_teaching_schedule.py` | **新增 4 例**：教师/学生课表的 `semester` 与 `week` 过滤、越界周次 422 |
| `backend/scripts/e2e_fix007_schedule.py` | **新增**排课真实 HTTP + MySQL 验收（37 项断言） |
| `backend/scripts/e2e_fix007_lan.py` | **新增**局域网真实浏览器验收 + 网络请求审计（25 项断言） |
| `docs/DEPLOYMENT.md` | 重写：拓扑 / 环境要求 / 环境变量 / 启动 / LAN 访问 / 停启 / 日志 / 健康检查 / 常见失败原因 / 安全边界 |
| `docs/API.md` | 标注前端数据源与新增的可选过滤参数 |

**未修改**：`/schedules/*`（保留，未删除）、`/teaching-classes/{id}/schedules`（保留）、学期字符串与 `academic_terms` 并存的现状（§三十二 明确不重构）。

---

## 3. 排课：前端接入 TASK-013

- **教务排课页**：`GET /teaching-schedules?teaching_class_id=` 列表、`POST` 新增、**`PUT /{id}` 修改（本次新增的 UI 能力）**、`DELETE /{id}` 删除（含二次确认）。
- **教师课表**：`GET /teaching-schedules/mine?semester=&week=`。
- **学生课表**：`GET /teaching-schedules/my?semester=&week=`。
- 周次过滤（含单双周）在**服务端**完成，前端不再实现该逻辑。

## 4. 冲突检测（§八/§九）

三类冲突全部由后端判定，前端只展示结果；实测：

| 场景 | 结果 |
|---|---|
| 同一教师同一时段两个教学班 | **409** `TEACHING_SCHEDULE_TEACHER_CONFLICT`，MySQL 无新记录 |
| 同一教室同一时段两个教学班 | **409** `TEACHING_SCHEDULE_CLASSROOM_CONFLICT`，MySQL 无新记录 |
| 同一教学班同一时段两条安排 | **409** `TEACHING_SCHEDULE_CLASS_CONFLICT`，MySQL 无多余记录 |
| **修改**后与他人冲突 | **409**，MySQL 保留原值（未落库） |

## 5. 教师课表 / 学生课表

- 教师：`/mine` 只返回本人教学班的排课；教师乙查询为空（实测）。
- 学生：`/my` 只返回本人**已选**教学班的排课；为未选教学班排课后，学生课表仍不含该条（实测）。
- 课表含课程名、教师、教室、星期、节次、周次（实测断言）。
- 修改排课后教师课表与学生课表**同步反映**新教室/新时间（实测）。

## 6. 部署：LAN

- 后端监听 `0.0.0.0:8000`，前端 `0.0.0.0:5173`（`ss -ltn` 实测）。
- 浏览器只请求 `http://<LAN_IP>:5173/api/v1/...`，由 Vite 服务端代理到 `127.0.0.1:8000` → **不产生跨域、不出现 127.0.0.1**（实测，见 §8）。
- `./start.sh`：检查 venv/node_modules → 检查 MySQL 连通 → 启动后端并轮询 `/health` → 启动前端 → 打印本机与 LAN 地址；支持 `prod`/`stop`/`restart`/`status`。
- **不在脚本中写死任何口令**；检测不到 `.env` 时明确告警。
- 健康检查复用既有 `GET /health`（返回应用与数据库状态），未新增接口。

---

## 7. 自动化测试（§二十七）

| 项 | 结果 |
|---|---|
| `pytest` 全量 | **409 passed**（原 405 + 新增 4） |
| `test_teaching_schedule.py` | **42 passed**（原 38 + 4） |
| `vue-tsc --noEmit` | **0 错误** |
| `npm run build` | **0 错误** |
| `bash -n start.sh` | 语法检查通过；`start.sh` 可执行（`chmod +x`） |

新增 4 例：`test_teacher_mine_semester_filter`、`test_teacher_mine_week_filter`（含单双周与跨学期）、`test_student_my_semester_and_week_filter`、`test_mine_week_filter_rejects_out_of_range`。

> 说明：新增断言过程中发现 `httpx` 会把 `params={"x": None}` 序列化为 `x=`（空串），导致 422；
> 这是**测试客户端写法**问题，不是接口缺陷 —— 已改为整键省略，接口行为未变。

## 8. 真实 HTTP/API（§二十五）

`scripts/e2e_fix007_schedule.py`：**37/37 通过**（独立学期 `2099-2099-1`，与演示数据隔离）

| Case | 结果 |
|---|---|
| A 新增成功 | 201；MySQL 新增，学期取自教学班；按教学班过滤可查到 |
| B 修改成功 | 200；MySQL 教室/星期/节次更新；**教师课表与学生课表同步反映** |
| C 冲突 | 教师 / 教室 / 教学班三类均 409 且**无脏数据**；修改造成的冲突同样 409 且未落库 |
| D 权限 | 教师新增/修改 403、学生删除 403、教师访问教务列表 403 |
| 教师 `/mine` | 只看到本人；他人为空；`week` 过滤生效；其它学期为空 |
| 学生 `/my` | 只看到已选教学班；含课程/教室/教师；未选课程排课不可见 |
| 删除 | 204；MySQL 删除；教师课表同步移除 |

## 9. 真实浏览器 + 真实 LAN（§二十二/§二十六）

`scripts/e2e_fix007_lan.py`：**25/25 通过**。从**局域网地址** `http://10.164.245.195:5173`（而非 localhost）驱动 Chrome：

| 项 | 结果 |
|---|---|
| 局域网地址可访问 | 200 |
| 局域网地址下 `/api` 代理可用 | 登录 200 |
| 管理员登录 → 开课排课 → 排课弹窗 | 渲染成功，列出真实排课 1 条（来自平铺接口） |
| 教师课表 | 渲染出 2 个真实课程块（含周次） |
| 学生课表 | 渲染出 3 个真实课程块（含教师与教室） |
| **无 127.0.0.1 / localhost 请求** | ✅（0 条） |
| 所有请求均指向局域网来源 | ✅ |
| 课表确实调用 `/teaching-schedules/mine` / `/my` | ✅ |
| 教务排课确实调用平铺 `/teaching-schedules` | ✅ |
| `/api` 请求无 4xx/5xx、无 CORS 失败、无加载失败 | ✅（共 111 条 API 请求） |

> 非 API 资源噪声：`favicon.ico` 404 ×1（应用未提供图标）、Vite 依赖预构建中止（开发服务器行为），均与局域网/接口无关，已单独列出未计入失败。

---

## 10. 四层证据

| 层级 | 结论 |
|---|---|
| 【代码存在】 | `scheduleApi` 平铺封装、`Schedule` 类型、`ScheduleGrid`、Teaching.vue 编辑入口、教师/学生课表迁移、`start.sh`、`vite preview` 配置、2 个 E2E 脚本、DEPLOYMENT.md |
| 【自动化测试】 | pytest **409 passed**；vue-tsc **0 错误**；build **0 错误** |
| 【真实 HTTP/API】 | 新增 201、修改 200、三类冲突 409（均无脏数据）、教师 `/mine` 正确、学生 `/my` 正确 —— **37/37** |
| 【真实浏览器】 | Chrome 从局域网地址操作 —— **25/25** |
| 【真实 LAN】 | 见 §11（受限说明） |
| 【MySQL】 | 新增/修改/冲突拒绝/删除均已逐条回查；E2E 数据已清理（隔离学期 + `finally` 清理） |
| 【BLOCKED】 | NONE |
| 【Git】 | `fix(FIX-007): 部署与排课前端联调收尾` |
| 【最终状态】 | **COMPLETE**（含 1 项受限说明） |

## 11. 关于「另一台设备」的说明（§二十二/§二十六）

**没有第二台物理设备可用**，因此未做「另一台电脑访问服务器」的实测。替代验证（已全部完成）：

1. 服务确实监听 `0.0.0.0`（`ss -ltn` 实测 5173/8000）；
2. 用**局域网 IP**（非 localhost）访问前端与 `/api` 代理均 200；
3. 用真实 Chrome 打开**局域网地址**完成登录与排课/课表操作 —— 这对浏览器而言已是一个**外部来源**，能捕获「浏览器里写死 127.0.0.1」这一 LAN 部署的经典故障；
4. 抓取浏览器全部请求，确认 **0 条**指向 `127.0.0.1`/`localhost`，无 CORS 失败。

因此该项标记为 **PARTIAL（未在第二台设备上实测）**，而不是「已验证通过」。

## 12. 已知问题

1. **默认口令与占位密钥（§十九 要求先报告）**：`backend/app/core/config.py` 内置了 `DATABASE_URL` 默认串（含 `uams_app:888888`）与 `JWT_SECRET="CHANGE_ME_IN_ENV"`；仓库内无 `.env`，未配置时即使用这些默认值。**未修改代码**（不属于当前部署阻塞项），但已：`start.sh` 明确告警、`.env.example` 与 `DEPLOYMENT.md` 写明必须替换。局域网正式部署前**必须**创建 `.env`。
2. **`favicon.ico` 404**：应用未提供图标，浏览器控制台会出现一条 404（纯外观，与功能无关，未处理以免越界做 UI）。
3. **旧接口保留**：`/schedules/mine`、`/schedules/students/{id}`、`/teaching-classes/{id}/schedules` 未删除（避免破坏既有代码与调用方），但前端已不再使用前两组中的课表接口；`/teaching-classes/{id}/schedules` 仍保留在后端但前端已改用平铺接口。
4. **教师课表与旧接口的一处行为差异**：旧 `/schedules/mine` 对教师额外过滤 `TeachingClass.status == 'ACTIVE'`，TASK-013 的 `/mine` 不做该过滤。已保持 TASK-013 现有行为（未改动其语义）；演示数据中无 `CANCELLED` 教学班，故无可见差异。
5. **`academic_terms` 与 `semester` 字符串并存**：FIX-006 已记录的已知问题，按 §三十二 **未在本 FIX 处理**。
6. **E2E 脚本的 CDP 客户端仍各有一份**（`e2e_fix005/006/007`）：延续既有取舍，未抽公共模块。

## 13. Git

```
fix(FIX-007): 部署与排课前端联调收尾
```

## 14. 最终状态

**COMPLETE** —— 排课链路（教务页面 → 平铺 API → 冲突检测 → MySQL → 教师课表 → 学生课表）与部署链路（`start.sh` → 后端 0.0.0.0 + 前端 0.0.0.0 → 局域网地址 → 真实浏览器登录使用 → API 全部同源成功）均已走通并留证；唯一受限项为「未在第二台物理设备上实测」（§11）。
