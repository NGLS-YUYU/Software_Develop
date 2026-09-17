# frontend —— Vue 3 前端

## 作用

UAMS 的前端单页应用，实现学生端、教师端、教务端三端界面与交互。

## 主要内容

```
frontend/
├── src/
│   ├── main.ts           入口（Pinia / Router / Element Plus / 图标注册）
│   ├── App.vue           根组件
│   ├── api/
│   │   ├── request.ts    Axios 实例、Token 注入、统一错误处理
│   │   └── index.ts      按业务模块组织的 API 调用
│   ├── types/index.ts    与后端 Schema 对应的 TypeScript 类型
│   ├── stores/auth.ts    认证状态（token / user / roles / permissions）
│   ├── router/index.ts   路由表与角色守卫
│   ├── layouts/          MainLayout.vue（侧边菜单 + 顶栏）
│   ├── components/       ScheduleGrid.vue（周课表网格）
│   ├── composables/      useCrudTable.ts、useSemester.ts
│   ├── assets/           main.css
│   └── views/            28 个页面
├── vite.config.ts        别名 @ → src、/api 代理、Element Plus 按需导入
├── tsconfig.app.json     路径别名与编译选项
└── index.html            页面模板
```

### 页面分布

| 端 | 数量 | 目录 |
|---|---|---|
| 学生端 | 7 | `views/student/` |
| 教师端 | 5 | `views/teacher/` |
| 教务端 | 12 | `views/admin/` |
| 公共 | 4 | `views/Login.vue`、`views/common/` |

## 依赖关系

```
views（页面） → api/index.ts（接口封装） → api/request.ts（Axios）
             → stores/auth.ts（认证状态，Pinia）
             → router/index.ts（路由守卫，角色控制）
             → components/ layouts/ composables/（复用）
```

后端 API 由 Vite 开发服务器代理：`/api` → `http://127.0.0.1:8000`。

## 开发注意事项

1. **前端权限只用于体验**（菜单、路由），不得替代后端校验（CLAUDE.md §9）
2. API 调用统一走 `src/api/index.ts`，不要散落 axios 调用
3. 类型集中在 `src/types/index.ts`，新增接口时同步补充
4. Element Plus 组件与 API 已配置**按需自动导入**，无需手动 import
5. 列表页复用 `useCrudTable` 组合式函数，避免重复样板
6. 类型检查请用 `node_modules/.bin/vue-tsc --noEmit`，**不要用 `npx vue-tsc`**（npx 缓存版本与本地 TypeScript 6.0 不兼容）
7. `src/assets/` 中的 `hero.png`、`vite.svg`、`vue.svg` 为 Vite 模板残留，未被引用

## 当前状态

- **已实现**：登录、三端全部页面、路由守卫、角色动态菜单、周课表网格、成绩录入、选课、考试、评价、公告、统计
- **V0.2 待完善**：学生端培养方案页面、Excel 导入导出界面、调停课申请页面

## 相关文档

- [ARCHITECTURE.md](../docs/ARCHITECTURE.md) — 架构与前端结构
- [API.md](../docs/API.md) — 后端接口
- [DEVELOPMENT.md](../docs/DEVELOPMENT.md) — 开发规范
