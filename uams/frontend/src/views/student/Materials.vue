<script setup lang="ts">
/** 学生查看/下载本人已选课程的教学资料（F-21）。 */
import { onMounted, ref } from 'vue'

import { materialApi } from '@/api'
import type { Material } from '@/types'

const rows = ref<Material[]>([])
const loading = ref(false)

function fileSize(size: number) {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${size} B`
}

async function load() {
  loading.value = true
  try {
    rows.value = await materialApi.my()
  } finally {
    loading.value = false
  }
}

async function download(row: Material) {
  await materialApi.download(row.id, row.file_name)
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="materials">
    <el-card shadow="never" class="page-card">
      <div class="toolbar">
        <span class="muted">仅显示本人已选课程的资料</span>
        <div class="spacer" />
        <el-button @click="load">刷新</el-button>
      </div>
      <el-table :data="rows" stripe>
        <el-table-column prop="teaching_class_code" label="教学班" width="150" />
        <el-table-column prop="title" label="标题" min-width="180" />
        <el-table-column prop="file_name" label="文件" min-width="200" />
        <el-table-column label="大小" width="100" align="center">
          <template #default="{ row }">{{ fileSize(row.file_size) }}</template>
        </el-table-column>
        <el-table-column prop="uploader_name" label="上传人" width="110" />
        <el-table-column prop="created_at" label="上传时间" width="160" />
        <el-table-column label="操作" width="90" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="download(row)">下载</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="暂无可下载资料" :image-size="70" /></template>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.materials { display: block; }
</style>
