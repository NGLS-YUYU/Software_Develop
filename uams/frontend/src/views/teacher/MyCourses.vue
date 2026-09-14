<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { teacherApi, teachingApi } from '@/api'
import { currentSemester, semesterOptions } from '@/composables/useSemester'
import type { TeachingClass } from '@/types'

const router = useRouter()
const semester = ref(currentSemester())
const classes = ref<TeachingClass[]>([])
const loading = ref(false)

const rosterVisible = ref(false)
const roster = ref<{ student_id: number; student_no: string; real_name: string; class_name?: string }[]>([])
const rosterTitle = ref('')

const DAY = ['', '周一', '周二', '周三', '周四', '周五', '周六', '周日']

function scheduleText(tc: TeachingClass) {
  if (!tc.schedules?.length) return '未排课'
  return tc.schedules
    .map((s) => `${DAY[s.day_of_week]} ${s.start_period}-${s.end_period}节 ${s.classroom_code ?? ''}`)
    .join('；')
}

async function load() {
  loading.value = true
  try {
    const me = await teacherApi.me()
    const res = await teachingApi.classes({
      teacher_id: me.id,
      semester: semester.value,
      page_size: 100,
    })
    classes.value = res.items
  } finally {
    loading.value = false
  }
}

async function showRoster(tc: TeachingClass) {
  roster.value = await teachingApi.students(tc.id)
  rosterTitle.value = `${tc.course_name} — 学生名单（${roster.value.length} 人）`
  rosterVisible.value = true
}

onMounted(load)
</script>

<template>
  <el-card shadow="never" v-loading="loading">
    <div class="toolbar">
      <el-select v-model="semester" style="width: 180px" @change="load">
        <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
      </el-select>
      <div class="spacer" />
      <el-tag type="info">共 {{ classes.length }} 个教学班</el-tag>
    </div>

    <el-empty v-if="!classes.length" description="本学期暂无授课安排" />
    <el-table v-else :data="classes" stripe>
      <el-table-column prop="course_code" label="课程代码" width="110" />
      <el-table-column prop="course_name" label="课程名称" min-width="150" />
      <el-table-column prop="code" label="教学班" min-width="160" />
      <el-table-column prop="credits" label="学分" width="70" align="center" />
      <el-table-column label="上课安排" min-width="230">
        <template #default="{ row }">
          <span class="sched">{{ scheduleText(row) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="人数" width="100" align="center">
        <template #default="{ row }">{{ row.selected_count }}/{{ row.capacity }}</template>
      </el-table-column>
      <el-table-column label="操作" width="170" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click="showRoster(row)">
            学生名单
          </el-button>
          <el-button
            size="small"
            link
            type="primary"
            @click="router.push(`/teacher/grades/${row.id}`)"
          >
            成绩录入
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="rosterVisible" :title="rosterTitle" width="560px">
      <el-table :data="roster" max-height="420" stripe size="small">
        <el-table-column type="index" label="#" width="55" align="center" />
        <el-table-column prop="student_no" label="学号" width="140" />
        <el-table-column prop="real_name" label="姓名" width="110" />
        <el-table-column prop="class_name" label="班级" min-width="150" />
      </el-table>
    </el-dialog>
  </el-card>
</template>

<style scoped>
.sched { font-size: 12px; color: #606266; }
</style>
