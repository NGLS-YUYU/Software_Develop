<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import { scheduleApi } from '@/api'
import ScheduleGrid from '@/components/ScheduleGrid.vue'
import { semesterOptions, currentSemester } from '@/composables/useSemester'
import type { Schedule } from '@/types'

const semester = ref(currentSemester())
const week = ref<number | undefined>(undefined)
const items = ref<Schedule[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    items.value = await scheduleApi.my(semester.value, week.value)
  } finally {
    loading.value = false
  }
}

watch([semester, week], load)
onMounted(load)
</script>

<template>
  <el-card shadow="never" class="page-card">
    <div class="toolbar">
      <el-select v-model="semester" style="width: 170px">
        <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
      </el-select>
      <el-select v-model="week" clearable placeholder="全部周次" style="width: 140px">
        <el-option v-for="w in 20" :key="w" :label="`第 ${w} 周`" :value="w" />
      </el-select>
      <div class="spacer" />
      <span class="count-chip">
        <el-icon><component :is="'Calendar'" /></el-icon>
        共 <strong>{{ items.length }}</strong> 门次安排
      </span>
    </div>

    <div v-loading="loading">
      <el-empty v-if="!items.length" description="本学期暂无课程安排">
        <template #description>
          <p class="muted">该学期你还没有已选课程的排课，先去「在线选课」选课吧。</p>
        </template>
      </el-empty>
      <ScheduleGrid v-else :items="items" show-teacher />
    </div>
  </el-card>
</template>

<style scoped lang="scss">
.count-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 999px;
  font-size: 13px;
  color: var(--uams-primary-dark);
  background: var(--uams-primary-soft);

  strong {
    font-size: 15px;
  }
}
</style>
