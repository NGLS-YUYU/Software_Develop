<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { courseApi, curriculumApi, majorApi } from '@/api'
import { useCrudTable } from '@/composables/useCrudTable'
import type { Course, CurriculumCourse, CurriculumPlan, Major } from '@/types'

const majors = ref<Major[]>([])
const allCourses = ref<Course[]>([])

const t = useCrudTable<CurriculumPlan>(curriculumApi, {
  entityName: '培养方案',
  emptyForm: () => ({
    code: '', name: '', major_id: undefined,
    grade_year: new Date().getFullYear(),
    total_credits_required: 160, required_credits: 120, elective_credits: 40,
    status: 'DRAFT',
  }),
})

const STATUS: Record<string, string> = { DRAFT: '草稿', PUBLISHED: '已发布', ARCHIVED: '已归档' }
const STATUS_TYPE: Record<string, string> = { DRAFT: 'info', PUBLISHED: 'success', ARCHIVED: 'warning' }

const detailVisible = ref(false)
const plan = ref<CurriculumPlan | null>(null)
const planCourses = ref<CurriculumCourse[]>([])
const addCourseId = ref<number | undefined>(undefined)
const addSemester = ref(1)
const addRequired = ref(true)

async function openDetail(row: CurriculumPlan) {
  plan.value = row
  planCourses.value = await curriculumApi.courses(row.id)
  detailVisible.value = true
}

async function addCourse() {
  if (!plan.value || !addCourseId.value) {
    ElMessage.warning('请选择课程')
    return
  }
  await curriculumApi.addCourse(plan.value.id, addCourseId.value, addSemester.value, addRequired.value)
  ElMessage.success('已添加')
  planCourses.value = await curriculumApi.courses(plan.value.id)
  addCourseId.value = undefined
}

async function removeCourse(row: CurriculumCourse) {
  if (!plan.value) return
  await curriculumApi.removeCourse(plan.value.id, row.id)
  planCourses.value = await curriculumApi.courses(plan.value.id)
}

function totalCredits() {
  return planCourses.value.reduce((s, c) => s + Number(c.credits ?? 0), 0)
}

onMounted(async () => {
  const [m, c] = await Promise.allSettled([
    majorApi.list({ page_size: 200 }),
    courseApi.list({ page_size: 200 }),
  ])
  if (m.status === 'fulfilled') majors.value = m.value.items
  if (c.status === 'fulfilled') allCourses.value = c.value.items
  await t.load()
})
</script>

