<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { announcementApi, gradeApi, scheduleApi, teacherApi, teachingApi } from '@/api'
import { currentSemester } from '@/composables/useSemester'
import type { Announcement, ScheduleItem, Teacher, TeachingClass } from '@/types'

const router = useRouter()
const semester = currentSemester()

const profile = ref<Teacher | null>(null)
const classes = ref<TeachingClass[]>([])
const schedule = ref<ScheduleItem[]>([])
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
  <div v-loading="loading">
    <el-card class="page-card" shadow="never">
      <div class="hello">
        <div>
          <h2>你好，{{ profile?.real_name || '老师' }}</h2>
          <p>{{ profile?.college_name }} · 工号 {{ profile?.teacher_no }}</p>
        </div>
        <el-tag size="large">{{ semester }} 学期</el-tag>
      </div>
    </el-card>

    <div class="stat-grid page-card">
      <el-card shadow="never"><el-statistic title="授课教学班" :value="classes.length" /></el-card>
      <el-card shadow="never"><el-statistic title="授课学生数" :value="totalStudents" /></el-card>
      <el-card shadow="never"><el-statistic title="本周课程" :value="schedule.length" /></el-card>
      <el-card shadow="never"><el-statistic title="待录入成绩" :value="pendingCount" /></el-card>
    </div>

    <el-row :gutter="16" class="page-card">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <span>今日课程</span>
              <el-link type="primary" :underline="false" @click="router.push('/teacher/schedule')">
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
              <div class="sub">{{ c.classroom_code }} · {{ c.teaching_class_code }}</div>
            </el-timeline-item>
          </el-timeline>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <span>我的教学班</span>
              <el-link type="primary" :underline="false" @click="router.push('/teacher/courses')">
                全部
              </el-link>
            </div>
          </template>
          <el-empty v-if="!classes.length" description="本学期暂无授课" :image-size="70" />
          <el-table v-else :data="classes.slice(0, 5)" size="small">
            <el-table-column prop="course_name" label="课程" min-width="130" />
            <el-table-column label="人数" width="90" align="center">
              <template #default="{ row }">{{ row.selected_count }}/{{ row.capacity }}</template>
            </el-table-column>
            <el-table-column label="操作" width="90" align="center">
              <template #default="{ row }">
                <el-button
                  size="small"
                  type="primary"
                  link
                  @click="router.push(`/teacher/grades/${row.id}`)"
                >
                  录成绩
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="page-card" shadow="never">
      <template #header><span>最新通知</span></template>
      <el-empty v-if="!announcements.length" description="暂无通知" :image-size="70" />
      <ul v-else class="ann-list">
        <li v-for="a in announcements" :key="a.id">
          <span class="title">{{ a.title }}</span>
          <span class="date">{{ a.published_at?.slice(0, 10) }}</span>
        </li>
      </ul>
    </el-card>
  </div>
</template>

<style scoped lang="scss">
.hello {
  display: flex;
  align-items: center;
  justify-content: space-between;
  h2 { margin: 0 0 6px; font-size: 20px; }
  p { margin: 0; color: #909399; font-size: 13px; }
}
.card-head { display: flex; justify-content: space-between; align-items: center; }
.sub { color: #909399; font-size: 12px; margin-top: 4px; }
.ann-list {
  list-style: none; margin: 0; padding: 0;
  li {
    display: flex; gap: 8px; padding: 9px 0; border-bottom: 1px dashed #ebeef5;
    &:last-child { border-bottom: none; }
  }
  .title { flex: 1; }
  .date { color: #909399; font-size: 12px; }
}
</style>
