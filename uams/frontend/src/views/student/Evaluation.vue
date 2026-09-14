<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { evaluationApi } from '@/api'
import { currentSemester } from '@/composables/useSemester'
import type { EvaluationTask, PendingEvaluation } from '@/types'

const tasks = ref<EvaluationTask[]>([])
const taskId = ref<number | undefined>(undefined)
const pending = ref<PendingEvaluation[]>([])
const loading = ref(false)

const dialog = ref(false)
const current = ref<PendingEvaluation | null>(null)
const form = ref({ score: 90, comment: '' })
const submitting = ref(false)

function isOpen(t: EvaluationTask) {
  const now = Date.now()
  return (
    t.status === 'ACTIVE' &&
    new Date(t.start_time).getTime() <= now &&
    now <= new Date(t.end_time).getTime()
  )
}

async function loadTasks() {
  tasks.value = await evaluationApi.tasks(currentSemester())
  const open = tasks.value.find(isOpen)
  taskId.value = open?.id ?? tasks.value[0]?.id
}

async function loadPending() {
  if (!taskId.value) return
  loading.value = true
  try {
    pending.value = await evaluationApi.pending(taskId.value)
  } finally {
    loading.value = false
  }
}

function open(row: PendingEvaluation) {
  current.value = row
  form.value = { score: 90, comment: '' }
  dialog.value = true
}

async function submit() {
  if (!current.value || !taskId.value) return
  submitting.value = true
  try {
    await evaluationApi.submit({
      task_id: taskId.value,
      teaching_class_id: current.value.teaching_class_id,
      score: form.value.score,
      comment: form.value.comment || undefined,
    })
    ElMessage.success('评价已提交')
    dialog.value = false
    await loadPending()
  } finally {
    submitting.value = false
  }
}

watch(taskId, loadPending)
onMounted(async () => {
  await loadTasks()
  await loadPending()
})
</script>

<template>
  <el-card shadow="never" v-loading="loading">
    <div class="toolbar">
      <el-select v-model="taskId" placeholder="选择评价任务" style="width: 280px">
        <el-option v-for="t in tasks" :key="t.id" :label="t.name" :value="t.id">
          <span>{{ t.name }}</span>
          <el-tag v-if="isOpen(t)" type="success" size="small" style="margin-left: 8px">
            进行中
          </el-tag>
        </el-option>
      </el-select>
      <div class="spacer" />
      <el-text size="small" type="info">评价内容匿名提交，教师无法看到评价人</el-text>
    </div>

    <el-empty v-if="!pending.length" description="暂无待评价课程" />
    <el-table v-else :data="pending" stripe>
      <el-table-column prop="course_name" label="课程" min-width="170" />
      <el-table-column prop="teacher_name" label="授课教师" width="120" />
      <el-table-column prop="teaching_class_code" label="教学班" min-width="150" />
      <el-table-column label="状态" width="110" align="center">
        <template #default="{ row }">
          <el-tag :type="row.evaluated ? 'success' : 'warning'" size="small">
            {{ row.evaluated ? '已评价' : '待评价' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" align="center">
        <template #default="{ row }">
          <el-button
            type="primary"
            size="small"
            :disabled="row.evaluated"
            @click="open(row)"
          >
            去评价
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" title="教学评价" width="480px">
      <el-form label-width="90px">
        <el-form-item label="课程">
          <span>{{ current?.course_name }}</span>
        </el-form-item>
        <el-form-item label="授课教师">
          <span>{{ current?.teacher_name }}</span>
        </el-form-item>
        <el-form-item label="评分">
          <el-slider v-model="form.score" :min="0" :max="100" show-input />
        </el-form-item>
        <el-form-item label="评语">
          <el-input
            v-model="form.comment"
            type="textarea"
            :rows="4"
            maxlength="1000"
            show-word-limit
            placeholder="选填，对教学的建议"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">提交</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>
