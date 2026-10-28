<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { collegeApi, courseApi, exportApi } from '@/api'
import { useCrudTable } from '@/composables/useCrudTable'
import type { College, Course, Prerequisite } from '@/types'

const colleges = ref<College[]>([])
const allCourses = ref<Course[]>([])

const t = useCrudTable<Course>(courseApi, {
  entityName: '课程',
  emptyForm: () => ({
    code: '', name: '', college_id: undefined, course_type: 'REQUIRED',
    credits: 3, total_hours: 48, theory_hours: 48, practice_hours: 0,
    exam_type: 'EXAM',
    description: '', status: 'ACTIVE',
  }),
  afterMutation: loadCourses,
})

const TYPE: Record<string, string> = {
  REQUIRED: '专业必修', ELECTIVE: '专业选修', PUBLIC_REQUIRED: '公共必修',
  PUBLIC_ELECTIVE: '公共选修', PRACTICE: '实践',
}

/** 成绩考核结构由总学时唯一推导（FIX-009 §三）：教务/教师不可自行选择权重。 */
const assessmentHint = computed(() => {
  const h = Number(t.form.value.total_hours ?? 0)
  if (h <= 32) return '两段式：平时 20% + 期末 80%（无期中）'
  return '三段式：平时 20% + 期中 30% + 期末 50%'
})

/** FIX-009 §四/§五：理论 + 实践 = 总学时，前端先校验，非法数据不提交后端。 */
function hoursError(): string | null {
  const total = Number(t.form.value.total_hours ?? 0)
  const theory = Number(t.form.value.theory_hours ?? 0)
  const practice = Number(t.form.value.practice_hours ?? 0)
  if (theory + practice !== total) {
    return (
      `理论课时 + 实践课时必须等于总学时（${total}）。` +
      `当前：理论 ${theory} + 实践 ${practice} = ${theory + practice}。`
    )
  }
  return null
}

async function save() {
  const err = hoursError()
  if (err) {
    ElMessage.error(err)
    return
  }
  await t.save()
}

// 先修课程管理
const preVisible = ref(false)
const preList = ref<Prerequisite[]>([])
const preCourse = ref<Course | null>(null)
const preTarget = ref<number | undefined>(undefined)
const preScore = ref(60)

async function openPrereq(row: Course) {
  preCourse.value = row
  preList.value = await courseApi.prerequisites(row.id)
  preTarget.value = undefined
  preVisible.value = true
}

async function addPrereq() {
  if (!preCourse.value || !preTarget.value) {
    ElMessage.warning('请选择先修课程')
    return
  }
  // 环路（A→B→A）由后端图检测拦截，这里只发请求
  await courseApi.addPrerequisite(preCourse.value.id, preTarget.value, preScore.value)
  ElMessage.success('已添加先修课程')
  preList.value = await courseApi.prerequisites(preCourse.value.id)
  preTarget.value = undefined
}

async function delPrereq(row: Prerequisite) {
  if (!preCourse.value) return
  await courseApi.removePrerequisite(preCourse.value.id, row.id)
  preList.value = await courseApi.prerequisites(preCourse.value.id)
}

async function loadCourses() {
  const res = await courseApi.list({ page_size: 200 })
  allCourses.value = res.items
}

onMounted(async () => {
  const c = await collegeApi.list({ page_size: 200 })
  colleges.value = c.items
  await t.load()
  await loadCourses()
})
</script>

