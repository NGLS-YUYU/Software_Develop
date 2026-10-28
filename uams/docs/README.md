# 项目文档体系

**UAMS 高校教务教学管理系统 —— 文档入口**

## 正式文档

| 文档 | 用途 |
|---|---|
| [PRD.md](PRD.md) | 产品需求文档（FR/NFR 编号、验收标准、实现状态） |
| [PRD.docx](PRD.docx) | PRD Word 版（封面、目录、页码、表格） |
| [UAMS_系统白皮书.md](UAMS_系统白皮书.md) | 面向管理人员与评审的产品白皮书 |
| [UAMS_系统技术文档.md](UAMS_系统技术文档.md) | 面向开发/维护/接手者的技术交接文档 |
| [UAMS_教务管理系统用户操作手册.md](UAMS_教务管理系统用户操作手册.md) | 管理员/教师/学生操作说明 |
| [UAMS_启动与环境切换说明.md](UAMS_启动与环境切换说明.md) | `start.sh` 环境选择、正式/测试启动与排障 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 系统架构、分层、部署形态 |
| [API.md](API.md) | 后端 API 清单（119 路径 / 169 操作） |
| [DATABASE.md](DATABASE.md) | 数据库表、关系、约束、迁移 |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Nginx + systemd 正式部署、回滚与验收 |
| [DEVELOPMENT.md](DEVELOPMENT.md) | 开发环境、编码规范、Git 工作流 |
| [TESTING.md](TESTING.md) | 测试规范、自动化测试与覆盖边界 |

## 历史归档

历史内容已按类别归档，保留审计与修复证据，不再作为当前操作指南：

| 目录 | 内容 |
|---|---|
| [archive/audits/](archive/audits/) | V0.2 审计、V3.1 功能差距审计与预检 |
| [archive/fixes/](archive/fixes/) | FIX-001～009、V3.1 FIX-001～004、登录错误修复 |
| [archive/reports/](archive/reports/) | 部署/验收/阶段基线/启动管理器/工程清理/最终交付报告 |

归档索引见 [archive/README.md](archive/README.md)。

## 推荐阅读顺序

1. 第一次打开项目：[../README.md](../README.md) → `UAMS_系统白皮书.md` → `PRD.md`
2. 部署与运维：`DEPLOYMENT.md` → [../deploy/README.md](../deploy/README.md) → `UAMS_启动与环境切换说明.md`
3. 开发与接手：`UAMS_系统技术文档.md` → `ARCHITECTURE.md` → `DATABASE.md` → `API.md` → `DEVELOPMENT.md`
4. 业务操作：`UAMS_教务管理系统用户操作手册.md`
5. 测试与验收：`TESTING.md`
6. 历史追溯：`archive/`

## 文档维护约定

- `docs/` 根目录只保留现行正式文档；
- 历史审计、修复、报告分别进入 `archive/audits|fixes|reports`；
- 历史 Alembic 迁移不删除、不改写；
- 文档不得包含数据库密码、JWT、Token 或真实敏感数据；
- 更新代码后同步更新受影响的 API/数据库/部署/用户手册。
