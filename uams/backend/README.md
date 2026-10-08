# backend —— FastAPI 后端

## 作用

UAMS 的后端服务，提供 REST API、认证鉴权、业务逻辑与数据持久化。

## 主要内容

```
backend/
├── app/
│   ├── main.py           FastAPI 入口（CORS、异常处理器、路由挂载）
│   ├── core/             配置、安全（bcrypt/JWT）、业务异常
│   ├── db/               SQLAlchemy Base 与 Session
│   ├── models/           28 张表的 ORM 模型（10 个模块文件）
│   ├── schemas/          Pydantic 请求/响应模型
│   ├── services/         业务逻辑（含 BaseCrudService 基类）
│   ├── repositories/     数据访问层
│   ├── api/
│   │   ├── deps.py       认证与权限依赖注入
│   │   └── v1/           11 个路由模块，75 个路径
│   └── utils/            预留（当前为空）
├── alembic/              数据库迁移
├── scripts/              种子数据与环境脚本
├── requirements.txt      依赖清单
├── alembic.ini           Alembic 配置
└── .env.example          环境变量模板
```

## 依赖关系

```
Frontend（Axios） → api/v1（Router） → services（Service）
                                        → repositories（Repository）
                                        → models（ORM） → MySQL
                   core/ 提供配置、密码哈希、JWT、异常
                   db/ 提供 Base 与 Session
```

分层约束：`Router → Service → Repository → SQLAlchemy → MySQL`，禁止跨层。

## 开发注意事项

1. **新增模型必须在 `app/models/__init__.py` 登记**，否则 Alembic autogenerate 会漏表
2. **表结构变更必须走 Alembic migration**，禁止手工改库
3. 不在 `alembic.ini` 中维护连接串（由 `alembic/env.py` 从配置读取）
4. `.env` 不入版本库；`.env.example` 只放占位值
5. 密码哈希不用 passlib（与 bcrypt 5.x 不兼容），直接调用 `bcrypt`（见 `core/security.py`）
6. 业务逻辑写在 Service，不要堆在 Router

## 当前状态

- **已实现**：认证 RBAC、基础数据、人员、课程、培养方案、开课排课、选课、课表、成绩、考试、评价、公告、统计、审计日志查询
- **部分实现**：审计日志（仅有查询接口，业务操作未自动写入）
- **V0.2 待完善**：Excel 导入导出、操作日志写入、核心业务测试、成绩模型重新设计

## 相关文档

- [ARCHITECTURE.md](../docs/ARCHITECTURE.md) — 架构与分层
- [API.md](../docs/API.md) — 接口清单
- [DATABASE.md](../docs/DATABASE.md) — 数据库设计
- [DEVELOPMENT.md](../docs/DEVELOPMENT.md) — 开发规范
