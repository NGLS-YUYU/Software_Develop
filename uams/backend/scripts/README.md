# backend/scripts —— 种子数据脚本

## 作用

生成角色权限与演示数据。均为 Python 模块，通过 `-m` 方式运行。

## 主要内容

| 文件 | 说明 |
|---|---|
| `seed_rbac.py` | 初始化 38 项权限 + 3 个角色（`STUDENT` / `TEACHER` / `ACADEMIC_ADMIN`）+ `admin` 账号并授权 |
| `seed_demo.py` | 生成完整演示数据：1 学院 / 2 专业 / 2 班级 / 5 教师 / 20 学生 / 10 课程 / 培养方案 / 教学任务 / 教学班 / 排课 / 选课 / 成绩 / 考试 / 评价任务 / 公告 |

> 环境准备类脚本（`setup_mysql.sh`、`uninstall_docker.sh`）位于 [`uams/scripts/`](../../scripts/)，不在本目录。

## 依赖关系

```
seed_rbac.py  →  app.core.security（密码哈希）、app.models、app.db.session
seed_demo.py  →  app.services（person / grade）、app.models、app.db.session
              →  依赖 seed_rbac.py 先执行（需要角色与 admin 账号）
```

## 开发注意事项

1. **两个脚本必须保持幂等** —— 重复执行不得产生重复数据
2. `seed_demo.py` 中的随机要素（选课组合、成绩分数）已改为**确定性生成**。原因：全局 `random` 序列会被前面的跳过逻辑改变，导致第二次运行选出不同课程而新增数据，破坏幂等性
3. `seed_demo.py` 对已存在用户**不覆盖密码**，因此改过的密码不会被 seed 重置
4. 用法：

```bash
cd uams/backend
.venv/bin/python -m scripts.seed_rbac    # 必须先执行
.venv/bin/python -m scripts.seed_demo    # 可选
```

5. 演示密码仅用于开发，正式环境必须修改

## 当前状态

- **已实现**：RBAC 种子、完整演示数据
- **V0.2 待完善**：Excel 导入脚本（学生/教师/课程/成绩）

## 相关文档

- [docs/DATABASE.md](../../docs/DATABASE.md) §15 — 初始化数据要求
- [docs/DEPLOYMENT.md](../../docs/DEPLOYMENT.md) — 环境准备
