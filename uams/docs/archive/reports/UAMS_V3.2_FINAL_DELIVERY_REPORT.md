# UAMS V3.2 最终交付报告

> 日期：2026-10-29
> 分支：`main`
> 正式环境：Nginx 80 + `uams-backend.service` + MySQL `uams`
> Alembic head：`e4f5a6b7c8d9`
> 报告位置：`docs/archive/reports/UAMS_V3.2_FINAL_DELIVERY_REPORT.md`
> Git 提交：见 `main` 最新记录

---

## 1. 实际完成事项

1. 按目标结构重整 `docs/`：正式文档留在根目录，历史资料按 `archive/audits|fixes|reports` 分类。
2. 重写 `docs/PRD.md`：需求编号 FR-001～FR-142、NFR-001～NFR-013，包含验收标准、实现状态与限制。
3. 基于 PRD.md 生成 `docs/PRD.docx`：A4、封面、可更新目录域、页码、统一表格样式；PDF 转换验证 38 页。
4. 新建 `docs/UAMS_系统白皮书.md`：15 章、5 个 Mermaid 图、功能矩阵与规划对照。
5. 新建 `docs/UAMS_系统技术文档.md`：14 章 + 2 个附录，含架构/部署/ER/调用流程、真实版本与故障处理。
6. 更新 API、DATABASE、ARCHITECTURE、DEPLOYMENT、TESTING、用户手册、启动说明、根 README、docs/README。
7. 修复前端发布脚本的代理误判、reload 时序、首次失败误删 `current` 等问题，并隔离验证。
8. 处理前端构建警告：修复全局 CSS 中错误的 `:deep()`；合理拆分 vendor chunk；npm 全局配置警告仅报告。
9. 完成自动化检查与正式环境三角色页面验收；最新构建经临时 Nginx 验证，但 live current 仍需重新发布。
10. 保持 Nginx、systemd、MySQL 与正式库正常运行，未修改业务数据。

---

## 2. 最终文档目录树

```text
docs/
├── README.md
├── PRD.md
├── PRD.docx
├── UAMS_系统白皮书.md
├── UAMS_系统技术文档.md
├── UAMS_教务管理系统用户操作手册.md
├── UAMS_启动与环境切换说明.md
├── ARCHITECTURE.md
├── API.md
├── DATABASE.md
├── DEPLOYMENT.md
├── DEVELOPMENT.md
├── TESTING.md
└── archive/
    ├── README.md
    ├── audits/
    │   ├── V0.2_AUDIT.md
    │   ├── V0.2_TASK001_013_REAUDIT.md
    │   ├── UAMS_V3.1_FUNCTION_GAP_AUDIT.md
    │   └── UAMS_V3.1_PRECHECK_REPORT.md
    ├── fixes/
    │   ├── FIX-001.md ～ FIX-009.md（含 FIX-005/006/007 REPORT）
    │   ├── UAMS_V3.1_FIX-001_REPORT.md ～ FIX-004_REPORT.md
    │   └── UAMS_V3.1_LOGIN_ERROR_FIX_REPORT.md
    └── reports/
        ├── UAMS_V3.1_DEPLOY-001/002_REPORT.md
        ├── UAMS_V3.1_FINAL_FIX_REPORT.md
        ├── UAMS_V3.1_FIX-002_DEPLOYMENT_CHECKLIST.md
        ├── UAMS_V3.1_PROD-001_REPORT.md
        ├── UAMS_V3.1_STARTUP_MANAGER_REPORT.md
        ├── UAMS_V3.2_ENGINEERING_CLEANUP_REPORT.md
        ├── UAMS_V3.2_FINAL_DELIVERY_REPORT.md
        ├── DOCUMENTATION_UPDATE_REPORT.md
        ├── ROADMAP.md
        ├── V2.0开发指南.md
        └── V2.1_FINAL_BASELINE.md
```

---

## 3. 新增文档

