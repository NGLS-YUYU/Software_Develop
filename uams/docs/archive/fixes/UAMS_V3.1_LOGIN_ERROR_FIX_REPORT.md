# UAMS V3.1 登录失败无提示修复报告

> 修复日期：2026-10-28
> 分支：`main`
> 基线：启动管理器提交 `4fa0145`
> 报告提交：见 `main` 最新 Git 记录
> 数据库结构/业务数据：未修改
> 正式库错误密码测试：**未执行**（避免锁定真实账号）

---

## 0. 结论

1. 登录失败无提示的真实根因已定位：Axios 拦截器在 `/login` 路径对 401 **主动不提示**，而登录页 `submit()` 只有 `try/finally`、**没有 `catch`**，请求异常被丢弃，页面既不显示错误也无法反馈。
2. 已实现按后端业务错误码映射的中文内联提示，覆盖密码错误、账号不存在、停用、锁定、网络失败、500、空输入。
3. 登录失败后按钮恢复、用户名保留、密码清空并聚焦；错误密码不会写入 Token、不会跳转。
4. 锁定提示使用后端返回的 `retry_after_seconds` 计算剩余时间，不硬编码。
5. 后端 JWT、RBAC、登录失败计数与锁定策略均保留，未放松任何安全校验。
6. 隔离库 API 测试与真实浏览器验收全部通过。

---

## 1. 真实根因

### 1.1 前端链路

`frontend/src/api/request.ts` 原逻辑：

```ts
if (status === 401) {
  if (!location.pathname.startsWith('/login')) {
    ElMessage.error('登录已过期，请重新登录')
    onUnauthorized?.()
  }
}
```

在登录页，401 被**有意静默**（本意是避免“登录失败 + 登录过期”重复提示），但登录页本身没有兜底提示。

`frontend/src/views/Login.vue` 原逻辑：

```ts
try {
  const res = await auth.login(...)
  ...
} finally {
  loading.value = false
}
```

没有 `catch`，Axios 的 rejected Promise 变成未处理异常：

- 屏幕上没有任何错误提示；
- 用户无法区分密码错误 / 账号不存在 / 停用 / 锁定 / 网络故障；
- 只有浏览器控制台可能看到未处理 Promise（不含密码）。

### 1.2 后端链路

后端本身已具备可识别错误码：

| 场景 | HTTP | code | message |
|---|---|---|---|
| 用户名或密码错误 / 账号不存在 | 401 | `AUTH_INVALID_CREDENTIALS` | 用户名或密码错误 |
| 账号停用 | 403 | `AUTH_ACCOUNT_DISABLED` | 账号已被停用 |
| 账号锁定 | 423 | `AUTH_ACCOUNT_LOCKED` | 账号已锁定，请于 … 后重试 |

问题不在后端错误码，而在前端未消费 401 错误；锁定响应也缺少机器可读的剩余时间字段。

---

## 2. 修改文件

| 文件 | 修改 |
|---|---|
| `frontend/src/views/Login.vue` | 增加 `catch`、业务码映射、内联错误提示、空值校验、失败后恢复按钮、保留用户名/清空密码/聚焦、成功响应校验、安全 redirect |
| `frontend/src/api/request.ts` | 登录请求/登录页不再走全局 toast 与 401/403 登录态处理，统一交给登录页，避免吞错和重复提示 |
| `frontend/src/stores/auth.ts` | 后端 200 但缺少 `access_token`/`user`/`home_route`/roles/permissions 时清理状态并抛错，不进入系统 |
| `backend/app/services/auth.py` | 锁定错误附带 `locked_until` 与 `retry_after_seconds`；触发锁定的当次即返回 423，而非继续返回密码错误 |
| `backend/tests/test_login_errors.py` | 新增 6 项登录 API 测试 |
| `backend/scripts/env_guard.py` / `start.sh` | 本任务期间同时修复局域网 IP 误选 VPN 地址（见启动管理器报告） |

未修改：数据库结构、历史业务数据、JWT 密钥、RBAC、密码哈希、锁定阈值。

---

## 3. 前端提示规则

| 场景 | 判定 | 页面提示 |
|---|---|---|
| 空输入 | 前端校验，不发请求 | 请输入用户名和密码 |
| 密码错误 | `AUTH_INVALID_CREDENTIALS` 或 401 | 用户名或密码错误，请重新输入 |
| 账号不存在 | 后端统一返回 `AUTH_INVALID_CREDENTIALS` | 用户名或密码错误，请重新输入 |
| 账号停用 | `AUTH_ACCOUNT_DISABLED` 或 403 | 该账号已被停用，请联系管理员 |
| 账号锁定 | `AUTH_ACCOUNT_LOCKED` / 423 / 429 | 账号已被暂时锁定，请 N 分钟后再试（N 由 `retry_after_seconds` 计算） |
| 无法连接 | 无 `response`（断网/后端关闭/超时） | 无法连接服务器，请检查网络或联系管理员 |
| 服务器异常 | HTTP 5xx | 登录服务暂时不可用，请稍后重试 |
| 其他 | 后端 message 兜底 | 登录失败，请稍后重试 |

行为保证：