<template>
  <el-card class="page-card" shadow="never">
    <!-- 筛选 + 主操作：查询在左，新增在右 -->
    <div class="toolbar">
      <el-select v-model="t.query.college_id" placeholder="全部学院" clearable
        style="width: 180px" @change="t.search">
        <el-option v-for="c in colleges" :key="c.id" :label="c.name" :value="c.id" />
      </el-select>
      <el-select v-model="t.query.course_type" placeholder="全部类型" clearable
        style="width: 150px" @change="t.search">
        <el-option v-for="(v, k) in TYPE" :key="k" :label="v" :value="k" />
      </el-select>
      <el-input v-model="t.query.keyword" placeholder="课程代码或名称" style="width: 200px"
        clearable @keyup.enter="t.search" @clear="t.search" />
      <el-button type="primary" @click="t.search">查询</el-button>
      <div class="spacer" />
      <el-button @click="exportApi.courses()">导出 Excel</el-button>
      <el-button type="primary" :icon="'Plus'" @click="t.openCreate">新增课程</el-button>
    </div>

    <!-- 桌面：表格 -->
    <div class="table-wrap">
      <el-table v-loading="t.loading.value" :data="t.rows.value" stripe>
        <el-table-column prop="code" label="课程代码" width="112" />
        <el-table-column prop="name" label="课程名称" min-width="180" />
        <el-table-column prop="college_name" label="开课学院" min-width="150" />
        <el-table-column label="课程性质" width="118">
          <template #default="{ row }">
            <el-tag size="small" effect="plain"
              :type="row.course_type === 'REQUIRED' || row.course_type === 'PUBLIC_REQUIRED'
                ? 'primary'
                : row.course_type === 'PRACTICE' ? 'warning' : 'info'">
              {{ TYPE[row.course_type] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="credits" label="学分" width="76" align="center" />
        <el-table-column label="学时" width="176">
          <template #default="{ row }">
            <span class="hours-cell">
              <b class="hours-cell__total">{{ row.total_hours }}</b>
              <span class="hours-cell__sub">
                （理论 {{ row.theory_hours }} · 实践 {{ row.practice_hours }}）
              </span>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="考核" width="116" align="center">
          <template #default="{ row }">
            <div class="exam-cell">
              <span class="exam-cell__type">
                {{ row.exam_type === 'EXAM' ? '考试' : '考查' }}
              </span>
              <span class="exam-cell__sub">
                {{ Number(row.total_hours ?? 0) <= 32 ? '两段式' : '三段式' }}
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openPrereq(row)">先修</el-button>
            <el-button size="small" link type="primary" @click="t.openEdit(row)">编辑</el-button>
            <el-button size="small" link type="danger" @click="t.remove(row, row.name)">
              删除
            </el-button>
          </template>
        </el-table-column>

        <template #empty>
          <el-empty description="没有符合条件的课程，试试调整筛选条件，或新增一门课程" :image-size="90" />
        </template>
      </el-table>
    </div>

    <!-- 窄屏：卡片列表，主字段 + 关键状态 + 操作 -->
    <div class="course-cards">
      <el-empty v-if="!t.rows.value.length"
        description="没有符合条件的课程，试试调整筛选条件，或新增一门课程" :image-size="90" />
      <article v-for="row in t.rows.value" :key="row.id" class="ccard">
        <header class="ccard__head">
          <div class="ccard__title">
            <span class="ccard__name">{{ row.name }}</span>
            <span class="ccard__code">{{ row.code }}</span>
          </div>
          <el-tag size="small" effect="plain"
            :type="row.course_type === 'REQUIRED' || row.course_type === 'PUBLIC_REQUIRED'
              ? 'primary'
              : row.course_type === 'PRACTICE' ? 'warning' : 'info'">
            {{ TYPE[row.course_type] }}
          </el-tag>
        </header>

        <div class="ccard__college muted">{{ row.college_name || '未指定学院' }}</div>

        <dl class="ccard__stats">
          <div>
            <dt>学分</dt>
            <dd>{{ row.credits }}</dd>
          </div>
          <div>
            <dt>总学时</dt>
            <dd>{{ row.total_hours }}</dd>
          </div>
          <div>
            <dt>理论 / 实践</dt>
            <dd>{{ row.theory_hours }} / {{ row.practice_hours }}</dd>
          </div>
          <div>
            <dt>考核</dt>
            <dd>
              {{ row.exam_type === 'EXAM' ? '考试' : '考查' }}
              <span class="ccard__dim">· {{ Number(row.total_hours ?? 0) <= 32 ? '两段式' : '三段式' }}</span>
            </dd>
          </div>
        </dl>

        <div class="ccard__actions">
          <el-button size="small" plain @click="openPrereq(row)">先修</el-button>
          <el-button size="small" type="primary" plain @click="t.openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" plain @click="t.remove(row, row.name)">删除</el-button>
        </div>
      </article>
    </div>

    <div class="pager">
      <el-pagination v-model:current-page="t.query.page" :total="t.total.value"
        :page-size="t.query.page_size" layout="total, prev, pager, next" @current-change="t.load" />
    </div>

    <!-- 课程表单 -->
    <el-dialog v-model="t.dialogVisible.value"
      :title="t.dialogMode.value === 'create' ? '新增课程' : '编辑课程'" width="560px">
      <el-form label-width="110px">
        <el-form-item label="课程代码" required>
          <el-input v-model="t.form.value.code" maxlength="30" />
        </el-form-item>
        <el-form-item label="课程名称" required>
          <el-input v-model="t.form.value.name" maxlength="100" />
        </el-form-item>
        <el-form-item label="开课学院" required>
          <el-select v-model="t.form.value.college_id" style="width: 100%">
            <el-option v-for="c in colleges" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="课程类型" required>
          <el-select v-model="t.form.value.course_type" style="width: 100%">
            <el-option v-for="(v, k) in TYPE" :key="k" :label="v" :value="k" />
          </el-select>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="学分" required>
              <el-input-number v-model="t.form.value.credits" :min="0.5" :max="30"
                :step="0.5" :precision="1" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="总学时" required>
              <el-input-number v-model="t.form.value.total_hours" :min="0" :max="500"
                style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="理论学时">
              <el-input-number v-model="t.form.value.theory_hours" :min="0" :max="500"
                style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="实践学时">
              <el-input-number v-model="t.form.value.practice_hours" :min="0" :max="500"
                style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>

        <!-- 学时成组即时呈现：总学时（理论 · 实践），并即时标注是否配平 -->
        <el-form-item label="学时构成">
          <div class="hours-inline">
            <b class="hours-inline__total">{{ t.form.value.total_hours ?? 0 }}</b>
            <span class="hours-inline__sub">
              理论 {{ t.form.value.theory_hours ?? 0 }} · 实践 {{ t.form.value.practice_hours ?? 0 }}
            </span>
            <span class="hours-inline__sum"
              :class="hoursError() ? 'is-error' : 'is-ok'">
              理论 + 实践 = {{ Number(t.form.value.theory_hours ?? 0) + Number(t.form.value.practice_hours ?? 0) }}
            </span>
          </div>
        </el-form-item>
        <el-form-item v-if="hoursError()">
          <el-alert :title="hoursError() || ''" type="error" :closable="false" show-icon />
        </el-form-item>

        <el-form-item label="考核方式">
          <el-radio-group v-model="t.form.value.exam_type">
            <el-radio value="EXAM">考试</el-radio>
            <el-radio value="CHECK">考查</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="成绩考核结构">
          <el-alert
            :title="`${assessmentHint}（由总学时自动决定，不可手动选择）`"
            type="info"
            :closable="false"
            show-icon
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="课程简介">
          <el-input v-model="t.form.value.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="t.dialogVisible.value = false">取消</el-button>
        <el-button type="primary" :loading="t.saving.value" @click="save">确定</el-button>
      </template>
    </el-dialog>

    <!-- 先修课程 -->
    <el-dialog v-model="preVisible" :title="`先修课程 — ${preCourse?.name}`" width="600px">
      <div class="toolbar pre-add">
        <el-select v-model="preTarget" placeholder="选择先修课程" filterable class="pre-add__select">
          <el-option v-for="c in allCourses.filter(x => x.id !== preCourse?.id)"
            :key="c.id" :label="`${c.code} ${c.name}`" :value="c.id" />
        </el-select>
        <el-input-number v-model="preScore" :min="0" :max="100" :step="5"
          class="pre-add__score" />
        <el-button type="primary" @click="addPrereq">添加</el-button>
      </div>
      <el-table :data="preList" size="small">
        <el-table-column prop="prerequisite_code" label="课程代码" width="120" />
        <el-table-column prop="prerequisite_name" label="课程名称" min-width="180" />
        <el-table-column prop="min_score" label="最低成绩" width="100" align="center" />
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="danger" @click="delPrereq(row)">移除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="该课程尚未设置先修课程" :image-size="60" />
        </template>
      </el-table>
      <el-alert type="info" :closable="false" show-icon style="margin-top: 12px"
        title="系统会自动检测先修关系环路（如 A→B→A），形成环路时将拒绝添加" />
    </el-dialog>
  </el-card>
</template>

<style scoped lang="scss">
/* --------------------------------------------------------------- 列表单元 */
/* 学时成组：总学时突出，理论/实践以括号次要信息紧随其后 */
.hours-cell {
  display: inline-flex;
  align-items: baseline;
  gap: 2px;
  white-space: nowrap;

  &__total {
    font-size: 14px;
    font-weight: 600;
    color: var(--uams-text);
    font-variant-numeric: tabular-nums;
  }

  &__sub {
    font-size: 12px;
    color: var(--uams-text-3);
  }
}

/* 考核：方式主、两段式/三段式次 */
.exam-cell {
  display: inline-flex;
  flex-direction: column;
  line-height: 1.35;

  &__type {
    color: var(--uams-text-2);
  }

  &__sub {
    font-size: 12px;
    color: var(--uams-text-3);
  }
}

/* --------------------------------------------------- 表单：学时构成反馈 */
.hours-inline {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 4px 10px;
  width: 100%;
  padding: 8px 12px;
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface-sunken);
  border: 1px solid var(--uams-border);

  &__total {
    font-size: 18px;
    font-weight: 700;
    color: var(--uams-primary-dark);
    font-variant-numeric: tabular-nums;
  }

  &__sub {
    font-size: 13px;
    color: var(--uams-text-2);
    font-variant-numeric: tabular-nums;
  }

  /* 配平状态：右对齐的轻声校验标记 */
  &__sum {
    margin-left: auto;
    font-size: 12px;
    font-variant-numeric: tabular-nums;

    &.is-ok {
      color: var(--uams-success);
    }

    &.is-error {
      color: var(--uams-danger);
      font-weight: 600;
    }
  }
}

/* 先修课程弹窗的操作条 */
.pre-add {
  &__select {
    width: 260px;
  }

  &__score {
    width: 130px;
  }
}

/* --------------------------------------------------------- 窄屏卡片列表 */
.course-cards {
  display: none;
  flex-direction: column;
  gap: 12px;
}

.ccard {
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface);
  overflow: hidden;

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
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  &__name {
    font-weight: 600;
    color: var(--uams-text);
  }

  &__code {
    margin-top: 2px;
    font-size: 12px;
    color: var(--uams-text-3);
    font-variant-numeric: tabular-nums;
  }

  &__college {
    padding: 10px 14px 0;
    font-size: 13px;
  }

  &__stats {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    margin: 0;
    padding: 12px 14px;

    > div {
      display: flex;
      flex-direction: column;
      gap: 2px;
      padding: 8px 10px;
      border-radius: var(--uams-radius-xs);
      background: var(--uams-surface-sunken);
      border: 1px solid var(--uams-border);
    }

    dt {
      font-size: 12px;
      color: var(--uams-text-3);
    }

    dd {
      margin: 0;
      font-size: 15px;
      font-weight: 600;
      color: var(--uams-text);
      font-variant-numeric: tabular-nums;
    }
  }

  &__dim {
    font-size: 12px;
    font-weight: 500;
    color: var(--uams-text-3);
  }

  &__actions {
    display: flex;
    gap: 8px;
    padding: 0 14px 14px;

    .el-button {
      flex: 1;
      margin-left: 0;
    }
  }
}

/* ------------------------------------------------------------- 响应式 */
@media (max-width: 768px) {
  .table-wrap {
    display: none;
  }

  .course-cards {
    display: flex;
  }

  /* 先修操作条：选择框占满整行 */
  .pre-add {
    &__select,
    &__score {
      width: 100%;
    }
  }
}
</style>
