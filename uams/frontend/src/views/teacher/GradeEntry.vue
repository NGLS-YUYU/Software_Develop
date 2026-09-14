<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { gradeApi, teacherApi, teachingApi } from '@/api'
import { currentSemester } from '@/composables/useSemester'
import type { Grade, GradeStatistics, TeachingClass } from '@/types'

const route = useRoute()
const router = useRouter()

const classes = ref<TeachingClass[]>([])
const classId = ref<number | undefined>(undefined)
const rows = ref<Grade[]>([])
const stats = ref<GradeStatistics | null>(null)
const loading = ref(false)
const saving = ref(false)

const STATUS_LABEL: Record<string, string> = {
  DRAFT: '草稿',
  SUBMITTED: '待审核',
  APPROVED: '已通过',
  REJECTED: '已驳回',
}
const STATUS_TYPE: Record<string, string> = {
  DRAFT: 'info',
  SUBMITTED: 'warning',
  APPROVED: 'success',
  REJECTED: 'danger',
}

const currentClass = computed(() => classes.value.find((c) => c.id === classId.value))

/** 整班状态：只要有一条已提交/已通过，就不允许再直接编辑。 */
const sheetStatus = computed(() => {
  if (!rows.value.length) return 'EMPTY'
  if (rows.value.some((r) => r.status === 'APPROVED')) return 'APPROVED'
  if (rows.value.some((r) => r.status === 'SUBMITTED')) return 'SUBMITTED'
  if (rows.value.some((r) => r.status === 'REJECTED')) return 'REJECTED'
  return 'DRAFT'
})

const editable = computed(
  () => sheetStatus.value === 'DRAFT' || sheetStatus.value === 'REJECTED',
)

const rejectReason = computed(
  () => rows.value.find((r) => r.status === 'REJECTED')?.reject_reason,
)

const filled = computed(
  () => rows.value.filter((r) => r.regular_score != null && r.final_score != null).length,
)

/** 前端只做即时预览，最终总评以后端计算为准（CLAUDE.md §21）。 */
function preview(row: Grade) {
  const c = currentClass.value
  if (row.regular_score == null || row.final_score == null || !c) return null
  // 课程权重未随教学班返回，这里用常见的 4:6 仅作预览提示
  return (Number(row.regular_score) * 0.4 + Number(row.final_score) * 0.6).toFixed(2)
}

async function loadClasses() {
  const me = await teacherApi.me()
  const res = await teachingApi.classes({
    teacher_id: me.id,
    semester: currentSemester(),
    page_size: 100,
  })
  classes.value = res.items
  const fromRoute = Number(route.params.classId)
  classId.value = fromRoute || classes.value[0]?.id
}

async function loadSheet() {
  if (!classId.value) return
  loading.value = true
  try {
    rows.value = await gradeApi.byClass(classId.value)
    stats.value = await gradeApi.statistics(classId.value)
  } finally {
    loading.value = false
  }
}

async function initSheet() {
  if (!classId.value) return
  rows.value = await gradeApi.initSheet(classId.value)
  ElMessage.success('成绩单已生成')
  await loadSheet()
}

async function save() {
  if (!classId.value) return
  saving.value = true
  try {
    const items = rows.value
      .filter((r) => r.regular_score != null || r.final_score != null)
      .map((r) => ({
        grade_id: r.id,
        regular_score: r.regular_score,
        final_score: r.final_score,
      }))
    if (!items.length) {
      ElMessage.warning('没有可保存的成绩')
      return
    }
    rows.value = await gradeApi.save(classId.value, items)
    ElMessage.success('已保存草稿')
    stats.value = await gradeApi.statistics(classId.value)
  } finally {
    saving.value = false
  }
}

async function submit() {
  if (!classId.value) return
  if (filled.value < rows.value.length) {
    ElMessage.warning(
      `还有 ${rows.value.length - filled.value} 名学生成绩未录入完整，无法提交`,
    )
    return
  }
  try {
    await ElMessageBox.confirm(
      '提交后成绩进入教务审核，期间不可修改。确认提交？',
      '确认提交',
      { type: 'warning' },
    )
  } catch {
    return
  }
  const res = await gradeApi.submit(classId.value)
  ElMessage.success(res.message)
  await loadSheet()
}

watch(classId, (v) => {
  if (v) {
    router.replace(`/teacher/grades/${v}`)
    loadSheet()
  }
})

onMounted(async () => {
  await loadClasses()
  await loadSheet()
})
</script>

