# app/api —— API 层（Router）

## 作用

处理 HTTP 请求与响应，调用 Service 完成业务，返回统一格式结果。**不写业务规则、不直接查库。**

## 主要内容

| 文件 | 前缀 | 说明 |
|---|---|---|
| `deps.py` | —— | `get_current_user`、`RequireRoles`、`RequirePermissions` 依赖注入 |
| `v1/auth.py` | `/auth` | 登录、当前用户、改密、退出 |
| `v1/organization.py` | `/colleges` `/majors` `/classes` `/classrooms` | 基础数据 CRUD |
| `v1/person.py` | `/students` `/teachers` | 人员档案与账号联动 |
| `v1/course.py` | `/courses` `/curriculum-plans` | 课程、先修、培养方案 |
| `v1/teaching.py` | `/teaching-tasks` `/teaching-classes` | 开课、教学班、排课 |
| `v1/selection.py` | `/course-selections` `/selection-periods` | 选课、退课、选课窗口 |
| `v1/schedule.py` | `/schedules` | 课表 |
| `v1/grade.py` | `/grades` | 成绩录入/提交/审核/统计 |
| `v1/exam.py` | `/exams` | 考试、考场、排座 |
| `v1/misc.py` | `/evaluations` `/announcements` `/statistics` `/audit-logs` | 评价、公告、统计、审计 |
| `v1/__init__.py` | —— | 汇总所有 v1 路由 |

## 依赖关系

```
api/v1/*  →  api/deps.py（认证权限）
          →  services/*（业务）
          →  schemas/*（入参校验、出参序列化）
```

## 开发注意事项

1. 每个写操作都必须通过 `Depends(RequirePermissions("xxx:write"))` 声明权限
2. 需要对象级权限校验时（如"只能查本人"），在函数内显式判断并抛 `PermissionDenied`
3. **新增路由模块必须在 `v1/__init__.py` 中注册**
4. 不在此层写业务规则，也不直接使用 `db.query`
5. 统一使用 `PageParams` / `PageResult` 处理分页

## 当前状态

- **已实现**：70 个路径 / 108 个操作
- **V0.2 待完善**：Excel 导入导出、调停课申请、教学资料上传

## 相关文档

- [docs/API.md](../../docs/API.md) — 完整接口清单
- [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) — 分层说明