| 文件 | 说明 |
|---|---|
| `docs/UAMS_系统白皮书.md` | 正式产品白皮书（15 章、5 图） |
| `docs/UAMS_系统技术文档.md` | 技术交接文档（14 章 + 附录） |
| `docs/archive/reports/UAMS_V3.2_FINAL_DELIVERY_REPORT.md` | 本报告 |

## 4. 更新文档

| 文件 | 更新 |
|---|---|
| `docs/PRD.md` | 全面重写，FR/NFR 编号、验收、状态、限制 |
| `docs/PRD.docx` | 由 PRD.md 重新生成 |
| `docs/API.md` | 119 路径/169 操作；新增接口组与错误码；原“未实现”改为当前状态 |
| `docs/DATABASE.md` | 32 业务表、57 FK、62 CHECK；新增三表与 source 字段 |
| `docs/ARCHITECTURE.md` | 正式/开发架构、38 页面、实际部署状态、技术文档链接 |
| `docs/DEPLOYMENT.md` | 正式部署已完成状态、Nginx/systemd 顺序、验证与回滚 |
| `docs/TESTING.md` | 44 项自动化测试、隔离库、覆盖边界、发布/浏览器验收 |
| `docs/UAMS_教务管理系统用户操作手册.md` | 删除过期限制章节/截图失效链接；更新学期/排名/更正/日志当前状态 |
| `docs/UAMS_启动与环境切换说明.md` | 正式模式与当前部署状态 |
| `docs/README.md` | 新文档导航与归档分类 |
| `README.md` | 新文档入口、目录、当前状态 |
| `docs/archive/README.md` | audits/fixes/reports 分类说明 |
| `deploy/README.md`、`deploy/deploy-frontend.sh`、`deploy/nginx/uams.conf`、`deploy/systemd/uams-backend.service` | 发布脚本修复、实际部署状态、默认站点说明 |

## 5. 归档文档

- 历史审计 → `archive/audits/`（4 份）
- 历史修复 → `archive/fixes/`（14 份）
- 历史报告/阶段基线 → `archive/reports/`（12 份，含本报告）
- 使用 `git mv` 保留历史；未删除 Alembic 迁移或历史 Git 记录。

---

## 6. PRD.md 与 PRD.docx 同步

| 项目 | 结果 |
|---|---|
| 内容来源 | 仅 PRD.md（单一来源） |
| 章节 | 24 个主章节 + 附录 |
| FR 编号 | FR-001～FR-142 |
| NFR 编号 | NFR-001～NFR-013 |
| Markdown 表格 | 26 |
| DOCX 表格 | 26 |
| DOCX 标题 | 43 |
| DOCX 段落 | 190 |
| 缺失的 FR/NFR | 0（155 个编号全部出现在 DOCX） |
| 文件完整性 | `unzip -t` 无错误 |
| PDF 转换 | 成功，38 页，A4（595×842 pt） |
| 目录 | Word TOC 域 + `updateFields`；打开 Word 后 Ctrl+A/F9 更新页码 |
| 已知表现 | LibreOffice 直接转 PDF 时目录域显示占位文字；DOCX 正文与表格完整 |

---

## 7. 白皮书章节与字数

章节（15 章）：执行摘要、建设背景与行业需求、产品定位与建设目标、目标用户与使用场景、系统整体解决方案、产品功能架构、核心业务流程、系统技术特点、权限管理与数据安全、部署模式及运行环境、应用价值、实际实现成果、当前局限与适用边界、未来发展规划、总结。

| 指标 | 数值 |
|---|---:|
| 字符数（去空白） | 7,825 |
| 汉字数 | 4,606 |
| Mermaid 图 | 5 |
| 功能矩阵/对照表 | 3 |

---

## 8. 技术文档章节与字数

章节（14 章）：系统概述、技术栈、总体架构、工程目录、后端架构、前端架构、数据库设计、核心业务实现、API 设计、安全设计、正式部署、测试与验收、故障处理、维护与扩展；附录 A/B。

