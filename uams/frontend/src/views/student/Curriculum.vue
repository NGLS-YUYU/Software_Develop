<script setup lang="ts">
/** 学生查看本人专业培养方案（F-20）。 */
import { computed, onMounted, ref } from 'vue'

import { curriculumApi, studentApi } from '@/api'
import type { CurriculumCourse, CurriculumPlan, Student } from '@/types'

const loading = ref(false)
const profile = ref<Student | null>(null)
const plans = ref<CurriculumPlan[]>([])
const selectedPlan = ref<CurriculumPlan | null>(null)
const courses = ref<CurriculumCourse[]>([])

const grouped = computed(() => {
  const map = new Map<number, CurriculumCourse[]>()
  for (const c of courses.value) {
    const arr = map.get(c.suggested_semester) ?? []
    arr.push(c)
    map.set(c.suggested_semester, arr)
  }
  return [...map.entries()].sort((a, b) => a[0] - b[0])
})

async function loadCourses(plan: CurriculumPlan) {
  selectedPlan.value = plan
  courses.value = await curriculumApi.courses(plan.id)
}

async function load() {
  loading.value = true
  try {
    profile.value = await studentApi.me()
    const res = await curriculumApi.list({
      major_id: profile.value.major_id,
      grade_year: profile.value.enrollment_year,
      page_size: 20,
    })
    plans.value = res.items
    if (plans.value.length) await loadCourses(plans.value[0])
    else {
      const all = await curriculumApi.list({ page_size: 50 })
      plans.value = all.items.filter((p) => p.major_id === profile.value?.major_id)
      if (plans.value.length) await loadCourses(plans.value[0])
    }
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="curriculum">
    <el-card shadow="never" class="page-card">
      <div class="toolbar">
        <span class="muted">
          {{ profile?.major_name || '本人专业' }} · {{ profile?.enrollment_year || '—' }} 级培养方案
        </span>
        <div class="spacer" />
        <el-select
          v-if="plans.length > 1"
          :model-value="selectedPlan?.id"
          style="width: 260px"
          @change="(id: number) => { const p = plans.find(x => x.id === id); if (p) loadCourses(p) }"
        >
          <el-option v-for="p in plans" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
      </div>

      <el-empty v-if="!plans.length" description="暂未发布本人专业的培养方案" :image-size="70" />

      <template v-else>
        <el-descriptions v-if="selectedPlan" :column="3" border size="small" class="meta">
          <el-descriptions-item label="方案名称">{{ selectedPlan.name }}</el-descriptions-item>
          <el-descriptions-item label="适用年级">{{ selectedPlan.grade_year }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ selectedPlan.status }}</el-descriptions-item>
          <el-descriptions-item label="毕业总学分">
            {{ selectedPlan.total_credits_required }}
          </el-descriptions-item>
          <el-descriptions-item label="必修学分">
            {{ selectedPlan.required_credits }}
          </el-descriptions-item>
          <el-descriptions-item label="选修学分">
            {{ selectedPlan.elective_credits }}
          </el-descriptions-item>
        </el-descriptions>

        <div v-for="[sem, rows] in grouped" :key="sem" class="sem-block">
          <div class="sem-head">
            <span class="section-title">建议第 {{ sem }} 学期</span>
            <el-tag size="small" type="info" effect="plain">{{ rows.length }} 门</el-tag>
          </div>
          <el-table :data="rows" size="small" stripe>
            <el-table-column prop="course_code" label="课程代码" width="120" />
            <el-table-column prop="course_name" label="课程名称" min-width="180" />
            <el-table-column prop="credits" label="学分" width="80" align="center" />
            <el-table-column label="性质" width="90" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="row.is_required ? 'danger' : 'info'" effect="plain">
                  {{ row.is_required ? '必修' : '选修' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <el-empty v-if="!courses.length" description="该方案暂无课程" :image-size="60" />
      </template>
    </el-card>
  </div>
</template>

<style scoped>
.curriculum {
  display: block;
}
.meta {
  margin-bottom: var(--uams-gap);
}
.sem-block + .sem-block {
  margin-top: 16px;
}
.sem-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
</style>
