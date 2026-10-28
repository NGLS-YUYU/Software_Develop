<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadFile, UploadInstance } from 'element-plus'

import { gradeApi, importApi, teacherApi, teachingApi } from '@/api'
import { currentSemester } from '@/composables/useSemester'
import { createLatestGuard } from '@/utils/latest'
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
const sheetGuard = createLatestGuard()

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
  const seq = sheetGuard.next()
  const id = classId.value
  loading.value = true
  try {
    const [sheet, statistics] = await Promise.all([
      gradeApi.byClass(id),
      gradeApi.statistics(id),
    ])
    // 快速切换教学班时，旧班级的慢响应不能覆盖当前班级。
    if (!sheetGuard.isCurrent(seq)) return
    rows.value = sheet
    stats.value = statistics
  } finally {
    if (sheetGuard.isCurrent(seq)) loading.value = false
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
      <!-- 工具条：教学班选择 + 整班状态 + 操作 -->
      <div class="toolbar">
        <el-select v-model="classId" placeholder="选择教学班" class="class-select">
          <el-option
            v-for="c in classes"
            :key="c.id"
            :label="`${c.course_name}（${c.code}）`"
            :value="c.id"
          />
        </el-select>
        <el-tag v-if="currentClass" type="info" effect="plain">
          已选 {{ currentClass.selected_count }} 人
        </el-tag>
        <el-tag v-if="rows.length" :type="STATUS_TYPE[sheetStatus] as any">
          {{ STATUS_LABEL[sheetStatus] ?? sheetStatus }}
        </el-tag>

        <div class="spacer" />

        <el-button v-if="!rows.length" type="primary" @click="initSheet">
          <el-icon><component :is="'Plus'" /></el-icon>
          生成成绩单
        </el-button>
        <template v-else>
          <span class="filled-hint">
            已录入
            <b>{{ filled }}</b>
            / {{ rows.length }}
          </span>
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

      <!-- 导入结果与错误明细 -->
      <el-alert
        v-if="importResult"
        class="notice-block"
        :type="importResult.failed ? 'warning' : 'success'"
        :title="`导入结果：成功 ${importResult.success} 条，失败 ${importResult.failed} 条（已保存为草稿，请核对后提交）`"
        :closable="true"
        show-icon
        @close="importResult = null"
      >
        <div
          v-for="e in importResult.errors"
          :key="`${e.row}-${e.field}`"
          class="import-error"
        >
          第 {{ e.row }} 行（{{ e.field }}）：{{ e.message }}
        </div>
      </el-alert>

      <!-- 成绩规则说明 -->
      <div v-if="rows.length && assessmentType" class="note note--info">
        <el-icon class="note__icon"><component :is="'InfoFilled'" /></el-icon>
        <span class="note__text">
          成绩规则：{{ weightHint }}。理论/实践总评、成绩总评、绩点、结果均由系统按课程考核方式统一计算，保存后回显。
        </span>
      </div>

      <!-- 整班状态提示条：统一视觉，颜色随状态变化 -->
      <div v-if="sheetStatus === 'REJECTED'" class="note note--danger">
        <el-icon class="note__icon"><component :is="'CircleCloseFilled'" /></el-icon>
        <span class="note__text">
          成绩被教务驳回：{{ rejectReason ?? '未填写原因' }}。修改后可重新提交。
        </span>
      </div>
      <div v-else-if="sheetStatus === 'SUBMITTED'" class="note note--warning">
        <el-icon class="note__icon"><component :is="'WarningFilled'" /></el-icon>
        <span class="note__text">成绩已提交，等待教务审核，此期间不可修改</span>
      </div>
      <div v-else-if="sheetStatus === 'APPROVED'" class="note note--success">
        <el-icon class="note__icon"><component :is="'SuccessFilled'" /></el-icon>
        <span class="note__text">成绩已审核通过，不可直接修改。如需更正请联系教务</span>
      </div>

      <el-empty v-if="!rows.length" description="尚未生成成绩单，请先点击「生成成绩单」" />

      <template v-else>
        <!-- 桌面端：表格式录入。左侧白底输入框可编辑，右侧浅底为系统计算区 -->
        <div class="sheet-table">
          <el-table :data="rows" border size="small">
            <el-table-column type="index" label="#" width="45" align="center" fixed="left" />
            <el-table-column prop="student_no" label="学号" width="118" fixed="left" />
            <el-table-column prop="student_name" label="姓名" width="88" fixed="left" />

            <!-- 教师可编辑：原始成绩（白底输入框） -->
            <el-table-column
              label="平时成绩"
              width="108"
              align="center"
              label-class-name="th-edit"
            >
              <template #default="{ row }">
                <el-input-number
                  v-model="row.regular_score"
                  :min="0"
                  :max="100"
                  :precision="1"
                  :controls="false"
                  :disabled="!editable"
                  class="cell-input"
                />
              </template>
            </el-table-column>
            <el-table-column
              v-if="!is32h && !hasPractice"
              label="期中成绩"
              width="108"
              align="center"
              label-class-name="th-edit"
            >
              <template #default="{ row }">
                <el-input-number
                  v-model="row.mid_score"
                  :min="0"
                  :max="100"
                  :precision="1"
                  :controls="false"
                  :disabled="!editable"
                  class="cell-input"
                />
              </template>
            </el-table-column>
            <el-table-column
              v-if="!is32h && hasPractice"
              label="期中理论"
              width="108"
              align="center"
              label-class-name="th-edit"
            >
              <template #default="{ row }">
                <el-input-number
                  v-model="row.mid_theory_score"
                  :min="0"
                  :max="100"
                  :precision="1"
                  :controls="false"
                  :disabled="!editable"
                  class="cell-input"
                />
              </template>
            </el-table-column>
            <el-table-column
              v-if="!is32h && hasPractice"
              label="期中实践"
              width="108"
              align="center"
              label-class-name="th-edit"
            >
              <template #default="{ row }">
                <el-input-number
                  v-model="row.mid_practice_score"
                  :min="0"
                  :max="100"
                  :precision="1"
                  :controls="false"
                  :disabled="!editable"
                  class="cell-input"
                />
              </template>
            </el-table-column>
            <el-table-column
              v-if="!hasPractice"
              label="期末成绩"
              width="108"
              align="center"
              label-class-name="th-edit"
            >
              <template #default="{ row }">
                <el-input-number
                  v-model="row.final_score"
                  :min="0"
                  :max="100"
                  :precision="1"
                  :controls="false"
                  :disabled="!editable"
                  class="cell-input"
                />
              </template>
            </el-table-column>
            <el-table-column
              v-if="hasPractice"
              label="期末理论"
              width="108"
              align="center"
              label-class-name="th-edit"
            >
              <template #default="{ row }">
                <el-input-number
                  v-model="row.final_theory_score"
                  :min="0"
                  :max="100"
                  :precision="1"
                  :controls="false"
                  :disabled="!editable"
                  class="cell-input"
                />
              </template>
            </el-table-column>
            <el-table-column
              v-if="hasPractice"
              label="期末实践"
              width="108"
              align="center"
              label-class-name="th-edit"
            >
              <template #default="{ row }">
                <el-input-number
                  v-model="row.final_practice_score"
                  :min="0"
                  :max="100"
                  :precision="1"
                  :controls="false"
                  :disabled="!editable"
                  class="cell-input"
                />
              </template>
            </el-table-column>
            <el-table-column
              :label="hasPractice ? '理论补考' : '补考成绩'"
              width="108"
              align="center"
              label-class-name="th-edit"
            >
              <template #default="{ row }">
                <el-input-number
                  v-model="row.theory_makeup_score"
                  :min="0"
                  :max="100"
                  :precision="1"
                  :controls="false"
                  :disabled="!editable"
                  class="cell-input"
                />
              </template>
            </el-table-column>
            <el-table-column
              v-if="hasPractice"
              label="实践补考"
              width="108"
              align="center"
              label-class-name="th-edit"
            >
              <template #default="{ row }">
                <el-input-number
                  v-model="row.practice_makeup_score"
                  :min="0"
                  :max="100"
                  :precision="1"
                  :controls="false"
                  :disabled="!editable"
                  class="cell-input"
                />
              </template>
            </el-table-column>

            <!-- 系统计算：只读，浅底 + 小字，与录入区分隔 -->
            <el-table-column
              label="理论总评"
              width="92"
              align="center"
              class-name="td-calc td-calc-first"
              label-class-name="th-calc th-calc-first"
            >
              <template #default="{ row }">
                <span v-if="row.theory_total_score != null" class="total">
                  {{ row.theory_total_score }}
                </span>
                <span v-else class="empty">-</span>
              </template>
            </el-table-column>
            <el-table-column
              v-if="hasPractice"
              label="实践总评"
              width="92"
              align="center"
              class-name="td-calc"
              label-class-name="th-calc"
            >
              <template #default="{ row }">
                <span v-if="row.practice_total_score != null" class="total">
                  {{ row.practice_total_score }}
                </span>
                <span v-else class="empty">-</span>
              </template>
            </el-table-column>
            <el-table-column
              label="成绩总评"
              width="92"
              align="center"
              class-name="td-calc"
              label-class-name="th-calc"
            >
              <template #default="{ row }">
                <span v-if="row.total_score != null" class="total">{{ row.total_score }}</span>
                <span v-else class="empty">未计算</span>
              </template>
            </el-table-column>
            <el-table-column
              prop="grade_point"
              label="绩点"
              width="70"
              align="center"
              class-name="td-calc"
              label-class-name="th-calc"
            >
              <template #default="{ row }">{{ row.grade_point ?? '-' }}</template>
            </el-table-column>
            <el-table-column
              label="结果"
              width="80"
              align="center"
              class-name="td-calc"
              label-class-name="th-calc"
            >
              <template #default="{ row }">
                <el-tag
                  v-if="row.is_passed != null"
                  :type="row.is_passed ? 'success' : 'danger'"
                  size="small"
                >
                  {{ row.is_passed ? '通过' : '不及格' }}
                </el-tag>
                <span v-else class="empty">-</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="88" align="center" fixed="right">
              <template #default="{ row }">
                <el-tag :type="STATUS_TYPE[row.status] as any" size="small">
                  {{ STATUS_LABEL[row.status] }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="88" align="center" fixed="right">
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

          <div class="table-legend">
            <span class="legend legend--edit"><i /> 可编辑原始成绩</span>
            <span class="legend legend--calc"><i /> 系统计算结果</span>
          </div>
        </div>

        <!-- 移动端：每个学生一张卡片，可编辑项用输入框，计算项为只读行 -->
        <div class="stu-list">
          <div v-for="(row, idx) in rows" :key="row.id" class="stu">
            <div class="stu__head">
              <span class="stu__idx">{{ idx + 1 }}</span>
              <div class="stu__who">
                <span class="stu__name">{{ row.student_name }}</span>
                <span class="stu__no muted">{{ row.student_no }}</span>
              </div>
              <el-tag :type="STATUS_TYPE[row.status] as any" size="small">
                {{ STATUS_LABEL[row.status] }}
              </el-tag>
            </div>

            <div class="stu__fields">
              <div class="field">
                <span class="field__label">平时成绩</span>
                <el-input-number
                  v-model="row.regular_score"
                  :min="0"
                  :max="100"
                  :precision="1"
                  :controls="false"
                  :disabled="!editable"
                  class="field__input"
                />
              </div>
              <div v-if="!is32h && !hasPractice" class="field">
                <span class="field__label">期中成绩</span>
                <el-input-number
                  v-model="row.mid_score"
                  :min="0"
                  :max="100"
                  :precision="1"
                  :controls="false"
                  :disabled="!editable"
                  class="field__input"
                />
              </div>
              <div v-if="!is32h && hasPractice" class="field">
                <span class="field__label">期中理论</span>
                <el-input-number
                  v-model="row.mid_theory_score"
                  :min="0"
                  :max="100"
                  :precision="1"
                  :controls="false"
                  :disabled="!editable"
                  class="field__input"
                />
              </div>
              <div v-if="!is32h && hasPractice" class="field">
                <span class="field__label">期中实践</span>
                <el-input-number
                  v-model="row.mid_practice_score"
                  :min="0"
                  :max="100"
                  :precision="1"
                  :controls="false"
                  :disabled="!editable"
                  class="field__input"
                />
              </div>
              <div v-if="!hasPractice" class="field">
                <span class="field__label">期末成绩</span>
                <el-input-number
                  v-model="row.final_score"
                  :min="0"
                  :max="100"
                  :precision="1"
                  :controls="false"
                  :disabled="!editable"
                  class="field__input"
                />
              </div>
              <div v-if="hasPractice" class="field">
                <span class="field__label">期末理论</span>
                <el-input-number
                  v-model="row.final_theory_score"
                  :min="0"
                  :max="100"
                  :precision="1"
                  :controls="false"
                  :disabled="!editable"
                  class="field__input"
                />
              </div>
              <div v-if="hasPractice" class="field">
                <span class="field__label">期末实践</span>
                <el-input-number
                  v-model="row.final_practice_score"
                  :min="0"
                  :max="100"
                  :precision="1"
                  :controls="false"
                  :disabled="!editable"
                  class="field__input"
                />
              </div>
              <div class="field">
                <span class="field__label">{{ hasPractice ? '理论补考' : '补考成绩' }}</span>
                <el-input-number
                  v-model="row.theory_makeup_score"
                  :min="0"
                  :max="100"
                  :precision="1"
                  :controls="false"
                  :disabled="!editable"
                  class="field__input"
                />
              </div>
              <div v-if="hasPractice" class="field">
                <span class="field__label">实践补考</span>
                <el-input-number
                  v-model="row.practice_makeup_score"
                  :min="0"
                  :max="100"
                  :precision="1"
                  :controls="false"
                  :disabled="!editable"
                  class="field__input"
                />
              </div>
            </div>

            <div class="stu__calc">
              <div class="stu__calc-title">系统计算</div>
              <div class="calc-row">
                <span class="calc-row__label">理论总评</span>
                <span class="calc-row__val">
                  {{ row.theory_total_score != null ? row.theory_total_score : '-' }}
                </span>
              </div>
              <div v-if="hasPractice" class="calc-row">
                <span class="calc-row__label">实践总评</span>
                <span class="calc-row__val">
                  {{ row.practice_total_score != null ? row.practice_total_score : '-' }}
                </span>
              </div>
              <div class="calc-row">
                <span class="calc-row__label">成绩总评</span>
                <span class="calc-row__val">
                  {{ row.total_score != null ? row.total_score : '未计算' }}
                </span>
              </div>
              <div class="calc-row">
                <span class="calc-row__label">绩点</span>
                <span class="calc-row__val">{{ row.grade_point ?? '-' }}</span>
              </div>
              <div class="calc-row">
                <span class="calc-row__label">结果</span>
                <el-tag
                  v-if="row.is_passed != null"
                  :type="row.is_passed ? 'success' : 'danger'"
                  size="small"
                >
                  {{ row.is_passed ? '通过' : '不及格' }}
                </el-tag>
                <span v-else class="calc-row__val">-</span>
              </div>
            </div>

            <div class="stu__foot">
              <el-button
                link
                type="danger"
                size="small"
                :disabled="row.status !== 'DRAFT'"
                @click="removeDraft(row)"
              >
                删除草稿
              </el-button>
            </div>
          </div>
        </div>
      </template>
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
/* ------------------------------------------------------------ 工具条 */
.class-select {
  width: 320px;
}

.filled-hint {
  font-size: 13px;
  color: var(--uams-text-2);
  white-space: nowrap;
}

.filled-hint b {
  color: var(--uams-primary-dark);
  font-weight: 600;
}

.inline-upload {
  display: inline-block;
}

/* ------------------------------------------------------------ 提示条 */
.notice-block {
  margin-bottom: 12px;
}

.import-error {
  font-size: 12px;
  color: var(--uams-text-2);
}

.note {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 14px;
  margin-bottom: 12px;
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface-sunken);
  font-size: 13px;
  line-height: 1.55;
}

.note__icon {
  flex: 0 0 auto;
  margin-top: 3px;
  font-size: 15px;
}

.note__text {
  color: var(--uams-text-2);
}

.note--info {
  background: var(--uams-primary-softer);
  border-color: var(--uams-primary-soft);
}

.note--info .note__icon {
  color: var(--uams-primary);
}

.note--warning {
  background: color-mix(in srgb, var(--uams-warning) 12%, var(--uams-surface));
  border-color: color-mix(in srgb, var(--uams-warning) 26%, var(--uams-surface));
}

.note--warning .note__icon {
  color: var(--uams-warning);
}

.note--danger {
  background: color-mix(in srgb, var(--uams-danger) 10%, var(--uams-surface));
  border-color: color-mix(in srgb, var(--uams-danger) 26%, var(--uams-surface));
}

.note--danger .note__icon {
  color: var(--uams-danger);
}

.note--success {
  background: color-mix(in srgb, var(--uams-success) 10%, var(--uams-surface));
  border-color: color-mix(in srgb, var(--uams-success) 26%, var(--uams-surface));
}

.note--success .note__icon {
  color: var(--uams-success);
}

/* ------------------------------------------------------- 桌面：录入表 */
.sheet-table :deep(.el-table) {
  border-radius: var(--uams-radius-sm);
}

/* 可编辑列：白底输入框，表头用主文本色强化「可填写」语义 */
.sheet-table :deep(.cell-input) {
  width: 86px;
}

.sheet-table :deep(.el-table th.th-edit .cell) {
  color: var(--uams-text);
}

/* 系统计算区：浅底 + 小字 + 次要色表头，与录入区形成视觉分隔 */
.sheet-table :deep(.el-table .td-calc) {
  background: var(--uams-surface-sunken);
}

.sheet-table :deep(.el-table .td-calc .cell) {
  font-size: 12.5px;
  color: var(--uams-text-2);
}

.sheet-table :deep(.el-table th.th-calc .cell) {
  color: var(--uams-text-3);
}

.sheet-table :deep(.el-table td.td-calc-first),
.sheet-table :deep(.el-table th.th-calc-first) {
  border-left: 2px solid var(--uams-border-strong);
}

.total {
  font-weight: 600;
  color: var(--uams-text);
}

.empty {
  color: var(--uams-text-3);
}

.table-legend {
  display: flex;
  gap: 18px;
  margin-top: 12px;
  font-size: 12px;
  color: var(--uams-text-3);
}

.legend {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.legend i {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  display: inline-block;
}

.legend--edit i {
  background: var(--uams-surface);
  border: 1px solid var(--uams-border-strong);
}

.legend--calc i {
  background: var(--uams-surface-sunken);
  border: 1px solid var(--uams-border);
}

/* ----------------------------------------------------- 移动端：学生卡 */
.stu-list {
  display: none;
}

.stu {
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface);
  box-shadow: var(--uams-shadow-sm);
  padding: 12px;
}

.stu + .stu {
  margin-top: 10px;
}

.stu__head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--uams-border);
}

