# backend/tests —— 后端测试

## 作用

pytest 测试用例，覆盖认证、权限与基础设施。**当前业务模块测试不足，V0.2 待补齐。**

## 主要内容

| 文件 | 用例数 | 覆盖内容 |
|---|---|---|
| `test_auth.py` | 17 | 密码哈希与校验、登录成功/失败、用户名枚举防护、登录失败锁定、账号停用、token 校验、`/me`、**角色权限隔离**、改密流程 |
| `test_smoke.py` | 4 | `/health` 连通性、RBAC 五表存在、表引擎与字符集合规、`CHECK` 约束实际生效 |

**合计 21 个用例，全部通过。**

## 依赖关系

```
tests  →  app.main（TestClient）  →  services / models  →  MySQL
       →  app.db.session（SessionLocal，直接建/清测试数据）
```

## 开发注意事项

1. **测试前提**：MySQL 运行中且已 `alembic upgrade head`；`test_admin_has_approve_permission` 还依赖 `seed_rbac` 已执行
2. 测试数据用 **fixture 自建自清**（参考 `test_auth.py::student_user`），避免污染开发数据
3. 断言必须覆盖四类场景：正常 / 异常 / 权限 / 边界（CLAUDE.md §29）
4. 权限测试要显式断言"**不应拥有**"的权限，而非只断言"拥有的权限"
5. 数据库约束测试应实际尝试写入非法数据，确认被拒绝
6. **禁止为了让测试通过而修改测试结果**（CLAUDE.md §27）

## 当前状态

- **已实现**：认证、权限隔离、基础设施冒烟
- **V0.2 待补齐**：organization / person / course / teaching / selection / grade / exam / misc **8 个模块全部无测试**，优先补选课并发、成绩状态机、排课冲突、总评计算

## 相关文档

- [docs/TESTING.md](../../docs/TESTING.md) — 测试规范与待补清单
