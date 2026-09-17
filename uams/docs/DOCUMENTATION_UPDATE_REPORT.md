# TASK-DOC-001 文档整理报告

**任务**：项目结构与文档整理
**执行时间**：2026-09-17
**范围**：仅文档与目录说明，**未修改任何业务代码**

---

## 1. 本次新增文件

### 1.1 文档体系（`uams/docs/`）

| 文件 | 说明 |
|---|---|
| `README.md` | 文档入口，说明各文档用途与阅读顺序 |
| `PRD.md` | 由 `PRD.docx` 转写并结代码实现状态标注（20 章） |
| `ARCHITECTURE.md` | 系统架构、分层职责、模块划分、关键业务机制 |
| `API.md` | 70 个路径 / 108 个操作的完整接口清单 + 38 项权限码表 |
| `DEVELOPMENT.md` | 环境、配置、Git 流程、编码规范、Claude Code 约定 |
| `ROADMAP.md` | V0.1 → V1.0 版本规划，含审计问题归档 |
| `TESTING.md` | 测试规范、现状、待补清单 |
| `DEPLOYMENT.md` | 当前部署方式与 LAN 部署规划 |
| `DOCUMENTATION_UPDATE_REPORT.md` | 本报告 |

### 1.2 目录说明（README）

| 文件 | 说明 |
|---|---|
| `README.md`（仓库根） | 重写：项目简介、技术栈、目录树、快速开始、文档导航 |
| `uams/backend/README.md` | 后端职责、目录结构、依赖关系、开发注意事项 |
| `uams/backend/app/api/README.md` | API 层：路由清单、权限声明规范 |
| `uams/backend/app/services/README.md` | Service 层：业务规则、事务边界、并发注意 |
| `uams/backend/app/models/README.md` | 模型层：表清单、模型注册注意事项 |
| `uams/backend/app/schemas/README.md` | Schema 层：命名约定、校验规范 |
| `uams/backend/app/core/README.md` | 核心层：配置、安全、异常 |
| `uams/backend/alembic/README.md` | 迁移：命令、已有迁移、禁止事项（替换原 Alembic 生成的占位 README） |
| `uams/backend/tests/README.md` | 测试：现有用例、编写规范、待补清单 |
| `uams/backend/scripts/README.md` | 种子脚本：幂等要求、运行方式 |
| `uams/scripts/README.md` | 环境脚本：sudo 要求、用途说明 |
| `uams/frontend/README.md` | 前端：目录结构、页面分布、开发注意事项（替换 Vite 模板残留） |

**新增合计：9 份文档 + 12 份目录说明。**

---

## 2. 修改文件

| 文件 | 修改内容 |
|---|---|
| `README.md`（仓库根） | 由 2 行占位内容重写为完整项目说明 |
| `uams/frontend/README.md` | 由 Vite 模板自带内容重写为项目说明 |
| `uams/backend/alembic/README.md` | 由 Alembic 生成的单行占位内容重写为项目说明 |
| `uams/docs/DATABASE.md` | **补充**：数据库版本与连接信息、ORM 模型与迁移文件位置、模型文件划分表、已有迁移列表、成绩模型 V0.2 标记 |

> `DATABASE.md` 原有 15 章字段级设计**完整保留，未做任何重新设计**。

---

## 3. 删除文件

**无。**

未删除任何文件，包括疑似冗余项。所有可疑文件均在下方第 5 节列出，等待确认。

---

## 4. 项目结构变化

**未移动业务代码文件。**

- 未移动、未重命名任何代码文件
- 未改变任何 Python / TypeScript import
- 未改变模块路径
- 未修改 `vite.config.ts` 的别名或代理配置
- 目录结构保持原样，仅新增说明性 README

新增的 README 文件均不影响构建与运行：

- `backend/README.md`、`backend/alembic/README.md`、`backend/tests/README.md`、`backend/scripts/README.md`、`backend/app/*/README.md` —— Markdown，不参与 Python 导入
- `frontend/README.md` —— Markdown，不参与前端构建
- `uams/scripts/README.md`、`docs/*.md` —— 纯文档

---

## 5. 疑似冗余文件（建议，未删除）

### 5.1 建议后续删除

| 文件 | 原因 |
|---|---|
| `frontend/src/assets/hero.png` | Vite 模板自带，全项目 0 处引用 |
| `frontend/src/assets/vite.svg` | 同上，0 处引用 |
| `frontend/src/assets/vue.svg` | 同上，0 处引用 |

> 建议在 V0.2 中删除。属清理项，不影响功能。

### 5.2 不确定用途（已保留）

| 文件 | 原因 |
|---|---|
| `uams/database/`（空目录） | 无法确认是为后续迁移脚本预留，还是历史遗留。PRD §5 与 CLAUDE.md 未明确要求此目录。**保留**，待确认 |
| `backend/app/utils/`（仅 `__init__.py`） | 空模块，无法确认是否计划放置工具函数。**保留** |
| `backend/app/repositories/user.py` | 仅有 `UserRepository`，其余模块未使用 Repository 层（直接走 Service + ORM）。功能正常，属设计一致性问题，**保留** |
| `backend/.env.example` | 存在且内容正确（占位值），**保留** |
| `frontend/auto-imports.d.ts`、`frontend/components.d.ts` | 由 `unplugin-*` 插件自动生成，当前未被 `.gitignore` 忽略。提交与忽略均可，**保留现状** |

