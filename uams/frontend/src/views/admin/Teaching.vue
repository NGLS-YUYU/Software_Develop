<script setup lang="ts">
/** 开课排课：教学任务 → 教学班 → 排课 → 开放选课。 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { classroomApi, collegeApi, courseApi, scheduleApi, teacherApi, teachingApi, termApi } from '@/api'
import ClassEnrollmentDialog from '@/components/ClassEnrollmentDialog.vue'
import { currentSemester, semesterOptions } from '@/composables/useSemester'
import { createLatestGuard } from '@/utils/latest'
import type {
  Classroom,
  College,
  Course,
  Schedule,
  Teacher,
  TeachingClass,
  TeachingTask,
  Term,
} from '@/types'

const tab = ref('class')
const semester = ref(currentSemester())

const colleges = ref<College[]>([])
const courses = ref<Course[]>([])
const teachers = ref<Teacher[]>([])
const classrooms = ref<Classroom[]>([])
/** 学期（academic_terms）列表：用于把页面上的学期字符串解析成后端要求的 term_id */
const terms = ref<Term[]>([])

/**
 * 把页面的学期字符串（如 2026-2027-1）解析为学期实体。
 * 后端 POST /teaching-classes 要求 term_id（academic_terms.id），
 * 而本页的学期筛选用的是 "学年-学年-序号" 字符串，两者需要在此对应（不写死 ID）。
 */
function termForSemester(s: string): Term | null {
  const m = /^(\d{4}-\d{4})-([12])$/.exec(s)
  if (!m) return null
  return (
    terms.value.find(
      (t) => t.academic_year === m[1] && t.semester === Number(m[2]),
    ) ?? null
  )
}

/** 新增教学班将归属的学期（取自页面当前选择的学期） */
const createTerm = computed(() => termForSemester(semester.value))

const tasks = ref<TeachingTask[]>([])
const tasksTotal = ref(0)
const taskPage = ref(1)
const classes = ref<TeachingClass[]>([])
const classesTotal = ref(0)
const classPage = ref(1)
const loading = ref(false)
const taskSelection = ref<TeachingTask[]>([])
const classSelection = ref<TeachingClass[]>([])
const scheduleSelection = ref<Schedule[]>([])
const batchBusy = ref(false)
const taskGuard = createLatestGuard()
const classGuard = createLatestGuard()

/** FIX-002：教学班学生安排/名单弹窗 */
const enrollVisible = ref(false)
const enrollClass = ref<TeachingClass | null>(null)

function openEnrollment(row: TeachingClass) {
  enrollClass.value = row
  enrollVisible.value = true
}

async function onEnrollmentChanged() {
  await loadClasses()
}

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
const taskEditingId = ref<number | null>(null)

function openTask() {
  taskEditingId.value = null
  taskForm.value = {
    semester: semester.value,
    course_id: undefined,
    college_id: colleges.value[0]?.id,
    planned_classes: 1,
    status: 'CONFIRMED',
  }
  taskDialog.value = true
}

function openTaskEdit(row: TeachingTask) {
  taskEditingId.value = row.id
  taskForm.value = {
    semester: row.semester,
    course_id: row.course_id,
    college_id: row.college_id,
    planned_classes: row.planned_classes,
    status: row.status,
  }
  taskDialog.value = true
}