.stu__idx {
  flex: 0 0 auto;
  width: 22px;
  height: 22px;
  border-radius: var(--uams-radius-xs);
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 600;
  color: var(--uams-primary-dark);
  background: var(--uams-primary-soft);
}

.stu__who {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}

.stu__name {
  font-weight: 600;
  color: var(--uams-text);
}

.stu__no {
  font-size: 12px;
}

.stu__fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 12px;
  padding: 12px 0;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.field__label {
  font-size: 12px;
  color: var(--uams-text-2);
}

.field__input {
  width: 100%;
}

.stu__calc {
  border-top: 1px dashed var(--uams-border-strong);
  padding-top: 8px;
}

.stu__calc-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--uams-text-3);
  margin-bottom: 2px;
}

.calc-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 6px 0;
  font-size: 13px;
}

.calc-row + .calc-row {
  border-top: 1px solid var(--uams-border);
}

.calc-row__label {
  font-size: 12px;
  color: var(--uams-text-3);
}

.calc-row__val {
  font-weight: 600;
  color: var(--uams-text);
}

.stu__foot {
  display: flex;
  justify-content: flex-end;
  padding-top: 8px;
  margin-top: 4px;
  border-top: 1px solid var(--uams-border);
}

/* ------------------------------------------------------------ 成绩分布 */
.dist {
  margin-top: 18px;
}

.bar-row {
  display: grid;
  grid-template-columns: 80px 1fr 70px;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.bar-row .label {
  font-size: 13px;
  color: var(--uams-text-2);
}

.bar-row .count {
  font-size: 12px;
  color: var(--uams-text-3);
  text-align: right;
}

/* ------------------------------------------------------------- 响应式 */
@media (max-width: 768px) {
  /* 手机端不再用横向滚动的大表格，改为「每个学生一张卡片」 */
  .sheet-table {
    display: none;
  }

  .stu-list {
    display: block;
  }

  .class-select {
    width: 100%;
  }

  .table-legend {
    margin-top: 10px;
  }
}

@media (max-width: 420px) {
  .stu__fields {
    grid-template-columns: 1fr;
  }
}
</style>
