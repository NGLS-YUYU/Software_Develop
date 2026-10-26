<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { classApi, collegeApi, exportApi, majorApi, studentApi } from '@/api'
import { useCrudTable } from '@/composables/useCrudTable'
import type { ClassInfo, College, Major, Student } from '@/types'
import { isValidEmail, normalizeEmailInput } from '@/utils/email'

const colleges = ref<College[]>([])
const majors = ref<Major[]>([])
const classes = ref<ClassInfo[]>([])

const t = useCrudTable<Student>(studentApi as never, {
  entityName: '学生',
  emptyForm: () => ({
    student_no: '',
    real_name: '',
    class_id: undefined,
    gender: 'UNKNOWN',
    birth_date: undefined,
    enrollment_year: new Date().getFullYear(),
    email: '',
    phone: '',
    password: '',
  }),
})

const GENDER: Record<string, string> = { MALE: '男', FEMALE: '女', UNKNOWN: '-' }
const STATUS: Record<string, string> = {
  ENROLLED: '在读', SUSPENDED: '休学', GRADUATED: '毕业', WITHDRAWN: '退学',
}
const STATUS_TYPE: Record<string, string> = {
  ENROLLED: 'success', SUSPENDED: 'warning', GRADUATED: 'info', WITHDRAWN: 'danger',
}

/** 新增时不传空密码，让后端用「默认密码=学号」的规则。 */
function payload(): Record<string, unknown> | null {
  const f = { ...t.form.value }

  // FIX-001：空白邮箱统一为 null；非空邮箱先做一次前端格式提示。
  const email = normalizeEmailInput(f.email)
  if (email && !isValidEmail(email)) {
    ElMessage.warning('邮箱格式不正确')
    return null
  }
  f.email = email

  if (!f.password) delete f.password
  if (t.dialogMode.value === 'edit') {
    delete f.student_no
    delete f.password
  }
  return f
}

function save() {
  const body = payload()
  if (body) t.save(body)
}

onMounted(async () => {
  const [c, m, k] = await Promise.allSettled([
    collegeApi.list({ page_size: 200 }),
    majorApi.list({ page_size: 200 }),
    classApi.list({ page_size: 200 }),
  ])
  if (c.status === 'fulfilled') colleges.value = c.value.items
  if (m.status === 'fulfilled') majors.value = m.value.items
  if (k.status === 'fulfilled') classes.value = k.value.items
  await t.load()
})
</script>

