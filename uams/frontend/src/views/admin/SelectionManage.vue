<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
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
const roster = ref<{ student_no: string; real_name: string; class_name?: string }[]>([])
const rosterTitle = ref('')

const STATUS: Record<string, string> = { PENDING: '未开始', ACTIVE: '进行中', CLOSED: '已结束' }
const STATUS_TYPE: Record<string, string> = { PENDING: 'info', ACTIVE: 'success', CLOSED: 'warning' }

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
  <div v-loading="loading">
    <el-card shadow="never" class="page-card">
      <template #header>
        <div class="head">
          <span>选课时间窗口</span>
          <el-button type="primary" size="small" :icon="'Plus'" @click="openCreate">
            新增窗口
          </el-button>
        </div>
      </template>
      <el-table :data="periods" size="small" stripe>
        <el-table-column prop="name" label="名称" min-width="180" />
        <el-table-column prop="semester" label="学期" width="130" />
        <el-table-column label="开始时间" width="170">
          <template #default="{ row }">{{ row.start_time?.slice(0, 16).replace('T', ' ') }}</template>
        </el-table-column>
        <el-table-column label="结束时间" width="170">
          <template #default="{ row }">{{ row.end_time?.slice(0, 16).replace('T', ' ') }}</template>
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
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="尚未设置选课时间窗口" :image-size="60" /></template>
      </el-table>
    </el-card>

    <el-card shadow="never" class="page-card">
      <div class="toolbar">
        <el-select v-model="semester" style="width: 180px">
          <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
        </el-select>
        <div class="spacer" />
        <el-text size="small" type="info">选课需同时满足：时间窗口开放 + 教学班开放</el-text>
      </div>
      <el-table :data="classes" stripe>
        <el-table-column prop="code" label="教学班号" min-width="170" />
        <el-table-column prop="course_name" label="课程" min-width="150" />
        <el-table-column prop="teacher_name" label="教师" width="100" />
        <el-table-column label="已选/容量" width="130" align="center">
          <template #default="{ row }">
            <el-progress :percentage="Math.round((row.selected_count / row.capacity) * 100)"
              :stroke-width="12" :text-inside="true" style="width: 100px" />
          </template>
        </el-table-column>
        <el-table-column label="人数" width="90" align="center">
          <template #default="{ row }">{{ row.selected_count }}/{{ row.capacity }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.selection_status === 'OPEN' ? 'success' : 'info'" size="small">
              {{ row.selection_status === 'OPEN' ? '选课中' : '未开放' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="170" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="showRoster(row)">名单</el-button>
            <el-button size="small" link type="primary" @click="toggle(row)">
              {{ row.selection_status === 'OPEN' ? '关闭' : '开放' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager">
        <el-pagination v-model:current-page="page" :total="total" :page-size="20"
          layout="total, prev, pager, next" @current-change="loadClasses" />
      </div>
    </el-card>

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

    <el-dialog v-model="rosterVisible" :title="rosterTitle" width="560px">
      <el-table :data="roster" max-height="420" size="small" stripe>
        <el-table-column type="index" label="#" width="55" align="center" />
        <el-table-column prop="student_no" label="学号" width="140" />
        <el-table-column prop="real_name" label="姓名" width="110" />
        <el-table-column prop="class_name" label="班级" min-width="150" />
      </el-table>
    </el-dialog>
  </div>
</template>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: center; }
</style>
