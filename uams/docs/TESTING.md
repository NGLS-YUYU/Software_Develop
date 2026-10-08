# 测试与验收记录

> **最终交付说明（V3.0 FINAL DELIVERY CLEANUP，2026-10-09）**
>
> 按最终交付要求，本版本已移除全部**自动化测试代码**（`backend/tests/`）与
> **端到端验收脚本**（`backend/scripts/e2e_fix00*.py`），数据库也已收敛为
> 「最小正式演示数据」。因此本文件不再描述如何运行测试，只保留验收结论的索引。

---

## 1. 历史验收记录

交付前的每一轮修复均留有实施报告与验收结论，作为本版本正确性的依据：

| 编号 | 主题 | 报告 |
|---|---|---|
| FIX-005 | 批量导入闭环 + 成绩模板动态生成 + 成绩草稿删除 | [FIX-005-REPORT.md](fixes/FIX-005-REPORT.md) |
| FIX-006 | 学期管理前端闭环 | [FIX-006-REPORT.md](fixes/FIX-006-REPORT.md) |
| FIX-007 | 部署优化 + 排课前端联调收尾 | [FIX-007-REPORT.md](fixes/FIX-007-REPORT.md) |
| FIX-008 | 成绩权重一致性治理 | [fixes/FIX-008.md](fixes/FIX-008.md) |
| FIX-009 | 课程学时 / 理论实践学时 / 学分与成绩结构闭环 | [fixes/FIX-009.md](fixes/FIX-009.md) |
| V2.1 发布审计 | 最终冻结审计（P0 = 0，P1 = 0，GO） | 见对话验收记录 |
| V3.0 | UI/UX 与响应式产品化重构 | 见对话验收记录 |

各报告中的具体测试数量与端到端断言结果，均对应**当时**的代码与数据状态；
清理后这些用例已不存在，报告作为历史证据保留，不再重复执行。

## 2. 清理完成后的验证方式

测试代码移除后，交付版本的验证按下述方式进行（对应 FINAL DELIVERY CLEANUP 的检查清单）：

| 项 | 方式 |
|---|---|
| 前端类型与构建 | `cd frontend && npm run build`（含 `vue-tsc -b`） |
| 后端可用性 | `curl http://127.0.0.1:8000/health` → `status: ok` / `database: up` |
| 三角色可登录 | 用 README 中的演示环境账号登录并访问核心页面 |
| 数据完整性 | 数据库只读校验（外键孤儿数、学时守恒、学期单激活等，均为 0） |

## 3. 相关文档

- [DEPLOYMENT.md](DEPLOYMENT.md) — Windows / Ubuntu / 局域网部署
- [DEVELOPMENT.md](DEVELOPMENT.md) — 开发规范
- [README.md](../README.md) — 项目简介与演示账号
