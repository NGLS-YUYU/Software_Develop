# 前端写入后数据同步 E2E

这些脚本用真实 Chrome（CDP）验证：写入成功后当前页面无需 F5 即显示服务器最新数据。

> **仅允许连接隔离测试环境**。脚本启动时会检查 `/health` 的 `env`，不是 `testing` 会直接拒绝。

## 1. 启动隔离测试栈

使用 `uams_test`，不要连接正式库：

```bash
# 终端 A：测试后端（8010）
cd uams/backend
.venv/bin/python scripts/env_guard.py exec testing -- \
  .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010

# 终端 B：测试前端（5180）
cd uams/frontend
UAMS_BACKEND_URL=http://127.0.0.1:8010 \
  node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5180
```

## 2. 执行

```bash
cd uams/frontend
python3 tests/e2e/test_student_crud.py
python3 tests/e2e/test_multi_page_refresh.py
python3 tests/e2e/test_materials_refresh.py
python3 tests/e2e/test_grade_entry_refresh.py
```

可选环境变量：

| 变量 | 默认值 |
|---|---|
| `UAMS_E2E_API` | `http://127.0.0.1:8010/api/v1` |
| `UAMS_E2E_FRONT` | `http://127.0.0.1:5180` |

依赖：Python 3（标准库）、`google-chrome`。无需额外 pip/npm 包。

## 3. 覆盖场景

| 脚本 | 场景 |
|---|---|
| `test_student_crud.py` | REF-001/002/003/014：新增、修改、删除、重复失败保留数据 |
| `test_multi_page_refresh.py` | REF-004/005/006/009/010/011/012：课程、教学班容量、学期编辑/激活拒绝、成绩审核、选课/退课、公告发布 |
| `test_materials_refresh.py` | REF-013：资料上传/删除后列表刷新 |
| `test_grade_entry_refresh.py` | REF-007/008：成绩草稿保存、提交审核后状态刷新 |

## 4. 数据隔离与清理

- 所有写入只发生在 `uams_test`；
- 学生/课程/教学班/学期/公告/资料等临时记录在脚本内创建并清理；
- 成绩审核场景会把测试库 `grades.id=1` 临时撤销/重提并恢复为 APPROVED；
- 若脚本中断，重复执行会先清理同名/同学号测试记录。

## 5. 未覆盖

- REF-015 的复杂筛选/翻页组合（学生新增跨页可见已覆盖）；
- REF-016 的浏览器级慢请求竞态（由 `npm run test:unit` 的竞态守卫单测覆盖）；
- 正式库上的写入验收（禁止）；
- 多浏览器矩阵（仅 Chrome/CDP）。
