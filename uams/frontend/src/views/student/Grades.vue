<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { gradeApi } from '@/api'
import { semesterOptions } from '@/composables/useSemester'
import type { Grade, GradeSummary } from '@/types'

const semester = ref<string | undefined>(undefined)
const grades = ref<Grade[]>([])
const summary = ref<GradeSummary | null>(null)
const loading = ref(false)

/** 按学期分组展示，便于查看每学期表现。 */
const grouped = computed(() => {
  const map = new Map<string, Grade[]>()
  for (const g of grades.value) {
    const arr = map.get(g.semester) ?? []
    arr.push(g)
    map.set(g.semester, arr)
  }
  return [...map.entries()].sort((a, b) => b[0].localeCompare(a[0]))
})

function semesterCredits(rows: Grade[]) {
  return rows.filter((r) => r.is_passed).reduce((s, r) => s + Number(r.credits), 0)
}

function scoreType(g: Grade) {
  const s = Number(g.total_score ?? 0)
  if (s >= 90) return 'success'
  if (s >= 60) return ''
  return 'danger'
}

async function load() {
  loading.value = true
  try {
    grades.value = await gradeApi.mine(semester.value)
    summary.value = await gradeApi.mySummary()
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <el-card shadow="never" class="page-card">
      <div class="stat-grid">
        <el-statistic title="已修学分" :value="Number(summary?.total_credits ?? 0)" />
        <el-statistic title="平均绩点" :value="Number(summary?.gpa ?? 0)" :precision="2" />
        <el-statistic title="已修课程" :value="summary?.total_courses ?? 0" />
        <el-statistic title="不及格" :value="summary?.failed_courses ?? 0" />
      </div>
    </el-card>

    <el-card shadow="never" class="page-card">
      <div class="toolbar">
        <el-select
          v-model="semester"
          clearable
          placeholder="全部学期"
          style="width: 180px"
          @change="load"
        >
          <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
        </el-select>
        <div class="spacer" />
        <el-text size="small" type="info">仅显示教务审核通过的成绩</el-text>
      </div>

      <el-empty v-if="!grades.length" description="暂无已发布的成绩" />

      <div v-for="[sem, rows] in grouped" :key="sem" class="sem-block">
        <div class="sem-head">
          <span class="sem">{{ sem }}</span>
          <el-tag size="small" type="info">
            {{ rows.length }} 门 · {{ semesterCredits(rows) }} 学分
          </el-tag>
        </div>
        <el-table :data="rows" stripe size="small">
          <el-table-column prop="course_code" label="课程代码" width="110" />
          <el-table-column prop="course_name" label="课程名称" min-width="160" />
          <el-table-column prop="credits" label="学分" width="70" align="center" />
          <el-table-column label="平时" width="80" align="center">
            <template #default="{ row }">{{ row.regular_score ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="期末" width="80" align="center">
            <template #default="{ row }">{{ row.final_score ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="总评" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="scoreType(row)" size="small">{{ row.total_score }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="grade_point" label="绩点" width="80" align="center" />
          <el-table-column label="结果" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.is_passed ? 'success' : 'danger'" size="small">
                {{ row.is_passed ? '通过' : '不及格' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.sem-block + .sem-block {
  margin-top: 20px;
}
.sem-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.sem {
  font-weight: 600;
  font-size: 15px;
}
</style>
