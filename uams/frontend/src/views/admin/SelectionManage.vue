<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { selectionApi, teachingApi } from '@/api'
import { currentSemester, semesterOptions } from '@/composables/useSemester'
import type { SelectionPeriod, TeachingClass } from '@/types'

const semester = ref(currentSemester())
const periods = ref<SelectionPeriod[]>([])
const classes = ref<TeachingClass[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)

const dialog = ref(false)
const form = ref<Record<string, unknown>>({})
const editingId = ref<number | null>(null)
const saving = ref(false)

const rosterVisible = ref(false)
const roster = ref<{ student_no: string; real_name: string; class_name?: string | null }[]>([])
const rosterTitle = ref('')

const STATUS: Record<string, string> = { PENDING: '未开始', ACTIVE: '进行中', CLOSED: '已结束' }
const STATUS_TYPE: Record<string, string> = { PENDING: 'info', ACTIVE: 'success', CLOSED: 'warning' }
const TIME_STATE: Record<string, string> = {
  OPEN: '开放中', NOT_STARTED: '未开始', EXPIRED: '已过期', INACTIVE: '未激活',
}
const TIME_STATE_TYPE: Record<string, string> = {
  OPEN: 'success', NOT_STARTED: 'info', EXPIRED: 'warning', INACTIVE: 'info',
}

/** 实际生效 = 时间开放 + 学期存在且 ACTIVE。 */
function effectiveLabel(row: SelectionPeriod) {
  if (row.is_effective) return '生效中'
  if (row.time_state === 'OPEN') {
    return row.term_status ? `学期${row.term_status}` : '学期不存在'
  }
  return TIME_STATE[row.time_state ?? 'INACTIVE']
}

function effectiveType(row: SelectionPeriod) {
  if (row.is_effective) return 'success'
  if (row.time_state === 'OPEN') return 'danger'
  return TIME_STATE_TYPE[row.time_state ?? 'INACTIVE']
}

/** 同一学期多个 ACTIVE 窗口时间重叠的组数（后端按并集判断）。 */
const overlappingActive = computed(() => {
  const active = periods.value.filter((p) => p.status === 'ACTIVE')
  let pairs = 0
  for (let i = 0; i < active.length; i += 1) {
    for (let j = i + 1; j < active.length; j += 1) {
      if (active[i].semester !== active[j].semester) continue
      const aStart = new Date(active[i].start_time).getTime()
      const aEnd = new Date(active[i].end_time).getTime()
      const bStart = new Date(active[j].start_time).getTime()
      const bEnd = new Date(active[j].end_time).getTime()
      if (aStart < bEnd && bStart < aEnd) pairs += 1
    }
  }
  return pairs
})

function openCreate() {
  editingId.value = null
  form.value = {
    semester: semester.value,
    name: `${semester.value} 正选`,
    start_time: '',
    end_time: '',
    target_grade_year: undefined,
    status: 'PENDING',
  }
  dialog.value = true
}

function openEdit(row: SelectionPeriod) {
  editingId.value = row.id
  form.value = { ...row }
  dialog.value = true
}

async function save() {
  if (!form.value.start_time || !form.value.end_time) {
    ElMessage.warning('请填写开始时间和结束时间')
    return
  }
  if (new Date(String(form.value.end_time)) <= new Date(String(form.value.start_time))) {
    ElMessage.warning('结束时间必须晚于开始时间')
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await selectionApi.updatePeriod(editingId.value, form.value)
      ElMessage.success('已更新')
    } else {
      await selectionApi.createPeriod(form.value)
      ElMessage.success('已创建')
    }
    dialog.value = false
    await loadPeriods()
  } finally {
    saving.value = false
  }
}

async function toggle(row: TeachingClass) {
  const open = row.selection_status !== 'OPEN'
  await teachingApi.toggleSelection(row.id, open)
  ElMessage.success(open ? '已开放选课' : '已关闭选课')
  await loadClasses()
}

async function showRoster(row: TeachingClass) {
  roster.value = await teachingApi.students(row.id)
  rosterTitle.value = `${row.course_name} — 选课名单（${roster.value.length} 人）`
  rosterVisible.value = true
}

async function loadPeriods() {
  periods.value = await selectionApi.periods(semester.value)
}

