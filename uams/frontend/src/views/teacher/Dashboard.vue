<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { announcementApi, gradeApi, scheduleApi, teacherApi, teachingApi } from '@/api'
import { currentSemester } from '@/composables/useSemester'
import type { Announcement, Schedule, Teacher, TeachingClass } from '@/types'

const router = useRouter()
const semester = currentSemester()

const profile = ref<Teacher | null>(null)
const classes = ref<TeachingClass[]>([])
const schedule = ref<Schedule[]>([])
const announcements = ref<Announcement[]>([])
const pendingCount = ref(0)
const loading = ref(true)

const todayCourses = computed(() => {
  const jsDay = new Date().getDay()
  const today = jsDay === 0 ? 7 : jsDay
  return schedule.value
    .filter((s) => s.day_of_week === today)
    .sort((a, b) => a.start_period - b.start_period)
})

const totalStudents = computed(() =>
  classes.value.reduce((s, c) => s + c.selected_count, 0),
)

onMounted(async () => {
  try {
    profile.value = await teacherApi.me()
    const [cls, sch, ann] = await Promise.allSettled([
      teachingApi.classes({ teacher_id: profile.value.id, semester, page_size: 100 }),
      scheduleApi.mine(semester),
      announcementApi.list({ page: 1, page_size: 5 }),
    ])
    if (cls.status === 'fulfilled') classes.value = cls.value.items
    if (sch.status === 'fulfilled') schedule.value = sch.value
    if (ann.status === 'fulfilled') announcements.value = ann.value.items

    // 统计还未提交成绩的教学班
    let pending = 0
    for (const c of classes.value) {
      try {
        const rows = await gradeApi.byClass(c.id)
        if (rows.some((r) => r.status === 'DRAFT' || r.status === 'REJECTED')) pending++
      } catch {
        // 单个教学班查询失败不影响整体展示
      }
    }
    pendingCount.value = pending
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div v-loading="loading" class="workbench">
    <!-- 顶部指标条：本学期教学班 / 授课学生 / 今日课程 / 待提交成绩 -->
    <el-card class="page-card metric-card" shadow="never">
      <div class="metric-bar">
        <div class="who">
          <div class="who__avatar">{{ (profile?.real_name || '?').slice(0, 1) }}</div>
          <div class="who__text">
            <div class="who__name">你好，{{ profile?.real_name || '老师' }}</div>
            <div class="who__sub muted">
              {{ profile?.college_name || '—' }} · 工号 {{ profile?.teacher_no || '—' }}
            </div>
          </div>
          <el-tag class="who__term" size="small" effect="plain">{{ semester }} 学期</el-tag>
        </div>

        <div class="metrics">
          <div class="metric">
            <span class="metric__icon"><el-icon><component :is="'Reading'" /></el-icon></span>
            <span class="metric__body">
              <span class="metric__num">{{ classes.length }}</span>
              <span class="metric__label muted">本学期教学班</span>
            </span>
          </div>
          <div class="metric">
            <span class="metric__icon"><el-icon><component :is="'User'" /></el-icon></span>
            <span class="metric__body">
              <span class="metric__num">{{ totalStudents }}</span>
              <span class="metric__label muted">授课学生</span>
            </span>
          </div>
          <div class="metric">
            <span class="metric__icon"><el-icon><component :is="'Calendar'" /></el-icon></span>
            <span class="metric__body">
              <span class="metric__num">{{ todayCourses.length }}</span>
              <span class="metric__label muted">今日课程</span>
            </span>
          </div>
          <div class="metric">
            <span class="metric__icon"><el-icon><component :is="'EditPen'" /></el-icon></span>
            <span class="metric__body">
              <span class="metric__num" :class="{ 'is-warn': pendingCount > 0 }">
                {{ pendingCount }}
              </span>
              <span class="metric__label muted">待提交成绩</span>
            </span>
          </div>
        </div>
      </div>
    </el-card>

    <div class="dash">
      <!-- 今日课程：按节次排序的时间线 -->
      <el-card class="page-card" shadow="never">
        <template #header>
          <div class="card-head">
            <span class="card-head__title">
              <el-icon><component :is="'Clock'" /></el-icon> 今日课程
            </span>
            <el-link type="primary" :underline="false" @click="router.push('/teacher/schedule')">
              完整课表
            </el-link>
          </div>
        </template>
        <el-empty v-if="!todayCourses.length" description="今天没有课" :image-size="70" />
        <el-timeline v-else class="tl">
          <el-timeline-item
            v-for="c in todayCourses"
            :key="c.id"
            :timestamp="`第 ${c.start_period}-${c.end_period} 节`"
            placement="top"
            color="var(--uams-primary)"
            size="large"
          >
            <div class="tl__top">
              <strong class="tl__course">{{ c.course_name }}</strong>
              <el-tag v-if="c.classroom_code" size="small" effect="plain">
                {{ c.classroom_code }}
              </el-tag>
            </div>
            <div class="tl__meta muted">
              <span>{{ c.teaching_class_code }}</span>
              <span v-if="c.building"> · {{ c.building }}</span>
            </div>
          </el-timeline-item>
        </el-timeline>
      </el-card>

      <!-- 我的教学班：课程 / 教学班编号 / 学生数 / 录入成绩入口 -->
      <el-card class="page-card" shadow="never">
        <template #header>
          <div class="card-head">
            <span class="card-head__title">
              <el-icon><component :is="'Reading'" /></el-icon> 我的教学班
            </span>
            <el-link type="primary" :underline="false" @click="router.push('/teacher/courses')">
              全部
            </el-link>
          </div>
        </template>
        <el-empty v-if="!classes.length" description="本学期暂无授课" :image-size="70" />
        <ul v-else class="cls-list">
          <li
            v-for="row in classes.slice(0, 6)"
            :key="row.id"
            class="cls"
            @click="router.push(`/teacher/grades/${row.id}`)"
          >
            <div class="cls__main">
              <span class="cls__name">{{ row.course_name }}</span>
              <span class="cls__code muted">{{ row.code }}</span>
            </div>
            <div class="cls__count">
              <span class="cls__num">{{ row.selected_count }}</span>
              <span class="cls__cap muted">/{{ row.capacity }}</span>
              <span class="cls__unit muted">学生</span>
            </div>
            <el-button
              class="cls__btn"
              size="small"
              type="primary"
              link
              @click.stop="router.push(`/teacher/grades/${row.id}`)"
            >
              录入成绩
            </el-button>
          </li>
        </ul>
      </el-card>

      <!-- 近期课程：本周已排课程（今日高亮），空则显示空状态 -->
      <el-card class="page-card" shadow="never">
        <template #header>
          <div class="card-head">
            <span class="card-head__title">
              <el-icon><component :is="'Calendar'" /></el-icon> 近期课程
            </span>
            <el-link type="primary" :underline="false" @click="router.push('/teacher/schedule')">
              本周课表
            </el-link>
          </div>
        </template>
        <el-empty v-if="!schedule.length" description="暂无排课" :image-size="70" />
        <ul v-else class="week-list">
          <li
            v-for="s in schedule.slice(0, 8)"
            :key="s.id"
            class="week"
            :class="{ 'is-today': s.day_of_week === (new Date().getDay() || 7) }"
          >
            <span class="week__day">
              {{ ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][s.day_of_week % 7] }}
            </span>
            <span class="week__period muted">第{{ s.start_period }}-{{ s.end_period }}节</span>
            <span class="week__course">{{ s.course_name }}</span>
            <span class="week__room muted">{{ s.classroom_code }}</span>
          </li>
        </ul>
      </el-card>

      <!-- 最新通知 -->
      <el-card class="page-card" shadow="never">
        <template #header>
          <div class="card-head">
            <span class="card-head__title">
              <el-icon><component :is="'Bell'" /></el-icon> 最新通知
            </span>
            <el-link type="primary" :underline="false" @click="router.push('/teacher/announcements')">
              更多
            </el-link>
          </div>
        </template>
        <el-empty v-if="!announcements.length" description="暂无通知" :image-size="70" />
        <ul v-else class="ann-list">
          <li v-for="a in announcements" :key="a.id">
            <span class="title">{{ a.title }}</span>
            <span class="date muted">{{ a.published_at?.slice(0, 10) }}</span>
          </li>
        </ul>
      </el-card>
    </div>
  </div>
</template>

<style scoped lang="scss">
.workbench {
  display: block;
}

/* ------------------------------------------------------------ 顶部指标条 */
.metric-bar {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(0, 1.7fr);
  align-items: center;
  gap: var(--uams-gap-lg);
}

.who {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  min-width: 0;

  &__avatar {
    width: 40px;
    height: 40px;
    flex: 0 0 40px;
    border-radius: var(--uams-radius);
    display: grid;
    place-items: center;
    font-size: 16px;
    font-weight: 600;
    color: #fff;
    background: linear-gradient(135deg, var(--uams-primary), var(--uams-primary-light));
  }

  &__text {
    min-width: 0;
  }

  &__name {
    font-size: 16px;
    font-weight: 600;
    line-height: 1.3;
    color: var(--uams-text);
  }

  &__sub {
    font-size: 12px;
    margin-top: 2px;
  }

  &__term {
    border-color: var(--uams-primary-light);
    color: var(--uams-primary-dark);
    background: var(--uams-primary-softer);
  }
}

.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.metric {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface-sunken);

  &__icon {
    width: 34px;
    height: 34px;
    flex: 0 0 34px;
    border-radius: var(--uams-radius-xs);
    display: grid;
    place-items: center;
    font-size: 17px;
    color: var(--uams-primary-dark);
    background: var(--uams-primary-soft);
  }

  &__body {
    display: flex;
    flex-direction: column;
    line-height: 1.2;
    min-width: 0;
  }

  &__num {
    font-size: 19px;
    font-weight: 700;
    color: var(--uams-text);

    &.is-warn {
      color: var(--uams-warning);
    }
  }

  &__label {
    font-size: 12px;
    white-space: nowrap;
  }
}

/* -------------------------------------------------------------- 主体网格 */
.dash {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr);
  align-items: start;
  gap: var(--uams-gap);
  margin-top: var(--uams-gap);

  /* 网格内用 gap 控制间距，避免全局 .page-card + .page-card 再叠加外边距 */
  .page-card + .page-card {
    margin-top: 0;
  }
}