<template>
  <el-card shadow="never" class="page-card">
    <div class="toolbar">
      <el-input
        v-model="t.query.keyword"
        placeholder="搜索学号或姓名"
        class="toolbar__search"
        clearable
        @keyup.enter="t.search"
        @clear="t.search"
      />
      <el-select v-model="t.query.college_id" placeholder="全部学院" clearable
        class="toolbar__select" @change="t.search">
        <el-option v-for="c in colleges" :key="c.id" :label="c.name" :value="c.id" />
      </el-select>
      <el-select v-model="t.query.major_id" placeholder="全部专业" clearable
        class="toolbar__select" @change="t.search">
        <el-option v-for="m in majors" :key="m.id" :label="m.name" :value="m.id" />
      </el-select>
      <el-select v-model="t.query.class_id" placeholder="全部班级" clearable
        class="toolbar__select" @change="t.search">
        <el-option v-for="k in classes" :key="k.id" :label="k.name" :value="k.id" />
      </el-select>
      <el-button type="primary" @click="t.search">查询</el-button>
      <div class="spacer" />
      <el-button @click="exportApi.students()">导出 Excel</el-button>
      <el-button type="primary" :icon="'Plus'" @click="t.openCreate">新增学生</el-button>
    </div>

    <div class="list" v-loading="t.loading.value">
      <!-- 桌面端：档案表格（表头次要色、行高舒适、操作列贴右固定） -->
      <div v-if="t.rows.value.length" class="table-wrap">
        <el-table :data="t.rows.value" stripe>
          <el-table-column label="学号" width="140">
            <template #default="{ row }">
              <span class="cell-no">{{ row.student_no }}</span>
            </template>
          </el-table-column>
          <el-table-column label="姓名" width="110">
            <template #default="{ row }">
              <span class="cell-name">{{ row.real_name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="性别" width="70" align="center">
            <template #default="{ row }">{{ GENDER[row.gender] }}</template>
          </el-table-column>
          <el-table-column label="班级" min-width="140">
            <template #default="{ row }">{{ row.class_name || '—' }}</template>
          </el-table-column>
          <el-table-column label="专业" min-width="170">
            <template #default="{ row }">
              <div class="cell-dept">
                <span class="cell-dept__name">{{ row.major_name || '—' }}</span>
                <span v-if="row.college_name" class="cell-dept__college">
                  {{ row.college_name }}
                </span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="enrollment_year" label="入学年份" width="100" align="center" />
          <el-table-column label="学籍" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="STATUS_TYPE[row.academic_status] as any" size="small">
                {{ STATUS[row.academic_status] }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="学分" width="90" align="center">
            <template #default="{ row }">
              <span class="cell-num">{{ row.total_credits }}</span>
            </template>
          </el-table-column>
          <el-table-column label="绩点" width="90" align="center">
            <template #default="{ row }">
              <span class="cell-num" :class="{ 'is-empty': row.gpa == null }">
                {{ row.gpa ?? '—' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="130" align="center" fixed="right">
            <template #default="{ row }">
              <el-button size="small" link type="primary" @click="t.openEdit(row)">编辑</el-button>
              <el-button size="small" link type="danger" @click="t.remove(row, row.real_name)">
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 移动端：每位学生一张卡片，主字段 + 学籍状态 + 操作 -->
      <div v-if="t.rows.value.length" class="stu-cards">
        <article v-for="row in t.rows.value" :key="row.id" class="stu-card">
          <header class="stu-card__head">
            <div class="stu-card__identity">
              <span class="stu-card__name">{{ row.real_name }}</span>
              <span class="stu-card__no">{{ row.student_no }}</span>
            </div>
            <el-tag :type="STATUS_TYPE[row.academic_status] as any" size="small">
              {{ STATUS[row.academic_status] }}
            </el-tag>
          </header>

          <p class="stu-card__dept">
            {{ row.major_name || '—' }} · {{ row.class_name || '—' }}
          </p>
          <p class="stu-card__sub muted">
            <template v-if="row.college_name">{{ row.college_name }} · </template>
            {{ row.enrollment_year }} 级 · {{ GENDER[row.gender] }}
          </p>

          <div class="stu-card__stats">
            <div class="stu-stat">
              <span class="stu-stat__value">{{ row.total_credits }}</span>
              <span class="stu-stat__label">已修学分</span>
            </div>
            <div class="stu-stat">
              <span class="stu-stat__value">{{ row.gpa ?? '—' }}</span>
              <span class="stu-stat__label">绩点 GPA</span>
            </div>
          </div>

          <footer class="stu-card__foot">
            <el-button size="small" @click="t.openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" plain @click="t.remove(row, row.real_name)">
              删除
            </el-button>
          </footer>
        </article>
      </div>

      <!-- 空状态：说明可用操作，而不是「暂无数据」 -->
      <el-empty
        v-if="!t.rows.value.length && !t.loading.value"
        description="没有找到符合条件的学生，可调整筛选条件，或点击「新增学生」录入"
      />
    </div>

    <div class="pager">
      <el-pagination v-model:current-page="t.query.page" :total="t.total.value"
        :page-size="t.query.page_size" :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next" @current-change="t.load" @size-change="t.load" />
    </div>

    <el-dialog v-model="t.dialogVisible.value"
      :title="t.dialogMode.value === 'create' ? '新增学生' : '编辑学生'" width="520px">
      <el-form label-width="100px">
        <el-form-item label="学号" required>
          <el-input v-model="t.form.value.student_no" :disabled="t.dialogMode.value === 'edit'"
            maxlength="30" />
        </el-form-item>
        <el-form-item label="姓名" required>
          <el-input v-model="t.form.value.real_name" maxlength="50" />
        </el-form-item>
        <el-form-item label="班级" required>
          <el-select v-model="t.form.value.class_id" style="width: 100%">
            <el-option v-for="k in classes" :key="k.id" :label="k.name" :value="k.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="性别">
          <el-radio-group v-model="t.form.value.gender">
            <el-radio value="MALE">男</el-radio>
            <el-radio value="FEMALE">女</el-radio>
            <el-radio value="UNKNOWN">未填写</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="出生日期">
          <el-date-picker v-model="t.form.value.birth_date" type="date"
            value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item v-if="t.dialogMode.value === 'create'" label="入学年份" required>
          <el-input-number v-model="t.form.value.enrollment_year" :min="1900" :max="2200" />
        </el-form-item>
        <el-form-item v-if="t.dialogMode.value === 'edit'" label="学籍状态">
          <el-select v-model="t.form.value.academic_status" style="width: 100%">
            <el-option label="在读" value="ENROLLED" />
            <el-option label="休学" value="SUSPENDED" />
            <el-option label="毕业" value="GRADUATED" />
            <el-option label="退学" value="WITHDRAWN" />
          </el-select>
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="t.form.value.email" maxlength="100" />
        </el-form-item>
        <el-form-item label="手机">
          <el-input v-model="t.form.value.phone" maxlength="20" />
        </el-form-item>
        <el-form-item v-if="t.dialogMode.value === 'create'" label="初始密码">
          <el-input v-model="t.form.value.password" placeholder="留空则默认为学号" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="t.dialogVisible.value = false">取消</el-button>
        <el-button type="primary" :loading="t.saving.value" @click="save">
          确定
        </el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<style scoped lang="scss">
/* 工具栏控件尺寸：桌面固定宽度；≤768px 由全局规则撑满整行 */
.toolbar__search {
  width: 220px;
}

.toolbar__select {
  width: 176px;
}

/* --------------------------------------------------------- 桌面表格单元 */
/* 学号：等宽数字 + 加粗，作为第一识别信息 */
.cell-no {
  font-weight: 600;
  color: var(--uams-text);
  letter-spacing: 0.01em;
  font-variant-numeric: tabular-nums;
}

.cell-name {
  font-weight: 600;
  color: var(--uams-text);
}

/* 专业：专业名主行 + 学院次行，形成紧凑层级 */
.cell-dept {
  display: flex;
  flex-direction: column;
  line-height: 1.35;

  &__name {
    color: var(--uams-text-2);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__college {
    font-size: 12px;
    color: var(--uams-text-3);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

/* 学分 / 绩点：等宽数字，同列居中对齐更整齐 */
.cell-num {
  font-weight: 600;
  color: var(--uams-text);
  font-variant-numeric: tabular-nums;

  &.is-empty {
    color: var(--uams-text-3);
    font-weight: 400;
  }
}

/* ------------------------------------------------------- 移动端卡片列表 */
.stu-cards {
  display: none;
  flex-direction: column;
  gap: 12px;
}

.stu-card {
  padding: 14px;
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface);

  &__head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
  }

  &__identity {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  &__name {
    font-size: 16px;
    font-weight: 600;
    line-height: 1.3;
    color: var(--uams-text);
  }

  &__no {
    margin-top: 2px;
    font-size: 12.5px;
    color: var(--uams-text-2);
    font-variant-numeric: tabular-nums;
  }

  &__dept {
    margin: 10px 0 0;
    font-size: 13.5px;
    font-weight: 500;
    color: var(--uams-text-2);
  }

  &__sub {
    margin: 2px 0 0;
    font-size: 12px;
  }

  &__stats {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    margin-top: 12px;
  }

  &__foot {
    display: flex;
    gap: 10px;
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px solid var(--uams-border);

    .el-button {
      flex: 1;
      margin-left: 0;
    }
  }
}

.stu-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 12px;
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface-sunken);
  border: 1px solid var(--uams-border);

  &__value {
    font-size: 20px;
    font-weight: 700;
    line-height: 1.15;
    color: var(--uams-text);
    font-variant-numeric: tabular-nums;
  }

  &__label {
    font-size: 12px;
    color: var(--uams-text-3);
  }
}

/* ------------------------------------------------------------- 响应式 */
@media (max-width: 768px) {
  /* 表格换成卡片列表，操作按钮始终可达 */
  .table-wrap {
    display: none;
  }

  .stu-cards {
    display: flex;
  }

  /* 触控目标加高，便于点按 */
  .stu-card__foot .el-button {
    height: 38px;
  }
}
</style>
