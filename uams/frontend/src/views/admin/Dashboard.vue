<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { gradeApi, statsApi } from '@/api'
import { currentSemester } from '@/composables/useSemester'
import type { Grade, GradeStatistics, Overview } from '@/types'

const router = useRouter()
const overview = ref<Overview | null>(null)
const dist = ref<GradeStatistics | null>(null)
const ranking = ref<{ course_name: string; selected: number }[]>([])
const pending = ref<Grade[]>([])
const loading = ref(true)

const CARDS = [
  { key: 'students', label: '学生总数', icon: 'User', color: '#1f6feb', to: '/admin/students' },
  { key: 'teachers', label: '教师总数', icon: 'Avatar', color: '#1f9254', to: '/admin/teachers' },
  { key: 'courses', label: '课程总数', icon: 'Reading', color: '#c76a15', to: '/admin/courses' },
  { key: 'teaching_classes', label: '教学班', icon: 'Grid', color: '#7d3cc4', to: '/admin/teaching' },
  { key: 'selections', label: '选课记录', icon: 'Checked', color: '#11808c', to: '/admin/selection' },
  { key: 'pending_grades', label: '待审成绩', icon: 'Stamp', color: '#c0392b', to: '/admin/grades' },
] as const

onMounted(async () => {
  try {
    const [o, d, r, p] = await Promise.allSettled([
      statsApi.overview(),
      statsApi.gradeDistribution(),
      statsApi.selectionRanking(currentSemester(), 8),
      gradeApi.pending(),
    ])
    if (o.status === 'fulfilled') overview.value = o.value
    if (d.status === 'fulfilled') dist.value = d.value
    if (r.status === 'fulfilled') ranking.value = r.value
    if (p.status === 'fulfilled') pending.value = p.value
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div v-loading="loading">
    <div class="cards page-card">
      <el-card
        v-for="c in CARDS"
        :key="c.key"
        shadow="hover"
        class="stat-card"
        @click="router.push(c.to)"
      >
        <div class="inner">
          <el-icon class="icon" :style="{ background: c.color }">
            <component :is="c.icon" />
          </el-icon>
          <div class="text">
            <div class="num">{{ overview?.[c.key] ?? 0 }}</div>
            <div class="label">{{ c.label }}</div>
          </div>
        </div>
      </el-card>
    </div>

    <el-row :gutter="16" class="page-card">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span>全校成绩分布</span></template>
          <el-empty v-if="!dist?.count" description="暂无成绩数据" :image-size="70" />
          <template v-else>
            <div class="mini-stats">
              <el-statistic title="已发布成绩" :value="dist.count" />
              <el-statistic title="平均分" :value="dist.average ?? 0" :precision="2" />
              <el-statistic title="及格率" :value="dist.pass_rate ?? 0" suffix="%" />
            </div>
            <div class="dist">
              <div v-for="(n, k) in dist.distribution" :key="k" class="bar-row">
                <span class="label">{{ k }}</span>
                <el-progress
                  :percentage="dist.count ? Math.round((n / dist.count) * 100) : 0"
                  :stroke-width="13"
                />
                <span class="count">{{ n }}</span>
              </div>
            </div>
          </template>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span>选课热度 Top 8</span></template>
          <el-empty v-if="!ranking.length" description="暂无选课数据" :image-size="70" />
          <div v-else class="dist">
            <div v-for="(r, i) in ranking" :key="r.course_name" class="bar-row">
              <span class="label">
                <el-tag :type="i < 3 ? 'danger' : 'info'" size="small">{{ i + 1 }}</el-tag>
                {{ r.course_name }}
              </span>
              <el-progress
                :percentage="Math.round((r.selected / (ranking[0]?.selected || 1)) * 100)"
                :stroke-width="13"
                :show-text="false"
              />
              <span class="count">{{ r.selected }} 人</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="page-card" shadow="never">
      <template #header>
        <div class="card-head">
          <span>待审核成绩</span>
          <el-link type="primary" :underline="false" @click="router.push('/admin/grades')">
            去审核
          </el-link>
        </div>
      </template>
      <el-empty v-if="!pending.length" description="没有待审核的成绩" :image-size="70" />
      <el-table v-else :data="pending.slice(0, 8)" size="small">
        <el-table-column prop="course_name" label="课程" min-width="150" />
        <el-table-column prop="student_no" label="学号" width="130" />
        <el-table-column prop="student_name" label="学生" width="100" />
        <el-table-column prop="total_score" label="总评" width="80" align="center" />
        <el-table-column label="提交时间" width="160">
          <template #default="{ row }">
            {{ row.submitted_at?.slice(0, 16).replace('T', ' ') }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped lang="scss">
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 14px;
}

.stat-card {
  cursor: pointer;

  .inner {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .icon {
    width: 46px;
    height: 46px;
    border-radius: 8px;
    color: #fff;
    font-size: 22px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .num {
    font-size: 22px;
    font-weight: 600;
    line-height: 1.2;
  }

  .label {
    font-size: 12px;
    color: #909399;
    margin-top: 2px;
  }
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.mini-stats {
  display: flex;
  gap: 36px;
  margin-bottom: 16px;
}

.dist .bar-row {
  display: grid;
  grid-template-columns: 130px 1fr 60px;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.dist .label {
  font-size: 13px;
  color: #606266;
  display: flex;
  align-items: center;
  gap: 6px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.dist .count {
  font-size: 12px;
  color: #909399;
  text-align: right;
}
</style>
