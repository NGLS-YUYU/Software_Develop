# app/schemas —— 数据校验与序列化层

## 作用

定义 API 的请求入参与响应出参模型（Pydantic v2），负责格式校验与序列化。**不查库、不含业务规则。**

## 主要内容

| 文件 | 说明 | 主要模型 |
|---|---|---|
| `common.py` | 通用 | `PageParams`、`PageResult[T]`、`IdResponse`、`MessageResponse` |
| `auth.py` | 认证 | `LoginRequest`、`LoginResponse`、`UserInfo`、`CurrentUserResponse`、`ChangePasswordRequest` |
| `organization.py` | 组织 | 学院/专业/班级/教室的 Create / Update / Out |
| `person.py` | 人员 | 学生/教师的 Create / Update / Out |
| `course.py` | 课程 | 课程、先修、培养方案、方案课程 |
| `teaching.py` | 开课排课 | 教学任务、教学班、排课、冲突信息 |

## 依赖关系

```
api/v1  →  schemas（校验入参、序列化出参）
```

## 开发注意事项

1. 命名约定：`XxxCreate`（新增）、`XxxUpdate`（修改，字段全可选）、`XxxOut`（出参）
2. 出参用 `model_config = ConfigDict(from_attributes=True)` 以便直接从 ORM 对象构造
3. 关联字段（如 `college_name`、`student_name`）在出参中声明为可选，由 Router 组装填充
4. **跨字段校验用 `@model_validator`**，例如课程权重之和必须为 1
5. 枚举值用 `Field(..., pattern="^(A|B|C)$")` 约束，与模型层的 `CheckConstraint` 保持一致
6. 密码字段禁止出现在任何 `XxxOut` 中
7. 本层不写业务规则，复杂校验放 Service

## 当前状态

- **已实现**：全部业务模块的 Schema；注意部分模块（grade / exam / selection / misc）的 Schema 直接定义在对应路由文件内，未拆分到本目录

## 相关文档

- [docs/API.md](../../docs/API.md) — 接口与参数
