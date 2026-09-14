<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { classroomApi, examApi, teachingApi } from '@/api'
import { currentSemester, semesterOptions } from '@/composables/useSemester'
import type { Classroom, Exam, TeachingClass } from '@/types'

const semester = ref(currentSemester())
const exams = ref<Exam[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)

const classes = ref<TeachingClass[]>([])
const classrooms = ref<Classroom[]>([])

const dialog = ref(false)
const form = ref<Record<string, unknown>>({})
const saving = ref(false)

const roomDialog = ref(false)
const currentExam = ref<Exam | null>(null)
const roomForm = ref<{ classroom_id?: number; capacity: number }>({ capacity: 60 })

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
  roomForm.value = { capacity: 60 }
  roomDialog.value = true
}

async function addRoom() {
  if (!currentExam.value || !roomForm.value.classroom_id) {
    ElMessage.warning('请选择教室')
    return
  }
  await examApi.addRoom(currentExam.value.id, { ...roomForm.value })
  ElMessage.success('考场已添加')
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
  loading.value = true
  try {
    const res = await examApi.list({ semester: semester.value, page: page.value, page_size: 20 })
    exams.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

watch(semester, () => {
  page.value = 1
  load()
})

onMounted(async () => {
  const [c, r] = await Promise.allSettled([
    teachingApi.classes({ semester: semester.value, page_size: 200 }),
    classroomApi.list({ page_size: 200 }),
  ])
  if (c.status === 'fulfilled') classes.value = c.value.items
  if (r.status === 'fulfilled') classrooms.value = r.value.items
  await load()
})
</script>

<template>
  <el-card shadow="never" v-loading="loading">
    <div class="toolbar">
      <el-select v-model="semester" style="width: 180px">
        <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
      </el-select>
      <div class="spacer" />
      <el-button type="primary" :icon="'Plus'" @click="openCreate">创建考试</el-button>
    </div>

    <el-table :data="exams" stripe>
      <el-table-column prop="course_name" label="课程" min-width="160" />
      <el-table-column prop="teaching_class_code" label="教学班" min-width="170" />
      <el-table-column label="类型" width="90" align="center">
        <template #default="{ row }">{{ TYPE[row.exam_type] }}</template>
      </el-table-column>
      <el-table-column prop="exam_date" label="日期" width="120" />
      <el-table-column label="时间" width="130">
        <template #default="{ row }">
          {{ row.start_time?.slice(0, 5) }}-{{ row.end_time?.slice(0, 5) }}
        </template>
      </el-table-column>
      <el-table-column label="考场" min-width="150">
        <template #default="{ row }">
          <template v-if="row.rooms?.length">
            <el-tag v-for="r in row.rooms" :key="r.id" size="small" style="margin-right: 4px">
              {{ r.classroom_code }} ({{ r.assigned_count }}/{{ r.capacity }})
            </el-tag>
          </template>
          <el-tag v-else type="warning" size="small">未设置</el-tag>
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
      <template #empty><el-empty description="本学期暂无考试安排" /></template>
    </el-table>

    <div class="pager">
      <el-pagination v-model:current-page="page" :total="total" :page-size="20"
        layout="total, prev, pager, next" @current-change="load" />
    </div>

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

    <el-dialog v-model="roomDialog" :title="`考场设置 — ${currentExam?.course_name}`" width="560px">
      <div class="toolbar">
        <el-select v-model="roomForm.classroom_id" placeholder="选择教室" filterable
          style="width: 200px">
          <el-option v-for="r in classrooms" :key="r.id"
            :label="`${r.code}（容量 ${r.capacity}）`" :value="r.id" />
        </el-select>
        <el-input-number v-model="roomForm.capacity" :min="1" :max="500"
          style="width: 130px" />
        <el-button type="primary" @click="addRoom">添加考场</el-button>
      </div>
      <el-table :data="currentExam?.rooms ?? []" size="small" stripe>
        <el-table-column prop="classroom_code" label="教室" width="120" />
        <el-table-column prop="building" label="楼栋" min-width="120" />
        <el-table-column prop="capacity" label="容量" width="90" align="center" />
        <el-table-column prop="assigned_count" label="已排" width="90" align="center" />
        <template #empty><el-empty description="尚未设置考场" :image-size="60" /></template>
      </el-table>
      <el-alert type="info" :closable="false" show-icon style="margin-top: 12px"
        title="添加考场后点击「排座」自动为已选课学生分配座位号" />
    </el-dialog>
  </el-card>
</template>
