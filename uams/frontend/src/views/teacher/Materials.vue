<script setup lang="ts">
/** 教师教学资料上传/下载（F-21）。 */
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadFile } from 'element-plus'

import { materialApi, teacherApi, teachingApi } from '@/api'
import { currentSemester } from '@/composables/useSemester'
import type { Material, TeachingClass } from '@/types'

const classes = ref<TeachingClass[]>([])
const classId = ref<number | undefined>(undefined)
const rows = ref<Material[]>([])
const title = ref('')
const selectedFile = ref<File | null>(null)
const loading = ref(false)
const uploading = ref(false)

function fileSize(size: number) {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${size} B`
}

function onFileChange(file: UploadFile) {
  selectedFile.value = file.raw ?? null
  if (!title.value && file.name) title.value = file.name.replace(/\.[^.]+$/, '')
}

async function loadRows() {
  if (!classId.value) {
    rows.value = []
    return
  }
  loading.value = true
  try {
    rows.value = await materialApi.list(classId.value)
  } finally {
    loading.value = false
  }
}

async function upload() {
  if (!classId.value || !selectedFile.value) {
    ElMessage.warning('请选择教学班和文件')
    return
  }
  uploading.value = true
  try {
    await materialApi.upload(classId.value, title.value.trim(), selectedFile.value)
    ElMessage.success('资料已上传')
    title.value = ''
    selectedFile.value = null
    await loadRows()
  } finally {
    uploading.value = false
  }
}

async function remove(row: Material) {
  try {
    await ElMessageBox.confirm(`确认删除资料「${row.title}」？`, '删除资料', { type: 'warning' })
  } catch {
    return
  }
  await materialApi.remove(row.id)
  ElMessage.success('已删除')
  await loadRows()
}

async function download(row: Material) {
  await materialApi.download(row.id, row.file_name)
}

onMounted(async () => {
  const me = await teacherApi.me()
  const res = await teachingApi.classes({
    teacher_id: me.id,
    semester: currentSemester(),
    page_size: 100,
  })
  classes.value = res.items
  classId.value = classes.value[0]?.id
  await loadRows()
})
</script>

<template>
  <div class="materials">
    <el-card shadow="never" class="page-card">
      <div class="toolbar">
        <el-select v-model="classId" placeholder="选择教学班" filterable style="width: 260px"
          @change="loadRows">
          <el-option v-for="c in classes" :key="c.id"
            :label="`${c.course_name || '—'}（${c.code}）`" :value="c.id" />
        </el-select>
        <span class="muted">仅本人授课教学班</span>
      </div>

      <div class="upload-row">
        <el-input v-model="title" placeholder="资料标题" maxlength="200" style="width: 240px" />
        <el-upload :auto-upload="false" :limit="1" :on-change="onFileChange" :show-file-list="false">
          <el-button>选择文件</el-button>
        </el-upload>
        <span class="muted">{{ selectedFile?.name || '未选择文件（≤10MB）' }}</span>
        <el-button type="primary" :loading="uploading" :disabled="!selectedFile" @click="upload">
          上传资料
        </el-button>
      </div>

      <el-table v-loading="loading" :data="rows" stripe>
        <el-table-column prop="title" label="标题" min-width="180" />
        <el-table-column prop="file_name" label="文件" min-width="200" />
        <el-table-column label="大小" width="100" align="center">
          <template #default="{ row }">{{ fileSize(row.file_size) }}</template>
        </el-table-column>
        <el-table-column prop="uploader_name" label="上传人" width="110" />
        <el-table-column prop="created_at" label="上传时间" width="160" />
        <el-table-column label="操作" width="140" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="download(row)">下载</el-button>
            <el-button link type="danger" size="small" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="该教学班暂无资料" :image-size="70" /></template>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.materials { display: block; }
.upload-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 14px;
}
</style>