async function loadClasses() {
  loading.value = true
  try {
    const res = await teachingApi.classes({
      semester: semester.value, page: page.value, page_size: 20,
    })
    classes.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

watch(semester, () => {
  page.value = 1
  loadPeriods()
  loadClasses()
})

onMounted(async () => {
  await loadPeriods()
  await loadClasses()
})
</script>

<template>
  <div v-loading="loading" class="selection-manage">
    <!-- ==================== 选课时间窗口 ==================== -->
    <el-card shadow="never" class="page-card">
      <template #header>
        <div class="card-head">
          <span>选课时间窗口</span>
          <el-button type="primary" size="small" :icon="'Plus'" @click="openCreate">
            新增窗口
          </el-button>
        </div>
      </template>

      <el-alert
        v-if="overlappingActive"
        type="warning"
        :closable="false"
        show-icon
        class="overlap-alert"
        :title="`检测到 ${overlappingActive} 组 ACTIVE 窗口时间重叠；后端按“任一适用窗口开放即可”判断，建议合并重叠窗口。`"
      />

      <!-- 桌面端：表格 -->
      <div class="table-wrap">
        <el-table :data="periods" stripe>
          <el-table-column prop="name" label="名称" min-width="160" />
          <el-table-column prop="semester" label="学期" width="120" />
          <el-table-column label="时间窗口" min-width="300">
            <template #default="{ row }">
              <span class="window">
                <span class="window__time">
                  {{ row.start_time?.slice(0, 16).replace('T', ' ') || '—' }}
                </span>
                <span class="window__sep">~</span>
                <span class="window__time">
                  {{ row.end_time?.slice(0, 16).replace('T', ' ') || '—' }}
                </span>
              </span>
            </template>
          </el-table-column>
          <el-table-column label="限定年级" width="100" align="center">
            <template #default="{ row }">{{ row.target_grade_year ?? '全部' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="STATUS_TYPE[row.status] as any" size="small">
                {{ STATUS[row.status] }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="实际状态" width="110" align="center">
            <template #default="{ row }">
              <el-tag :type="effectiveType(row) as any" size="small" effect="plain">
                {{ effectiveLabel(row) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90" align="center" fixed="right">
            <template #default="{ row }">
              <el-button size="small" link type="primary" @click="openEdit(row)">编辑</el-button>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty
              description="尚未设置选课时间窗口，点击右上角「新增窗口」开始配置"
              :image-size="70"
            />
          </template>
        </el-table>
      </div>

      <!-- 移动端：卡片 -->
      <div class="period-cards">
        <article v-for="row in periods" :key="row.id" class="pcard">
          <header class="pcard__head">
            <div class="pcard__title">
              <span class="pcard__name">{{ row.name }}</span>
              <span class="muted pcard__sem">{{ row.semester }}</span>
            </div>
            <div class="pcard__tags">
              <el-tag :type="STATUS_TYPE[row.status] as any" size="small">
                {{ STATUS[row.status] }}
              </el-tag>
              <el-tag :type="effectiveType(row) as any" size="small" effect="plain">
                {{ effectiveLabel(row) }}
              </el-tag>
            </div>
          </header>

          <span class="window window--block">
            <span class="window__time">
              {{ row.start_time?.slice(0, 16).replace('T', ' ') || '—' }}
            </span>
            <span class="window__sep">~</span>
            <span class="window__time">
              {{ row.end_time?.slice(0, 16).replace('T', ' ') || '—' }}
            </span>
          </span>

          <footer class="pcard__foot">
            <span class="muted pcard__grade">限定年级：{{ row.target_grade_year ?? '全部' }}</span>
            <el-button size="small" link type="primary" @click="openEdit(row)">编辑</el-button>
          </footer>
        </article>
        <el-empty
          v-if="!periods.length"
          description="尚未设置选课时间窗口，点击右上角「新增窗口」开始配置"
          :image-size="70"
        />
      </div>
    </el-card>

    <!-- ==================== 教学班选课情况 ==================== -->
    <el-card shadow="never" class="page-card">
      <div class="toolbar">
        <el-select v-model="semester" style="width: 180px">
          <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
        </el-select>
        <div class="spacer" />
        <el-text size="small" type="info">选课需同时满足：时间窗口开放 + 教学班开放</el-text>
      </div>

      <!-- 桌面端：表格 -->
      <div class="table-wrap">
        <el-table :data="classes" stripe>
          <el-table-column prop="code" label="教学班号" min-width="150" />
          <el-table-column label="课程" min-width="170">
            <template #default="{ row }">
              <div class="cell-course">
                <span class="cell-course__name">{{ row.course_name || '—' }}</span>
                <span v-if="row.course_code" class="cell-course__meta">{{ row.course_code }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="teacher_name" label="教师" width="100" />
          <el-table-column label="选课情况" width="220">
            <template #default="{ row }">
              <div class="enroll">
                <div class="enroll__head">
                  <span class="enroll__picked">
                    已选 <b>{{ row.selected_count }}</b> / {{ row.capacity }}
                  </span>
                  <span class="enroll__remain" :class="{ 'is-full': row.remaining <= 0 }">
                    {{ row.remaining > 0 ? `余 ${row.remaining}` : '已满' }}
                  </span>
                </div>
                <el-progress
                  :percentage="row.capacity ? Math.min(100, Math.round((row.selected_count / row.capacity) * 100)) : 0"
                  :stroke-width="8"
                  :show-text="false"
                />
              </div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="row.selection_status === 'OPEN' ? 'success' : 'info'" size="small">
                {{ row.selection_status === 'OPEN' ? '选课中' : '未开放' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" align="center" fixed="right">
            <template #default="{ row }">
              <el-button size="small" link type="primary" @click="showRoster(row)">名单</el-button>
              <el-button size="small" link type="primary" @click="toggle(row)">
                {{ row.selection_status === 'OPEN' ? '关闭' : '开放' }}
              </el-button>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty
              description="该学期暂无教学班，可切换学期或先在开课管理中创建教学班"
              :image-size="70"
            />
          </template>
        </el-table>
      </div>

      <!-- 移动端：卡片 -->
      <div class="class-cards">
        <article v-for="row in classes" :key="row.id" class="ccard">
          <header class="ccard__head">
            <div class="ccard__title">
              <span class="ccard__name">{{ row.course_name || '—' }}</span>
              <span class="muted ccard__code">
                {{ row.code }}<template v-if="row.course_code"> · {{ row.course_code }}</template>
              </span>
            </div>
            <el-tag :type="row.selection_status === 'OPEN' ? 'success' : 'info'" size="small">
              {{ row.selection_status === 'OPEN' ? '选课中' : '未开放' }}
            </el-tag>
          </header>

          <div class="ccard__meta">
            <span class="muted">教师</span>
            <span>{{ row.teacher_name || '—' }}</span>
          </div>

          <div class="enroll enroll--block">
            <div class="enroll__head">
              <span class="enroll__picked">
                已选 <b>{{ row.selected_count }}</b> / {{ row.capacity }}
              </span>
              <span class="enroll__remain" :class="{ 'is-full': row.remaining <= 0 }">
                {{ row.remaining > 0 ? `余 ${row.remaining}` : '已满' }}
              </span>
            </div>
            <el-progress
              :percentage="row.capacity ? Math.min(100, Math.round((row.selected_count / row.capacity) * 100)) : 0"
              :stroke-width="8"
              :show-text="false"
            />
          </div>

          <footer class="ccard__foot">
            <el-button size="small" @click="showRoster(row)">名单</el-button>
            <el-button size="small" type="primary" plain @click="toggle(row)">
              {{ row.selection_status === 'OPEN' ? '关闭选课' : '开放选课' }}
            </el-button>
          </footer>
        </article>
        <el-empty
          v-if="!classes.length"
          description="该学期暂无教学班，可切换学期或先在开课管理中创建教学班"
          :image-size="70"
        />
      </div>

      <div class="pager">
        <el-pagination v-model:current-page="page" :total="total" :page-size="20"
          layout="total, prev, pager, next" @current-change="loadClasses" />
      </div>
    </el-card>

    <!-- ==================== 选课窗口编辑弹窗 ==================== -->
    <el-dialog v-model="dialog" :title="editingId ? '编辑选课窗口' : '新增选课窗口'" width="480px">
      <el-form label-width="100px">
        <el-form-item label="学期" required>
          <el-select v-model="form.semester" style="width: 100%">
            <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="form.name" maxlength="50" />
        </el-form-item>
        <el-form-item label="开始时间" required>
          <el-date-picker v-model="form.start_time" type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
        </el-form-item>
        <el-form-item label="结束时间" required>
          <el-date-picker v-model="form.end_time" type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
        </el-form-item>
        <el-form-item label="限定年级">
          <el-input-number v-model="form.target_grade_year" :min="1900" :max="2200"
            placeholder="留空为全部" style="width: 100%" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status" style="width: 100%">
            <el-option label="未开始" value="PENDING" />
            <el-option label="进行中" value="ACTIVE" />
            <el-option label="已结束" value="CLOSED" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">确定</el-button>
      </template>
    </el-dialog>

    <!-- ==================== 选课名单弹窗 ==================== -->
    <el-dialog v-model="rosterVisible" :title="rosterTitle" width="560px">
      <el-empty v-if="!roster.length" description="该教学班暂无学生选课" :image-size="70" />
      <el-table v-else :data="roster" max-height="420" size="small" stripe>
        <el-table-column type="index" label="#" width="55" align="center" />
        <el-table-column prop="student_no" label="学号" width="140" />
        <el-table-column prop="real_name" label="姓名" width="110" />
        <el-table-column prop="class_name" label="班级" min-width="150" />
      </el-table>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.selection-manage {
  display: block;
}

/* -------------------------------------------------------------- 卡片头 */
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

/* ---------------------------------------------------------- 时间窗口 */
.window {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  border-radius: var(--uams-radius-xs);
  background: var(--uams-primary-softer);
  border: 1px solid var(--uams-border);
  color: var(--uams-primary-dark);

  &__time {
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    letter-spacing: 0.2px;
    white-space: nowrap;
  }

  &__sep {
    font-weight: 700;
    color: var(--uams-primary-light);
  }

  &--block {
    display: flex;
    width: 100%;
    justify-content: center;
    padding: 8px 10px;
  }
}

/* ------------------------------------------------------------ 课程单元格 */
.cell-course {
  display: flex;
  flex-direction: column;
  line-height: 1.35;

  &__name {
    font-weight: 600;
    color: var(--uams-text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__meta {
    font-size: 12px;
    color: var(--uams-text-3);
  }
}

/* ------------------------------------------------------------ 选课情况 */
.enroll {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 140px;

  &__head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
  }

  &__picked {
    font-size: 12px;
    color: var(--uams-text-2);
    font-variant-numeric: tabular-nums;

    b {
      font-size: 15px;
      font-weight: 700;
      color: var(--uams-text);
    }
  }

  &__remain {
    font-size: 12px;
    font-weight: 600;
    color: var(--uams-success);
    white-space: nowrap;

    &.is-full {
      color: var(--uams-danger);
    }
  }
}

/* --------------------------------------------------------- 移动端卡片 */
.period-cards,
.class-cards {
  display: none;
  flex-direction: column;
  gap: 12px;
}

.pcard,
.ccard {
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface);
  padding: 14px;
}

/* 时间窗口卡片 */
.pcard {
  &__head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 10px;
  }

  &__title {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  &__name {
    font-weight: 600;
    color: var(--uams-text);
  }

  &__sem {
    font-size: 12px;
  }

  &__foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--uams-border);
  }

  &__grade {
    font-size: 12px;
  }
}

/* 教学班卡片 */
.ccard {
  display: flex;
  flex-direction: column;
  gap: 12px;

  &__head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
  }

  &__title {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  &__name {
    font-weight: 600;
    color: var(--uams-text);
  }

  &__code {
    font-size: 12px;
  }

  &__meta {
    display: flex;
    align-items: baseline;
    gap: 8px;
    font-size: 13px;
    color: var(--uams-text);
  }

  &__foot {
    display: flex;
    gap: 10px;
    padding-top: 12px;
    border-top: 1px solid var(--uams-border);

    .el-button {
      flex: 1;
      margin-left: 0;
      height: 38px;
    }
  }
}

/* ------------------------------------------------------------- 响应式 */
@media (max-width: 768px) {
  /* 表格换成卡片列表 */
  .table-wrap {
    display: none;
  }

  .period-cards,
  .class-cards {
    display: flex;
  }
}
.overlap-alert {
  margin-bottom: 12px;
}

.pcard__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
}
</style>
