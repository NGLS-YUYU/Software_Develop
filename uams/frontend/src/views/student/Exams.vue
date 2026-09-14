<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { examApi } from '@/api'
import { currentSemester, semesterOptions } from '@/composables/useSemester'
import type { Exam } from '@/types'

const semester = ref(currentSemester())
const exams = ref<Exam[]>([])
const loading = ref(false)

const TYPE: Record<string, string> = { FINAL: '期末考试', MAKEUP: '补考', RETAKE: '重修' }

function daysLeft(d: string) {
  const diff = Math.ceil(
    (new Date(d).getTime() - new Date(new Date().toDateString()).getTime()) / 86400000,
  )
  return diff
}

async function load() {
  loading.value = true
  try {
    exams.value = await examApi.mine(semester.value)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <el-card shadow="never" v-loading="loading">
    <div class="toolbar">
      <el-select v-model="semester" style="width: 180px" @change="load">
        <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
      </el-select>
      <div class="spacer" />
      <el-text size="small" type="info">仅显示已发布的考试安排</el-text>
    </div>

    <el-empty v-if="!exams.length" description="暂无考试安排" />
    <el-table v-else :data="exams" stripe>
      <el-table-column prop="course_name" label="课程" min-width="160" />
      <el-table-column label="类型" width="100">
        <template #default="{ row }">
          <el-tag size="small">{{ TYPE[row.exam_type] ?? row.exam_type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="exam_date" label="考试日期" width="120" />
      <el-table-column label="时间" width="130">
        <template #default="{ row }">
          {{ row.start_time?.slice(0, 5) }} - {{ row.end_time?.slice(0, 5) }}
        </template>
      </el-table-column>
      <el-table-column label="时长" width="90" align="center">
        <template #default="{ row }">{{ row.duration_minutes }} 分钟</template>
      </el-table-column>
      <el-table-column label="考场" width="100">
        <template #default="{ row }">{{ row.classroom_code ?? '待定' }}</template>
      </el-table-column>
      <el-table-column label="座位号" width="90" align="center">
        <template #default="{ row }">{{ row.seat_no ?? '-' }}</template>
      </el-table-column>
      <el-table-column label="倒计时" width="110" align="center">
        <template #default="{ row }">
          <el-tag
            v-if="daysLeft(row.exam_date) >= 0"
            :type="daysLeft(row.exam_date) <= 7 ? 'danger' : 'info'"
            size="small"
          >
            {{ daysLeft(row.exam_date) === 0 ? '今天' : `${daysLeft(row.exam_date)} 天后` }}
          </el-tag>
          <span v-else class="past">已结束</span>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<style scoped>
.past {
  color: #c0c4cc;
  font-size: 12px;
}
</style>
