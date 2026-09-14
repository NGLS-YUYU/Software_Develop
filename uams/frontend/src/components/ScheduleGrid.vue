<script setup lang="ts">
/** 周课表网格。学生端与教师端复用。 */
import { computed } from 'vue'

import type { ScheduleItem } from '@/types'

const props = defineProps<{
  items: ScheduleItem[]
  /** 显示教师姓名（学生课表用）还是不显示（教师本人课表） */
  showTeacher?: boolean
}>()

const DAYS = [1, 2, 3, 4, 5, 6, 7]
const DAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
/** 每大节覆盖两小节：1-2 / 3-4 / 5-6 / 7-8 / 9-10 / 11-12 */
const SLOTS = [
  { label: '第 1-2 节', start: 1, end: 2 },
  { label: '第 3-4 节', start: 3, end: 4 },
  { label: '第 5-6 节', start: 5, end: 6 },
  { label: '第 7-8 节', start: 7, end: 8 },
  { label: '第 9-10 节', start: 9, end: 10 },
  { label: '第 11-12 节', start: 11, end: 12 },
]

/** 课程块按 (星期, 大节) 归位；节次区间与大节有交集即落入该格。 */
const grid = computed(() => {
  const map = new Map<string, ScheduleItem[]>()
  for (const it of props.items) {
    for (const [i, slot] of SLOTS.entries()) {
      if (it.start_period <= slot.end && it.end_period >= slot.start) {
        const key = `${it.day_of_week}-${i}`
        const arr = map.get(key) ?? []
        arr.push(it)
        map.set(key, arr)
      }
    }
  }
  return map
})

function cell(day: number, slotIdx: number) {
  return grid.value.get(`${day}-${slotIdx}`) ?? []
}

function weekLabel(it: ScheduleItem) {
  const base = `${it.start_week}-${it.end_week}周`
  if (it.week_type === 'ODD') return `${base} 单`
  if (it.week_type === 'EVEN') return `${base} 双`
  return base
}

/** 课程块配色：按课程名散列，保证同一门课颜色稳定。 */
const PALETTE = [
  '#e8f3ff,#1f6feb',
  '#e9f7ef,#1f9254',
  '#fff4e6,#c76a15',
  '#fdecef,#c0392b',
  '#f3ecfd,#7d3cc4',
  '#e6f7f8,#11808c',
]

function colorOf(name?: string | null) {
  const s = name ?? ''
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  const [bg, fg] = PALETTE[h % PALETTE.length].split(',')
  return { background: bg, borderLeft: `3px solid ${fg}`, color: '#303133' }
}
</script>

<template>
  <div class="schedule-grid">
    <table>
      <thead>
        <tr>
          <th class="time-col">时间</th>
          <th v-for="(d, i) in DAYS" :key="d">{{ DAY_NAMES[i] }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(slot, si) in SLOTS" :key="slot.label">
          <td class="time-col">{{ slot.label }}</td>
          <td v-for="d in DAYS" :key="d">
            <div
              v-for="it in cell(d, si)"
              :key="it.schedule_id"
              class="course"
              :style="colorOf(it.course_name)"
            >
              <div class="name">{{ it.course_name }}</div>
              <div class="meta">{{ it.classroom_code }}</div>
              <div v-if="showTeacher && it.teacher_name" class="meta">
                {{ it.teacher_name }}
              </div>
              <div class="meta weeks">{{ weekLabel(it) }}</div>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped lang="scss">
.schedule-grid {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  min-width: 860px;
}

th,
td {
  border: 1px solid #ebeef5;
  vertical-align: top;
  padding: 5px;
}

th {
  background: #fafafa;
  font-weight: 600;
  padding: 10px 5px;
  text-align: center;
}

td {
  height: 84px;
}

.time-col {
  width: 92px;
  text-align: center;
  background: #fafafa;
  font-size: 12px;
  color: #606266;
  vertical-align: middle;
}

.course {
  border-radius: 4px;
  padding: 6px 7px;
  font-size: 12px;
  line-height: 1.5;

  + .course {
    margin-top: 4px;
  }

  .name {
    font-weight: 600;
  }

  .meta {
    color: #606266;
    font-size: 11px;
  }

  .weeks {
    color: #909399;
  }
}
</style>
