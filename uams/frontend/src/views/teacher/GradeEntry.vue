<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadFile, UploadInstance } from 'element-plus'

import { gradeApi, importApi, teacherApi, teachingApi } from '@/api'
import { currentSemester } from '@/composables/useSemester'
import type { Grade, GradeStatistics, ImportResult, TeachingClass } from '@/types'

const route = useRoute()
const router = useRouter()

const classes = ref<TeachingClass[]>([])
const classId = ref<number | undefined>(undefined)
const rows = ref<Grade[]>([])
const stats = ref<GradeStatistics | null>(null)
const loading = ref(false)
const saving = ref(false)
const importing = ref(false)
const importResult = ref<ImportResult | null>(null)
const uploader = ref<UploadInstance>()

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

/** 考核方式来自成绩单返回的课程 assessment_type（32=两段式；48/64=三段式）。 */
const assessmentType = computed(() => rows.value[0]?.assessment_type ?? null)

/** 是否有期中：以后端返回的 has_midterm 为准；无值时按考核方式兜底。 */
const hasMidterm = computed(() => {
  const h = rows.value[0]?.has_midterm
  if (h != null) return h
  return rows.value[0]?.assessment_type !== '32'
})

/** 32 学时课程没有期中考试，隐藏期中列。 */
const is32h = computed(() => !hasMidterm.value)

/** 课程含实践：仅由课程实践学时（后端 has_practice）决定，禁止由已录成绩反推课程属性（FIX-009 §八）。 */
const hasPractice = computed(() => rows.value[0]?.has_practice ?? false)

/** 权重提示：与后端 ScoreService.WEIGHT_RULES 一致，仅作展示，不参与计算。 */
const weightHint = computed(() => {
  const base = is32h.value ? '平时 20% + 期末 80%' : '平时 20% + 期中 30% + 期末 50%'
  return hasPractice.value ? `${base}；理论/实践取两侧平均` : base
})

/** 已录入完整 = 后端已算出总评（成绩总评由系统统一计算，前端不自行计算）。 */
const filled = computed(() => rows.value.filter((r) => r.total_score != null).length)

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
    // 只提交教师可编辑的原始成绩字段（显式带上 null 以便清空），
    // 理论/实践总评、成绩总评、绩点、结果一律由后端 ScoreService 计算。
    // 无实践拆分时沿用合并口径字段（mid_score / final_score），
    // 有实践拆分时按理论/实践成对提交。
    const items = rows.value.map((r) => ({
      grade_id: r.id,
      regular_score: r.regular_score ?? null,
      ...(is32h.value
        ? {}
        : hasPractice.value
          ? {
              mid_theory_score: r.mid_theory_score ?? null,
              mid_practice_score: r.mid_practice_score ?? null,
            }
          : { mid_score: r.mid_score ?? null }),
      ...(hasPractice.value
        ? {
            final_theory_score: r.final_theory_score ?? null,
            final_practice_score: r.final_practice_score ?? null,
          }
        : { final_score: r.final_score ?? null }),
      theory_makeup_score: r.theory_makeup_score ?? null,
      ...(hasPractice.value
        ? { practice_makeup_score: r.practice_makeup_score ?? null }
        : {}),
    }))
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