| 指标 | 数值 |
|---|---:|
| 字符数（去空白） | 14,681 |
| 汉字数 | 3,194 |
| Mermaid 图 | 3 |
| 版本来源 | `backend/requirements.txt`、`package.json`、`npm ls`、运行环境 |

---

## 9. 发布脚本修复

### 9.1 真实原因

1. 本机检查使用普通 `curl http://127.0.0.1/`；当环境存在 `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY` 时，localhost 请求可能被代理，导致首页校验误判。
2. reload 后 Nginx worker 尚未就绪，单次检查可能过早失败。
3. 首次发布没有 `previous`，旧实现失败时删除 `current`，把可访问站点变成 404。

### 9.2 修复

- 所有本机检查使用 `curl --noproxy '*'`；
- 首页校验重试 20 次（约 5 秒），要求 HTTP 200 + `<div id="app"></div>` + `/assets/`；
- API 代理检查（200/401/403）作为附加校验；
- 首次发布失败**保留新 `current`**，不再删除；有 `previous` 时回滚；
- 切换使用临时软链 + `mv -T` 原子替换；
- 记录 `previous`；reload 失败回滚；
- 发布前 `nginx -t`；Nginx 未运行/未安装时跳过 reload 并明确告警；
- release 目录 755、文件 644；
- 只清理 `releases/` 下时间戳命名且非 current/previous 的版本。

### 9.3 隔离验证

| 场景 | 结果 |
|---|---|
| 构建成功后才创建 release | 通过 |
| 首次发布 + 代理环境变量 | 通过（`--noproxy` 生效） |
| 临时 Nginx 首页/SPA/API | 通过 |
| reload 失败回滚 | 通过（current 回到上一版本） |
| 首次校验失败 | 保留 current，退出码 1 |
| 连续发布保留版本/权限 | 通过（3 个版本，755/644） |

---

## 10. 前端构建警告处理

| 警告 | 处理 |
|---|---|
| `:deep()` 伪类无效 | 来源 `src/assets/main.css` 全局样式误用；改为 `.page-card .el-card__header`，警告消失 |
| Chunk >500kB | 曾尝试 Rolldown `codeSplitting` vendor 拆包，但运行时出现 `TypeError`（vendor 初始化顺序）；已回退，保留路由懒加载，警告作为已知限制记录，未提高阈值 |
| 拆包回归 | 回退后构建产物经临时 Nginx + 三角色浏览器 19 页验证通过；不再上线损坏拆包版本 |
| npm `globalignorefile` | 来源为系统级 npm 配置 `/etc/npmignore`，不是项目文件；未修改用户全局配置。可选修复：`sudo npm config delete globalignorefile --location=global`（需用户授权） |
| 过时注释配置 | 删除 `vite.config.ts` 顶部重复的注释配置块 |

构建结果：成功；页面按路由动态加载，主包约 618kB（Element Plus 共享依赖），仍有 Vite >500kB 提示；自定义拆包因运行时错误已回退。

---

## 11. 自动化测试结果

| 检查 | 结果 |
|---|---|
| `pytest -q` | **44 passed, 0 failed** |
| `npm run build` | 通过（`:deep` 警告已修复；仍有 >500kB chunk 提示；npm globalignorefile 警告来自系统配置） |
| `bash -n start.sh deploy/*.sh` | 通过 |
| `systemd-analyze verify` | 通过（无 UAMS unit 错误） |
| `nginx -t`（普通用户） | 失败：无法打开 `/run/nginx.pid`/需要 root；**未以 sudo 执行** |
| `alembic current` | `e4f5a6b7c8d9 (head)` |
| 健康检查 | `{"status":"ok","env":"production","database":"up"}` |
| Git 敏感信息 | 数据库密码/JWT 跟踪文件命中 0 |

---

## 12. Nginx / systemd 当前真实状态

