# 项目文档体系

**UAMS 高校教务教学管理系统 —— 文档入口**

## 当前使用文档

| 文档 | 用途 |
|---|---|
| [PRD.md](PRD.md) | 产品需求与业务规则 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 系统架构、模块关系、分层职责、正式部署拓扑 |
| [DATABASE.md](DATABASE.md) | 数据库结构、表关系、迁移管理 |
| [API.md](API.md) | 后端 API 清单与说明 |
| [DEVELOPMENT.md](DEVELOPMENT.md) | 开发环境、编码规范、Git 工作流 |
| [TESTING.md](TESTING.md) | 测试规范、自动化测试与历史用例索引 |
| [STARTUP.md](STARTUP.md) | 首次初始化、日常启动、正式/测试环境切换 |
| [DEPLOYMENT.md](DEPLOYMENT.md) | 正式部署（Nginx + systemd + MySQL）、回滚与验收 |
| [ROADMAP.md](ROADMAP.md) | 版本规划 |
| [UAMS_教务管理系统用户操作手册.md](UAMS_教务管理系统用户操作手册.md) | 管理员/教师/学生操作说明 |
| [UAMS_启动与环境切换说明.md](UAMS_启动与环境切换说明.md) | `start.sh` 交互菜单、环境选择与故障排查 |
| [UAMS_V3.2_ENGINEERING_CLEANUP_REPORT.md](UAMS_V3.2_ENGINEERING_CLEANUP_REPORT.md) | V3.2 工程清理与部署准备报告 |
| [PRD.docx](PRD.docx) | 原始 PRD（Word） |

## 归档文档

历史审计、开发阶段报告与修复记录已移至 [archive/](archive/)，保留作为开发与审计证据，不再作为当前操作指南：

| 文档目录 | 内容 |
|---|---|
| [archive/UAMS_V3.1_*](archive/) | V3.1 功能审计、FIX/DEPLOY/PROD/启动管理器/登录修复报告 |
| [archive/fixes/](archive/fixes/) | FIX-001～FIX-009 阶段修复说明与报告 |
| [archive/V0.2_AUDIT.md](archive/V0.2_AUDIT.md)、[archive/V0.2_TASK001_013_REAUDIT.md](archive/V0.2_TASK001_013_REAUDIT.md) | V0.2 审计 |
| [archive/V2.0开发指南.md](archive/V2.0开发指南.md)、[archive/V2.1_FINAL_BASELINE.md](archive/V2.1_FINAL_BASELINE.md) | V2.x 开发阶段基线 |
| [archive/DOCUMENTATION_UPDATE_REPORT.md](archive/DOCUMENTATION_UPDATE_REPORT.md) | 早期文档整理记录 |

## 推荐阅读顺序

1. 第一次打开项目：[../README.md](../README.md) → `STARTUP.md` → `ARCHITECTURE.md`
2. 部署正式环境：`DEPLOYMENT.md` → [../deploy/README.md](../deploy/README.md)
3. 参与开发：`DEVELOPMENT.md` → `DATABASE.md` → `API.md`
4. 业务与验收：`PRD.md` → 用户操作手册 → `TESTING.md`
5. 了解历史：`archive/`

## 文档维护约定

- 当前操作指南放在 `docs/` 根目录；
- 阶段报告、审计与修复记录放入 `docs/archive/`；
- 历史 Alembic 迁移文件不删除、不改写；
- 文档不得包含数据库密码、JWT 密钥或真实 Token。
