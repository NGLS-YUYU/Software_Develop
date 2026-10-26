<script setup lang="ts">
/** 教学评价任务管理（F-10）。管理员创建/修改评价任务，学生在开放期内评价。 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { evaluationApi } from '@/api'
import type { EvaluationTask } from '@/types'

const rows = ref<EvaluationTask[]>([])
const loading = ref(false)
const dialog = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = ref<Record<string, unknown>>({})

const STATUS: Record<string, string> = { PENDING: '未开始', ACTIVE: '进行中', CLOSED: '已结束' }
const STATUS_TYPE: Record<string, string> = { PENDING: 'info', ACTIVE: 'success', CLOSED: 'warning' }

function openCreate() {
  editingId.value = null
  form.value = {
    name: '',
    semester: '',
    start_time: '',
    end_time: '',
    status: 'PENDING',
  }
  dialog.value = true
}

function openEdit(row: EvaluationTask) {
  editingId.value = row.id
  form.value = { ...row }
  dialog.value = true
}

async function load() {
  loading.value = true
  try {
    rows.value = await evaluationApi.tasks()
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!form.value.name || !form.value.semester || !form.value.start_time || !form.value.end_time) {
    ElMessage.warning('请填写名称、学期和起止时间')
    return
  }
  if (new Date(String(form.value.end_time)) <= new Date(String(form.value.start_time))) {
    ElMessage.warning('结束时间必须晚于开始时间')
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await evaluationApi.updateTask(editingId.value, form.value)
      ElMessage.success('评价任务已更新')
    } else {
      await evaluationApi.createTask(form.value)
      ElMessage.success('评价任务已创建')
    }
    dialog.value = false
    await load()
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="admin-evaluations">
    <el-card shadow="never" class="page-card">
      <div class="toolbar">
        <span class="muted">评价任务决定学生端可评价的课程；仅“进行中”且在时间范围内的任务可提交。</span>
        <div class="spacer" />
        <el-button type="primary" :icon="'Plus'" @click="openCreate">新增评价任务</el-button>
        <el-button @click="load">刷新</el-button>
      </div>

      <el-table :data="rows" stripe>
        <el-table-column prop="name" label="名称" min-width="180" />
        <el-table-column prop="semester" label="学期" width="130" />
        <el-table-column label="起止时间" min-width="300">
          <template #default="{ row }">
            {{ row.start_time?.slice(0, 16).replace('T', ' ') }}
            ~
            {{ row.end_time?.slice(0, 16).replace('T', ' ') }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="STATUS_TYPE[row.status] as any" size="small">
              {{ STATUS[row.status] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无评价任务" :image-size="70" />
        </template>
      </el-table>
    </el-card>

    <el-dialog v-model="dialog" :title="editingId ? '编辑评价任务' : '新增评价任务'" width="520px">
      <el-form label-width="100px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name as string" maxlength="100" />
        </el-form-item>
        <el-form-item label="学期" required>
          <el-input v-model="form.semester as string" placeholder="如 2026-2027-1" maxlength="16" />
        </el-form-item>
        <el-form-item label="开始时间" required>
          <el-date-picker v-model="form.start_time" type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
        </el-form-item>
        <el-form-item label="结束时间" required>
          <el-date-picker v-model="form.end_time" type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
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
  </div>
</template>

<style scoped>
.admin-evaluations {
  display: block;
}
</style>
