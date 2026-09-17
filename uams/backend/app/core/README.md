# app/core —— 核心基础设施

## 作用

提供配置、安全、异常处理等跨模块基础能力。

## 主要内容

| 文件 | 说明 |
|---|---|
| `config.py` | `Settings`（pydantic-settings），从 `backend/.env` 读取配置；`get_settings()` 带 lru_cache |
| `security.py` | 密码哈希（bcrypt）、JWT 签发与校验（python-jose）；含 72 字节截断处理 |
| `exceptions.py` | `BizError` 基类与全部业务异常子类（带错误码与 HTTP 状态） |

## 依赖关系

```
所有层  →  core/config（配置）
服务层  →  core/security（哈希、令牌）
所有层  →  core/exceptions（异常）
```

## 开发注意事项

1. **不要在源码中保留真实凭据默认值** —— 当前 `config.py` 存在默认数据库密码与 `JWT_SECRET` 占位，属 V0.2 待修复项（见 [docs/V0.2_AUDIT.md](../../docs/V0.2_AUDIT.md) P0-1）
2. **不使用 passlib** —— 它依赖 `bcrypt.__about__`，该属性在 bcrypt 4.1+ 已移除，在 bcrypt 5.x 下会报错。直接调用 `bcrypt`
3. bcrypt 只取前 72 字节，`security.py` 已显式截断，哈希与校验用同一规则
4. 新增业务异常继承 `BizError`，并声明 `code`、`http_status`、`message`
5. `main.py` 中的异常处理器依赖 `exceptions.py` 的 `{code, message}` 结构，改动需同步

## 当前状态

- **已实现**：配置、安全、异常
- **V0.2 待完善**：移除 `config.py` 中的默认凭据（P0-1）

## 相关文档

- [docs/DEVELOPMENT.md](../../docs/DEVELOPMENT.md) — 配置管理
- [docs/API.md](../../docs/API.md) — 错误码表
