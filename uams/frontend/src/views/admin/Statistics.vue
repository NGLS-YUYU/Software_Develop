<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import { statsApi } from '@/api'
import { currentSemester, semesterOptions } from '@/composables/useSemester'
import type { GradeStatistics, Overview } from '@/types'

const semester = ref(currentSemester())
const overview = ref<Overview | null>(null)
const dist = ref<GradeStatistics | null>(null)
const ranking = ref<{ course_name: string; selected: number }[]>([])
const loading = ref(false)

const OVERVIEW_ITEMS = [
  { key: 'colleges', label: '学院' }, { key: 'majors', label: '专业' },
  { key: 'classes', label: '班级' }, { key: 'students', label: '学生' },
  { key: 'teachers', label: '教师' }, { key: 'courses', label: '课程' },
  { key: 'teaching_classes', label: '教学班' }, { key: 'selections', label: '选课记录' },
] as const

async function load() {
  loading.value = true
  try {
    const [o, d, r] = await Promise.allSettled([
      statsApi.overview(),
      statsApi.gradeDistribution(semester.value),
      statsApi.selectionRanking(semester.value, 10),
    ])
    if (o.status === 'fulfilled') overview.value = o.value
    if (d.status === 'fulfilled') dist.value = d.value
    if (r.status === 'fulfilled') ranking.value = r.value
  } finally {
    loading.value = false
  }
}

watch(semester, load)
onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <el-card shadow="never" class="page-card">
      <div class="toolbar">
        <el-select v-model="semester" style="width: 180px">
          <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
        </el-select>
        <el-button type="primary" @click="load">刷新</el-button>
      </div>
      <div class="stat-grid">
        <el-statistic v-for="i in OVERVIEW_ITEMS" :key="i.key" :title="i.label"
          :value="overview?.[i.key] ?? 0" />
      </div>
    </el-card>

    <el-row :gutter="16" class="page-card">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span>成绩分布（{{ semester }}）</span></template>
          <el-empty v-if="!dist?.count" description="该学期暂无成绩数据" :image-size="70" />
          <template v-else>
            <div class="mini-stats">
              <el-statistic title="成绩条数" :value="dist.count" />
              <el-statistic title="平均分" :value="dist.average ?? 0" :precision="2" />
              <el-statistic title="及格率" :value="dist.pass_rate ?? 0" suffix="%" />
            </div>
            <div class="bars">
              <div v-for="(n, k) in dist.distribution" :key="k" class="bar-row">
                <span class="label">{{ k }} 分</span>
                <el-progress :percentage="dist.count ? Math.round((n / dist.count) * 100) : 0"
                  :stroke-width="15" />
                <span class="count">{{ n }} 人</span>
              </div>
            </div>
          </template>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span>选课热度 Top 10</span></template>
          <el-empty v-if="!ranking.length" description="该学期暂无选课数据" :image-size="70" />
          <div v-else class="bars">
            <div v-for="(r, i) in ranking" :key="r.course_name" class="bar-row">
              <span class="label">
                <el-tag :type="i < 3 ? 'danger' : 'info'" size="small">{{ i + 1 }}</el-tag>
                {{ r.course_name }}
              </span>
              <el-progress
                :percentage="Math.round((r.selected / (ranking[0]?.selected || 1)) * 100)"
                :stroke-width="15" :show-text="false" />
              <span class="count">{{ r.selected }} 人</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.mini-stats { display: flex; gap: 40px; margin-bottom: 18px; }
.bars .bar-row {
  display: grid; grid-template-columns: 140px 1fr 70px;
  align-items: center; gap: 12px; margin-bottom: 9px;
}
.bars .label {
  font-size: 13px; color: #606266; display: flex; align-items: center; gap: 6px;
  overflow: hidden; white-space: nowrap; text-overflow: ellipsis;
}
.bars .count { font-size: 12px; color: #909399; text-align: right; }
</style>
