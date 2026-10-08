<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { announcementApi, examApi, gradeApi, scheduleApi, studentApi } from '@/api'
import { currentSemester } from '@/composables/useSemester'
import type { Announcement, Exam, GradeSummary, Schedule, Student } from '@/types'

const router = useRouter()
const semester = currentSemester()

const profile = ref<Student | null>(null)
const summary = ref<GradeSummary | null>(null)
const schedule = ref<Schedule[]>([])
const exams = ref<Exam[]>([])
const announcements = ref<Announcement[]>([])
const loading = ref(true)

/** 今日课程：day_of_week 1=周一，JS getDay() 0=周日 */
const todayCourses = computed(() => {
  const jsDay = new Date().getDay()
  const today = jsDay === 0 ? 7 : jsDay
  return schedule.value
    .filter((s) => s.day_of_week === today)
    .sort((a, b) => a.start_period - b.start_period)
})

const upcomingExams = computed(() =>
  [...exams.value]
    .filter((e) => new Date(e.exam_date) >= new Date(new Date().toDateString()))
    .sort((a, b) => a.exam_date.localeCompare(b.exam_date))
    .slice(0, 5),
)

/** 纯展示：按教学班去重后的"我的课程"（周次取首次排课），不改变任何业务逻辑 */
const myCourses = computed(() => {
  const seen = new Map<number, Schedule>()
  for (const s of schedule.value) {
    if (!seen.has(s.teaching_class_id)) seen.set(s.teaching_class_id, s)
  }
  return [...seen.values()].sort((a, b) =>
    (a.course_name ?? '').localeCompare(b.course_name ?? ''),
  )
})

