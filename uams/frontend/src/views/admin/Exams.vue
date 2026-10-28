<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { classroomApi, examApi, teacherApi, teachingApi } from '@/api'
import { currentSemester, semesterOptions } from '@/composables/useSemester'
import type { Classroom, Exam, ExamRoom, Teacher, TeachingClass } from '@/types'
import { createLatestGuard } from '@/utils/latest'

const semester = ref(currentSemester())
const exams = ref<Exam[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const loadGuard = createLatestGuard()

const classes = ref<TeachingClass[]>([])
const classrooms = ref<Classroom[]>([])
const teachers = ref<Teacher[]>([])

const dialog = ref(false)
const form = ref<Record<string, unknown>>({})
const saving = ref(false)

const roomDialog = ref(false)
const currentExam = ref<Exam | null>(null)
const roomEditingId = ref<number | null>(null)
const roomForm = ref<{ classroom_id?: number; capacity: number; invigilator_id?: number }>({ capacity: 60 })

const TYPE: Record<string, string> = { FINAL: '期末', MAKEUP: '补考', RETAKE: '重修' }
const STATUS: Record<string, string> = { DRAFT: '草稿', PUBLISHED: '已发布', FINISHED: '已结束' }
const STATUS_TYPE: Record<string, string> = { DRAFT: 'info', PUBLISHED: 'success', FINISHED: 'warning' }

function openCreate() {
  form.value = {
    teaching_class_id: undefined,
    exam_type: 'FINAL',
    exam_date: '',
    start_time: '09:00:00',
    end_time: '11:00:00',
    duration_minutes: 120,
  }
  dialog.value = true
}

async function save() {
  saving.value = true
  try {
    await examApi.create(form.value)
    ElMessage.success('考试已创建')
    dialog.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function remove(row: Exam) {
  try {
    await ElMessageBox.confirm(`确认删除《${row.course_name}》的考试？`, '确认删除', {
      type: 'warning',
    })
  } catch {
    return
  }
  await examApi.remove(row.id)
  ElMessage.success('已删除')
  await load()
}

function openRooms(row: Exam) {
  currentExam.value = row
  roomEditingId.value = null
  roomForm.value = { capacity: 60 }
  roomDialog.value = true
}

function editRoom(row: ExamRoom) {
  roomEditingId.value = row.id
  roomForm.value = {
    classroom_id: row.classroom_id,
    capacity: row.capacity,
    invigilator_id: row.invigilator_id ?? undefined,
  }
}

async function saveRoom() {
  if (!currentExam.value || !roomForm.value.classroom_id) {
    ElMessage.warning('请选择教室')
    return
  }
  if (roomEditingId.value) {
    await examApi.updateRoom(currentExam.value.id, roomEditingId.value, { ...roomForm.value })
    ElMessage.success('考场已更新')
  } else {
    await examApi.addRoom(currentExam.value.id, { ...roomForm.value })
    ElMessage.success('考场已添加')
  }
  roomEditingId.value = null
  roomForm.value = { capacity: 60 }
  await load()
  currentExam.value = exams.value.find((e) => e.id === currentExam.value?.id) ?? null
}

async function removeRoom(row: ExamRoom) {
  if (!currentExam.value) return
  try {
    await ElMessageBox.confirm(`确认删除考场 ${row.classroom_code}？已分配考生时系统会拒绝。`, '删除考场', { type: 'warning' })
  } catch { return }
  await examApi.removeRoom(currentExam.value.id, row.id)
  ElMessage.success('考场已删除')
  await load()
  currentExam.value = exams.value.find((e) => e.id === currentExam.value?.id) ?? null
}

async function assign(row: Exam) {
  const res = await examApi.assign(row.id)
  ElMessage.success(`已为 ${res.assigned} 名考生分配座位`)
  await load()
}

async function publish(row: Exam) {
  try {
    await ElMessageBox.confirm('发布后学生即可查询考试安排，确认发布？', '确认发布', {
      type: 'warning',
    })
  } catch {
    return
  }
  await examApi.publish(row.id)
  ElMessage.success('考试已发布')
  await load()
}

async function load() {
  const seq = loadGuard.next()
  loading.value = true
  try {
    const res = await examApi.list({ semester: semester.value, page: page.value, page_size: 20 })
    if (!loadGuard.isCurrent(seq)) return
    exams.value = res.items
    total.value = res.total
    if (!res.items.length && page.value > 1) {
      page.value -= 1
      await load()
    }
  } finally {
    if (loadGuard.isCurrent(seq)) loading.value = false
  }
}

watch(semester, () => {
  page.value = 1
  load()
})

onMounted(async () => {
  const [c, r, t] = await Promise.allSettled([
    teachingApi.classes({ semester: semester.value, page_size: 200 }),
    classroomApi.list({ page_size: 200 }),
    teacherApi.list({ page_size: 200 }),
  ])
  if (c.status === 'fulfilled') classes.value = c.value.items
  if (r.status === 'fulfilled') classrooms.value = r.value.items
  if (t.status === 'fulfilled') teachers.value = t.value.items
  await load()
})
</script>

<template>
  <div class="admin-exams">
    <el-card shadow="never" class="page-card" v-loading="loading">
      <!-- 筛选 + 主操作 -->
      <div class="toolbar">
        <el-select v-model="semester" style="width: 180px">
          <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
        </el-select>
        <div class="spacer" />
        <el-button type="primary" :icon="'Plus'" @click="openCreate">创建考试</el-button>
      </div>

      <!-- 空状态 -->
      <el-empty
        v-if="!exams.length"
        description="本学期暂无考试安排，点击右上角「创建考试」录入考试时间与教学班"
      />

      <template v-else>
        <!-- 桌面端：表格 -->
        <div class="table-wrap">
          <el-table :data="exams" stripe>
            <el-table-column label="课程" min-width="180">
              <template #default="{ row }">
                <div class="cell-course">
                  <span class="cell-course__name">{{ row.course_name }}</span>
                  <span class="cell-course__meta muted">{{ row.course_code }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="teaching_class_code" label="教学班" min-width="170" />
            <el-table-column label="类型" width="90" align="center">
              <template #default="{ row }">
                <el-tag size="small" effect="plain" type="info">
                  {{ TYPE[row.exam_type] }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="exam_date" label="日期" width="120" />
            <el-table-column label="时间" width="120" align="center">
              <template #default="{ row }">
                <span class="cell-time">
                  {{ row.start_time?.slice(0, 5) }}-{{ row.end_time?.slice(0, 5) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="考场" min-width="200">
              <template #default="{ row }">
                <div v-if="row.rooms?.length" class="room-list">
                  <span v-for="r in row.rooms" :key="r.id" class="room-chip">
                    <span class="room-chip__code">{{ r.classroom_code }}</span>
                    <span class="room-chip__seat">已排 {{ r.assigned_count }}/{{ r.capacity }}</span>
                  </span>
                </div>
                <el-tag v-else type="warning" size="small" effect="plain">未设置考场</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="STATUS_TYPE[row.status] as any" size="small">
                  {{ STATUS[row.status] }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="230" align="center" fixed="right">
              <template #default="{ row }">
                <el-button size="small" link type="primary" @click="openRooms(row)">考场</el-button>
                <el-button size="small" link type="primary" :disabled="!row.rooms?.length"
                  @click="assign(row)">排座</el-button>
                <el-button size="small" link type="primary" :disabled="row.status === 'PUBLISHED'"
                  @click="publish(row)">发布</el-button>
                <el-button size="small" link type="danger" @click="remove(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 移动端：每场考试一张卡片 -->
        <div class="exam-cards">
          <article v-for="row in exams" :key="row.id" class="exam-card">
            <header class="exam-card__head">
              <div class="exam-card__title">
                <span class="exam-card__name">{{ row.course_name }}</span>
                <span class="exam-card__meta muted">
                  {{ row.course_code }} · {{ row.teaching_class_code }}
                </span>
              </div>
              <el-tag :type="STATUS_TYPE[row.status] as any" size="small">
                {{ STATUS[row.status] }}
              </el-tag>
            </header>

            <div class="exam-card__when">
              <span class="when__item">
                <el-icon><component :is="'Calendar'" /></el-icon>
                {{ row.exam_date }}
              </span>
              <span class="when__item">
                <el-icon><component :is="'Clock'" /></el-icon>
                {{ row.start_time?.slice(0, 5) }}-{{ row.end_time?.slice(0, 5) }}
              </span>
              <el-tag size="small" effect="plain" type="info">{{ TYPE[row.exam_type] }}</el-tag>
            </div>

            <div class="exam-card__rooms">
              <template v-if="row.rooms?.length">
                <span v-for="r in row.rooms" :key="r.id" class="room-chip">
                  <span class="room-chip__code">{{ r.classroom_code }}</span>
                  <span class="room-chip__seat">已排 {{ r.assigned_count }}/{{ r.capacity }}</span>
                </span>
              </template>
              <el-tag v-else type="warning" size="small" effect="plain">未设置考场</el-tag>
            </div>

            <footer class="exam-card__foot">
              <el-button size="small" @click="openRooms(row)">考场</el-button>
              <el-button size="small" :disabled="!row.rooms?.length" @click="assign(row)">
                排座
              </el-button>
              <el-button size="small" :disabled="row.status === 'PUBLISHED'" @click="publish(row)">
                发布
              </el-button>
              <el-button size="small" type="danger" plain @click="remove(row)">删除</el-button>
            </footer>
          </article>
        </div>
      </template>

      <div class="pager">
        <el-pagination v-model:current-page="page" :total="total" :page-size="20"
          layout="total, prev, pager, next" @current-change="load" />
      </div>
    </el-card>

    <!-- 创建考试 -->
    <el-dialog v-model="dialog" title="创建考试" width="500px">
      <el-form label-width="100px">
        <el-form-item label="教学班" required>
          <el-select v-model="form.teaching_class_id" filterable style="width: 100%">
            <el-option v-for="c in classes" :key="c.id"
              :label="`${c.course_name}（${c.code}）`" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="考试类型">
          <el-radio-group v-model="form.exam_type">
            <el-radio value="FINAL">期末</el-radio>
            <el-radio value="MAKEUP">补考</el-radio>
            <el-radio value="RETAKE">重修</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="考试日期" required>
          <el-date-picker v-model="form.exam_date" type="date" value-format="YYYY-MM-DD"
            style="width: 100%" />
        </el-form-item>
        <el-form-item label="开始时间" required>
          <el-time-picker v-model="form.start_time" value-format="HH:mm:ss"
            style="width: 100%" />
        </el-form-item>
        <el-form-item label="结束时间" required>
          <el-time-picker v-model="form.end_time" value-format="HH:mm:ss"
            style="width: 100%" />
        </el-form-item>
        <el-form-item label="时长（分钟）">
          <el-input-number v-model="form.duration_minutes" :min="10" :max="480" :step="10" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">确定</el-button>
      </template>
    </el-dialog>

    <!-- 考场设置 -->
    <el-dialog v-model="roomDialog" :title="`考场设置 — ${currentExam?.course_name}`" width="560px">
      <div class="toolbar">
        <el-select v-model="roomForm.classroom_id" placeholder="选择教室" filterable
          style="width: 200px">
          <el-option v-for="r in classrooms" :key="r.id"
            :label="`${r.code}（容量 ${r.capacity}）`" :value="r.id" />
        </el-select>
        <el-input-number v-model="roomForm.capacity" :min="1" :max="500"
          style="width: 130px" />
        <el-select v-model="roomForm.invigilator_id" placeholder="监考教师" clearable
          filterable style="width: 160px">
          <el-option v-for="t in teachers" :key="t.id"
            :label="`${t.real_name}（${t.teacher_no}）`" :value="t.id" />
        </el-select>
        <el-button type="primary" @click="saveRoom">
          {{ roomEditingId ? '保存考场' : '添加考场' }}
        </el-button>
        <el-button v-if="roomEditingId" @click="roomEditingId = null; roomForm = { capacity: 60 }">
          取消编辑
        </el-button>
      </div>

      <div class="table-wrap">
        <el-table :data="currentExam?.rooms ?? []" size="small" stripe>
          <el-table-column prop="classroom_code" label="教室" width="120" />
          <el-table-column prop="building" label="楼栋" min-width="120" />
          <el-table-column prop="capacity" label="容量" width="90" align="center" />
          <el-table-column prop="assigned_count" label="已排" width="80" align="center" />
          <el-table-column prop="invigilator_name" label="监考教师" width="110" />
          <el-table-column label="操作" width="110" align="center">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="editRoom(row)">编辑</el-button>
              <el-button link type="danger" size="small" @click="removeRoom(row)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty><el-empty description="尚未设置考场" :image-size="60" /></template>
        </el-table>
      </div>

      <div class="room-cards">
        <div v-for="r in currentExam?.rooms ?? []" :key="r.id" class="room-row">
          <span class="room-row__code">{{ r.classroom_code }}</span>
          <span class="room-row__building muted">{{ r.building }}</span>
          <span class="room-row__seat">已排 {{ r.assigned_count }}/{{ r.capacity }}</span>
        </div>
        <el-empty v-if="!(currentExam?.rooms?.length)"
          description="尚未设置考场" :image-size="60" />
      </div>

      <el-alert type="info" :closable="false" show-icon style="margin-top: 12px"
        title="添加考场后点击「排座」自动为已选课学生分配座位号" />
    </el-dialog>
  </div>
</template>

<style scoped>
.admin-exams {
  display: block;
}

/* ------------------------------------------------------------- 表格单元 */
.cell-course {
  display: flex;
  flex-direction: column;
  line-height: 1.35;
}

.cell-course__name {
  font-weight: 600;
  color: var(--uams-text);
}

.cell-course__meta {
  font-size: 12px;
}

/* 考试时间属核心信息，稍作强调 */
.cell-time {
  font-weight: 600;
  color: var(--uams-text);
  font-variant-numeric: tabular-nums;
}

/* -------------------------------------------------------------- 考场 chip */
.room-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.room-chip {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  padding: 2px 8px;
  border-radius: var(--uams-radius-xs);
  background: var(--uams-primary-soft);
  font-size: 12px;
  line-height: 1.7;
}

.room-chip__code {
  font-weight: 600;
  color: var(--uams-primary-dark);
}

.room-chip__seat {
  color: var(--uams-text-2);
  font-variant-numeric: tabular-nums;
}

/* ------------------------------------------------------- 移动端考试卡片 */
.exam-cards {
  display: none;
  flex-direction: column;
  gap: 12px;
}

.exam-card {
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface);
  overflow: hidden;
}

.exam-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 14px;
  background: var(--uams-surface-sunken);
  border-bottom: 1px solid var(--uams-border);
}

.exam-card__title {
  min-width: 0;
}

.exam-card__name {
  font-weight: 600;
  color: var(--uams-text);
}

.exam-card__meta {
  display: block;
  margin-top: 2px;
  font-size: 12px;
  word-break: break-word;
}

.exam-card__when {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  padding: 12px 14px;
}

.when__item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: var(--uams-text);
  font-variant-numeric: tabular-nums;
}

.when__item .el-icon {
  color: var(--uams-primary);
}

.exam-card__rooms {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 14px 12px;
}

.exam-card__foot {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  padding: 12px 14px;
  border-top: 1px solid var(--uams-border);
}

.exam-card__foot .el-button {
  width: 100%;
  margin-left: 0;
}

/* --------------------------------------------------- 弹窗内考场移动形态 */
.room-cards {
  display: none;
  flex-direction: column;
  gap: 8px;
}

.room-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-xs);
  background: var(--uams-surface-sunken);
}

.room-row__code {
  font-weight: 600;
  color: var(--uams-text);
}

.room-row__building {
  flex: 1;
  font-size: 12px;
  min-width: 0;
}

.room-row__seat {
  font-size: 12px;
  font-weight: 600;
  color: var(--uams-primary-dark);
  font-variant-numeric: tabular-nums;
}

/* -------------------------------------------------------------- 响应式 */
@media (max-width: 768px) {
  .table-wrap {
    display: none;
  }

  .exam-cards {
    display: flex;
  }

  .room-cards {
    display: flex;
  }

  /* 触控目标：按钮加高，操作列更易点按 */
  .exam-card__foot .el-button {
    height: 38px;
  }
}
</style>