<script setup lang="ts">
/** 教学班学生安排/名单管理（FIX-002）。
 *
 * 批量安排：按行政班/专业/学院预览 → 二次确认 → 单事务提交。
 * 名单管理：查看来源/安排时间，手动添加/移除；已有成绩时后端拒绝移除。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { classApi, collegeApi, majorApi, studentApi, teachingApi } from '@/api'
import type {
  ClassInfo,
  ClassRosterStudent,
  College,
  Major,
  RequiredAssignResult,
  Student,
  TeachingClass,
} from '@/types'

const props = defineProps<{
  modelValue: boolean
  teachingClass: TeachingClass | null
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'changed'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

type ScopeType = 'class' | 'major' | 'college'

const activeTab = ref<'batch' | 'roster'>('batch')
const scopeType = ref<ScopeType>('class')
const scopeId = ref<number | undefined>(undefined)
const classes = ref<ClassInfo[]>([])
const majors = ref<Major[]>([])
const colleges = ref<College[]>([])
const optionsLoaded = ref(false)

const preview = ref<RequiredAssignResult | null>(null)
const previewing = ref(false)
const committing = ref(false)

const roster = ref<ClassRosterStudent[]>([])
const rosterLoading = ref(false)
const studentKeyword = ref('')
const studentOptions = ref<Student[]>([])
const selectedStudentId = ref<number | undefined>(undefined)
const searchLoading = ref(false)
const adding = ref(false)

const REASON_LABELS: Record<string, string> = {
  ALREADY_ASSIGNED: '已安排',
  PREVIOUSLY_REMOVED: '曾移除',
  SAME_COURSE_OTHER_CLASS: '同课程其他班',
  TIME_CONFLICT: '时间冲突',
  CAPACITY_FULL: '容量不足',
  INVALID_STATUS: '学籍无效',
}

const dialogTitle = computed(() => {
  const tc = props.teachingClass
  if (!tc) return '安排学生'
  return `安排学生 — ${tc.course_name || '未命名课程'}（${tc.code}）`
})

const scopeOptions = computed(() => {
  if (scopeType.value === 'class') {
    return classes.value.map((c) => ({ id: c.id, label: `${c.name}（${c.code}）` }))
  }
  if (scopeType.value === 'major') {
    return majors.value.map((m) => ({ id: m.id, label: `${m.name}（${m.code}）` }))
  }
  return colleges.value.map((c) => ({ id: c.id, label: `${c.name}（${c.code}）` }))
})

const reasonRows = computed(() =>
  Object.entries(preview.value?.reason_counts || {}).map(([code, count]) => ({
    code,
    label: REASON_LABELS[code] || code,
    count,
  })),
)

function scopePayload(): Record<string, number> | null {
  if (!scopeId.value) return null
  return { [`${scopeType.value}_id`]: scopeId.value }
}

function actionText(action: string) {
  if (action === 'ADD') return '新增'
  if (action === 'ALREADY') return '已安排'
  return '跳过'
}

function actionType(action: string): 'success' | 'info' | 'warning' {
  if (action === 'ADD') return 'success'
  if (action === 'ALREADY') return 'info'
  return 'warning'
}

function formatTime(value?: string | null) {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 16)
}

function sourceText(row: ClassRosterStudent) {
  return row.source_label || (row.source ? row.source : '历史记录（未标记来源）')
}

async function loadOptions() {
  if (optionsLoaded.value) return
  const [c, m, k] = await Promise.allSettled([
    collegeApi.list({ page_size: 200 }),
    majorApi.list({ page_size: 200 }),
    classApi.list({ page_size: 200 }),
  ])
  if (c.status === 'fulfilled') colleges.value = c.value.items
  if (m.status === 'fulfilled') majors.value = m.value.items
  if (k.status === 'fulfilled') classes.value = k.value.items
  optionsLoaded.value = true
}

async function loadRoster() {
  if (!props.teachingClass) return
  rosterLoading.value = true
  try {
    roster.value = await teachingApi.students(props.teachingClass.id)
  } finally {
    rosterLoading.value = false
  }
}

async function doPreview() {
  if (!props.teachingClass) return
  const body = scopePayload()
  if (!body) {
    ElMessage.warning('请先选择安排范围')
    return
  }
  previewing.value = true
  try {
    preview.value = await teachingApi.assignRequired(
      props.teachingClass.id,
      body,
      true,
    )
  } catch {
    // 错误提示由 Axios 拦截器统一给出
  } finally {
    previewing.value = false
  }
}

async function doCommit() {
  if (!props.teachingClass || !preview.value) return
  const body = scopePayload()
  if (!body) {
    ElMessage.warning('请先选择安排范围')
    return
  }
  const p = preview.value
  if (p.would_add <= 0) {
    ElMessage.warning('没有可新增的安排，请调整范围或查看跳过原因')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将新增 ${p.would_add} 人，跳过 ${p.skipped} 人（已安排 ${p.already_assigned} 人，时间冲突 ${p.conflict_count} 人）。提交后名单与课表立即生效，确认继续？`,
      '确认安排',
      { type: 'warning' },
    )
  } catch {
    return
  }
  committing.value = true
  try {
    const res = await teachingApi.assignRequired(
      props.teachingClass.id,
      body,
      false,
    )
    preview.value = res
    ElMessage.success(`已新增 ${res.added} 人安排；跳过 ${res.skipped} 人`)
    emit('changed')
    await loadRoster()
  } catch {
    // 409 等业务错误由拦截器提示
  } finally {
    committing.value = false
  }
}

async function searchStudents(query: string) {
  studentKeyword.value = query
  if (!query.trim()) {
    studentOptions.value = []
    return
  }
  searchLoading.value = true
  try {
    const res = await studentApi.list({ keyword: query.trim(), page_size: 20 })
    studentOptions.value = res.items
  } catch {
    studentOptions.value = []
  } finally {
    searchLoading.value = false
  }
}

async function addStudent() {
  if (!props.teachingClass || !selectedStudentId.value) {
    ElMessage.warning('请先搜索并选择学生')
    return
  }
  adding.value = true
  try {
    await teachingApi.addStudent(props.teachingClass.id, selectedStudentId.value)
    ElMessage.success('已添加到教学班')
    selectedStudentId.value = undefined
    studentKeyword.value = ''
    studentOptions.value = []
    preview.value = null
    await loadRoster()
    emit('changed')
  } catch {
    // 容量/冲突/学籍等错误由拦截器提示
  } finally {
    adding.value = false
  }
}

async function removeStudent(row: ClassRosterStudent) {
  if (!props.teachingClass) return
  try {
    await ElMessageBox.confirm(
      `确认将 ${row.student_no} ${row.real_name} 从该教学班移除？已有成绩时系统会拒绝。`,
      '确认移除',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await teachingApi.removeStudent(props.teachingClass.id, row.student_id)
    ElMessage.success('已移除')
    preview.value = null
    await loadRoster()
    emit('changed')
  } catch {
    // 已有成绩/学期结束等错误由拦截器提示
  }
}

watch(
  () => props.modelValue,
  async (open) => {
    if (!open) return
    activeTab.value = 'batch'
    scopeType.value = 'class'
    scopeId.value = undefined
    preview.value = null
    studentKeyword.value = ''
    studentOptions.value = []
    selectedStudentId.value = undefined
    await loadOptions()
    await loadRoster()
  },
)

watch(scopeType, () => {
  scopeId.value = undefined
  preview.value = null
})

watch(scopeId, () => {
  preview.value = null
})

watch(
  () => props.teachingClass?.id,
  async () => {
    if (!props.modelValue) return
    preview.value = null
    await loadRoster()
  },
)
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    width="1000px"
    top="5vh"
    destroy-on-close
  >
    <el-tabs v-model="activeTab">
      <el-tab-pane label="批量安排" name="batch">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="仅必修/公共必修/实践课程可批量预安排；选修课由学生自主选择。预览不写库，正式提交前会二次确认。"
          class="tip"
        />

        <div class="scope-row">
          <el-select v-model="scopeType" style="width: 120px">
            <el-option label="行政班" value="class" />
            <el-option label="专业" value="major" />
            <el-option label="学院" value="college" />
          </el-select>
          <el-select
            v-model="scopeId"
            filterable
            placeholder="选择安排范围"
            style="width: 340px"
            :disabled="!scopeOptions.length"
          >
            <el-option
              v-for="o in scopeOptions"
              :key="o.id"
              :label="o.label"
              :value="o.id"
            />
          </el-select>
          <el-button type="primary" :loading="previewing" @click="doPreview">
            预览安排
          </el-button>
        </div>

        <template v-if="preview">
          <div class="stats">
            <div class="stat">
              <span class="stat__value">{{ preview.matched }}</span>
              <span class="stat__label">匹配学生</span>
            </div>
            <div class="stat">
              <span class="stat__value">{{ preview.already_assigned }}</span>
              <span class="stat__label">已安排</span>
            </div>
            <div class="stat stat--primary">
              <span class="stat__value">{{ preview.would_add }}</span>
              <span class="stat__label">将新增</span>
            </div>
            <div class="stat stat--warn">
              <span class="stat__value">{{ preview.skipped }}</span>
              <span class="stat__label">跳过</span>
            </div>
            <div class="stat">
              <span class="stat__value">{{ preview.selected_count }}/{{ preview.capacity }}</span>
              <span class="stat__label">当前已选/容量</span>
            </div>
            <div class="stat">
              <span class="stat__value">{{ preview.remaining }}</span>
              <span class="stat__label">剩余容量</span>
            </div>
            <div class="stat stat--danger">
              <span class="stat__value">{{ preview.conflict_count }}</span>
              <span class="stat__label">时间冲突</span>
            </div>
            <div class="stat stat--danger">
              <span class="stat__value">{{ preview.ineligible_count }}</span>
              <span class="stat__label">不符合条件</span>
            </div>
          </div>

          <div v-if="reasonRows.length" class="reason-row">
            <span class="muted">跳过/已安排原因：</span>
            <el-tag
              v-for="r in reasonRows"
              :key="r.code"
              size="small"
              type="info"
              effect="plain"
            >
              {{ r.label }} {{ r.count }}
            </el-tag>
          </div>

          <el-table
            v-loading="previewing"
            :data="preview.items"
            size="small"
            stripe
            max-height="340"
            class="preview-table"
          >
            <el-table-column prop="student_no" label="学号" width="130" />
            <el-table-column prop="student_name" label="姓名" width="100" />
            <el-table-column prop="class_name" label="行政班" min-width="150" />
            <el-table-column prop="major_name" label="专业" min-width="140" />
            <el-table-column label="结果" width="90" align="center">
              <template #default="{ row }">
                <el-tag :type="actionType(row.action)" size="small">
                  {{ actionText(row.action) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="原因" min-width="200">
              <template #default="{ row }">
                {{ row.reason || '—' }}
              </template>
            </el-table-column>
          </el-table>

          <div class="commit-bar">
            <span class="muted">
              提交后预计已选 {{ preview.selected_count_after }} 人，剩余
              {{ preview.remaining_after }} 个名额。
            </span>
            <el-button
              type="primary"
              :loading="committing"
              :disabled="!preview.preview || preview.would_add <= 0"
              @click="doCommit"
            >
              {{ preview.committed ? '已提交' : `确认安排（新增 ${preview.would_add} 人）` }}
            </el-button>
          </div>
        </template>

        <el-empty
          v-else
          description="选择行政班/专业/学院后点击「预览安排」"
          :image-size="70"
        />
      </el-tab-pane>

      <el-tab-pane label="当前名单" name="roster">
        <div class="roster-toolbar">
          <el-select
            v-model="selectedStudentId"
            filterable
            remote
            clearable
            :remote-method="searchStudents"
            :loading="searchLoading"
            placeholder="输入学号/姓名搜索学生"
            style="width: 320px"
          >
            <el-option
              v-for="s in studentOptions"
              :key="s.id"
              :label="`${s.student_no} ${s.real_name}（${s.class_name || '—'}）`"
              :value="s.id"
            />
          </el-select>
          <el-button
            type="primary"
            :loading="adding"
            :disabled="!selectedStudentId"
            @click="addStudent"
          >
            添加学生
          </el-button>
          <el-button @click="loadRoster">刷新</el-button>
          <span class="muted">共 {{ roster.length }} 人</span>
        </div>

        <el-empty
          v-if="!roster.length && !rosterLoading"
          description="该教学班暂无学生"
          :image-size="70"
        />
        <el-table
          v-else
          v-loading="rosterLoading"
          :data="roster"
          size="small"
          stripe
          max-height="420"
        >
          <el-table-column prop="student_no" label="学号" width="130" />
          <el-table-column prop="real_name" label="姓名" width="100" />
          <el-table-column prop="class_name" label="行政班" min-width="150" />
          <el-table-column prop="major" label="专业" min-width="140" />
          <el-table-column label="安排来源" width="160">
            <template #default="{ row }">{{ sourceText(row) }}</template>
          </el-table-column>
          <el-table-column label="安排时间" width="150">
            <template #default="{ row }">{{ formatTime(row.selected_at) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="90" align="center">
            <template #default>
              <el-tag size="small" type="success">已安排</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" align="center" fixed="right">
            <template #default="{ row }">
              <el-button link type="danger" @click="removeStudent(row)">移除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped lang="scss">
.tip {
  margin-bottom: 14px;
}

.scope-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 16px;
}

.stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 12px;
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface);

  &__value {
    font-size: 20px;
    font-weight: 700;
    color: var(--uams-text);
    font-variant-numeric: tabular-nums;
  }

  &__label {
    font-size: 12px;
    color: var(--uams-text-3);
  }

  &--primary &__value {
    color: var(--uams-primary-dark);
  }

  &--warn &__value {
    color: #b26a00;
  }

  &--danger &__value {
    color: var(--el-color-danger);
  }
}

.reason-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-bottom: 12px;
}

.preview-table {
  margin-bottom: 12px;
}

.commit-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.roster-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 14px;
}

.muted {
  color: var(--uams-text-3);
  font-size: 12px;
}

@media (max-width: 768px) {
  .stats {
    grid-template-columns: repeat(2, minmax(120px, 1fr));
  }

  .scope-row :deep(.el-select),
  .roster-toolbar :deep(.el-select) {
    width: 100% !important;
  }
}
</style>