<template>
  <div v-loading="loading">
    <el-card shadow="never" class="page-card">
      <div class="toolbar">
        <el-select v-model="classId" placeholder="选择教学班" style="width: 320px">
          <el-option
            v-for="c in classes"
            :key="c.id"
            :label="`${c.course_name}（${c.code}）`"
            :value="c.id"
          />
        </el-select>
        <el-tag v-if="currentClass" type="info">
          已选 {{ currentClass.selected_count }} 人
        </el-tag>
        <el-tag v-if="rows.length" :type="STATUS_TYPE[sheetStatus] as any">
          {{ STATUS_LABEL[sheetStatus] ?? sheetStatus }}
        </el-tag>
        <div class="spacer" />
        <el-button v-if="!rows.length" type="primary" @click="initSheet">
          生成成绩单
        </el-button>
        <template v-else>
          <el-text size="small" type="info">
            已录入 {{ filled }}/{{ rows.length }}
          </el-text>
          <el-button :disabled="!editable" :loading="saving" @click="save">
            保存草稿
          </el-button>
          <el-button type="primary" :disabled="!editable" @click="submit">
            提交审核
          </el-button>
        </template>
      </div>

      <el-alert
        v-if="sheetStatus === 'REJECTED'"
        :title="`成绩被教务驳回：${rejectReason ?? '未填写原因'}。修改后可重新提交。`"
        type="error"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      />
      <el-alert
        v-else-if="sheetStatus === 'SUBMITTED'"
        title="成绩已提交，等待教务审核，此期间不可修改"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      />
      <el-alert
        v-else-if="sheetStatus === 'APPROVED'"
        title="成绩已审核通过，不可直接修改。如需更正请联系教务"
        type="success"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      />

      <el-empty v-if="!rows.length" description="尚未生成成绩单，请先点击「生成成绩单」" />
      <el-table v-else :data="rows" stripe border>
        <el-table-column type="index" label="#" width="55" align="center" />
        <el-table-column prop="student_no" label="学号" width="130" />
        <el-table-column prop="student_name" label="姓名" width="110" />
        <el-table-column label="平时成绩" width="150" align="center">
          <template #default="{ row }">
            <el-input-number
              v-model="row.regular_score"
              :min="0"
              :max="100"
              :precision="1"
              :controls="false"
              :disabled="!editable"
              size="small"
              style="width: 100px"
            />
          </template>
        </el-table-column>
        <el-table-column label="期末成绩" width="150" align="center">
          <template #default="{ row }">
            <el-input-number
              v-model="row.final_score"
              :min="0"
              :max="100"
              :precision="1"
              :controls="false"
              :disabled="!editable"
              size="small"
              style="width: 100px"
            />
          </template>
        </el-table-column>
        <el-table-column label="总评" width="110" align="center">
          <template #default="{ row }">
            <span v-if="row.total_score != null" class="total">{{ row.total_score }}</span>
            <span v-else-if="preview(row)" class="preview">{{ preview(row) }} ?</span>
            <span v-else class="empty">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="grade_point" label="绩点" width="80" align="center">
          <template #default="{ row }">{{ row.grade_point ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="STATUS_TYPE[row.status] as any" size="small">
              {{ STATUS_LABEL[row.status] }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="stats && stats.count" shadow="never" class="page-card">
      <template #header><span>成绩分布</span></template>
      <div class="stat-grid">
        <el-statistic title="已录入" :value="stats.count" />
        <el-statistic title="平均分" :value="stats.average ?? 0" :precision="2" />
        <el-statistic title="最高分" :value="stats.max ?? 0" />
        <el-statistic title="最低分" :value="stats.min ?? 0" />
        <el-statistic title="及格率" :value="stats.pass_rate ?? 0" suffix="%" />
      </div>
      <div v-if="stats.distribution" class="dist">
        <div v-for="(n, k) in stats.distribution" :key="k" class="bar-row">
          <span class="label">{{ k }}</span>
          <el-progress
            :percentage="stats.count ? Math.round((n / stats.count) * 100) : 0"
            :stroke-width="14"
          />
          <span class="count">{{ n }} 人</span>
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.total { font-weight: 600; }
.preview { color: #909399; font-size: 12px; }
.empty { color: #c0c4cc; }
.dist { margin-top: 18px; }
.bar-row {
  display: grid;
  grid-template-columns: 80px 1fr 70px;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.bar-row .label { font-size: 13px; color: #606266; }
.bar-row .count { font-size: 12px; color: #909399; text-align: right; }
</style>