/* 卡片头：标题 + 右侧链接 */
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;

  &__title {
    display: inline-flex;
    align-items: center;
    gap: 6px;

    .el-icon {
      color: var(--uams-primary);
    }
  }
}

/* ------------------------------------------------------------ 今日时间线 */
.tl {
  padding-left: 2px;
}

.tl__top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.tl__course {
  font-size: 14px;
  color: var(--uams-text);
}

.tl__meta {
  font-size: 12px;
  margin-top: 3px;
}

/* ------------------------------------------------------------ 教学班列表 */
.cls-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.cls {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 8px;
  border-bottom: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  cursor: pointer;
  transition: background-color 0.16s ease;

  &:last-child {
    border-bottom: none;
  }

  &:hover {
    background: var(--uams-primary-softer);
  }

  &__main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }

  &__name {
    font-weight: 500;
    color: var(--uams-text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  &__code {
    font-size: 12px;
  }

  &__count {
    display: inline-flex;
    align-items: baseline;
    gap: 2px;
    flex: 0 0 auto;
  }

  &__num {
    font-weight: 600;
    color: var(--uams-primary-dark);
  }

  &__cap,
  &__unit {
    font-size: 12px;
  }

  &__btn {
    flex: 0 0 auto;
  }
}

/* -------------------------------------------------------- 近期课程列表 */
.week-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.week {
  display: grid;
  grid-template-columns: 44px 76px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  padding: 9px 8px;
  border-bottom: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  font-size: 13px;

  &:last-child {
    border-bottom: none;
  }

  &__day {
    font-weight: 600;
    color: var(--uams-text-2);
  }

  &__period {
    font-size: 12px;
  }

  &__course {
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--uams-text);
  }

  &__room {
    font-size: 12px;
    text-align: right;
  }

  &.is-today {
    background: var(--uams-primary-softer);

    .week__day {
      color: var(--uams-primary-dark);
    }
  }
}

