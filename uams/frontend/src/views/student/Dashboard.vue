<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { announcementApi, examApi, gradeApi, scheduleApi, studentApi } from '@/api'
import { currentSemester } from '@/composables/useSemester'
import type { Announcement, Exam, GradeSummary, ScheduleItem, Student } from '@/types'

const router = useRouter()
const semester = currentSemester()

const profile = ref<Student | null>(null)
const summary = ref<GradeSummary | null>(null)
const schedule = ref<ScheduleItem[]>([])
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

onMounted(async () => {
  try {
    const [p, s, sch, ex, ann] = await Promise.allSettled([
      studentApi.me(),
      gradeApi.mySummary(),
      scheduleApi.mine(semester),
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
  <div v-loading="loading">
    <el-card class="page-card welcome" shadow="never">
      <div class="hello">
        <div>
          <h2>你好，{{ profile?.real_name || '同学' }}</h2>
          <p>
            {{ profile?.college_name }} · {{ profile?.major_name }} ·
            {{ profile?.class_name }} · 学号 {{ profile?.student_no }}
          </p>
        </div>
        <el-tag size="large">{{ semester }} 学期</el-tag>
      </div>
    </el-card>

    <div class="stat-grid page-card">
      <el-card shadow="never">
        <el-statistic title="已修学分" :value="Number(summary?.total_credits ?? 0)" />
      </el-card>
      <el-card shadow="never">
        <el-statistic title="平均绩点" :value="Number(summary?.gpa ?? 0)" :precision="2" />
      </el-card>
      <el-card shadow="never">
        <el-statistic title="本学期课程" :value="new Set(schedule.map(s => s.teaching_class_id)).size" />
      </el-card>
      <el-card shadow="never">
        <el-statistic title="待考科目" :value="upcomingExams.length" />
      </el-card>
    </div>

    <el-row :gutter="16" class="page-card">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <span>今日课程</span>
              <el-link type="primary" :underline="false" @click="router.push('/student/schedule')">
                完整课表
              </el-link>
            </div>
          </template>
          <el-empty v-if="!todayCourses.length" description="今天没有课" :image-size="70" />
          <el-timeline v-else>
            <el-timeline-item
              v-for="c in todayCourses"
              :key="c.schedule_id"
              :timestamp="`第 ${c.start_period}-${c.end_period} 节`"
              placement="top"
            >
              <strong>{{ c.course_name }}</strong>
              <div class="sub">{{ c.teacher_name }} · {{ c.classroom_code }}</div>
            </el-timeline-item>
          </el-timeline>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never">
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
      </el-col>
    </el-row>

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
.welcome .hello {
  display: flex;
  align-items: center;
  justify-content: space-between;

  h2 {
    margin: 0 0 6px;
    font-size: 20px;
  }

  p {
    margin: 0;
    color: #909399;
    font-size: 13px;
  }
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.sub {
  color: #909399;
  font-size: 12px;
  margin-top: 4px;
}

.ann-list {
  list-style: none;
  margin: 0;
  padding: 0;

  li {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 9px 0;
    border-bottom: 1px dashed #ebeef5;

    &:last-child {
      border-bottom: none;
    }
  }

  .title {
    flex: 1;
  }

  .date {
    color: #909399;
    font-size: 12px;
  }
}
</style>
