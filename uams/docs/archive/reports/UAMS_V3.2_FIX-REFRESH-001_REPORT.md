# UAMS V3.2 FIX-REFRESH-001 前端写入后数据同步修复报告

> 日期：2026-10-29  
> 分支：`main`  
> 范围：前端当前用户写入后的列表/状态/统计同步与查询竞态  
> 测试库：`uams_test`（所有写入测试均在此）  
> 正式库：`uams`（未执行写入测试）  
> 正式环境：Nginx 80 + `uams-backend.service`（运行中）  
> Alembic head：`e4f5a6b7c8d9`

---

## 1. 问题描述

新增、编辑、删除、保存、提交、审核等写入操作在服务器成功后，部分页面仍显示旧数据，需要 F5、重新登录或切换路由才能看到最新内容。

---

## 2. 复现步骤（修复前代码审计 + 隔离环境）

1. 在 `uams_test` 环境登录管理员/教师/学生；
2. 在列表页新增/修改/删除记录；
3. 观察弹窗关闭后表格行、总数、状态标签或关联下拉是否立即变化。

审计与复现中发现的主要失败模式：

- 新建记录落在第 2 页时，页面固定 reload 第 1 页，用户看不到新记录；
- 删除当前页最后一条后停留在空页；
- 快速切换学期/教学班/筛选时，旧 GET 请求晚返回并覆盖新结果；
- 学期激活/编辑后，全局 `useSemester` 仍保留旧 ACTIVE 学期；
- 学院/课程/教学任务变更后，关联下拉或“实际开班数”未同步；
- GET 列表未声明不缓存，存在浏览器缓存旧响应的可能；
- 写入按钮缺少防重复提交。

---

## 3. 具体根因

| 根因 | 位置 | 影响 |
|---|---|---|
| 公共列表无查询序号 | `composables/useCrudTable.ts` | 旧请求覆盖新查询 |
| 新建后固定回第 1 页 | 同上 | 新记录在后续页不可见 |
| 删除最后一条不回退页 | 同上 | 当前页空列表 |
| 无 `afterMutation` 关联刷新 | 同上 | 学院/课程等关联数据陈旧 |
| 无重复提交保护 | 同上 | 连续点击可能重复创建 |
| 学期 ACTIVE 只在本页更新 | `views/admin/Terms.vue` | 其他页面使用旧学期 |
| 页面级加载无竞态保护 | 选课、排课、成绩、考试、资料、评价、调停课、导入 | 快速切换时旧数据覆盖 |
| 业务 GET 未声明 no-cache | `api/request.ts` | 潜在浏览器缓存旧列表 |
| 关联数据未刷新 | Organization / Courses / Teaching | 下拉/统计与真实数据不一致 |

> 审计同时确认：多数页面原本已在写入后调用 `load`/`loadSheet`/`loadRows`；问题主要出在公共机制的边界、竞态与跨数据刷新，而不是“所有页面都缺少 reload”。

---

## 4. 受影响页面清单

| 页面 | 写入操作 | 审计结果 | 处理 |
|---|---|---|---|
| `admin/Students.vue` | 新增/编辑/删除 | 使用公共 CRUD，已 reload；缺少分页/竞态 | 公共修复 |
| `admin/Teachers.vue` | 新增/编辑/删除 | 同上 | 公共修复 |
| `admin/Organization.vue` | 学院/专业/班级/教室 CRUD | 本表 reload；关联下拉不刷新 | `afterMutation: loadOptions` |
| `admin/Courses.vue` | 课程 CRUD、先修课程 | 本表 reload；课程候选不刷新 | `afterMutation: loadCourses` |
| `admin/Teaching.vue` | 任务/教学班/排课 | 已 reload；任务开班数不同步、查询竞态 | 新增 `loadTasks`、竞态守卫 |
| `admin/Terms.vue` | 学期 CRUD/激活/结束 | 本表 reload；全局 ACTIVE 不同步 | `syncActiveSemester` + `afterMutation` |
| `admin/Curriculum.vue` | 方案 CRUD、方案课程 | 本表/详情已 reload | 保持 |
| `admin/SelectionManage.vue` | 窗口 CRUD、开放选课 | 已 reload；查询竞态/空页 | 守卫 + 分页回退 |
| `admin/GradeApproval.vue` | 审核/驳回/更正/撤销 | 已 reload；查询竞态 | 守卫 |
| `admin/Exams.vue` | 考试/考场/发布/排座 | 已 reload；查询竞态/空页 | 守卫 + 分页回退 |
| `admin/AnnouncementManage.vue` | 新增/编辑/发布/撤回/删除 | 公共 CRUD + reload | 公共修复 |
| `admin/Evaluations.vue` | 评价任务保存 | 已 reload；查询竞态 | 守卫 |
| `admin/Adjustments.vue` | 调停课审批 | 已 reload；查询竞态 | 守卫 |
| `admin/ImportCenter.vue` | 学生/教师/课程/成绩导入 | 显示服务端结果；班级查询竞态 | 守卫 |
| `admin/AdminManage.vue` | 创建/授权/撤销/启停/改密 | 列表已 reload；改密无列表字段 | 保持 |
| `teacher/GradeEntry.vue` | 保存草稿/提交/初始化/导入/删草稿 | 保存回写服务端行+统计；查询竞态 | 并发加载 + 守卫 |
| `teacher/Materials.vue` | 上传/删除 | 已 reload；查询竞态 | 守卫 |
| `teacher/Adjustments.vue` | 提交申请 | 已 reload；查询竞态 | 守卫 |
| `student/Selection.vue` | 选课/退课 | 已 load 全部状态；查询竞态 | 守卫 |
| `student/Evaluation.vue` | 提交评价 | 已 reload 待评价；查询竞态 | 守卫 |
| 其他只读页面（Profile/MyCourses/Schedule/Exams/Curriculum/Materials 等） | 无写入 | 不适用 | 未改动 |

