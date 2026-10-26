<script setup lang="ts">
/** 通用操作日志查询（F-15）。 */
import { onMounted, reactive, ref } from 'vue'

import { adminApi } from '@/api'
import type { AuditLog } from '@/types'

const rows = ref<AuditLog[]>([])
const total = ref(0)
const loading = ref(false)
const query = reactive({
  page: 1,
  page_size: 20,
  action: '',
  user_id: undefined as number | undefined,
  resource_type: '',
  resource_id: undefined as number | undefined,
})

async function load() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      page: query.page,
      page_size: query.page_size,
    }
    if (query.action) params.action = query.action
    if (query.user_id) params.user_id = query.user_id
    if (query.resource_type) params.resource_type = query.resource_type
    if (query.resource_id) params.resource_id = query.resource_id
    const res = await adminApi.auditLogs(params)
    rows.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

function search() {
  query.page = 1
  load()
}

function reset() {
  query.action = ''
  query.user_id = undefined
  query.resource_type = ''
  query.resource_id = undefined
  search()
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="audit-logs">
    <el-card shadow="never" class="page-card">
      <div class="toolbar">
        <el-input v-model="query.action" placeholder="动作，如 ADMIN_GRANT" clearable
          style="width: 190px" @keyup.enter="search" />
        <el-input v-model="query.resource_type" placeholder="资源类型，如 user/grade" clearable
          style="width: 190px" @keyup.enter="search" />
        <el-input-number v-model="query.user_id" :min="1" placeholder="操作人ID"
          style="width: 140px" />
        <el-input-number v-model="query.resource_id" :min="1" placeholder="资源ID"
          style="width: 140px" />
        <el-button type="primary" @click="search">查询</el-button>
        <el-button @click="reset">重置</el-button>
        <div class="spacer" />
        <span class="muted">共 {{ total }} 条</span>
      </div>

      <el-table :data="rows" stripe size="small">
        <el-table-column prop="created_at" label="时间" width="160">
          <template #default="{ row }">
            {{ row.created_at?.slice(0, 19).replace('T', ' ') }}
          </template>
        </el-table-column>
        <el-table-column prop="username" label="操作人" width="120" />
        <el-table-column prop="action" label="动作" width="150" />
        <el-table-column prop="module" label="模块" width="110" />
        <el-table-column label="资源" width="150">
          <template #default="{ row }">
            {{ row.resource_type || '—' }}{{ row.resource_id ? `#${row.resource_id}` : '' }}
          </template>
        </el-table-column>
        <el-table-column prop="result" label="结果" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.result === 'SUCCESS' ? 'success' : 'danger'" size="small">
              {{ row.result }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="detail" label="详情" min-width="280" show-overflow-tooltip />
        <el-table-column prop="ip_address" label="IP" width="130" />
        <template #empty>
          <el-empty description="暂无操作日志" :image-size="70" />
        </template>
      </el-table>

      <div class="pager">
        <el-pagination v-model:current-page="query.page" :total="total" :page-size="query.page_size"
          layout="total, prev, pager, next" @current-change="load" />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.audit-logs {
  display: block;
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