### 5.3 已确认的正常文件（未列入删除建议）

- `backend/.pytest_cache/` —— 已被 `.gitignore` 忽略
- `frontend/dist/` —— 已被 `.gitignore` 忽略
- `backend/scripts/__init__.py` —— 使 `scripts` 成为包，`python -m` 运行需要

---

## 6. 文档缺口

### 6.1 本次已补齐

CLAUDE.md §34 要求的文档中，本次补齐 7 份：`ARCHITECTURE.md`、`API.md`、`DEVELOPMENT.md`、`ROADMAP.md`、`TESTING.md`、`DEPLOYMENT.md`、`PRD.md`。

### 6.2 仍然存在

| 缺口 | 说明 |
|---|---|
| `PRD.docx` 与 `PRD.md` 并存 | 两份内容同源。建议保留 `.docx` 作为原始存档，以 `PRD.md` 为维护版本；或后续归档 `.docx` |
| 部分 Schema 未拆分 | `grade` / `exam` / `selection` / `misc` 的 Pydantic 模型直接定义在路由文件中，未归入 `app/schemas/`。属代码组织问题，**本任务不改代码** |
| `docs/DATABASE.md` 未含 ER 图 | 当前为文本版 ER 关系（§2），无图形化 ER 图 |
| 无 CHANGELOG | 版本变更记录缺失 |

---

## 7. 后续建议

> 以下仅为建议，**未执行**。

1. **P0-1（安全）**：重建 `backend/.env`，更换随机 `JWT_SECRET`，移除 `app/core/config.py` 中的默认凭据
2. **P1-2**：补核心业务自动化测试 —— 优先选课并发、成绩状态机、排课冲突、总评计算
3. **P1-3**：实现操作日志写入（登录 + 关键写操作）
4. **P1-4**：实现 Excel 导入导出
5. **V0.2 业务**：成绩模型重新设计（实践/理论拆分、GPA、排名）—— 需先更新 `DATABASE.md` §9，再写迁移
6. **清理**：删除 `frontend/src/assets/` 中 3 个未被引用的模板文件
7. **确认**：`uams/database/` 空目录的用途；`app/utils/` 是否需要保留
8. **一致性**：评估是否将 `grade`/`exam`/`selection`/`misc` 的 Schema 拆分到 `app/schemas/`

---

## 8. 验证记录

### 8.1 测试与构建

| 项 | 命令 | 结果 |
|---|---|---|
| 后端测试 | `.venv/bin/python -m pytest tests/ -q` | ✅ **21 passed**（6.70s） |
| 前端类型检查 | `node_modules/.bin/vue-tsc --noEmit` | ✅ 零错误 |
| 前端生产构建 | `npm run build` | ✅ 1841 modules，built in 818ms |

### 8.2 零代码改动确认

```bash
git status --porcelain | grep -E "\.(py|ts|vue|json|ini|sh|mako)$"
# → 无输出
```

| 检查项 | 结果 |
|---|---|
| `uams/backend/app/**/*.py` | ✅ 无改动 |
| `uams/backend/alembic/versions/` | ✅ 无改动 |
| `uams/backend/.env` | ✅ 无改动 |
| `uams/backend/requirements.txt` | ✅ 无改动 |
| `uams/frontend/src/**` | ✅ 无改动 |
| `uams/frontend/package.json` | ✅ 无改动 |
| `uams/CLAUDE.md` | ✅ 无改动 |
| `uams/scripts/*.sh` | ✅ 无改动 |

### 8.3 git diff --stat

```
 README.md                   | 128 +++++++++++++++++++++++++++++++++++-
 uams/backend/alembic/README |   1 -
 uams/docs/DATABASE.md       |  57 ++++++++++++++++++-
 uams/frontend/README.md     |  70 ++++++++++++++++++++++--
 4 files changed, 249 insertions(+), 7 deletions(-)
```

**关于 `alembic/README` 的删除**：该文件是 Alembic 初始化时生成的无扩展名占位文件（内容仅一行 `Generic single-database configuration.`）。本次将其重写为 `README.md`，因此在 git 中显示为「删除 `README` + 新增 `README.md`」。**这不是误删，且不影响 Alembic 运行**（Alembic 不读取该文件）。

### 8.4 文档事实核验

所有文档中的数字均与代码实际核对一致：

| 指标 | 实际值 | 文档记载 |
|---|---|---|
| API 路径数 | 70 | ✅ 一致 |
| API 操作数 | 108 | ✅ 一致 |
| 路由模块数 | 10（+ `__init__.py`） | ✅ 一致 |
| 模型文件数 | 10 | ✅ 一致 |
| 前端页面数 | 28 | ✅ 一致 |
| 权限项数 | 38 | ✅ 一致 |
| 迁移文件数 | 2 | ✅ 一致 |
| 后端测试用例数 | 21（17 + 4） | ✅ 一致 |
| 数据库表数 | 28 + `alembic_version` | ✅ 一致 |

**引用路径核验**：文档中引用的 32 个文件路径全部存在。
**内部链接核验**：`docs/` 下所有 Markdown 相对链接全部有效。