onMounted(async () => {
  try {
    const [p, s, sch, ex, ann] = await Promise.allSettled([
      studentApi.me(),
      gradeApi.mySummary(),
      scheduleApi.my(semester),
      examApi.mine(semester),
      announcementApi.list({ page: 1, page_size: 5 }),
    ])
    if (p.status === 'fulfilled') profile.value = p.value
    if (s.status === 'fulfilled') summary.value = s.value
    if (sch.status === 'fulfilled') schedule.value = sch.value
    if (ex.status === 'fulfilled') exams.value = ex.value
    if (ann.status === 'fulfilled') announcements.value = ann.value.items
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div v-loading="loading" class="portal">
    <!-- 顶部：身份 + 紧凑指标条 + 成绩概览卡 -->
    <section class="portal__top">
      <el-card class="page-card hero" shadow="never">
        <div class="hero__id">
          <div class="hero__avatar">{{ (profile?.real_name || '同').slice(0, 1) }}</div>
          <div class="hero__who">
            <h2>你好，{{ profile?.real_name || '同学' }}</h2>
            <p class="muted">
              {{ profile?.college_name }} · {{ profile?.major_name }} ·
              {{ profile?.class_name }} · 学号 {{ profile?.student_no }}
            </p>
          </div>
          <el-tag class="hero__semester" effect="plain">{{ semester }} 学期</el-tag>
        </div>

        <div class="metric-bar">
          <div class="metric">
            <span class="metric__value">
              {{ new Set(schedule.map((s) => s.teaching_class_id)).size }}
            </span>
            <span class="metric__label">本学期课程</span>
          </div>
          <div class="metric">
            <span class="metric__value">{{ summary?.total_credits ?? 0 }}</span>
            <span class="metric__label">已修学分</span>
          </div>
          <div class="metric">
            <span class="metric__value">
              {{ summary?.gpa != null ? Number(summary.gpa).toFixed(2) : '—' }}
            </span>
            <span class="metric__label">平均绩点</span>
          </div>
        </div>
      </el-card>

      <el-card class="page-card grade-card" shadow="never">
        <div class="grade-card__head">
          <span class="section-title">成绩概览</span>
          <el-link type="primary" :underline="false" @click="router.push('/student/grades')">
            成绩单
          </el-link>
        </div>

        <div class="grade-card__gpa">
          <span class="grade-card__num">
            {{ summary?.gpa != null ? Number(summary.gpa).toFixed(2) : '—' }}
          </span>
          <span class="grade-card__unit">GPA</span>
        </div>

        <div class="grade-card__ranks">
          <div class="rank">
            <span class="rank__label">班级排名</span>
            <span class="rank__value">—</span>
          </div>
          <div class="rank">
            <span class="rank__label">专业排名</span>
            <span class="rank__value">—</span>
          </div>
        </div>

        <div class="grade-card__foot">
          <span>已修 <b>{{ summary?.total_credits ?? 0 }}</b> 学分</span>
          <span>
            通过 <b>{{ summary?.passed_courses ?? 0 }}</b> /
            {{ summary?.total_courses ?? 0 }} 门
          </span>
        </div>
      </el-card>
    </section>

    <!-- 今日课程 + 我的课程 -->
    <section class="portal__mid">
      <el-card class="page-card" shadow="never">
        <template #header>
          <div class="card-head">
            <span>今日课程</span>
            <el-link type="primary" :underline="false" @click="router.push('/student/schedule')">
              完整课表
            </el-link>
          </div>
        </template>
        <el-empty v-if="!todayCourses.length" description="今天没有课，好好休息" :image-size="70" />
        <el-timeline v-else class="timeline">
          <el-timeline-item
            v-for="c in todayCourses"
            :key="c.id"
            :timestamp="`第 ${c.start_period}-${c.end_period} 节`"
            placement="top"
          >
            <div class="tl-title">{{ c.course_name }}</div>
            <div class="sub">{{ c.teacher_name }} · {{ c.classroom_code }}</div>
          </el-timeline-item>
        </el-timeline>
      </el-card>

      <el-card class="page-card" shadow="never">
        <template #header>
          <div class="card-head">
            <span>我的课程</span>
            <span class="muted">共 {{ myCourses.length }} 门</span>
          </div>
        </template>
        <el-empty v-if="!myCourses.length" description="本学期暂无课程" :image-size="70" />
        <ul v-else class="course-list">
          <li v-for="c in myCourses" :key="c.teaching_class_id">
            <div class="course-list__main">
              <span class="course-list__name">{{ c.course_name }}</span>
              <span class="sub">{{ c.teacher_name }} · {{ c.classroom_code }}</span>
            </div>
            <span class="course-list__time">
              周{{ c.day_of_week }} 第{{ c.start_period }}-{{ c.end_period }} 节
            </span>
          </li>
        </ul>
      </el-card>
    </section>

    <!-- 待关注事项 + 考试提醒 -->
    <section class="portal__mid">
      <el-card class="page-card" shadow="never">
        <template #header>
          <div class="card-head"><span>待关注事项</span></div>
        </template>
        <ul v-if="todayCourses.length || upcomingExams.length || summary?.failed_courses" class="alert-list">
          <li v-if="todayCourses.length">
            <el-icon class="alert-list__icon"><component :is="'Clock'" /></el-icon>
            <span>今日有 <b>{{ todayCourses.length }}</b> 节课程待上</span>
          </li>
          <li v-if="upcomingExams.length">
            <el-icon class="alert-list__icon"><component :is="'Calendar'" /></el-icon>
            <span>临近 <b>{{ upcomingExams.length }}</b> 场考试</span>
          </li>
          <li v-if="summary?.failed_courses">
            <el-icon class="alert-list__icon is-warning"><component :is="'Warning'" /></el-icon>
            <span>有 <b>{{ summary?.failed_courses }}</b> 门课程未通过</span>
          </li>
        </ul>
        <el-empty v-else description="暂无待关注事项" :image-size="70" />
      </el-card>

      <el-card class="page-card" shadow="never">
        <template #header>
          <div class="card-head">
            <span>考试提醒</span>
            <el-link type="primary" :underline="false" @click="router.push('/student/exams')">
              全部考试
            </el-link>
          </div>
        </template>
        <el-empty v-if="!upcomingExams.length" description="暂无考试安排" :image-size="70" />
        <el-table v-else :data="upcomingExams" size="small">
          <el-table-column prop="course_name" label="课程" min-width="120" />
          <el-table-column prop="exam_date" label="日期" width="110" />
          <el-table-column label="时间" width="110">
            <template #default="{ row }">
              {{ row.start_time?.slice(0, 5) }}-{{ row.end_time?.slice(0, 5) }}
            </template>
          </el-table-column>
          <el-table-column prop="classroom_code" label="考场" width="80" />
        </el-table>
      </el-card>
    </section>

    <!-- 最新通知 -->
    <el-card class="page-card" shadow="never">
      <template #header>
        <div class="card-head">
          <span>最新通知</span>
          <el-link
            type="primary"
            :underline="false"
            @click="router.push('/student/announcements')"
          >
            更多
          </el-link>
        </div>
      </template>
      <el-empty v-if="!announcements.length" description="暂无通知" :image-size="70" />
      <ul v-else class="ann-list">
        <li v-for="a in announcements" :key="a.id">
          <el-tag v-if="a.is_top" type="danger" size="small">置顶</el-tag>
          <span class="title">{{ a.title }}</span>
          <span class="date">{{ a.published_at?.slice(0, 10) }}</span>
        </li>
      </ul>
    </el-card>
  </div>
</template>

<style scoped lang="scss">
.portal {
  display: flex;
  flex-direction: column;
  gap: var(--uams-gap);
}

/* ------------------------------------------------------------- 顶部区域 */
.portal__top,
.portal__mid {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(0, 1fr);
  gap: var(--uams-gap);
  align-items: stretch;
}

.portal__mid {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
}

/* 用 grid 排布后，卡片自身不再叠加外边距 */
.portal__top > .page-card,
.portal__mid > .page-card {
  margin-top: 0;
  height: 100%;
}

/* --------------------------------------------------------------- 身份条 */
.hero {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: var(--uams-gap-lg);
}

.hero__id {
  display: flex;
  align-items: center;
  gap: 14px;
}

.hero__avatar {
  width: 46px;
  height: 46px;
  flex: 0 0 46px;
  border-radius: 13px;
  display: grid;
  place-items: center;
  font-size: 19px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, var(--uams-primary), var(--uams-primary-light));
  box-shadow: 0 6px 16px color-mix(in srgb, var(--uams-primary) 24%, transparent);
}

.hero__who {
  min-width: 0;
  flex: 1;

  h2 {
    margin: 0 0 4px;
    font-size: 19px;
    font-weight: 600;
    color: var(--uams-text);
  }

  p {
    margin: 0;
    font-size: 13px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.hero__semester {
  border-color: var(--uams-primary-light);
  color: var(--uams-primary-dark);
  background: var(--uams-primary-softer);
  flex: 0 0 auto;
}

.metric-bar {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  border-top: 1px solid var(--uams-border);
  padding-top: var(--uams-gap);
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-left: 18px;
  border-left: 1px solid var(--uams-border);

  &:first-child {
    padding-left: 0;
    border-left: none;
  }

  &__value {
    font-size: 26px;
    font-weight: 700;
    line-height: 1.1;
    color: var(--uams-text);
    font-variant-numeric: tabular-nums;
  }

  &__label {
    font-size: 12px;
    color: var(--uams-text-3);
  }
}

/* ----------------------------------------------------------- 成绩概览卡 */
.grade-card {
  display: flex;
  flex-direction: column;
  background: linear-gradient(165deg, var(--uams-primary-softer) 0%, var(--uams-surface) 58%);
  border-color: var(--uams-border);
}

.grade-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;

  .section-title {
    margin: 0;
  }
}

.grade-card__gpa {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 14px 0 4px;
}

.grade-card__num {
  font-size: 46px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: -1px;
  color: var(--uams-primary-dark);
  font-variant-numeric: tabular-nums;
}

.grade-card__unit {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 1px;
  color: var(--uams-text-3);
}

.grade-card__ranks {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 14px;
}

.rank {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 12px;
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface);
  border: 1px solid var(--uams-border);

  &__label {
    font-size: 12px;
    color: var(--uams-text-3);
  }

  &__value {
    font-size: 20px;
    font-weight: 700;
    color: var(--uams-text);
    font-variant-numeric: tabular-nums;
  }
}

.grade-card__foot {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 8px;
  margin-top: auto;
  padding-top: 14px;
  font-size: 13px;
  color: var(--uams-text-2);

  b {
    color: var(--uams-text);
  }
}

/* --------------------------------------------------------------- 通用 */
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.sub {
  color: var(--uams-text-3);
  font-size: 12px;
  margin-top: 2px;
}

.timeline {
  padding-left: 2px;

  .tl-title {
    font-weight: 600;
    color: var(--uams-text);
  }
}

/* ----------------------------------------------------------- 我的课程 */
.course-list {
  list-style: none;
  margin: 0;
  padding: 0;

  li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 0;
    border-bottom: 1px dashed var(--uams-border);

    &:last-child {
      border-bottom: none;
    }
  }

  &__main {
    min-width: 0;
    display: flex;
    flex-direction: column;
  }

  &__name {
    font-weight: 600;
    color: var(--uams-text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__time {
    flex: 0 0 auto;
    font-size: 12px;
    color: var(--uams-primary-dark);
    background: var(--uams-primary-soft);
    border-radius: var(--uams-radius-xs);
    padding: 3px 8px;
  }
}

/* --------------------------------------------------------- 待关注事项 */
.alert-list {
  list-style: none;
  margin: 0;
  padding: 0;

  li {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 11px 0;
    border-bottom: 1px dashed var(--uams-border);
    font-size: 13px;
    color: var(--uams-text-2);

    &:last-child {
      border-bottom: none;
    }

    b {
      color: var(--uams-text);
    }
  }

  &__icon {
    color: var(--uams-primary);
    font-size: 16px;

    &.is-warning {
      color: var(--uams-warning);
    }
  }
}

/* ----------------------------------------------------------- 最新通知 */
.ann-list {
  list-style: none;
  margin: 0;
  padding: 0;

  li {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 0;
    border-bottom: 1px dashed var(--uams-border);

    &:last-child {
      border-bottom: none;
    }
  }

  .title {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .date {
    flex: 0 0 auto;
    color: var(--uams-text-3);
    font-size: 12px;
  }
}

/* ------------------------------------------------------------- 响应式 */
@media (max-width: 1024px) {
  .portal__top,
  .portal__mid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 768px) {
  .portal {
    gap: 12px;
  }

  .hero {
    gap: var(--uams-gap);
  }

  /* 指标条在窄屏改为两列，避免三个大数字挤在一行 */
  .metric-bar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    row-gap: 14px;
  }

  .metric {
    &:nth-child(3) {
      padding-left: 0;
      border-left: none;
    }

    &__value {
      font-size: 22px;
    }
  }

  .grade-card__num {
    font-size: 38px;
  }

  .hero__semester {
    display: none;
  }

  .course-list__time {
    font-size: 11px;
    padding: 2px 6px;
  }
}

@media (max-width: 420px) {
  .metric-bar {
    grid-template-columns: minmax(0, 1fr);
  }

  .metric {
    padding-left: 0;
    border-left: none;
  }
}
</style>
