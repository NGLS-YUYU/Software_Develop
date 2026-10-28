# UAMS V3.2 表单标签关联修复报告

> 日期：2026-10-29
> 分支：`main`
> 问题：Chrome DevTools Issues — `Incorrect use of <label for=FORM_ELEMENT>`
> 范围：仅修复确认的 Element Plus 复合控件标签关联，不做全站无障碍重构
> 正式库：未修改；后端：未修改；node_modules：未修改

---

## 1. 问题定位

在真实页面 DOM 中检查 `label[for]` 与目标元素，确认违规来自 Element Plus 表单：

- `el-form-item label` 会自动生成 `<label for="...">`，其 `for` 指向唯一注册控件的 id；
- `el-radio-group` / `el-slider` 的根节点是 `div`，Element Plus 将 id 放在根 `div` 上；
- `<label for>` 指向非可标注表单元素（`DIV`），触发 Chrome Issue。

确认的违规控件：

| 页面 | 字段 | 控件 |
|---|---|---|
| 学生管理 | 性别 | `el-radio-group` |
| 教师管理 | 性别 | `el-radio-group` |
| 课程管理 | 考核方式 | `el-radio-group` |
| 学期管理 | 学期序号 | `el-radio-group` |
| 考试管理 | 考试类型 | `el-radio-group` |
| 公告管理 | 面向对象 | `el-radio-group` |
| 组织机构 | 学院状态 | `el-radio-group` |
| 学生评价 | 评分 | `el-slider` |

未发现手写原生 `<label for>`；其余单输入控件（input/select/date-picker/input-number/textarea/switch）的标签目标均为有效表单元素。

---

## 2. 修复方式

新增应用层指令 `frontend/src/directives/controlId.ts`：

- 组件挂载/更新时，在复合控件内部查找第一个 `input/textarea/select`；
- 为其设置稳定 id；
- FormItem 的 `for` 指向该 id。

示例：

```vue
<el-form-item label="性别" for="student-gender">
  <el-radio-group v-model="form.gender" v-control-id="'student-gender'">
    <el-radio value="MALE">男</el-radio>
    ...
  </el-radio-group>
</el-form-item>
```

效果：

- `<label for="student-gender">` 指向真实 radio input；
- 点击标签可聚焦首个 radio（已验证 `activeElement`）；
- 不再出现指向 `div` 的无效 label；
- 未修改 Element Plus `node_modules`。

---

## 3. 修改文件

- `frontend/src/directives/controlId.ts`（新增）
- `frontend/src/main.ts`（注册指令）
- `frontend/src/views/admin/Students.vue`
- `frontend/src/views/admin/Teachers.vue`
- `frontend/src/views/admin/Courses.vue`
- `frontend/src/views/admin/Terms.vue`
- `frontend/src/views/admin/Exams.vue`
- `frontend/src/views/admin/AnnouncementManage.vue`
- `frontend/src/views/admin/Organization.vue`
- `frontend/src/views/student/Evaluation.vue`
- `docs/TESTING.md`（新增 §4.4）

---

## 4. 验证结果

| 检查 | 结果 |
|---|---|
| `npm run build` | 通过 |
| DOM 扫描（已检查页面/弹窗） | `label[for]` 均指向 INPUT/TEXTAREA，无 DIV/不存在目标 |
| 点击性别标签 | 聚焦 `student-gender`（radio）通过 |
| 学生表单 E2E | 新增/编辑/删除/失败保留全部通过 |
| 多页面 E2E | 课程/教学班/学期/公告/选课/成绩审核全部通过 |
| 后端 | 未修改，无需回归 |
| 正式数据库 | 未修改 |

未覆盖：未直接读取 Chrome DevTools Issues 面板（使用等价 DOM 规则检查）；其余未打开的表单弹窗未逐一枚举。

---

## 5. 发布状态

- 当前 live：`/var/www/uams/current` → `releases/20261029_023646`（`index-w-iuU7Xf.js`，不含本次标签修复）；
- 最新构建：`frontend/dist`（`index-Bp_4vmXA.js`，含本次标签修复）；
- **最新构建尚未发布**，且未经授权不执行发布。
- 发布需授权后执行：

```bash
cd /home/nglsyuyu/Software_Develop/Software_Develop/uams
bash deploy/deploy-frontend.sh
```

发布后应在 Chrome DevTools Issues 面板复核该问题消失。

---

## 6. 结论

已确认并修复应用层 Element Plus 复合控件的无效 `label for` 关联，未改第三方源码、后端或数据库；构建与相关 E2E 通过。正式站点需授权发布后生效。

