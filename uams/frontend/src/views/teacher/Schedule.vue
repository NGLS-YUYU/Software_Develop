<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import { scheduleApi } from '@/api'
import ScheduleGrid from '@/components/ScheduleGrid.vue'
import { currentSemester, semesterOptions } from '@/composables/useSemester'
import type { ScheduleItem } from '@/types'

const semester = ref(currentSemester())
const week = ref<number | undefined>(undefined)
const items = ref<ScheduleItem[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    items.value = await scheduleApi.mine(semester.value, week.value)
  } finally {
    loading.value = false
  }
}

watch([semester, week], load)
onMounted(load)
</script>

<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-select v-model="semester" style="width: 170px">
        <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
      </el-select>
      <el-select v-model="week" clearable placeholder="全部周次" style="width: 140px">
        <el-option v-for="w in 20" :key="w" :label="`第 ${w} 周`" :value="w" />
      </el-select>
      <div class="spacer" />
      <el-tag type="info">共 {{ items.length }} 门次安排</el-tag>
    </div>
    <div v-loading="loading">
      <el-empty v-if="!items.length" description="本学期暂无授课安排" />
      <ScheduleGrid v-else :items="items" />
    </div>
  </el-card>
</template>
