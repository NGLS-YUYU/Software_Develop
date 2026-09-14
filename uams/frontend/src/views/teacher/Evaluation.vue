<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { evaluationApi } from '@/api'
import type { EvaluationStats } from '@/types'

const stats = ref<EvaluationStats[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    stats.value = await evaluationApi.statistics()
  } finally {
    loading.value = false
  }
}

function level(avg?: number | null) {
  const v = Number(avg ?? 0)
  if (v >= 90) return { text: '优秀', type: 'success' }
  if (v >= 80) return { text: '良好', type: '' }
  if (v >= 70) return { text: '合格', type: 'warning' }
  return { text: '待改进', type: 'danger' }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <el-alert
      title="学生评价匿名提交，此处仅展示聚合结果，无法查看具体评价人"
      type="info"
      :closable="false"
      show-icon
      class="page-card"
    />

    <el-empty v-if="!stats.length" description="暂无评价数据" />
    <el-card v-for="s in stats" :key="s.teaching_class_id" shadow="never" class="page-card">
      <template #header>
        <div class="head">
          <span>{{ s.course_name }}（{{ s.teaching_class_code }}）</span>
          <div>
            <el-tag size="small" type="info">{{ s.count }} 人评价</el-tag>
            <el-tag size="small" :type="level(s.average).type as any" style="margin-left: 8px">
              {{ level(s.average).text }}
            </el-tag>
          </div>
        </div>
      </template>
      <div class="score-row">
        <el-statistic title="平均得分" :value="Number(s.average ?? 0)" :precision="2" />
        <el-progress
          type="dashboard"
          :percentage="Math.round(Number(s.average ?? 0))"
          :width="110"
        />
      </div>
      <el-divider v-if="s.comments.length" content-position="left">学生评语</el-divider>
      <ul v-if="s.comments.length" class="comments">
        <li v-for="(c, i) in s.comments" :key="i">{{ c }}</li>
      </ul>
    </el-card>
  </div>
</template>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: center; }
.score-row { display: flex; align-items: center; gap: 48px; }
.comments { margin: 0; padding-left: 18px; color: #606266; line-height: 1.9; }
</style>
