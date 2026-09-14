<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { gradeApi, studentApi } from '@/api'
import type { GradeSummary, Student } from '@/types'

const profile = ref<Student | null>(null)
const summary = ref<GradeSummary | null>(null)
const loading = ref(true)

const GENDER: Record<string, string> = { MALE: '男', FEMALE: '女', UNKNOWN: '未填写' }
const STATUS: Record<string, string> = {
  ENROLLED: '在读',
  SUSPENDED: '休学',
  GRADUATED: '毕业',
  WITHDRAWN: '退学',
}

onMounted(async () => {
  try {
    profile.value = await studentApi.me()
    summary.value = await gradeApi.mySummary()
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div v-loading="loading">
    <el-card shadow="never" class="page-card">
      <template #header><span>基本信息</span></template>
      <el-descriptions :column="3" border>
        <el-descriptions-item label="学号">{{ profile?.student_no }}</el-descriptions-item>
        <el-descriptions-item label="姓名">{{ profile?.real_name }}</el-descriptions-item>
        <el-descriptions-item label="性别">
          {{ GENDER[profile?.gender ?? ''] ?? '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="学院">{{ profile?.college_name }}</el-descriptions-item>
        <el-descriptions-item label="专业">{{ profile?.major_name }}</el-descriptions-item>
        <el-descriptions-item label="班级">{{ profile?.class_name }}</el-descriptions-item>
        <el-descriptions-item label="入学年份">
          {{ profile?.enrollment_year }}
        </el-descriptions-item>
        <el-descriptions-item label="出生日期">
          {{ profile?.birth_date ?? '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="学籍状态">
          <el-tag size="small">{{ STATUS[profile?.academic_status ?? ''] ?? '-' }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="邮箱">{{ profile?.email ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="手机">{{ profile?.phone ?? '-' }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card shadow="never" class="page-card">
      <template #header><span>学业概况</span></template>
      <div class="stat-grid">
        <el-statistic title="已修学分" :value="Number(summary?.total_credits ?? 0)" />
        <el-statistic title="平均绩点" :value="Number(summary?.gpa ?? 0)" :precision="2" />
        <el-statistic title="已修课程" :value="summary?.total_courses ?? 0" />
        <el-statistic title="不及格课程" :value="summary?.failed_courses ?? 0" />
      </div>
    </el-card>
  </div>
</template>