- 错误提示同时以内联 `el-alert` 显示在登录表单下方；
- 登录请求失败不会弹全局重复 toast；
- 失败后 `loading=false`，按钮可再次点击；
- 密码错误时保留用户名、清空密码并聚焦密码框；
- 失败时 `localStorage` 不写入 Token；
- 成功前校验响应结构，缺失凭证直接清理并提示，不跳转。

---

## 4. API 测试（隔离库 `uams_test`）

运行：`cd backend && .venv/bin/pytest -q tests/test_login_errors.py`

| # | 用例 | 结果 |
|---|---|---|
| 1 | 正确用户名/密码登录 | 200，返回 Token + `/student/dashboard` |
| 2 | 错误密码 | 401 `AUTH_INVALID_CREDENTIALS` |
| 3 | 不存在账号 | 401，与错误密码 code/message 完全一致 |
| 4 | 停用账号 | 403 `AUTH_ACCOUNT_DISABLED` |
| 5 | 连续输错触发锁定 | 前 4 次 401；第 5 次 423，含 `retry_after_seconds` 与 `locked_until`；锁定期间正确密码仍 423 |
| 6 | 空用户名/密码 | 422 `VALIDATION_ERROR` |
| 7 | 强制后端异常 | 500，不返回敏感信息 |

**6 项测试通过，0 失败。** 锁定测试只使用临时测试账号，测试后删除。

全量后端回归：**44 通过，0 失败**。

---

## 5. 浏览器验收

环境：`uams_test` + `./start.sh --env testing`，真实 Vite 页面 + 无头 Chrome/CDP。

| # | 场景 | 结果 |
|---|---|---|
| 1 | 空用户名/密码点击登录 | PASS：内联“请输入用户名和密码”，无请求、无 Token |
| 2 | 错误密码 | PASS：内联“用户名或密码错误，请重新输入” |
| 3 | 错误后检查输入 | PASS：用户名保留、密码清空、按钮非 loading、无 Token |
| 4 | 同一页面重试正确密码 | PASS：进入 `/student/dashboard`，Token 写入 |
| 5 | 不存在账号 | PASS：与错误密码提示完全一致 |
| 6 | 停用账号 | PASS：“该账号已被停用，请联系管理员” |
| 7 | 锁定账号 | PASS：“账号已被暂时锁定，请 10 分钟后再试”（后端剩余 600 秒） |
| 8 | 后端不可达（CDP 模拟连接拒绝） | PASS：“无法连接服务器，请检查网络或联系管理员” |
| 9 | 500（CDP 模拟） | PASS：“登录服务暂时不可用，请稍后重试”，页面未卡死 |
| 10 | 500 后重试正确密码 | PASS：进入 `/admin/dashboard` |
| 11 | 管理员正确登录 | PASS：`/admin/dashboard` + Token |
| 12 | 教师正确登录 | PASS：`/teacher/dashboard` + Token（API 验证） |

补充：

- 错误密码场景下未出现全局重复 toast（拦截器对登录请求不再提示）；
- 浏览器场景使用的临时账号 `PYTEST_UI_*` 已从 `uams_test` 删除；
- 正式库未执行任何错误密码尝试，避免触发真实账号锁定。

---

## 6. 构建与回归

| 检查 | 结果 |
|---|---|
| 前端 `npm run build`（含 vue-tsc） | 通过 |
| 后端 `compileall` | 通过 |
| 后端全量 `pytest` | 44 通过 |
| `bash -n start.sh` | 通过 |
| 正式环境正确登录（admin/T001/20260001） | 通过 |
| 正式环境健康检查 | `database: up` |

---

## 7. 安全确认

- 未取消密码校验、失败计数、账号锁定、JWT 或 RBAC；
- 未在日志/控制台打印密码、Token、JWT；
- 账号不存在与密码错误统一提示，不泄露账号是否存在；
- 锁定剩余时间来自后端 `retry_after_seconds`，不硬编码；
- 未修改正式数据库结构或历史业务数据；
- 未在正式库制造失败登录。

---

## 8. 未验证/剩余风险

| 项目 | 说明 |
|---|---|
| 正式库错误密码提示 | 为避免锁定真实账号，未在正式库执行；同一代码已在 `uams_test` 真实验证 |
| 真实断网（拔网线） | 使用 CDP `ConnectionRefused` 模拟后端不可达，未物理断网 |
| 真实 500 | 使用 CDP 拦截并返回 500，未在生产后端制造异常 |
| 并发登录锁定竞争 | 未做并发压测；沿用原有计数与锁定逻辑 |
| 浏览器视觉截图 | 以 DOM 文本与状态检查为准，未逐像素比对 |

---

## 9. Git

| 项目 | 结果 |
|---|---|
| 分支 | `main` |
| 新建分支/worktree/PR | 否 |
| 强制推送/硬重置 | 否 |
| 提交内容 | 登录修复代码、后端锁定响应增强、测试、报告、局域网 IP 修复 |
| 未提交 | `.env`、密码、JWT、日志、备份 |
| 推送 | 已推送 `origin/main`（详见最终 Git 记录） |

---

## 10. 最终结论

**登录失败无提示问题已修复：错误密码、账号不存在、停用、锁定、断网、500、空输入均有明确中文提示；失败后可重试，成功后才进入系统。原有 JWT、RBAC 与锁定策略保持不变。**

> 报告结束。
> 本报告不包含数据库密码、JWT、Token 或敏感个人数据。