async function removeDraft(row: Grade) {
  try {
    await ElMessageBox.confirm(
      `确定删除 ${row.student_name ?? ''}（${row.student_no}）的成绩草稿吗？删除后该学生回到「未录入」。`,
      '删除成绩草稿',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  await gradeApi.removeDraft(row.id)
  ElMessage.success('删除成功')
  await loadSheet()
}

/** 下载当前教学班的成绩模板（名单与考核结构由后端生成）。 */
async function downloadTemplate() {
  if (!classId.value) return
  await importApi.template('grades', classId.value)
  ElMessage.success('模板已开始下载：已带出学生名单，只需填写成绩列')
}

async function importFile(f: UploadFile) {
  if (!classId.value || !f.raw) return
  importing.value = true
  try {
    const res = await importApi.upload('grades', f.raw as File)
    importResult.value = res
    if (res.failed === 0) {
      ElMessage.success(`导入完成：成功 ${res.success} 条，已保存为草稿`)
    } else {
      ElMessage.warning(`导入完成：成功 ${res.success} 条，失败 ${res.failed} 条`)
    }
    await loadSheet()
  } finally {
    importing.value = false
    uploader.value?.clearFiles()
  }
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
          <el-button @click="downloadTemplate">下载导入模板</el-button>
          <el-upload
            ref="uploader"
            class="inline-upload"
            :auto-upload="false"
            :limit="1"
            accept=".xlsx"
            :show-file-list="false"
            :on-change="importFile"
          >
            <el-button :loading="importing" :disabled="!editable">
              导入成绩
            </el-button>
          </el-upload>
          <el-button :disabled="!editable" :loading="saving" @click="save">
            保存草稿
          </el-button>
          <el-button type="primary" :disabled="!editable" @click="submit">
            提交审核
          </el-button>
        </template>
      </div>

      <el-alert
        v-if="importResult"
        :type="importResult.failed ? 'warning' : 'success'"
        :title="`导入结果：成功 ${importResult.success} 条，失败 ${importResult.failed} 条（已保存为草稿，请核对后提交）`"
        :closable="true"
        show-icon
        style="margin-bottom: 12px"
        @close="importResult = null"
      >
        <div v-for="e in importResult.errors" :key="`${e.row}-${e.field}`">
          第 {{ e.row }} 行（{{ e.field }}）：{{ e.message }}
        </div>
      </el-alert>

      <el-alert
        v-if="rows.length && assessmentType"
        :title="`成绩规则：${weightHint}。理论/实践总评、成绩总评、绩点、结果均由系统按课程考核方式统一计算，保存后回显。`"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      />
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
      <el-table v-else :data="rows" stripe border size="small">
        <el-table-column type="index" label="#" width="45" align="center" fixed="left" />
        <el-table-column prop="student_no" label="学号" width="120" fixed="left" />
        <el-table-column prop="student_name" label="姓名" width="90" fixed="left" />

        <!-- 教师可编辑：原始成绩 -->
        <el-table-column label="平时成绩" width="110" align="center">
          <template #default="{ row }">
            <el-input-number
              v-model="row.regular_score"
              :min="0"
              :max="100"
              :precision="1"
              :controls="false"
              :disabled="!editable"
              style="width: 90px"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="!is32h && !hasPractice" label="期中成绩" width="110" align="center">
          <template #default="{ row }">
            <el-input-number
              v-model="row.mid_score"
              :min="0"
              :max="100"
              :precision="1"
              :controls="false"
              :disabled="!editable"
              style="width: 90px"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="!is32h && hasPractice" label="期中理论" width="110" align="center">
          <template #default="{ row }">
            <el-input-number
              v-model="row.mid_theory_score"
              :min="0"
              :max="100"
              :precision="1"
              :controls="false"
              :disabled="!editable"
              style="width: 90px"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="!is32h && hasPractice" label="期中实践" width="110" align="center">
          <template #default="{ row }">
            <el-input-number
              v-model="row.mid_practice_score"
              :min="0"
              :max="100"
              :precision="1"
              :controls="false"
              :disabled="!editable"
              style="width: 90px"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="!hasPractice" label="期末成绩" width="110" align="center">
          <template #default="{ row }">
            <el-input-number
              v-model="row.final_score"
              :min="0"
              :max="100"
              :precision="1"
              :controls="false"
              :disabled="!editable"
              style="width: 90px"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="hasPractice" label="期末理论" width="110" align="center">
          <template #default="{ row }">
            <el-input-number
              v-model="row.final_theory_score"
              :min="0"
              :max="100"
              :precision="1"
              :controls="false"
              :disabled="!editable"
              style="width: 90px"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="hasPractice" label="期末实践" width="110" align="center">
          <template #default="{ row }">
            <el-input-number
              v-model="row.final_practice_score"
              :min="0"
              :max="100"
              :precision="1"
              :controls="false"
              :disabled="!editable"
              style="width: 90px"
            />
          </template>
        </el-table-column>
        <el-table-column :label="hasPractice ? '理论补考' : '补考成绩'" width="110" align="center">
          <template #default="{ row }">
            <el-input-number
              v-model="row.theory_makeup_score"
              :min="0"
              :max="100"
              :precision="1"
              :controls="false"
              :disabled="!editable"
              style="width: 90px"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="hasPractice" label="实践补考" width="110" align="center">
          <template #default="{ row }">
            <el-input-number
              v-model="row.practice_makeup_score"
              :min="0"
              :max="100"
              :precision="1"
              :controls="false"
              :disabled="!editable"
              style="width: 90px"
            />
          </template>
        </el-table-column>

        <!-- 系统计算：只读 -->
        <el-table-column label="理论总评" width="95" align="center">
          <template #default="{ row }">
            <span v-if="row.theory_total_score != null" class="total">
              {{ row.theory_total_score }}
            </span>
            <span v-else class="empty">-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="hasPractice" label="实践总评" width="95" align="center">
          <template #default="{ row }">
            <span v-if="row.practice_total_score != null" class="total">
              {{ row.practice_total_score }}
            </span>
            <span v-else class="empty">-</span>
          </template>
        </el-table-column>
        <el-table-column label="成绩总评" width="95" align="center">
          <template #default="{ row }">
            <span v-if="row.total_score != null" class="total">{{ row.total_score }}</span>
            <span v-else class="empty">未计算</span>
          </template>
        </el-table-column>
        <el-table-column prop="grade_point" label="绩点" width="70" align="center">
          <template #default="{ row }">{{ row.grade_point ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="结果" width="80" align="center">
          <template #default="{ row }">
            <el-tag
              v-if="row.is_passed != null"
              :type="row.is_passed ? 'success' : 'danger'"
              size="small"
            >
              {{ row.is_passed ? '通过' : '不及格' }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center" fixed="right">
          <template #default="{ row }">
            <el-tag :type="STATUS_TYPE[row.status] as any" size="small">
              {{ STATUS_LABEL[row.status] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              link
              type="danger"
              size="small"
              :disabled="row.status !== 'DRAFT'"
              @click="removeDraft(row)"
            >
              删除草稿
            </el-button>
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
.empty { color: #c0c4cc; }
.inline-upload { display: inline-block; }
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
