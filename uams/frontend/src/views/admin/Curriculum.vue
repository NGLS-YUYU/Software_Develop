<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { courseApi, curriculumApi, majorApi } from '@/api'
import { useCrudTable } from '@/composables/useCrudTable'
import type { Course, CurriculumCourse, CurriculumPlan, Major } from '@/types'

const majors = ref<Major[]>([])
const allCourses = ref<Course[]>([])

const t = useCrudTable<CurriculumPlan>(curriculumApi, {
  entityName: '培养方案',
  emptyForm: () => ({
    code: '', name: '', major_id: undefined,
    grade_year: new Date().getFullYear(),
    total_credits_required: 160, required_credits: 120, elective_credits: 40,
    status: 'DRAFT',
  }),
})

const STATUS: Record<string, string> = { DRAFT: '草稿', PUBLISHED: '已发布', ARCHIVED: '已归档' }
const STATUS_TYPE: Record<string, string> = { DRAFT: 'info', PUBLISHED: 'success', ARCHIVED: 'warning' }

const detailVisible = ref(false)
const plan = ref<CurriculumPlan | null>(null)
const planCourses = ref<CurriculumCourse[]>([])
const addCourseId = ref<number | undefined>(undefined)
const addSemester = ref(1)
const addRequired = ref(true)

async function openDetail(row: CurriculumPlan) {
  plan.value = row
  planCourses.value = await curriculumApi.courses(row.id)
  detailVisible.value = true
}

async function addCourse() {
  if (!plan.value || !addCourseId.value) {
    ElMessage.warning('请选择课程')
    return
  }
  await curriculumApi.addCourse(plan.value.id, addCourseId.value, addSemester.value, addRequired.value)
  ElMessage.success('已添加')
  planCourses.value = await curriculumApi.courses(plan.value.id)
  addCourseId.value = undefined
}

async function removeCourse(row: CurriculumCourse) {
  if (!plan.value) return
  await curriculumApi.removeCourse(plan.value.id, row.id)
  planCourses.value = await curriculumApi.courses(plan.value.id)
}

function totalCredits() {
  return planCourses.value.reduce((s, c) => s + Number(c.credits ?? 0), 0)
}

onMounted(async () => {
  const [m, c] = await Promise.allSettled([
    majorApi.list({ page_size: 200 }),
    courseApi.list({ page_size: 200 }),
  ])
  if (m.status === 'fulfilled') majors.value = m.value.items
  if (c.status === 'fulfilled') allCourses.value = c.value.items
  await t.load()
})
</script>

<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-select v-model="t.query.major_id" placeholder="全部专业" clearable
        style="width: 200px" @change="t.search">
        <el-option v-for="m in majors" :key="m.id" :label="m.name" :value="m.id" />
      </el-select>
      <el-input v-model="t.query.keyword" placeholder="方案代码或名称" style="width: 200px"
        clearable @keyup.enter="t.search" @clear="t.search" />
      <el-button type="primary" @click="t.search">查询</el-button>
      <div class="spacer" />
      <el-button type="primary" :icon="'Plus'" @click="t.openCreate">新增方案</el-button>
    </div>

    <el-table v-loading="t.loading.value" :data="t.rows.value" stripe>
      <el-table-column prop="code" label="方案代码" width="130" />
      <el-table-column prop="name" label="方案名称" min-width="200" />
      <el-table-column prop="major_name" label="适用专业" min-width="160" />
      <el-table-column prop="grade_year" label="年级" width="90" align="center" />
      <el-table-column label="总学分" width="90" align="center">
        <template #default="{ row }">{{ row.total_credits_required }}</template>
      </el-table-column>
      <el-table-column label="必修/选修" width="120" align="center">
        <template #default="{ row }">
          {{ row.required_credits }} / {{ row.elective_credits }}
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="STATUS_TYPE[row.status] as any" size="small">
            {{ STATUS[row.status] }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click="openDetail(row)">课程</el-button>
          <el-button size="small" link type="primary" @click="t.openEdit(row)">编辑</el-button>
          <el-button size="small" link type="danger" @click="t.remove(row, row.name)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination v-model:current-page="t.query.page" :total="t.total.value"
        :page-size="t.query.page_size" layout="total, prev, pager, next" @current-change="t.load" />
    </div>

    <el-dialog v-model="t.dialogVisible.value"
      :title="t.dialogMode.value === 'create' ? '新增培养方案' : '编辑培养方案'" width="520px">
      <el-form label-width="110px">
        <el-form-item label="方案代码" required>
          <el-input v-model="t.form.value.code" :disabled="t.dialogMode.value === 'edit'"
            maxlength="30" />
        </el-form-item>
        <el-form-item label="方案名称" required>
          <el-input v-model="t.form.value.name" maxlength="100" />
        </el-form-item>
        <el-form-item label="适用专业" required>
          <el-select v-model="t.form.value.major_id" :disabled="t.dialogMode.value === 'edit'"
            style="width: 100%">
            <el-option v-for="m in majors" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="适用年级" required>
          <el-input-number v-model="t.form.value.grade_year" :min="1900" :max="2200"
            :disabled="t.dialogMode.value === 'edit'" />
        </el-form-item>
        <el-form-item label="毕业总学分" required>
          <el-input-number v-model="t.form.value.total_credits_required" :min="1" :max="300"
            :precision="1" />
        </el-form-item>
        <el-form-item label="必修学分" required>
          <el-input-number v-model="t.form.value.required_credits" :min="0" :max="300"
            :precision="1" />
        </el-form-item>
        <el-form-item label="选修学分" required>
          <el-input-number v-model="t.form.value.elective_credits" :min="0" :max="300"
            :precision="1" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="t.form.value.status" style="width: 100%">
            <el-option label="草稿" value="DRAFT" />
            <el-option label="已发布" value="PUBLISHED" />
            <el-option label="已归档" value="ARCHIVED" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="t.dialogVisible.value = false">取消</el-button>
        <el-button type="primary" :loading="t.saving.value" @click="t.save()">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailVisible" :title="`方案课程 — ${plan?.name}`" width="760px">
      <div class="toolbar">
        <el-select v-model="addCourseId" placeholder="选择课程" filterable style="width: 260px">
          <el-option v-for="c in allCourses" :key="c.id"
            :label="`${c.code} ${c.name} (${c.credits}学分)`" :value="c.id" />
        </el-select>
        <el-select v-model="addSemester" style="width: 130px">
          <el-option v-for="s in 8" :key="s" :label="`第 ${s} 学期`" :value="s" />
        </el-select>
        <el-checkbox v-model="addRequired">必修</el-checkbox>
        <el-button type="primary" @click="addCourse">添加</el-button>
        <div class="spacer" />
        <el-tag type="info">共 {{ planCourses.length }} 门 / {{ totalCredits() }} 学分</el-tag>
      </div>
      <el-table :data="planCourses" max-height="420" size="small" stripe>
        <el-table-column prop="course_code" label="课程代码" width="110" />
        <el-table-column prop="course_name" label="课程名称" min-width="170" />
        <el-table-column prop="credits" label="学分" width="80" align="center" />
        <el-table-column label="建议学期" width="100" align="center">
          <template #default="{ row }">第 {{ row.suggested_semester }} 学期</template>
        </el-table-column>
        <el-table-column label="性质" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_required ? 'danger' : 'info'" size="small">
              {{ row.is_required ? '必修' : '选修' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="danger" @click="removeCourse(row)">移除</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="尚未添加课程" :image-size="60" /></template>
      </el-table>
    </el-dialog>
  </el-card>
</template>
