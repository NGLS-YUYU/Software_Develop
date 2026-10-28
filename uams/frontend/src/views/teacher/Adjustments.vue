<script setup lang="ts">
/** 教师调课/停课/补课申请（F-22）。 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { adjustmentApi, classroomApi, teacherApi, teachingApi } from '@/api'
import { currentSemester } from '@/composables/useSemester'
import type { Adjustment, Classroom, Schedule, TeachingClass } from '@/types'
import { createLatestGuard } from '@/utils/latest'

const classes = ref<TeachingClass[]>([])
const schedules = ref<Schedule[]>([])
const classrooms = ref<Classroom[]>([])
const rows = ref<Adjustment[]>([])
const loading = ref(false)
const listGuard = createLatestGuard()
const scheduleGuard = createLatestGuard()
const saving = ref(false)
const form = ref<Record<string, unknown>>({
  teaching_class_id: undefined,
  request_type: 'CHANGE',
  schedule_id: undefined,
  reason: '',
  new_day_of_week: undefined,
  new_start_period: undefined,
  new_end_period: undefined,
  new_start_week: undefined,
  new_end_week: undefined,
  new_week_type: 'ALL',
  new_classroom_id: undefined,
})

const TYPE: Record<string, string> = { CHANGE: '调课', CANCEL: '停课', ADD: '补课' }
const STATUS: Record<string, string> = { PENDING: '待审核', APPROVED: '已批准', REJECTED: '已驳回' }
const STATUS_TYPE: Record<string, string> = { PENDING: 'warning', APPROVED: 'success', REJECTED: 'danger' }

async function loadSchedules() {
  if (!form.value.teaching_class_id) {
    schedules.value = []
    return
  }
  const seq = scheduleGuard.next()
  const data = await teachingApi.schedules(Number(form.value.teaching_class_id))
  if (scheduleGuard.isCurrent(seq)) schedules.value = data
}

async function submit() {
  if (!form.value.teaching_class_id || !form.value.reason) {
    ElMessage.warning('请选择教学班并填写原因')
    return
  }
  if (form.value.request_type !== 'ADD' && !form.value.schedule_id) {
    ElMessage.warning('调课/停课必须选择原排课')
    return
  }
  saving.value = true
  try {
    await adjustmentApi.create(form.value)
    ElMessage.success('申请已提交，等待教务审核')
    form.value = {
      teaching_class_id: form.value.teaching_class_id,
      request_type: 'CHANGE',
      schedule_id: undefined,
      reason: '',
      new_day_of_week: undefined,
      new_start_period: undefined,
      new_end_period: undefined,
      new_start_week: undefined,
      new_end_week: undefined,
      new_week_type: 'ALL',
      new_classroom_id: undefined,
    }
    await load()
  } finally {
    saving.value = false
  }
}

async function load() {
  const seq = listGuard.next()
  loading.value = true
  try {
    const data = await adjustmentApi.mine()
    if (listGuard.isCurrent(seq)) rows.value = data
  } finally {
    if (listGuard.isCurrent(seq)) loading.value = false
  }
}

onMounted(async () => {
  const [me, rooms] = await Promise.all([teacherApi.me(), classroomApi.list({ page_size: 200 })])
  classrooms.value = rooms.items
  const res = await teachingApi.classes({
    teacher_id: me.id, semester: currentSemester(), page_size: 100,
  })
  classes.value = res.items
  form.value.teaching_class_id = classes.value[0]?.id
  await loadSchedules()
  await load()
})
</script>

<template>
  <div class="adjustments">
    <el-card shadow="never" class="page-card">
      <template #header><span class="section-title">提交调停课申请</span></template>
      <el-form label-width="100px" class="form">
        <el-form-item label="教学班" required>
          <el-select v-model="form.teaching_class_id" filterable style="width: 320px"
            @change="loadSchedules">
            <el-option v-for="c in classes" :key="c.id"
              :label="`${c.course_name || '—'}（${c.code}）`" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型" required>
          <el-select v-model="form.request_type" style="width: 180px">
            <el-option label="调课" value="CHANGE" />
            <el-option label="停课" value="CANCEL" />
            <el-option label="补课" value="ADD" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.request_type !== 'ADD'" label="原排课" required>
          <el-select v-model="form.schedule_id" style="width: 320px">
            <el-option v-for="s in schedules" :key="s.id"
              :label="`周${s.day_of_week} 第${s.start_period}-${s.end_period}节 ${s.classroom_code || ''}`"
              :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.request_type !== 'CANCEL'" label="新安排">
          <div class="new-row">
            <el-select v-model="form.new_day_of_week" placeholder="星期" style="width: 100px">
              <el-option v-for="d in 7" :key="d" :label="`周${d}`" :value="d" />
            </el-select>
            <el-input-number v-model="form.new_start_period" :min="1" :max="14" placeholder="开始节" />
            <el-input-number v-model="form.new_end_period" :min="1" :max="14" placeholder="结束节" />
            <el-input-number v-model="form.new_start_week" :min="1" :max="30" placeholder="开始周" />
            <el-input-number v-model="form.new_end_week" :min="1" :max="30" placeholder="结束周" />
            <el-select v-model="form.new_week_type" style="width: 100px">
              <el-option label="每周" value="ALL" />
              <el-option label="单周" value="ODD" />
              <el-option label="双周" value="EVEN" />
            </el-select>
            <el-select v-model="form.new_classroom_id" placeholder="教室" filterable style="width: 140px">
              <el-option v-for="r in classrooms" :key="r.id"
                :label="`${r.code}（${r.capacity}）`" :value="r.id" />
            </el-select>
          </div>
        </el-form-item>
        <el-form-item label="原因" required>
          <el-input v-model="form.reason as string" type="textarea" :rows="2" maxlength="500" show-word-limit />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="submit">提交申请</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="page-card">
      <template #header><span class="section-title">我的申请</span></template>
      <el-table v-loading="loading" :data="rows" stripe>
        <el-table-column prop="course_name" label="课程" min-width="150" />
        <el-table-column prop="teaching_class_code" label="教学班" width="150" />
        <el-table-column label="类型" width="80" align="center">
          <template #default="{ row }">{{ TYPE[row.request_type] }}</template>
        </el-table-column>
        <el-table-column prop="reason" label="原因" min-width="180" />
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="STATUS_TYPE[row.status] as any" size="small">
              {{ STATUS[row.status] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="review_reason" label="审核意见" min-width="160" />
        <el-table-column prop="created_at" label="提交时间" width="160" />
        <template #empty><el-empty description="暂无申请" :image-size="70" /></template>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.adjustments { display: block; }
.form { max-width: 900px; }
.new-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
</style>