---

## 5. 公共机制修复

`frontend/src/composables/useCrudTable.ts`：

1. **查询序号 `loadSeq`**：只有最新请求可写回 `rows/total/loading`；
2. **新建跨页可见**：创建成功后回第一页；若新记录不在当前页，定位到包含它的末页；
3. **删除空页回退**：当前页删空且存在上一页时自动回退并重查；
4. **防重复提交**：`saving` 期间直接拒绝再次保存；
5. **`afterMutation` 回调**：写入/删除成功后刷新关联下拉、统计或其它 Tab 数据；
6. 失败时不关闭弹窗、不改变列表；成功后才关闭并重查。

`frontend/src/utils/latest.ts`：新增 `createLatestGuard()`，用于页面级查询竞态控制。

`frontend/src/api/request.ts`：GET 请求附带 `Cache-Control: no-cache`、`Pragma: no-cache`，业务数据不使用浏览器缓存。

---

## 6. 各页面修复内容

- **Organization**：四个 CRUD 均接入 `afterMutation: loadOptions`，学院/专业/教师下拉同步；
- **Courses**：课程变更后刷新 `allCourses`（先修课程候选）；
- **Teaching**：教学班新增/删除后同时刷新教学任务列表（实际开班数）；
- **Terms**：新增/编辑/激活/结束后调用 `termApi.active()`，更新页面 `activeTerm` 与全局 `setActiveSemester`；
- **SelectionManage / Teaching / GradeEntry / GradeApproval / Exams / Materials / Evaluations / Adjustments / Teacher Adjustments / Student Evaluation / ImportCenter**：接入 `createLatestGuard`，旧请求不覆盖新状态；
- **GradeEntry**：成绩单与统计改为并行查询并统一守卫，保存后仍以服务端返回行与统计为准；
- **Students / Teachers / Announcements / Curriculum / AdminManage**：确认原有 reload 路径正确，公共机制统一增强。

---

## 7. 异步请求竞态处理

```ts
const guard = createLatestGuard()
async function load() {
  const seq = guard.next()
  const data = await api.list()
  if (!guard.isCurrent(seq)) return
  rows.value = data
}
```

- 旧请求结果直接丢弃，不写回响应式状态；
- loading 只由最新请求结束；
- 公共列表、选课、排课、成绩、考试、资料、评价、调停课、导入等关键查询已接入；
- 未引入 WebSocket/SSE 或重量级状态框架。

---

## 8. 新增测试

### 8.1 前端单元测试

- 文件：`frontend/tests/latest.test.mjs`
- 命令：`cd frontend && npm run test:unit`
- 覆盖：`createLatestGuard` 的最新请求判定、旧响应拒绝
- 结果：**2 通过**

### 8.2 浏览器 E2E（Chrome/CDP，仅 uams_test）

| 脚本 | 覆盖 |
|---|---|
| `tests/e2e/test_student_crud.py` | REF-001/002/003/014 |
| `tests/e2e/test_multi_page_refresh.py` | REF-004/005/006/009/010/011/012 |
| `tests/e2e/test_materials_refresh.py` | REF-013 |
| `tests/e2e/test_grade_entry_refresh.py` | REF-007/008 |

环境：

- 后端 8010：`env_guard.py exec testing` → `uams_test`
- 前端 5180：Vite
- 另用临时 Nginx 5181 加载 **生产构建产物**，同一组 E2E 再次执行
- 脚本启动时检查 `/health.env == testing`，否则拒绝；临时数据自动清理

---

## 9. 自动化测试结果

| 检查 | 结果 |
|---|---|
| 后端 `pytest -q` | 44 通过，0 失败 |
| 前端 `npm run test:unit` | 2 通过，0 失败 |
| 前端 `npm run build` | 通过（仍有 >500kB 警告，见 §11） |
| `bash -n start.sh deploy/*.sh` | 通过 |
| E2E（开发栈） | 4 组全部通过 |
| E2E（生产构建 + 临时 Nginx） | 4 组全部通过 |
| 测试库残留 | REF 学生/课程/班级/学期/公告/资料为 0；grade1 恢复 APPROVED；选课恢复 |
| 正式库写入 | 未执行 |

---

## 10. 浏览器交互验收结果

