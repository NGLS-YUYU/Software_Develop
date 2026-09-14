<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { gradeApi } from '@/api'
import { semesterOptions } from '@/composables/useSemester'
import type { Grade } from '@/types'

const semester = ref<string | undefined>(undefined)
const rows = ref<Grade[]>([])
const selected = ref<Grade[]>([])
const loading = ref(false)

/** 按教学班分组，教务通常整班审核。 */
const grouped = computed(() => {
  const map = new Map<number, Grade[]>()
  for (const g of rows.value) {
    const arr = map.get(g.teaching_class_id) ?? []
    arr.push(g)
    map.set(g.teaching_class_id, arr)
  }
  return [...map.values()]
})

async function load() {
  loading.value = true
  try {
    rows.value = await gradeApi.pending(semester.value)
    selected.value = []
  } finally {
    loading.value = false
  }
}

async function approve(ids: number[]) {
  if (!ids.length) {
    ElMessage.warning('请先选择要审核的成绩')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认通过 ${ids.length} 条成绩？通过后学生即可查询，教师不能再直接修改。`,
      '确认审核',
      { type: 'warning' },
    )
  } catch {
    return
  }
  const res = await gradeApi.approve(ids)
  ElMessage.success(res.message)
  await load()
}

async function reject(ids: number[]) {
  if (!ids.length) {
    ElMessage.warning('请先选择要驳回的成绩')
    return
  }
  let reason = ''
  try {
    const { value } = await ElMessageBox.prompt('请输入驳回原因', '驳回成绩', {
      inputPlaceholder: '如：平时成绩偏高，请复核',
      inputValidator: (v) => (v && v.trim() ? true : '驳回原因不能为空'),
    })
    reason = value
  } catch {
    return
  }
  const res = await gradeApi.reject(ids, reason)
  ElMessage.success(res.message)
  await load()
}

onMounted(load)
</script>

<template>
  <el-card shadow="never" v-loading="loading">
    <div class="toolbar">
      <el-select v-model="semester" clearable placeholder="全部学期" style="width: 180px"
        @change="load">
        <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
      </el-select>
      <el-button type="primary" @click="load">刷新</el-button>
      <div class="spacer" />
      <el-tag type="warning">待审核 {{ rows.length }} 条</el-tag>
      <el-button type="success" :disabled="!selected.length"
        @click="approve(selected.map(s => s.id))">
        批量通过 ({{ selected.length }})
      </el-button>
      <el-button type="danger" plain :disabled="!selected.length"
        @click="reject(selected.map(s => s.id))">
        批量驳回
      </el-button>
    </div>

    <el-empty v-if="!rows.length" description="没有待审核的成绩" />

    <template v-else>
      <el-card v-for="group in grouped" :key="group[0].teaching_class_id"
        shadow="never" class="group-card">
        <template #header>
          <div class="group-head">
            <span>
              {{ group[0].course_name }}
              <el-tag size="small" type="info" style="margin-left: 8px">
                {{ group.length }} 人
              </el-tag>
              <span class="sem">{{ group[0].semester }}</span>
            </span>
            <div>
              <el-button size="small" type="success"
                @click="approve(group.map(g => g.id))">整班通过</el-button>
              <el-button size="small" type="danger" plain
                @click="reject(group.map(g => g.id))">整班驳回</el-button>
            </div>
          </div>
        </template>
        <el-table :data="group" size="small" stripe
          @selection-change="(v: Grade[]) => selected = v">
          <el-table-column type="selection" width="45" />
          <el-table-column prop="student_no" label="学号" width="130" />
          <el-table-column prop="student_name" label="姓名" width="100" />
          <el-table-column label="平时" width="80" align="center">
            <template #default="{ row }">{{ row.regular_score ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="期末" width="80" align="center">
            <template #default="{ row }">{{ row.final_score ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="总评" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="Number(row.total_score) >= 60 ? '' : 'danger'" size="small">
                {{ row.total_score }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="grade_point" label="绩点" width="80" align="center" />
          <el-table-column prop="credits" label="学分" width="80" align="center" />
          <el-table-column label="提交时间" min-width="160">
            <template #default="{ row }">
              {{ row.submitted_at?.slice(0, 16).replace('T', ' ') }}
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>
  </el-card>
</template>

<style scoped>
.group-card { margin-bottom: 16px; }
.group-head { display: flex; justify-content: space-between; align-items: center; }
.sem { color: #909399; font-size: 12px; margin-left: 10px; }
</style>