async function saveTask() {
  taskSaving.value = true
  try {
    if (taskEditingId.value) {
      await teachingApi.updateTask(taskEditingId.value, {
        planned_classes: taskForm.value.planned_classes,
        status: taskForm.value.status,
      })
      ElMessage.success('教学任务已更新')
    } else {
      await teachingApi.createTask(taskForm.value)
      ElMessage.success('教学任务已创建')
    }
    taskDialog.value = false
    await loadTasks()
  } catch {
    // 失败提示由 axios 拦截器统一给出；保留弹窗便于修改后重试
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
  try {
    await teachingApi.removeTask(row.id)
    ElMessage.success('已删除')
    await loadTasks()
  } catch {
    // 有引用等业务拒绝由拦截器提示
  }
}

// --- 教学班表单 ---
const classDialog = ref(false)
const classForm = ref<Record<string, unknown>>({})
const classMode = ref<'create' | 'edit'>('create')
const classEditingId = ref<number | null>(null)
const classSaving = ref(false)

function openClassCreate() {
  // 没有对应学期就不要打开表单：后端要求 term_id，提交必然失败
  if (!createTerm.value) {
    ElMessage.warning(
      `当前学期「${semester.value}」在学期管理中不存在，请先在「学期管理」创建该学期后再新增教学班`,
    )
    return
  }
  classMode.value = 'create'
  classEditingId.value = null
  classForm.value = {
    code: '',
    task_id: undefined,
    teacher_id: undefined,
    capacity: 40,
    // 后端 TeachingClassCreate.term_id 必填；course_id / semester 由教学任务带入
    term_id: createTerm.value.id,
  }
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
  if (classMode.value === 'create') {
    // 提交前校验：字段缺失或学期不可用时给出明确提示，不发出无效请求
    const t = createTerm.value
    if (!t) {
      ElMessage.warning(`学期「${semester.value}」不存在，无法新增教学班`)
      return
    }
    if (t.status === 'ENDED') {
      ElMessage.warning(`学期「${t.name}」已结束，不能新增教学班`)
      return
    }
    if (!classForm.value.code || !classForm.value.task_id) {
      ElMessage.warning('请填写教学班号并选择教学任务')
      return
    }
  }
  classSaving.value = true
  try {
    if (classMode.value === 'create') {
      await teachingApi.createClass(classForm.value)
      ElMessage.success('教学班已创建')
    } else if (classEditingId.value) {
      // 编辑不带 term_id：后端约定教学班所属学期不可修改（TeachingClassTermImmutable）
      await teachingApi.updateClass(classEditingId.value, classForm.value)
      ElMessage.success('教学班已更新')
    }
    classDialog.value = false
    await loadClasses()
    // 教学任务列表中的“已开班数”依赖教学班数量，必须同步刷新。
    await loadTasks()
  } catch {
    // 失败时保留弹窗与已填内容，错误提示由 axios 拦截器统一给出
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
  try {
    await teachingApi.removeClass(row.id)
    ElMessage.success('已删除')
    await loadClasses()
    await loadTasks()
  } catch {
    // 有选课/成绩等业务拒绝由拦截器提示
  }
}

async function toggleSelection(row: TeachingClass) {
  const open = row.selection_status !== 'OPEN'
  try {
    await teachingApi.toggleSelection(row.id, open)
    ElMessage.success(open ? '已开放选课' : '已关闭选课')
    await loadClasses()
  } catch {
    // 开放条件不满足等业务拒绝由拦截器提示
  }
}

// --- 排课 ---
const schedDialog = ref(false)
const schedClass = ref<TeachingClass | null>(null)
const schedList = ref<Schedule[]>([])
/** 编辑中的排课 id；为空表示新增（FIX-007 新增修改入口）。 */
const schedEditingId = ref<number | null>(null)
const schedSaving = ref(false)

const emptySchedForm = () => ({
  classroom_id: undefined as number | undefined,
  day_of_week: 1,
  start_period: 1,
  end_period: 2,
  start_week: 1,
  end_week: 16,
  week_type: 'ALL',
})
const schedForm = ref(emptySchedForm())

async function openSchedule(row: TeachingClass) {
  schedClass.value = row
  schedEditingId.value = null
  schedForm.value = emptySchedForm()
  // 教学安排统一走 TASK-013 平铺接口（按教学班过滤在数据库层完成）
  schedList.value = await scheduleApi.list({ teaching_class_id: row.id })
  schedDialog.value = true
}

async function reloadSchedules() {
  if (!schedClass.value) return
  schedList.value = await scheduleApi.list({ teaching_class_id: schedClass.value.id })
}

/** 把一行排课载入表单，切换为「编辑」状态。 */
function editSchedule(row: Schedule) {
  schedEditingId.value = row.id
  schedForm.value = {
    classroom_id: row.classroom_id,
    day_of_week: row.day_of_week,
    start_period: row.start_period,
    end_period: row.end_period,
    start_week: row.start_week,
    end_week: row.end_week,
    week_type: row.week_type,
  }
}

function cancelEditSchedule() {
  schedEditingId.value = null
  schedForm.value = emptySchedForm()
}

async function saveSchedule() {
  if (!schedClass.value || !schedForm.value.classroom_id) {
    ElMessage.warning('请选择教室')
    return
  }
  const f = schedForm.value
  if (f.end_period < f.start_period) {
    ElMessage.warning('结束节次不能早于开始节次')
    return
  }
  if (f.end_week < f.start_week) {
    ElMessage.warning('结束周不能早于开始周')
    return
  }
  schedSaving.value = true
  try {
    if (schedEditingId.value != null) {
      // 教室/教师/教学班冲突一律由后端重新检测，失败时拦截器提示具体冲突原因
      await scheduleApi.update(schedEditingId.value, { ...f })
      ElMessage.success('排课已更新')
    } else {
      await scheduleApi.create({
        teaching_class_id: schedClass.value.id,
        ...f,
      })
      ElMessage.success('排课成功')
    }
    cancelEditSchedule()
    await reloadSchedules()
    await loadClasses()
  } catch {
    // 409 冲突由 axios 拦截器统一提示，表单保持原样便于修改后重试
  } finally {
    schedSaving.value = false
  }
}

async function removeSchedule(row: Schedule) {
  try {
    await ElMessageBox.confirm(
      `${DAY[row.day_of_week]} ${row.start_period}-${row.end_period} 节（${row.classroom_code ?? ''}）确定删除？`,
      '删除排课',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await scheduleApi.remove(row.id)
    ElMessage.success('已删除')
    if (schedEditingId.value === row.id) cancelEditSchedule()
    await reloadSchedules()
    await loadClasses()
  } catch {
    // 已结束学期等业务拒绝由拦截器提示
  }
}

function scheduleText(tc: TeachingClass) {
  if (!tc.schedules?.length) return '未排课'
  return tc.schedules
    .map((s) => `${DAY[s.day_of_week]}${s.start_period}-${s.end_period}节 ${s.classroom_code ?? ''}`)
    .join('；')
}

// --- 批量删除 ---
function onTaskSelection(rows: TeachingTask[]) { taskSelection.value = rows }
function onClassSelection(rows: TeachingClass[]) { classSelection.value = rows }
function onScheduleSelection(rows: Schedule[]) { scheduleSelection.value = rows }

async function batchDeleteTasks() {
  const ids = taskSelection.value.map((r) => r.id)
  if (!ids.length) { ElMessage.warning('请先选择教学任务'); return }
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${ids.length} 个教学任务？`, '批量删除', { type: 'warning' })
  } catch { return }
  batchBusy.value = true
  try {
    const res = await teachingApi.batchRemoveTasks(ids)
    if (res.failed.length) ElMessage.warning(`已删除 ${res.deleted.length}，失败 ${res.failed.length}：${res.failed.slice(0,3).map(f=>`#${f.id} ${f.reason}`).join('；')}`)
    else ElMessage.success(`已删除 ${res.deleted.length} 个教学任务`)
    await loadTasks()
    await loadClasses()
  } finally { batchBusy.value = false }
}

async function batchDeleteClasses() {
  const ids = classSelection.value.map((r) => r.id)
  if (!ids.length) { ElMessage.warning('请先选择教学班'); return }
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${ids.length} 个教学班？`, '批量删除', { type: 'warning' })
  } catch { return }
  batchBusy.value = true
  try {
    const res = await teachingApi.batchRemoveClasses(ids)
    if (res.failed.length) ElMessage.warning(`已删除 ${res.deleted.length}，失败 ${res.failed.length}：${res.failed.slice(0,3).map(f=>`#${f.id} ${f.reason}`).join('；')}`)
    else ElMessage.success(`已删除 ${res.deleted.length} 个教学班`)
    await loadClasses()
    await loadTasks()
  } finally { batchBusy.value = false }
}

async function batchDeleteSchedules() {
  const ids = scheduleSelection.value.map((r) => r.id)
  if (!ids.length) { ElMessage.warning('请先选择排课记录'); return }
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${ids.length} 条排课？不会删除教学班和学生。`, '批量删除', { type: 'warning' })
  } catch { return }
  batchBusy.value = true
  try {
    const res = await scheduleApi.batchRemove(ids)
    if (res.failed.length) ElMessage.warning(`已删除 ${res.deleted.length}，失败 ${res.failed.length}：${res.failed.slice(0,3).map(f=>`#${f.id} ${f.reason}`).join('；')}`)
    else ElMessage.success(`已删除 ${res.deleted.length} 条排课`)
    await reloadSchedules()
    await loadClasses()
  } finally { batchBusy.value = false }
}

// --- 加载 ---
async function loadTasks() {
  const seq = taskGuard.next()
  loading.value = true
  try {
    const res = await teachingApi.tasks({
      semester: semester.value,
      page: taskPage.value,
      page_size: 20,
    })
    if (!taskGuard.isCurrent(seq)) return
    tasks.value = res.items
    tasksTotal.value = res.total
  } finally {
    if (taskGuard.isCurrent(seq)) loading.value = false
  }
}

async function loadClasses() {
  const seq = classGuard.next()
  loading.value = true
  try {
    const res = await teachingApi.classes({
      semester: semester.value,
      page: classPage.value,
      page_size: 20,
    })
    if (!classGuard.isCurrent(seq)) return
    classes.value = res.items
    classesTotal.value = res.total
    if (!res.items.length && classPage.value > 1) {
      classPage.value -= 1
      await loadClasses()
    }
  } finally {
    if (classGuard.isCurrent(seq)) loading.value = false
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
  const [co, cr, te, rm, tm] = await Promise.allSettled([
    collegeApi.list({ page_size: 200 }),
    courseApi.list({ page_size: 200 }),
    teacherApi.list({ page_size: 200 }),
    classroomApi.list({ page_size: 200 }),
    termApi.list({ page_size: 200 }),
  ])
  if (co.status === 'fulfilled') colleges.value = co.value.items
  if (cr.status === 'fulfilled') courses.value = cr.value.items
  if (te.status === 'fulfilled') teachers.value = te.value.items
  if (rm.status === 'fulfilled') classrooms.value = rm.value.items
  if (tm.status === 'fulfilled') terms.value = tm.value.items
  await loadTasks()
  await loadClasses()
})
</script>

<template>
  <el-card shadow="never" class="page-card" v-loading="loading">
    <!-- 工具栏：学期筛选 + 当前 Tab 的新增入口 -->
    <div class="toolbar">
      <el-select v-model="semester" class="sem-select" style="width: 180px">
        <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
      </el-select>
      <div class="spacer" />
      <el-button v-if="tab === 'task'" type="danger" plain
        :disabled="!taskSelection.length" :loading="batchBusy" @click="batchDeleteTasks">
        批量删除
      </el-button>
      <el-button v-else type="danger" plain
        :disabled="!classSelection.length" :loading="batchBusy" @click="batchDeleteClasses">
        批量删除
      </el-button>
      <el-button v-if="tab === 'task'" type="primary" :icon="'Plus'" @click="openTask">
        新增教学任务
      </el-button>
      <el-button v-else type="primary" :icon="'Plus'" @click="openClassCreate">
        新增教学班
      </el-button>
    </div>

    <el-tabs v-model="tab">
      <el-tab-pane label="教学班" name="class">
        <!-- 桌面端：表格 -->
        <div class="table-wrap">
          <el-table :data="classes" stripe @selection-change="onClassSelection">
            <el-table-column type="selection" width="45" />
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
            <el-table-column label="操作" width="320" align="center" fixed="right">
              <template #default="{ row }">
                <el-button size="small" link type="primary" @click="openSchedule(row)">
                  排课
                </el-button>
                <el-button size="small" link type="primary" @click="openEnrollment(row)">
                  安排学生
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
            <template #empty>
              <el-empty description="暂无教学班" :image-size="70" />
            </template>
          </el-table>
        </div>

        <!-- 窄屏：卡片列表 -->
        <div class="row-cards">
          <el-empty v-if="!classes.length" description="暂无教学班" :image-size="70" />
          <article v-for="row in classes" :key="row.id" class="rcard">
            <header class="rcard__head">
              <div class="rcard__title">
                <span class="rcard__name">{{ row.course_name || '未命名课程' }}</span>
                <span class="rcard__code">{{ row.code }}</span>
              </div>
              <el-tag :type="SEL_TYPE[row.selection_status] as any" size="small">
                {{ SEL_STATUS[row.selection_status] }}
              </el-tag>
            </header>

            <div class="rcard__meta">
              <div class="rmeta">
                <span class="rmeta__label">授课教师</span>
                <span class="rmeta__value">
                  <span v-if="row.teacher_name">{{ row.teacher_name }}</span>
                  <el-tag v-else type="warning" size="small">未分配</el-tag>
                </span>
              </div>
              <div class="rmeta">
                <span class="rmeta__label">学分</span>
                <span class="rmeta__value">{{ row.credits }}</span>
              </div>
              <div class="rmeta">
                <span class="rmeta__label">选课人数</span>
                <span class="rmeta__value">
                  <el-tag :type="row.remaining > 0 ? '' : 'danger'" size="small">
                    {{ row.selected_count }}/{{ row.capacity }}
                  </el-tag>
                </span>
              </div>
            </div>

            <div class="rcard__sched">
              <el-icon class="rcard__sched-icon"><component :is="'Clock'" /></el-icon>
              <span class="rcard__sched-text">{{ scheduleText(row) }}</span>
            </div>

            <div class="rcard__actions">
              <el-button size="small" link type="primary" @click="openSchedule(row)">
                排课
              </el-button>
              <el-button size="small" link type="primary" @click="openEnrollment(row)">
                安排学生
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
            </div>
          </article>
        </div>

        <div class="pager">
          <el-pagination v-model:current-page="classPage" :total="classesTotal"
            :page-size="20" layout="total, prev, pager, next" @current-change="loadClasses" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="教学任务" name="task">
        <!-- 桌面端：表格 -->
        <div class="table-wrap">
          <el-table :data="tasks" stripe @selection-change="onTaskSelection">
            <el-table-column type="selection" width="45" />
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
            <el-table-column label="操作" width="140" align="center">
              <template #default="{ row }">
                <el-button size="small" link type="primary" @click="openTaskEdit(row)">编辑</el-button>
                <el-button size="small" link type="danger" @click="removeTask(row)">删除</el-button>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty description="暂无教学任务" :image-size="70" />
            </template>
          </el-table>
        </div>

        <!-- 窄屏：卡片列表 -->
        <div class="row-cards">
          <el-empty v-if="!tasks.length" description="暂无教学任务" :image-size="70" />
          <article v-for="row in tasks" :key="row.id" class="rcard">
            <header class="rcard__head">
              <div class="rcard__title">
                <span class="rcard__name">{{ row.course_name || '未命名课程' }}</span>
                <span class="rcard__code">{{ row.course_code }}</span>
              </div>
              <el-tag size="small">{{ TASK_STATUS[row.status] }}</el-tag>
            </header>

            <div class="rcard__meta">
              <div class="rmeta">
                <span class="rmeta__label">学期</span>
                <span class="rmeta__value">{{ row.semester }}</span>
              </div>
              <div class="rmeta">
                <span class="rmeta__label">承担学院</span>
                <span class="rmeta__value">{{ row.college_name }}</span>
              </div>
              <div class="rmeta">
                <span class="rmeta__label">计划 / 实际开班</span>
                <span class="rmeta__value">{{ row.class_count }} / {{ row.planned_classes }}</span>
              </div>
            </div>

            <div class="rcard__actions">
              <el-button size="small" link type="primary" @click="openTaskEdit(row)">编辑</el-button>
              <el-button size="small" link type="danger" @click="removeTask(row)">删除</el-button>
            </div>
          </article>
        </div>

        <div class="pager">
          <el-pagination v-model:current-page="taskPage" :total="tasksTotal"
            :page-size="20" layout="total, prev, pager, next" @current-change="loadTasks" />
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 教学任务表单 -->
    <el-dialog v-model="taskDialog" :title="taskEditingId ? '编辑教学任务' : '新增教学任务'" width="480px">
      <el-form label-width="100px">
        <el-form-item v-if="!taskEditingId" label="学期" required>
          <el-select v-model="taskForm.semester" style="width: 100%">
            <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="!taskEditingId" label="课程" required>
          <el-select v-model="taskForm.course_id" filterable style="width: 100%">
            <el-option v-for="c in courses" :key="c.id"
              :label="`${c.code} ${c.name}`" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="!taskEditingId" label="承担学院" required>
          <el-select v-model="taskForm.college_id" style="width: 100%">
            <el-option v-for="c in colleges" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="计划开班数">
          <el-input-number v-model="taskForm.planned_classes" :min="1" :max="50" />
        </el-form-item>
        <el-form-item label="任务状态">
          <el-select v-model="taskForm.status" style="width: 100%">
            <el-option label="草稿" value="DRAFT" />
            <el-option label="已确认" value="CONFIRMED" />
            <el-option label="已取消" value="CANCELLED" />
          </el-select>
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
          <el-form-item label="所属学期">
            <span class="term-hint">
              {{ createTerm ? createTerm.name : `${semester}（学期管理中不存在）` }}
            </span>
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
      <!-- 三类冲突提示：教室 / 教师 / 教学班 -->
      <el-alert class="sched-alert" type="info" :closable="false" show-icon
        title="系统自动检测教室冲突、教师冲突与教学班冲突；单周/双周课程在同一时段可共用教室" />

      <!-- 排课表单：按「教室 / 时间 / 周次」分组 -->
      <div class="sched-form">
        <div class="sgroup">
          <span class="sgroup__label">
            <el-icon><component :is="'Location'" /></el-icon>
            <span>教室</span>
          </span>
          <div class="sgroup__body">
            <el-select v-model="schedForm.classroom_id" placeholder="选择教室" filterable
              style="width: 150px">
              <el-option v-for="r in classrooms" :key="r.id"
                :label="`${r.code}(${r.capacity}人)`" :value="r.id" />
            </el-select>
          </div>
        </div>

        <div class="sgroup">
          <span class="sgroup__label">
            <el-icon><component :is="'Clock'" /></el-icon>
            <span>时间</span>
          </span>
          <div class="sgroup__body">
            <el-select v-model="schedForm.day_of_week" style="width: 100px">
              <el-option v-for="d in 7" :key="d" :label="DAY[d]" :value="d" />
            </el-select>
            <el-input-number v-model="schedForm.start_period" :min="1" :max="14"
              controls-position="right" style="width: 100px" />
            <span class="dash">-</span>
            <el-input-number v-model="schedForm.end_period" :min="1" :max="14"
              controls-position="right" style="width: 100px" />
            <span class="unit">节</span>
          </div>
        </div>

        <div class="sgroup">
          <span class="sgroup__label">
            <el-icon><component :is="'Calendar'" /></el-icon>
            <span>周次</span>
          </span>
          <div class="sgroup__body">
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
          </div>
        </div>
      </div>

      <div class="sched-submit">
        <el-button type="danger" plain :disabled="!scheduleSelection.length"
          :loading="batchBusy" @click="batchDeleteSchedules">批量删除</el-button>
        <el-button type="primary" :loading="schedSaving" @click="saveSchedule">
          {{ schedEditingId != null ? '保存修改' : '添加' }}
        </el-button>
        <el-button v-if="schedEditingId != null" @click="cancelEditSchedule">取消修改</el-button>
      </div>

      <!-- 已排课列表：桌面表格，每行突出 星期 + 节次 + 教室 -->
      <div class="table-wrap sched-table-wrap">
        <el-table :data="schedList" @selection-change="onScheduleSelection" size="small" stripe>
          <el-table-column type="selection" width="42" />
          <el-table-column label="星期" width="80" align="center">
            <template #default="{ row }">
              <span class="when-day">{{ DAY[row.day_of_week] }}</span>
            </template>
          </el-table-column>
          <el-table-column label="节次" width="100" align="center">
            <template #default="{ row }">
              <span class="period">{{ row.start_period }}-{{ row.end_period }} 节</span>
            </template>
          </el-table-column>
          <el-table-column label="周次" width="120" align="center">
            <template #default="{ row }">
              {{ row.start_week }}-{{ row.end_week }} 周
              <span v-if="row.week_type !== 'ALL'">
                ({{ row.week_type === 'ODD' ? '单' : '双' }})
              </span>
            </template>
          </el-table-column>
          <el-table-column label="教室" width="130" align="center">
            <template #default="{ row }">
              <span class="room-chip">{{ row.classroom_code }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="building" label="楼栋" min-width="110" />
          <el-table-column label="操作" width="130" align="center">
            <template #default="{ row }">
              <el-button size="small" link type="primary" @click="editSchedule(row)">编辑</el-button>
              <el-button size="small" link type="danger" @click="removeSchedule(row)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty><el-empty description="尚未排课" :image-size="60" /></template>
        </el-table>
      </div>

      <!-- 已排课列表：窄屏卡片 -->
      <div class="sched-cards">
        <el-empty v-if="!schedList.length" description="尚未排课" :image-size="60" />
        <article v-for="row in schedList" :key="row.id" class="scard">
          <div class="scard__main">
            <span class="when-day">{{ DAY[row.day_of_week] }}</span>
            <span class="period">{{ row.start_period }}-{{ row.end_period }} 节</span>
            <span class="room-chip">{{ row.classroom_code }}</span>
          </div>
          <div class="scard__meta">
            <span>
              {{ row.start_week }}-{{ row.end_week }} 周
              <span v-if="row.week_type !== 'ALL'">
                ({{ row.week_type === 'ODD' ? '单' : '双' }})
              </span>
            </span>
            <span v-if="row.building">{{ row.building }}</span>
          </div>
          <div class="scard__actions">
            <el-button size="small" link type="primary" @click="editSchedule(row)">编辑</el-button>
            <el-button size="small" link type="danger" @click="removeSchedule(row)">删除</el-button>
          </div>
        </article>
      </div>
    </el-dialog>

    <!-- FIX-002：批量安排 + 教学班名单管理 -->
    <ClassEnrollmentDialog
      v-model="enrollVisible"
      :teaching-class="enrollClass"
      @changed="onEnrollmentChanged"
    />
  </el-card>
</template>

<style scoped lang="scss">
.term-hint {
  color: var(--uams-text-2);
  font-size: 13px;
}

/* 桌面表格 / 窄屏卡片的显示切换由下方断点统一控制 */
.table-wrap {
  width: 100%;
}

/* ------------------------------------------------ 教学班/教学任务 卡片形态 */
.row-cards {
  display: none;
  flex-direction: column;
  gap: 12px;
}

.rcard {
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

  &__meta {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px 12px;
    padding: 12px 14px 0;
  }

  /* 上课安排：用极浅紫底把时间地点拎出来 */
  &__sched {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    margin: 12px 14px 0;
    padding: 10px 12px;
    border-radius: var(--uams-radius-sm);
    background: var(--uams-primary-softer);
    border: 1px solid var(--uams-primary-soft);
  }

  &__sched-icon {
    margin-top: 3px;
    color: var(--uams-primary-dark);
  }

  &__sched-text {
    font-size: 13px;
    color: var(--uams-text-2);
    word-break: break-word;
  }

  &__actions {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 12px;
    padding: 12px 14px;
    border-top: 1px dashed var(--uams-border);
  }

  &__actions .el-button {
    margin-left: 0;
  }
}

.rmeta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;

  &__label {
    font-size: 12px;
    color: var(--uams-text-3);
  }

  &__value {
    font-size: 13px;
    color: var(--uams-text);
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

/* 上课安排文字（桌面表格内） */
.sched {
  font-size: 12px;
  color: var(--uams-text-2);
}

/* --------------------------------------------------------- 排课弹窗 */
.sched-alert {
  margin-bottom: 14px;
}

/* 表单按 教室 / 时间 / 周次 三组纵向排列 */
.sched-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sgroup {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface-sunken);

  &__label {
    flex: 0 0 60px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 600;
    color: var(--uams-text-2);
  }

  &__body {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
  }
}

.dash,
.unit {
  color: var(--uams-text-3);
  font-size: 13px;
}

.sched-submit {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}

/* 排课列表中的强调元素：星期 / 节次 / 教室 */
.when-day {
  display: inline-block;
  min-width: 42px;
  padding: 2px 8px;
  border-radius: var(--uams-radius-xs);
  background: var(--uams-primary-soft);
  color: var(--uams-primary-dark);
  font-weight: 600;
  text-align: center;
}

.period {
  font-weight: 600;
  color: var(--uams-text);
  font-variant-numeric: tabular-nums;
}

.room-chip {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--uams-radius-xs);
  background: var(--uams-surface-sunken);
  border: 1px solid var(--uams-border);
  color: var(--uams-text-2);
  font-variant-numeric: tabular-nums;
}

.sched-table-wrap {
  margin-top: 14px;
}

/* 排课列表：窄屏卡片 */
.sched-cards {
  display: none;
  flex-direction: column;
  gap: 10px;
  margin-top: 14px;
}

.scard {
  padding: 12px 14px;
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface);

  &__main {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }

  &__meta {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 14px;
    margin-top: 8px;
    font-size: 12px;
    color: var(--uams-text-3);
  }

  &__actions {
    display: flex;
    gap: 6px;
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px dashed var(--uams-border);
  }

  &__actions .el-button {
    margin-left: 0;
  }
}

/* ------------------------------------------------------------- 响应式 */
@media (max-width: 768px) {
  /* 表格换卡片，避免窄屏横向溢出 */
  .table-wrap {
    display: none;
  }

  .row-cards,
  .sched-cards {
    display: flex;
  }

  /* 排课表单：分组标签移到控件上方，控件换行排满 */
  .sgroup {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }

  .sgroup__label {
    flex: none;
  }

  .sched-submit {
    gap: 8px;
  }

  .sched-submit .el-button {
    flex: 1 1 auto;
    margin-left: 0;
  }

  .rcard__meta {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 420px) {
  .rcard__meta {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
