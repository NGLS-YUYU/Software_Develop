# app/services —— Service 层（业务逻辑）

## 作用

承载全部业务规则、校验与事务边界。**这是业务逻辑唯一应该存在的地方。**

## 主要内容

| 文件 | 说明 |
|---|---|
| `base.py` | `BaseCrudService` 通用基类（唯一校验、引用保护、分页、事务） |
| `auth.py` | 登录、失败锁定、改密、角色路由 |
| `organization.py` | 学院/专业/班级/教室，含引用保护 |
| `person.py` | 学生/教师建档（同步创建账号并授角色）、冗余字段同步 |
| `course.py` | 课程、先修课**环路检测**、培养方案 |
| `teaching.py` | 教学任务、教学班、排课**冲突检测**（`ConflictChecker`） |
| `selection.py` | 选课/退课，**行级锁防超卖** |
| `grade.py` | 成绩状态机、总评计算、学分与 GPA 汇总 |

## 依赖关系

```
api/v1  →  services  →  models（ORM） → MySQL
                     →  repositories（复杂查询）
                     →  core/exceptions（业务异常）
```

## 开发注意事项

1. **事务边界在此层**：`self.db.commit()` 在 Service 方法内，失败整体回滚
2. 业务异常统一抛 `BizError` 子类（`Conflict` / `NotFound` / `PermissionDenied`），带上明确 `code`
3. 数据库约束冲突（IntegrityError）在 `BaseCrudService._commit` 中转为 `Conflict`
4. 涉及并发的操作必须显式加锁（参考 `selection.py` 的 `with_for_update()`）
5. 总评、绩点等计算**必须在此层完成**，不接受前端传入结果（CLAUDE.md §21）
6. 简单 CRUD 继承 `BaseCrudService`，只覆写 `validate_create` / `validate_update` / `validate_delete` 与 `search_fields` / `unique_fields`

## 当前状态

- **已实现**：全部核心业务逻辑
- **V0.2 待完善**：成绩模型重新设计（实践/理论拆分、GPA、排名）、Excel 导入导出、操作日志写入

## 相关文档

- [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) — 关键业务机制
- [docs/DATABASE.md](../../docs/DATABASE.md) — 表结构与事务规则