/* ------------------------------------------------------------ 通知列表 */
.ann-list {
  list-style: none;
  margin: 0;
  padding: 0;

  li {
    display: flex;
    gap: 8px;
    padding: 9px 0;
    border-bottom: 1px solid var(--uams-border);

    &:last-child {
      border-bottom: none;
    }
  }

  .title {
    flex: 1;
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .date {
    flex: 0 0 auto;
    font-size: 12px;
  }
}

/* ------------------------------------------------------------- 响应式 */
@media (max-width: 1024px) {
  .metric-bar {
    grid-template-columns: 1fr;
    gap: var(--uams-gap);
  }

  .dash {
    grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  }
}

@media (max-width: 768px) {
  .metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }

  .dash {
    grid-template-columns: 1fr;
    gap: 12px;
    margin-top: 12px;
  }

  /* 教学目标：手机端课程不再横向挤压，改为两行排布 */
  .week {
    grid-template-columns: auto minmax(0, 1fr) auto;
    grid-template-areas:
      'day period room'
      'course course course';
    row-gap: 2px;
  }

  .week__day {
    grid-area: day;
  }

  .week__period {
    grid-area: period;
  }

  .week__room {
    grid-area: room;
  }

  .week__course {
    grid-area: course;
    white-space: normal;
  }

  .cls {
    gap: 8px;
    padding: 10px 4px;
  }
}

@media (max-width: 420px) {
  .metrics {
    grid-template-columns: 1fr;
  }
}
</style>