| 编号 | 场景 | 结果 |
|---|---|---|
| REF-001 | 新增学生后当前列表出现 | 通过（含跨页定位） |
| REF-002 | 修改学生后字段显示 | 通过 |
| REF-003 | 删除学生后列表/总数 | 通过 |
| REF-004 | 新增课程后列表 | 通过 |
| REF-005 | 修改教学班容量后行显示 | 通过 |
| REF-006 | 学期编辑行刷新；已有 ACTIVE 时激活被拒绝且不改变当前学期 | 通过（**成功激活另一学期未验证**，因测试库已有 ACTIVE 且不允许并存） |
| REF-007 | 教师保存成绩后最新分数 | 通过 |
| REF-008 | 教师提交后状态/按钮 | 通过 |
| REF-009 | 管理员审核后状态 | 通过 |
| REF-010 | 学生选课后已选列表 | 通过 |
| REF-011 | 学生退课后列表 | 通过 |
| REF-012 | 公告发布后状态 | 通过 |
| REF-013 | 教学资料上传/删除列表 | 通过 |
| REF-014 | 失败写入保留原数据 | 通过（重复学号） |
| REF-015 | 分页/搜索状态 | 部分验证：新增跨页可见、删除回退；复杂筛选/翻页组合未覆盖 |
| REF-016 | 并发查询竞态 | 守卫单元测试通过；浏览器级慢请求竞态未做 |

---

## 11. 生产构建结果

- `npm run build` 成功；
- 输出 `frontend/dist`，最新入口 `index-w-iuU7Xf.js`；
- 页面按路由懒加载；主包约 618kB，仍有 Vite >500kB 提示（未通过提高阈值或破坏性拆包掩盖）；
- 构建产物已用临时 Nginx + 测试后端执行全部 E2E，无运行时 TypeError；
- npm `globalignorefile` 警告来自系统级 `/etc/npmignore`，未修改用户全局配置。

---

## 12. 正式部署结果或待授权状态

| 项目 | 状态 |
|---|---|
| Nginx | active，80 |
| systemd | `uams-backend.service` active，127.0.0.1:8000 |
| 正式库 | `uams` @ `e4f5a6b7c8d9` |
| 当前 live release | `20261029_014756`（`index-Bcblv2za.js`） |
| 最新构建 | `index-w-iuU7Xf.js`（含本次同步修复） |
| 本次发布 | **未执行**：`/var/www/uams` 属 root，当前无免密 sudo，且任务要求明确发布授权 |

待授权命令：

```bash
cd /home/nglsyuyu/Software_Develop/Software_Develop/uams
bash deploy/deploy-frontend.sh
```

发布后需验证：首页 200、systemd active、登录/三角色页面、上述写入后无需 F5 的交互。

---

## 13. 文档更新清单

- `docs/UAMS_系统技术文档.md`：新增 §6.5 写入后同步、竞态、跨数据刷新与缓存策略；
- `docs/TESTING.md`：新增 §4.3 前端写入同步回归（单元 + E2E + 结果 + 未覆盖）；
- `docs/DEVELOPMENT.md`：新增 §2.4 前端写入后数据同步规范；
- `docs/ARCHITECTURE.md`：更新状态管理与公共 CRUD/竞态职责；
- 用户手册：仅内部刷新机制变化，无用户可见流程改变，未重写；
- PRD / 白皮书：需求范围与产品能力未变化，未修改；
- 本报告：`docs/archive/reports/UAMS_V3.2_FIX-REFRESH-001_REPORT.md`。

---

## 14. 尚未解决的问题

1. **REF-006 成功激活另一学期**：测试库已有 ACTIVE 学期，后端禁止并存；已验证编辑刷新与“激活被拒绝不污染状态”，未验证成功切换 ACTIVE。
2. **REF-015 复杂分页/筛选组合**：已覆盖新增跨页可见与删除回退，未穷举所有筛选组合。
3. **REF-016 浏览器级慢请求竞态**：守卫逻辑单测通过，未用网络延迟注入做浏览器级验证。
4. **多浏览器矩阵**：仅 Chrome/CDP。
5. **正式环境最新构建**：尚未发布；当前 live 为上一构建。
6. **多用户实时同步**：不在本次范围，未引入 WebSocket/SSE。

---

## 15. Git 提交记录

| 项目 | 内容 |
|---|---|
| 分支 | `main` |
| 代码/测试/文档 | 本次提交（见 `main` 最新记录） |
| 未提交 | `.env`、密码、JWT、日志、备份、上传资料 |
| 推送 | 已推送 `origin/main` |

---

## 结论

- 公共 CRUD、分页边界、重复提交、跨数据联动、学期全局状态、页面级查询竞态与 GET 缓存问题已修复；
- 13 个核心写入场景通过浏览器 E2E（开发栈 + 生产构建），单元测试覆盖竞态守卫；
- 正式系统保持运行，未修改正式库；最新前端构建需授权后发布；
- 成功激活另一学期、复杂筛选和浏览器级竞态仍列为未验证。

> 报告结束。
> 不包含数据库密码、JWT、Token 或敏感个人数据。
