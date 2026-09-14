<script setup lang="ts">
/** 开课排课：教学任务 → 教学班 → 排课 → 开放选课。 */
import { onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { classroomApi, collegeApi, courseApi, teacherApi, teachingApi } from '@/api'
import { currentSemester, semesterOptions } from '@/composables/useSemester'
import type {
  Classroom,
  College,
  Course,
  Schedule,
  Teacher,
  TeachingClass,
  TeachingTask,
} from '@/types'

const tab = ref('class')
const semester = ref(currentSemester())

const colleges = ref<College[]>([])
const courses = ref<Course[]>([])
const teachers = ref<Teacher[]>([])
const classrooms = ref<Classroom[]>([])

const tasks = ref<TeachingTask[]>([])
const tasksTotal = ref(0)
const taskPage = ref(1)
const classes = ref<TeachingClass[]>([])
const classesTotal = ref(0)
const classPage = ref(1)
const loading = ref(false)

const DAY = ['', '周一', '周二', '周三', '周四', '周五', '周六', '周日']
const TASK_STATUS: Record<string, string> = {
  DRAFT: '草稿', CONFIRMED: '已确认', CANCELLED: '已取消',
}
const SEL_STATUS: Record<string, string> = {
  CLOSED: '未开放', OPEN: '选课中', FINISHED: '已结束',
}
const SEL_TYPE: Record<string, string> = {
  CLOSED: 'info', OPEN: 'success', FINISHED: 'warning',
}

// --- 教学任务表单 ---
const taskDialog = ref(false)
const taskForm = ref<Record<string, unknown>>({})
const taskSaving = ref(false)

function openTask() {
  taskForm.value = {
    semester: semester.value,
    course_id: undefined,
    college_id: colleges.value[0]?.id,
    planned_classes: 1,
    status: 'CONFIRMED',
  }
  taskDialog.value = true
}

async function saveTask() {
  taskSaving.value = true
  try {
    await teachingApi.createTask(taskForm.value)
    ElMessage.success('教学任务已创建')
    taskDialog.value = false
    await loadTasks()
  } finally {
    taskSaving.value = false
  }
}

async function removeTask(row: TeachingTask) {
  try {
    await ElMessageBox.confirm(`确认删除《${row.course_name}》的教学任务？`, '确认删除', {
      type: 'warning',
    })
  } catch {
    return
  }
  await teachingApi.removeTask(row.id)
  ElMessage.success('已删除')
  await loadTasks()
}

// --- 教学班表单 ---
const classDialog = ref(false)
const classForm = ref<Record<string, unknown>>({})
const classMode = ref<'create' | 'edit'>('create')
const classEditingId = ref<number | null>(null)
const classSaving = ref(false)

function openClassCreate() {
  classMode.value = 'create'
  classEditingId.value = null
  classForm.value = { code: '', task_id: undefined, teacher_id: undefined, capacity: 40 }
  classDialog.value = true
}

function openClassEdit(row: TeachingClass) {
  classMode.value = 'edit'
  classEditingId.value = row.id
  classForm.value = {
    teacher_id: row.teacher_id ?? undefined,
    capacity: row.capacity,
    selection_status: row.selection_status,
  }
  classDialog.value = true
}

async function saveClass() {
  classSaving.value = true
  try {
    if (classMode.value === 'create') {
      await teachingApi.createClass(classForm.value)
      ElMessage.success('教学班已创建')
    } else if (classEditingId.value) {
      await teachingApi.updateClass(classEditingId.value, classForm.value)
      ElMessage.success('教学班已更新')
    }
    classDialog.value = false
    await loadClasses()
  } finally {
    classSaving.value = false
  }
}

async function removeClass(row: TeachingClass) {
  try {
    await ElMessageBox.confirm(`确认删除教学班「${row.code}」？`, '确认删除', {
      type: 'warning',
    })
  } catch {
    return
  }
  await teachingApi.removeClass(row.id)
  ElMessage.success('已删除')
  await loadClasses()
}

async function toggleSelection(row: TeachingClass) {
  const open = row.selection_status !== 'OPEN'
  await teachingApi.toggleSelection(row.id, open)
  ElMessage.success(open ? '已开放选课' : '已关闭选课')
  await loadClasses()
}

// --- 排课 ---
const schedDialog = ref(false)
const schedClass = ref<TeachingClass | null>(null)
const schedList = ref<Schedule[]>([])
const schedForm = ref({
  classroom_id: undefined as number | undefined,
  day_of_week: 1,
  start_period: 1,
  end_period: 2,
  start_week: 1,
  end_week: 16,
  week_type: 'ALL',
})

async function openSchedule(row: TeachingClass) {
  schedClass.value = row
  schedList.value = await teachingApi.schedules(row.id)
  schedDialog.value = true
}

async function addSchedule() {
  if (!schedClass.value || !schedForm.value.classroom_id) {
    ElMessage.warning('请选择教室')
    return
  }
  // 教室/教师冲突由后端检测，失败时拦截器会提示具体冲突原因
  await teachingApi.addSchedule(schedClass.value.id, { ...schedForm.value })
  ElMessage.success('排课成功')
  schedList.value = await teachingApi.schedules(schedClass.value.id)
  await loadClasses()
}

async function removeSchedule(row: Schedule) {
  if (!schedClass.value) return
  await teachingApi.removeSchedule(schedClass.value.id, row.id)
  schedList.value = await teachingApi.schedules(schedClass.value.id)
  await loadClasses()
}

function scheduleText(tc: TeachingClass) {
  if (!tc.schedules?.length) return '未排课'
  return tc.schedules
    .map((s) => `${DAY[s.day_of_week]}${s.start_period}-${s.end_period}节 ${s.classroom_code ?? ''}`)
    .join('；')
}

// --- 加载 ---
async function loadTasks() {
  loading.value = true
  try {
    const res = await teachingApi.tasks({
      semester: semester.value,
      page: taskPage.value,
      page_size: 20,
    })
    tasks.value = res.items
    tasksTotal.value = res.total
  } finally {
    loading.value = false
  }
}

async function loadClasses() {
  loading.value = true
  try {
    const res = await teachingApi.classes({
      semester: semester.value,
      page: classPage.value,
      page_size: 20,
    })
    classes.value = res.items
    classesTotal.value = res.total
  } finally {
    loading.value = false
  }
}

watch(semester, () => {
  taskPage.value = 1
  classPage.value = 1
  loadTasks()
  loadClasses()
})
watch(tab, (v) => (v === 'task' ? loadTasks() : loadClasses()))

onMounted(async () => {
  const [co, cr, te, rm] = await Promise.allSettled([
    collegeApi.list({ page_size: 200 }),
    courseApi.list({ page_size: 200 }),
    teacherApi.list({ page_size: 200 }),
    classroomApi.list({ page_size: 200 }),
  ])
  if (co.status === 'fulfilled') colleges.value = co.value.items
  if (cr.status === 'fulfilled') courses.value = cr.value.items
  if (te.status === 'fulfilled') teachers.value = te.value.items
  if (rm.status === 'fulfilled') classrooms.value = rm.value.items
  await loadTasks()
  await loadClasses()
})
</script>

<template>
  <el-card shadow="never" v-loading="loading">
    <div class="toolbar">
      <el-select v-model="semester" style="width: 180px">
        <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
      </el-select>
      <div class="spacer" />
      <el-button v-if="tab === 'task'" type="primary" :icon="'Plus'" @click="openTask">
        新增教学任务
      </el-button>
      <el-button v-else type="primary" :icon="'Plus'" @click="openClassCreate">
        新增教学班
      </el-button>
    </div>

    <el-tabs v-model="tab">
      <el-tab-pane label="教学班" name="class">
        <el-table :data="classes" stripe>
          <el-table-column prop="code" label="教学班号" min-width="170" />
          <el-table-column prop="course_name" label="课程" min-width="150" />
          <el-table-column prop="credits" label="学分" width="70" align="center" />
          <el-table-column label="授课教师" width="110">
            <template #default="{ row }">
              <span v-if="row.teacher_name">{{ row.teacher_name }}</span>
              <el-tag v-else type="warning" size="small">未分配</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="上课安排" min-width="220">
            <template #default="{ row }">
              <span class="sched">{{ scheduleText(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="选课人数" width="110" align="center">
            <template #default="{ row }">
              <el-tag :type="row.remaining > 0 ? '' : 'danger'" size="small">
                {{ row.selected_count }}/{{ row.capacity }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="选课状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="SEL_TYPE[row.selection_status] as any" size="small">
                {{ SEL_STATUS[row.selection_status] }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="230" align="center" fixed="right">
            <template #default="{ row }">
              <el-button size="small" link type="primary" @click="openSchedule(row)">
                排课
              </el-button>
              <el-button size="small" link type="primary" @click="toggleSelection(row)">
                {{ row.selection_status === 'OPEN' ? '关闭选课' : '开放选课' }}
              </el-button>
              <el-button size="small" link type="primary" @click="openClassEdit(row)">
                编辑
              </el-button>
              <el-button size="small" link type="danger" @click="removeClass(row)">
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="pager">
          <el-pagination v-model:current-page="classPage" :total="classesTotal"
            :page-size="20" layout="total, prev, pager, next" @current-change="loadClasses" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="教学任务" name="task">
        <el-table :data="tasks" stripe>
          <el-table-column prop="semester" label="学期" width="130" />
          <el-table-column prop="course_code" label="课程代码" width="110" />
          <el-table-column prop="course_name" label="课程名称" min-width="170" />
          <el-table-column prop="college_name" label="承担学院" min-width="160" />
          <el-table-column label="计划/实际开班" width="130" align="center">
            <template #default="{ row }">
              {{ row.class_count }} / {{ row.planned_classes }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag size="small">{{ TASK_STATUS[row.status] }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90" align="center">
            <template #default="{ row }">
              <el-button size="small" link type="danger" @click="removeTask(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="pager">
          <el-pagination v-model:current-page="taskPage" :total="tasksTotal"
            :page-size="20" layout="total, prev, pager, next" @current-change="loadTasks" />
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 教学任务表单 -->
    <el-dialog v-model="taskDialog" title="新增教学任务" width="480px">
      <el-form label-width="100px">
        <el-form-item label="学期" required>
          <el-select v-model="taskForm.semester" style="width: 100%">
            <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="课程" required>
          <el-select v-model="taskForm.course_id" filterable style="width: 100%">
            <el-option v-for="c in courses" :key="c.id"
              :label="`${c.code} ${c.name}`" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="承担学院" required>
          <el-select v-model="taskForm.college_id" style="width: 100%">
            <el-option v-for="c in colleges" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="计划开班数">
          <el-input-number v-model="taskForm.planned_classes" :min="1" :max="50" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="taskDialog = false">取消</el-button>
        <el-button type="primary" :loading="taskSaving" @click="saveTask">确定</el-button>
      </template>
    </el-dialog>

    <!-- 教学班表单 -->
    <el-dialog v-model="classDialog"
      :title="classMode === 'create' ? '新增教学班' : '编辑教学班'" width="480px">
      <el-form label-width="100px">
        <template v-if="classMode === 'create'">
          <el-form-item label="教学班号" required>
            <el-input v-model="classForm.code" placeholder="如 CS101-2026-2027-1-01" />
          </el-form-item>
          <el-form-item label="教学任务" required>
            <el-select v-model="classForm.task_id" filterable style="width: 100%">
              <el-option v-for="t in tasks" :key="t.id"
                :label="`${t.course_name}（${t.semester}）`" :value="t.id" />
            </el-select>
          </el-form-item>
        </template>
        <el-form-item label="授课教师">
          <el-select v-model="classForm.teacher_id" filterable clearable style="width: 100%">
            <el-option v-for="t in teachers" :key="t.id"
              :label="`${t.real_name}（${t.teacher_no}）`" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="容量" required>
          <el-input-number v-model="classForm.capacity" :min="1" :max="1000" />
        </el-form-item>
        <el-form-item v-if="classMode === 'edit'" label="选课状态">
          <el-select v-model="classForm.selection_status" style="width: 100%">
            <el-option label="未开放" value="CLOSED" />
            <el-option label="选课中" value="OPEN" />
            <el-option label="已结束" value="FINISHED" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="classDialog = false">取消</el-button>
        <el-button type="primary" :loading="classSaving" @click="saveClass">确定</el-button>
      </template>
    </el-dialog>

    <!-- 排课 -->
    <el-dialog v-model="schedDialog" :title="`排课 — ${schedClass?.course_name}`" width="780px">
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 14px"
        title="系统自动检测教室冲突与教师冲突；单周/双周课程在同一时段可共用教室" />
      <div class="sched-form">
        <el-select v-model="schedForm.classroom_id" placeholder="教室" filterable
          style="width: 150px">
          <el-option v-for="r in classrooms" :key="r.id"
            :label="`${r.code}(${r.capacity}人)`" :value="r.id" />
        </el-select>
        <el-select v-model="schedForm.day_of_week" style="width: 100px">
          <el-option v-for="d in 7" :key="d" :label="DAY[d]" :value="d" />
        </el-select>
        <el-input-number v-model="schedForm.start_period" :min="1" :max="14"
          controls-position="right" style="width: 100px" />
        <span class="dash">-</span>
        <el-input-number v-model="schedForm.end_period" :min="1" :max="14"
          controls-position="right" style="width: 100px" />
        <span class="unit">节</span>
        <el-input-number v-model="schedForm.start_week" :min="1" :max="30"
          controls-position="right" style="width: 100px" />
        <span class="dash">-</span>
        <el-input-number v-model="schedForm.end_week" :min="1" :max="30"
          controls-position="right" style="width: 100px" />
        <span class="unit">周</span>
        <el-select v-model="schedForm.week_type" style="width: 100px">
          <el-option label="每周" value="ALL" />
          <el-option label="单周" value="ODD" />
          <el-option label="双周" value="EVEN" />
        </el-select>
        <el-button type="primary" @click="addSchedule">添加</el-button>
      </div>

      <el-table :data="schedList" size="small" stripe style="margin-top: 14px">
        <el-table-column label="星期" width="80" align="center">
          <template #default="{ row }">{{ DAY[row.day_of_week] }}</template>
        </el-table-column>
        <el-table-column label="节次" width="100" align="center">
          <template #default="{ row }">{{ row.start_period }}-{{ row.end_period }} 节</template>
        </el-table-column>
        <el-table-column label="周次" width="120" align="center">
          <template #default="{ row }">
            {{ row.start_week }}-{{ row.end_week }} 周
            <span v-if="row.week_type !== 'ALL'">
              ({{ row.week_type === 'ODD' ? '单' : '双' }})
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="classroom_code" label="教室" width="110" />
        <el-table-column prop="building" label="楼栋" min-width="110" />
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="danger" @click="removeSchedule(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="尚未排课" :image-size="60" /></template>
      </el-table>
    </el-dialog>
  </el-card>
</template>

<style scoped>
.sched { font-size: 12px; color: #606266; }
.sched-form {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.dash, .unit { color: #909399; font-size: 13px; }
</style>