| 组件 | 状态 |
|---|---|
| Nginx | 1.28.3，active，监听 80（IPv4/IPv6） |
| 站点 | `/etc/nginx/sites-enabled/uams`（默认站点已移出） |
| 前端 | `/var/www/uams/current` → `releases/20261029_005724` |
| 后端 | `uams-backend.service` active，127.0.0.1:8000 |
| 后端启动校验 | `env_guard.py check production` 成功 |
| 数据库 | `uams`，head `e4f5a6b7c8d9` |
| 5173 | 已停止 |
| Nginx 访问日志 | `/var/log/nginx/uams.access.log` |
| 后端日志 | `journalctl -u uams-backend` |

> 实测 live `current` 仍指向 `releases/20261029_005724`（`index-dk4d-phK.js`），
> 最新 `frontend/dist` 为 `index-Bcblv2za.js`（CSS 修复、拆包回退后）。`/var/www/uams` 属 root，
> 当前无免密 sudo，**最新构建尚未写入 live**；需再次执行 `bash deploy/deploy-frontend.sh`（sudo）。
> 最新构建已通过临时 Nginx + 三角色浏览器 19 页验证，可安全发布。

---

## 13. 三角色验收结果

通过 Nginx 80 的正式站点，使用无头 Chrome 实际渲染：

| 角色 | 页面 | 结果 |
|---|---|---|
| 管理员 | 仪表盘、学生、教师、课程、开课排课、选课、成绩、考试、评价 | 9/9 OK |
| 教师 | 仪表盘、我的课程、成绩、课表 | 4/4 OK |
| 学生 | 仪表盘、个人信息、选课、课表、成绩、考试 | 6/6 OK |

- 首页 HTTP 200，包含 UAMS 入口；
- SPA 子路由直接访问 200；
- `/api/v1/terms/active` 未登录返回 401（代理生效）；
- 静态资源 200；
- `./start.sh --env production` 与 `status` 通过。

教学资料上传/下载/删除与权限由隔离库自动化测试覆盖；未在正式库做写入测试。

---

## 14. 未完成事项及原因

| 事项 | 原因/状态 |
|---|---|
| 发布最新前端构建 | `/var/www/uams` root 所有，当前无免密 sudo；live 仍为旧构建 |
| `sudo nginx -t` | 需要 root；普通用户执行失败；Nginx 服务本身 active |
| HTTPS/证书 | 当前 HTTP；规划中 |
| Mermaid 图渲染截图 | 环境无 `mmdc`；Markdown 结构已检查，未生成图片 |
| 正式库教学资料写入验收 | 遵守非破坏性要求，未在正式库创建资料 |
| 高并发/性能测试 | 未执行，不在本次范围 |
| DOCX 目录页码预渲染 | TOC 为 Word 域；Word 打开后更新；LibreOffice PDF 预览显示占位提示 |

---

## 15. Git

| 项目 | 结果 |
|---|---|
| 分支 | `main` |
| 新建分支/worktree/PR | 否 |
| 强制推送/硬重置 | 否 |
| 提交内容 | 文档重构、PRD/DOCX、白皮书、技术文档、脚本修复、警告处理、归档、报告 |
| 未提交 | `.env`、密码、JWT、日志、备份、上传资料 |
| 推送 | 见 `main` 最新 Git 记录（已推送 `origin/main`） |

---

## 结论

文档体系、PRD/DOCX、白皮书、技术文档与核心参考文档已完成并通过结构/链接/内容校验；发布脚本误判与回滚逻辑已修复并在隔离环境验证；前端构建警告已合理处理；Nginx/systemd/MySQL 保持正常运行，三角色页面通过 Nginx 验收。

唯一与“最新代码完全上线”相关的未完成项是**最新前端构建尚未写入 `/var/www/uams`**（需要 sudo）；这不影响当前站点可用，但需要管理员执行 `deploy/deploy-frontend.sh` 完成最终发布。

> 报告结束。
> 不包含数据库密码、JWT、Token 或敏感个人数据。
