<script setup lang="ts">
/** 教务审核调停课申请（F-22）。 */
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { adjustmentApi } from '@/api'
import type { Adjustment } from '@/types'

const rows = ref<Adjustment[]>([])
const loading = ref(false)
const statusFilter = ref<string>('PENDING')

const TYPE: Record<string, string> = { CHANGE: '调课', CANCEL: '停课', ADD: '补课' }
const STATUS: Record<string, string> = { PENDING: '待审核', APPROVED: '已批准', REJECTED: '已驳回' }
const STATUS_TYPE: Record<string, string> = { PENDING: 'warning', APPROVED: 'success', REJECTED: 'danger' }

async function load() {
  loading.value = true
  try {
    rows.value = await adjustmentApi.list(statusFilter.value || undefined)
  } finally {
    loading.value = false
  }
}

async function approve(row: Adjustment) {
  try {
    await ElMessageBox.confirm('批准后将直接修改该教学班排课并影响课表，确认批准？', '批准调停课', { type: 'warning' })
  } catch { return }
  await adjustmentApi.approve(row.id)
  ElMessage.success('已批准并应用排课变更')
  await load()
}

async function reject(row: Adjustment) {
  let reason = ''
  try {
    const { value } = await ElMessageBox.prompt('请输入驳回原因', '驳回申请', {
      inputValidator: (v) => (v && v.trim() ? true : '原因不能为空'),
    })
    reason = value
  } catch { return }
  await adjustmentApi.reject(row.id, reason)
  ElMessage.success('已驳回')
  await load()
}

onMounted(load)
</script>

<template>
  <div class="adjustments">
    <el-card shadow="never" class="page-card">
      <div class="toolbar">
        <el-select v-model="statusFilter" style="width: 160px" @change="load">
          <el-option label="待审核" value="PENDING" />
          <el-option label="已批准" value="APPROVED" />
          <el-option label="已驳回" value="REJECTED" />
          <el-option label="全部" value="" />
        </el-select>
        <el-button @click="load">刷新</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" stripe>
        <el-table-column prop="course_name" label="课程" min-width="150" />
        <el-table-column prop="teaching_class_code" label="教学班" width="150" />
        <el-table-column label="类型" width="80" align="center">
          <template #default="{ row }">{{ TYPE[row.request_type] }}</template>
        </el-table-column>
        <el-table-column prop="requester_name" label="申请人" width="110" />
        <el-table-column prop="reason" label="原因" min-width="180" />
        <el-table-column label="新安排" min-width="180">
          <template #default="{ row }">
            <template v-if="row.request_type !== 'CANCEL'">
              周{{ row.new_day_of_week ?? '—' }} 第{{ row.new_start_period ?? '—' }}-{{ row.new_end_period ?? '—' }}节
              （{{ row.new_start_week ?? '—' }}-{{ row.new_end_week ?? '—' }}周）
            </template>
            <span v-else>停课</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="STATUS_TYPE[row.status] as any" size="small">{{ STATUS[row.status] }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="review_reason" label="审核意见" min-width="140" />
        <el-table-column v-if="statusFilter === 'PENDING'" label="操作" width="140" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="success" size="small" @click="approve(row)">批准</el-button>
            <el-button link type="danger" size="small" @click="reject(row)">驳回</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="暂无调停课申请" :image-size="70" /></template>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.adjustments { display: block; }
</style>
