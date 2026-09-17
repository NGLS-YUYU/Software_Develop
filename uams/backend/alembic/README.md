# backend/alembic —— 数据库迁移

## 作用

管理数据库结构的版本演进，全部表结构变更必须通过迁移完成。

## 主要内容

| 文件 | 说明 |
|---|---|
| `env.py` | 迁移运行环境。从 `app.core.config` 读取连接串；导入 `app.models` 以发现全部表 |
| `versions/` | 迁移脚本 |
| `script.py.mako` | 新迁移的文件模板 |
| `../alembic.ini` | Alembic 配置（`file_template` 带时间戳前缀） |

### 已有迁移

| 版本 | 文件 | 内容 |
|---|---|---|
| `bc0a832224a4` | `20260915_0114_bc0a832224a4_create_rbac_tables.py` | RBAC 五张表 |
| `7d34560e8aba` | `20260915_0128_7d34560e8aba_create_business_tables.py` | 其余 23 张业务表 |

## 依赖关系

```
alembic/env.py  →  app.core.config（DATABASE_URL）
                →  app.models.__init__（Base.metadata 全部表）
```

## 开发注意事项

1. **连接串不在此维护** —— `env.py` 从配置读取并注入，避免与 `app/core/config.py` 两处漂移
2. **新增模型必须先在 `app/models/__init__.py` 登记**，否则 autogenerate 会漏表
3. 生成迁移后**必须人工审阅**，autogenerate 不保证完全正确（尤其涉及约束变更）
4. **禁止删除已提交的历史迁移**（CLAUDE.md §27）
5. **禁止手工改库替代迁移**；迁移必须可重复执行
6. 建表顺序受外键依赖约束，见 [docs/DATABASE.md](../../docs/DATABASE.md) §14.1

## 常用命令

```bash
cd uams/backend
.venv/bin/alembic current                          # 当前版本
.venv/bin/alembic upgrade head                     # 升到最新
.venv/bin/alembic downgrade -1                     # 回滚一版
.venv/bin/alembic revision --autogenerate -m "描述"  # 生成迁移（需审阅）
```

> 生成空迁移（只有 `pass`）即表示**模型与数据库已同步**，可用于漂移检查。

## 当前状态

- **已实现**：28 张业务表，当前 head `7d34560e8aba`，与模型零漂移
- **V0.2 待完善**：成绩模型重新设计后需新增迁移

## 相关文档

- [docs/DATABASE.md](../../docs/DATABASE.md) — 表结构与迁移策略