<template>
  <el-card shadow="never" class="page-card">
    <!-- 筛选区：搜索 + 专业筛选在左，新增主操作在右 -->
    <div class="toolbar">
      <el-input
        v-model="t.query.keyword"
        class="toolbar__search"
        placeholder="方案代码或名称"
        clearable
        @keyup.enter="t.search"
        @clear="t.search"
      />
      <el-select
        v-model="t.query.major_id"
        class="toolbar__major"
        placeholder="全部专业"
        clearable
        @change="t.search"
      >
        <el-option v-for="m in majors" :key="m.id" :label="m.name" :value="m.id" />
      </el-select>
      <el-button type="primary" @click="t.search">查询</el-button>
      <div class="spacer" />
      <el-button type="primary" :icon="'Plus'" @click="t.openCreate">新增方案</el-button>
    </div>

    <!-- 桌面：方案表格 -->
    <div class="table-wrap" v-show="t.rows.value.length || t.loading.value">
      <el-table v-loading="t.loading.value" :data="t.rows.value" stripe>
        <el-table-column prop="code" label="方案代码" width="130" />
        <el-table-column prop="name" label="方案名称" min-width="200" />
        <el-table-column prop="major_name" label="适用专业" min-width="160" />
        <el-table-column prop="grade_year" label="年级" width="90" align="center" />
        <el-table-column label="总学分" width="90" align="center">
          <template #default="{ row }">{{ row.total_credits_required }}</template>
        </el-table-column>
        <el-table-column label="必修/选修" width="120" align="center">
          <template #default="{ row }">
            {{ row.required_credits }} / {{ row.elective_credits }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="STATUS_TYPE[row.status] as any" size="small">
              {{ STATUS[row.status] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openDetail(row)">课程</el-button>
            <el-button size="small" link type="primary" @click="t.openEdit(row)">编辑</el-button>
            <el-button size="small" link type="danger" @click="t.remove(row, row.name)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 移动端：方案卡片列表 -->
    <div class="plan-cards" v-show="t.rows.value.length">
      <article v-for="row in t.rows.value" :key="row.id" class="pcard">
        <header class="pcard__head">
          <div class="pcard__title">
            <span class="pcard__name">{{ row.name }}</span>
            <span class="pcard__code muted">{{ row.code }}</span>
          </div>
          <el-tag :type="STATUS_TYPE[row.status] as any" size="small">
            {{ STATUS[row.status] }}
          </el-tag>
        </header>

        <div class="pcard__facts">
          <div class="pfact">
            <span class="pfact__label muted">适用专业</span>
            <span class="pfact__value">{{ row.major_name || '—' }}</span>
          </div>
          <div class="pfact">
            <span class="pfact__label muted">适用年级</span>
            <span class="pfact__value">{{ row.grade_year }}</span>
          </div>
          <div class="pfact">
            <span class="pfact__label muted">毕业总学分</span>
            <span class="pfact__value">{{ row.total_credits_required }}</span>
          </div>
          <div class="pfact">
            <span class="pfact__label muted">必修 / 选修</span>
            <span class="pfact__value">{{ row.required_credits }} / {{ row.elective_credits }}</span>
          </div>
        </div>

        <footer class="pcard__foot">
          <el-button size="small" @click="openDetail(row)">课程</el-button>
          <el-button size="small" @click="t.openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" plain @click="t.remove(row, row.name)">删除</el-button>
        </footer>
      </article>
    </div>

    <!-- 空状态 -->
    <el-empty
      v-if="!t.loading.value && !t.rows.value.length"
      description="暂无培养方案，可点击右上角「新增方案」新建，或调整筛选条件重试"
    />

    <div class="pager">
      <el-pagination v-model:current-page="t.query.page" :total="t.total.value"
        :page-size="t.query.page_size" layout="total, prev, pager, next" @current-change="t.load" />
    </div>

    <el-dialog v-model="t.dialogVisible.value"
      :title="t.dialogMode.value === 'create' ? '新增培养方案' : '编辑培养方案'" width="520px">
      <el-form label-width="110px">
        <el-form-item label="方案代码" required>
          <el-input v-model="t.form.value.code" :disabled="t.dialogMode.value === 'edit'"
            maxlength="30" />
        </el-form-item>
        <el-form-item label="方案名称" required>
          <el-input v-model="t.form.value.name" maxlength="100" />
        </el-form-item>
        <el-form-item label="适用专业" required>
          <el-select v-model="t.form.value.major_id" :disabled="t.dialogMode.value === 'edit'"
            style="width: 100%">
            <el-option v-for="m in majors" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="适用年级" required>
          <el-input-number v-model="t.form.value.grade_year" :min="1900" :max="2200"
            :disabled="t.dialogMode.value === 'edit'" />
        </el-form-item>
        <el-form-item label="毕业总学分" required>
          <el-input-number v-model="t.form.value.total_credits_required" :min="1" :max="300"
            :precision="1" />
        </el-form-item>
        <el-form-item label="必修学分" required>
          <el-input-number v-model="t.form.value.required_credits" :min="0" :max="300"
            :precision="1" />
        </el-form-item>
        <el-form-item label="选修学分" required>
          <el-input-number v-model="t.form.value.elective_credits" :min="0" :max="300"
            :precision="1" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="t.form.value.status" style="width: 100%">
            <el-option label="草稿" value="DRAFT" />
            <el-option label="已发布" value="PUBLISHED" />
            <el-option label="已归档" value="ARCHIVED" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="t.dialogVisible.value = false">取消</el-button>
        <el-button type="primary" :loading="t.saving.value" @click="t.save()">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailVisible" :title="`方案课程 — ${plan?.name}`" width="760px">
      <!-- 学分结构：紧凑指标行，独立于课程列表 -->
      <div class="credit-row">
        <div class="credit">
          <span class="credit__label muted">毕业总学分</span>
          <span class="credit__value">{{ plan?.total_credits_required ?? '—' }}</span>
        </div>
        <div class="credit">
          <span class="credit__label muted">必修学分</span>
          <span class="credit__value">{{ plan?.required_credits ?? '—' }}</span>
        </div>
        <div class="credit">
          <span class="credit__label muted">选修学分</span>
          <span class="credit__value">{{ plan?.elective_credits ?? '—' }}</span>
        </div>
      </div>

      <div class="toolbar">
        <el-select v-model="addCourseId" class="toolbar__course" placeholder="选择课程" filterable>
          <el-option v-for="c in allCourses" :key="c.id"
            :label="`${c.code} ${c.name} (${c.credits}学分)`" :value="c.id" />
        </el-select>
        <el-select v-model="addSemester" class="toolbar__sem">
          <el-option v-for="s in 8" :key="s" :label="`第 ${s} 学期`" :value="s" />
        </el-select>
        <el-checkbox v-model="addRequired">必修</el-checkbox>
        <el-button type="primary" @click="addCourse">添加</el-button>
        <div class="spacer" />
        <el-tag type="info">共 {{ planCourses.length }} 门 / {{ totalCredits() }} 学分</el-tag>
      </div>

      <!-- 桌面：课程表格 -->
      <div class="table-wrap" v-show="planCourses.length">
        <el-table :data="planCourses" max-height="420" size="small" stripe>
          <el-table-column prop="course_code" label="课程代码" width="110" />
          <el-table-column prop="course_name" label="课程名称" min-width="170" />
          <el-table-column prop="credits" label="学分" width="80" align="center" />
          <el-table-column label="建议学期" width="100" align="center">
            <template #default="{ row }">第 {{ row.suggested_semester }} 学期</template>
          </el-table-column>
          <el-table-column label="性质" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="row.is_required ? 'danger' : 'info'" size="small">
                {{ row.is_required ? '必修' : '选修' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" align="center">
            <template #default="{ row }">
              <el-button size="small" link type="danger" @click="removeCourse(row)">移除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 移动端：课程卡片列表 -->
      <div class="course-cards" v-show="planCourses.length">
        <article v-for="row in planCourses" :key="row.id" class="ccard">
          <header class="ccard__head">
            <div class="ccard__title">
              <span class="ccard__name">{{ row.course_name }}</span>
              <span class="ccard__code muted">{{ row.course_code }}</span>
            </div>
            <el-tag :type="row.is_required ? 'danger' : 'info'" size="small">
              {{ row.is_required ? '必修' : '选修' }}
            </el-tag>
          </header>
          <div class="ccard__meta">
            <span><b>{{ row.credits }}</b> 学分</span>
            <span class="muted">建议第 {{ row.suggested_semester }} 学期</span>
          </div>
          <footer class="ccard__foot">
            <el-button size="small" type="danger" plain @click="removeCourse(row)">移除</el-button>
          </footer>
        </article>
      </div>

      <el-empty
        v-if="!planCourses.length"
        description="该方案尚未添加课程，请在上方选择课程后点击「添加」"
        :image-size="70"
      />
    </el-dialog>
  </el-card>
</template>

<style scoped lang="scss">
/* ------------------------------------------------------------ 工具栏控件 */
.toolbar__search {
  width: 220px;
}

.toolbar__major {
  width: 180px;
}

.toolbar__course {
  width: 260px;
}

.toolbar__sem {
  width: 130px;
}

/* 桌面表格容器：占满整行 */
.table-wrap {
  width: 100%;
}

/* ------------------------------------------------ 方案卡片（移动端列表） */
.plan-cards {
  display: none;
  flex-direction: column;
  gap: 12px;
}

.pcard {
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface);
  overflow: hidden;
  transition: border-color 0.16s ease, box-shadow 0.16s ease;

  &:hover {
    border-color: var(--uams-border-strong);
    box-shadow: var(--uams-shadow-sm);
  }

  &__head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
    padding: 12px 14px;
    background: var(--uams-surface-sunken);
    border-bottom: 1px solid var(--uams-border);
  }

  &__title {
    min-width: 0;
  }

  &__name {
    display: block;
    font-weight: 600;
    color: var(--uams-text);
  }

  &__code {
    display: block;
    margin-top: 2px;
    font-size: 12px;
  }

  &__facts {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px 14px;
    padding: 14px;
  }

  &__foot {
    display: flex;
    gap: 10px;
    padding: 12px 14px 14px;
    border-top: 1px solid var(--uams-border);

    .el-button {
      flex: 1;
      margin-left: 0;
    }
  }
}

.pfact {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;

  &__label {
    font-size: 12px;
  }

  &__value {
    font-size: 14px;
    font-weight: 600;
    color: var(--uams-text);
    font-variant-numeric: tabular-nums;
  }
}

/* ------------------------------------------------ 学分结构紧凑指标行 */
.credit-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.credit {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 14px;
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface-sunken);
  border: 1px solid var(--uams-border);

  &__label {
    font-size: 12px;
  }

  &__value {
    font-size: 20px;
    font-weight: 700;
    line-height: 1.2;
    color: var(--uams-text);
    font-variant-numeric: tabular-nums;
  }
}

/* ------------------------------------------------ 课程卡片（移动端详情） */
.course-cards {
  display: none;
  flex-direction: column;
  gap: 10px;
}

.ccard {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface);

  &__head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
  }

  &__title {
    min-width: 0;
  }

  &__name {
    display: block;
    font-weight: 600;
    color: var(--uams-text);
  }

  &__code {
    display: block;
    margin-top: 2px;
    font-size: 12px;
  }

  &__meta {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 16px;
    font-size: 13px;
    color: var(--uams-text-2);

    b {
      color: var(--uams-text);
      font-variant-numeric: tabular-nums;
    }
  }

  &__foot {
    display: flex;
    justify-content: flex-end;
  }
}

/* ------------------------------------------------------------- 响应式 */
@media (max-width: 768px) {
  /* 表格换成卡片列表，避免横向溢出 */
  .table-wrap {
    display: none;
  }

  .plan-cards,
  .course-cards {
    display: flex;
  }

  .toolbar__search,
  .toolbar__major,
  .toolbar__course,
  .toolbar__sem {
    width: 100%;
  }

  .pcard__foot .el-button {
    height: 38px;
  }
}

@media (max-width: 420px) {
  .pcard__facts {
    grid-template-columns: minmax(0, 1fr);
  }

  .credit-row {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
