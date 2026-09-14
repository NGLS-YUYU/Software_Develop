<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { selectionApi } from '@/api'
import { currentSemester, semesterOptions } from '@/composables/useSemester'
import type { Selection, SelectionPeriod, TeachingClass } from '@/types'

const semester = ref(currentSemester())
const keyword = ref('')
const available = ref<TeachingClass[]>([])
const mine = ref<Selection[]>([])
const periods = ref<SelectionPeriod[]>([])
const loading = ref(false)
const tab = ref('available')

const totalCredits = computed(() =>
  mine.value.reduce((sum, s) => sum + Number(s.credits ?? 0), 0),
)

/** 选课是否开放：由后端时间窗口决定，这里只做提示。 */
const openPeriod = computed(() => {
  const now = Date.now()
  return periods.value.find(
    (p) =>
      p.status === 'ACTIVE' &&
      new Date(p.start_time).getTime() <= now &&
      now <= new Date(p.end_time).getTime(),
  )
})

async function load() {
  loading.value = true
  try {
    const [a, m, p] = await Promise.allSettled([
      selectionApi.available(semester.value, keyword.value || undefined),
      selectionApi.mine(semester.value),
      selectionApi.periods(semester.value),
    ])
    if (a.status === 'fulfilled') available.value = a.value
    if (m.status === 'fulfilled') mine.value = m.value
    if (p.status === 'fulfilled') periods.value = p.value
  } finally {
    loading.value = false
  }
}

function scheduleText(tc: TeachingClass) {
  const DAY = ['', '周一', '周二', '周三', '周四', '周五', '周六', '周日']
  if (!tc.schedules?.length) return '未排课'
  return tc.schedules
    .map((s) => {
      const wk =
        s.week_type === 'ODD' ? '单' : s.week_type === 'EVEN' ? '双' : ''
      return `${DAY[s.day_of_week]} ${s.start_period}-${s.end_period}节 ${s.classroom_code ?? ''} (${s.start_week}-${s.end_week}周${wk})`
    })
    .join('；')
}

async function doSelect(tc: TeachingClass) {
  try {
    await ElMessageBox.confirm(
      `确认选择《${tc.course_name}》（${tc.code}）？\n${scheduleText(tc)}`,
      '确认选课',
      { type: 'info' },
    )
  } catch {
    return
  }
  // 失败原因（已满/冲突/先修不满足等）由后端返回，拦截器统一提示
  await selectionApi.select(tc.id)
  ElMessage.success('选课成功')
  await load()
}

async function doDrop(s: Selection) {
  try {
    await ElMessageBox.confirm(`确认退选《${s.course_name}》？`, '确认退课', {
      type: 'warning',
    })
  } catch {
    return
  }
  await selectionApi.drop(s.id)
  ElMessage.success('已退课')
  await load()
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <el-alert
      v-if="openPeriod"
      :title="`选课开放中：${openPeriod.name}（截止 ${openPeriod.end_time.slice(0, 16).replace('T', ' ')}）`"
      type="success"
      :closable="false"
      show-icon
      class="page-card"
    />
    <el-alert
      v-else
      title="当前不在选课时间内，仅可查看"
      type="warning"
      :closable="false"
      show-icon
      class="page-card"
    />

    <el-card shadow="never" class="page-card">
      <div class="toolbar">
        <el-select v-model="semester" style="width: 170px" @change="load">
          <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
        </el-select>
        <el-input
          v-model="keyword"
          placeholder="搜索课程名称或代码"
          style="width: 240px"
          clearable
          @keyup.enter="load"
          @clear="load"
        />
        <el-button type="primary" @click="load">查询</el-button>
        <div class="spacer" />
        <el-tag type="success">已选 {{ mine.length }} 门 / {{ totalCredits }} 学分</el-tag>
      </div>

      <el-tabs v-model="tab">
        <el-tab-pane label="可选课程" name="available">
          <el-table :data="available" stripe>
            <el-table-column prop="course_code" label="课程代码" width="110" />
            <el-table-column prop="course_name" label="课程名称" min-width="150" />
            <el-table-column prop="credits" label="学分" width="70" align="center" />
            <el-table-column prop="teacher_name" label="教师" width="100" />
            <el-table-column label="上课安排" min-width="260">
              <template #default="{ row }">
                <span class="sched">{{ scheduleText(row) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="余量" width="110" align="center">
              <template #default="{ row }">
                <el-tag :type="row.remaining > 0 ? 'success' : 'danger'" size="small">
                  {{ row.selected_count }}/{{ row.capacity }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="90" align="center" fixed="right">
              <template #default="{ row }">
                <el-button
                  type="primary"
                  size="small"
                  :disabled="row.remaining <= 0"
                  @click="doSelect(row)"
                >
                  选课
                </el-button>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty description="暂无可选课程" />
            </template>
          </el-table>
        </el-tab-pane>

        <el-tab-pane :label="`已选课程 (${mine.length})`" name="mine">
          <el-table :data="mine" stripe>
            <el-table-column prop="course_code" label="课程代码" width="110" />
            <el-table-column prop="course_name" label="课程名称" min-width="160" />
            <el-table-column prop="credits" label="学分" width="70" align="center" />
            <el-table-column prop="teacher_name" label="教师" width="100" />
            <el-table-column prop="teaching_class_code" label="教学班" min-width="150" />
            <el-table-column label="选课时间" width="160">
              <template #default="{ row }">
                {{ row.selected_at?.slice(0, 16).replace('T', ' ') }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="90" align="center" fixed="right">
              <template #default="{ row }">
                <el-button type="danger" size="small" plain @click="doDrop(row)">
                  退课
                </el-button>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty description="尚未选课" />
            </template>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<style scoped>
.sched {
  font-size: 12px;
  color: #606266;
}
</style>
