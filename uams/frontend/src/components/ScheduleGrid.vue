<script setup lang="ts">
/** 周课表。桌面端为网格，移动端自动切换为按星期分组的列表（V3.0）。
 *  学生端与教师端复用，数据来自 TASK-013 平铺接口。 */
import { computed } from 'vue'

import type { Schedule } from '@/types'

const props = defineProps<{
  items: Schedule[]
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
  const map = new Map<string, Schedule[]>()
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

function weekLabel(it: Schedule) {
  const base = `${it.start_week}-${it.end_week}周`
  if (it.week_type === 'ODD') return `${base} 单`
  if (it.week_type === 'EVEN') return `${base} 双`
  return base
}

/** 移动端列表：按星期分组并按节次排序（纯展示用派生数据）。 */
const dayGroups = computed(() =>
  DAYS.map((d) => ({
    day: d,
    name: DAY_NAMES[d - 1],
    list: props.items
      .filter((it) => it.day_of_week === d)
      .slice()
      .sort((a, b) => a.start_period - b.start_period),
  })).filter((g) => g.list.length > 0),
)

/** 课程块配色：按课程名散列，保证同一门课颜色稳定（低饱和淡紫/冷色系）。 */
const PALETTE = [
  '#f1eefc,#5b4bc4',
  '#eef6f0,#2f7d55',
  '#fdf3e6,#a9701f',
  '#fdeeee,#b04c4c',
  '#eef3fd,#3f5fae',
  '#f2f1f7,#5f6273',
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
  <div class="schedule">
    <!-- 桌面端：周网格 -->
    <div class="schedule-grid desktop-only">
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
                :key="it.id"
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

    <!-- 移动端：按星期分组的列表，避免把网格硬塞进窄屏 -->
    <div class="schedule-list mobile-only">
      <section v-for="g in dayGroups" :key="g.day" class="day-group">
        <header class="day-group__head">
          <span class="day-group__name">{{ g.name }}</span>
          <span class="day-group__count">{{ g.list.length }} 门</span>
        </header>
        <article
          v-for="it in g.list"
          :key="it.id"
          class="day-item"
          :style="colorOf(it.course_name)"
        >
          <div class="day-item__time">
            第 {{ it.start_period }}-{{ it.end_period }} 节
          </div>
          <div class="day-item__body">
            <div class="day-item__name">{{ it.course_name }}</div>
            <div class="day-item__meta">
              <span v-if="it.classroom_code">
                <el-icon><component :is="'Location'" /></el-icon>{{ it.classroom_code }}
              </span>
              <span v-if="showTeacher && it.teacher_name">
                <el-icon><component :is="'User'" /></el-icon>{{ it.teacher_name }}
              </span>
              <span><el-icon><component :is="'Calendar'" /></el-icon>{{ weekLabel(it) }}</span>
            </div>
          </div>
        </article>
      </section>
    </div>
  </div>
</template>

<style scoped lang="scss">
/* ------------------------------------------------------- 桌面：周网格 */
.schedule-grid {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  table-layout: fixed;
  min-width: 860px;
}

th,
td {
  border-bottom: 1px solid var(--uams-border);
  border-right: 1px solid var(--uams-border);
  vertical-align: top;
  padding: 6px;

  &:last-child {
    border-right: none;
  }
}

th {
  background: var(--uams-surface-sunken);
  font-weight: 600;
  color: var(--uams-text-2);
  padding: 11px 6px;
  text-align: center;
  font-size: 13px;
  border-bottom: 1px solid var(--uams-border-strong);
}

td {
  height: 92px;
}

.time-col {
  width: 94px;
  text-align: center;
  background: var(--uams-surface-sunken);
  font-size: 12px;
  color: var(--uams-text-3);
  vertical-align: middle;
  border-right: 1px solid var(--uams-border-strong);
}

.course {
  border-radius: var(--uams-radius-xs);
  padding: 7px 8px;
  font-size: 12px;
  line-height: 1.5;

  + .course {
    margin-top: 5px;
  }

  .name {
    font-weight: 600;
    margin-bottom: 2px;
  }

  .meta {
    color: var(--uams-text-2);
    font-size: 11px;
  }

  .weeks {
    color: var(--uams-text-3);
  }
}

/* --------------------------------------------------------- 移动：列表 */
.schedule-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.day-group {
  &__head {
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding-bottom: 8px;
    margin-bottom: 10px;
    border-bottom: 1px solid var(--uams-border);
  }

  &__name {
    font-size: 14px;
    font-weight: 600;
    color: var(--uams-text);
  }

  &__count {
    font-size: 12px;
    color: var(--uams-text-3);
  }
}

.day-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  border-radius: var(--uams-radius-sm);

  + .day-item {
    margin-top: 8px;
  }

  &__time {
    flex: 0 0 82px;
    font-size: 12px;
    font-weight: 600;
    color: var(--uams-text-2);
    padding-top: 1px;
  }

  &__body {
    min-width: 0;
    flex: 1;
  }

  &__name {
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 6px;
  }

  &__meta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 14px;
    font-size: 12px;
    color: var(--uams-text-2);

    span {
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
  }
}

/* 显示/隐藏：默认桌面网格，窄屏切换为列表 */
.mobile-only {
  display: none;
}

@media (max-width: 768px) {
  .desktop-only {
    display: none;
  }

  .mobile-only {
    display: block;
  }
}
</style>
