<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { collegeApi, courseApi } from '@/api'
import { useCrudTable } from '@/composables/useCrudTable'
import type { College, Course, Prerequisite } from '@/types'

const colleges = ref<College[]>([])
const allCourses = ref<Course[]>([])

const t = useCrudTable<Course>(courseApi, {
  entityName: '课程',
  emptyForm: () => ({
    code: '', name: '', college_id: undefined, course_type: 'REQUIRED',
    credits: 3, total_hours: 48, theory_hours: 48, practice_hours: 0,
    exam_type: 'EXAM', regular_weight: 0.4, final_weight: 0.6,
    description: '', status: 'ACTIVE',
  }),
})

const TYPE: Record<string, string> = {
  REQUIRED: '专业必修', ELECTIVE: '专业选修', PUBLIC_REQUIRED: '公共必修',
  PUBLIC_ELECTIVE: '公共选修', PRACTICE: '实践',
}

// 先修课程管理
const preVisible = ref(false)
const preList = ref<Prerequisite[]>([])
const preCourse = ref<Course | null>(null)
const preTarget = ref<number | undefined>(undefined)
const preScore = ref(60)

async function openPrereq(row: Course) {
  preCourse.value = row
  preList.value = await courseApi.prerequisites(row.id)
  preTarget.value = undefined
  preVisible.value = true
}

async function addPrereq() {
  if (!preCourse.value || !preTarget.value) {
    ElMessage.warning('请选择先修课程')
    return
  }
  // 环路（A→B→A）由后端图检测拦截，这里只发请求
  await courseApi.addPrerequisite(preCourse.value.id, preTarget.value, preScore.value)
  ElMessage.success('已添加先修课程')
  preList.value = await courseApi.prerequisites(preCourse.value.id)
  preTarget.value = undefined
}

async function delPrereq(row: Prerequisite) {
  if (!preCourse.value) return
  await courseApi.removePrerequisite(preCourse.value.id, row.id)
  preList.value = await courseApi.prerequisites(preCourse.value.id)
}

/** 权重联动：两者之和必须为 1（后端有 CHECK 约束）。 */
function onRegularChange(v: number) {
  t.form.value.final_weight = Number((1 - v).toFixed(2))
}

async function loadCourses() {
  const res = await courseApi.list({ page_size: 200 })
  allCourses.value = res.items
}

onMounted(async () => {
  const c = await collegeApi.list({ page_size: 200 })
  colleges.value = c.items
  await t.load()
  await loadCourses()
})
</script>

<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-select v-model="t.query.college_id" placeholder="全部学院" clearable
        style="width: 180px" @change="t.search">
        <el-option v-for="c in colleges" :key="c.id" :label="c.name" :value="c.id" />
      </el-select>
      <el-select v-model="t.query.course_type" placeholder="全部类型" clearable
        style="width: 150px" @change="t.search">
        <el-option v-for="(v, k) in TYPE" :key="k" :label="v" :value="k" />
      </el-select>
      <el-input v-model="t.query.keyword" placeholder="课程代码或名称" style="width: 200px"
        clearable @keyup.enter="t.search" @clear="t.search" />
      <el-button type="primary" @click="t.search">查询</el-button>
      <div class="spacer" />
      <el-button type="primary" :icon="'Plus'" @click="t.openCreate">新增课程</el-button>
    </div>

    <el-table v-loading="t.loading.value" :data="t.rows.value" stripe>
      <el-table-column prop="code" label="课程代码" width="110" />
      <el-table-column prop="name" label="课程名称" min-width="160" />
      <el-table-column prop="college_name" label="开课学院" min-width="150" />
      <el-table-column label="类型" width="110">
        <template #default="{ row }">{{ TYPE[row.course_type] }}</template>
      </el-table-column>
      <el-table-column prop="credits" label="学分" width="70" align="center" />
      <el-table-column prop="total_hours" label="学时" width="70" align="center" />
      <el-table-column label="考核" width="80" align="center">
        <template #default="{ row }">{{ row.exam_type === 'EXAM' ? '考试' : '考查' }}</template>
      </el-table-column>
      <el-table-column label="成绩权重" width="110" align="center">
        <template #default="{ row }">
          平时 {{ Math.round(row.regular_weight * 100) }}%
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click="openPrereq(row)">先修</el-button>
          <el-button size="small" link type="primary" @click="t.openEdit(row)">编辑</el-button>
          <el-button size="small" link type="danger" @click="t.remove(row, row.name)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination v-model:current-page="t.query.page" :total="t.total.value"
        :page-size="t.query.page_size" layout="total, prev, pager, next" @current-change="t.load" />
    </div>

    <!-- 课程表单 -->
    <el-dialog v-model="t.dialogVisible.value"
      :title="t.dialogMode.value === 'create' ? '新增课程' : '编辑课程'" width="560px">
      <el-form label-width="110px">
        <el-form-item label="课程代码" required>
          <el-input v-model="t.form.value.code" maxlength="30" />
        </el-form-item>
        <el-form-item label="课程名称" required>
          <el-input v-model="t.form.value.name" maxlength="100" />
        </el-form-item>
        <el-form-item label="开课学院" required>
          <el-select v-model="t.form.value.college_id" style="width: 100%">
            <el-option v-for="c in colleges" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="课程类型" required>
          <el-select v-model="t.form.value.course_type" style="width: 100%">
            <el-option v-for="(v, k) in TYPE" :key="k" :label="v" :value="k" />
          </el-select>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="学分" required>
              <el-input-number v-model="t.form.value.credits" :min="0.5" :max="30"
                :step="0.5" :precision="1" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="总学时" required>
              <el-input-number v-model="t.form.value.total_hours" :min="0" :max="500"
                style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="理论学时">
              <el-input-number v-model="t.form.value.theory_hours" :min="0" :max="500"
                style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="实践学时">
              <el-input-number v-model="t.form.value.practice_hours" :min="0" :max="500"
                style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="考核方式">
          <el-radio-group v-model="t.form.value.exam_type">
            <el-radio value="EXAM">考试</el-radio>
            <el-radio value="CHECK">考查</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="平时成绩权重">
          <el-slider v-model="t.form.value.regular_weight" :min="0" :max="1" :step="0.05"
            :format-tooltip="(v: number) => `${Math.round(v * 100)}%`"
            @input="onRegularChange" />
          <div class="weight-hint">
            平时 {{ Math.round(Number(t.form.value.regular_weight) * 100) }}% +
            期末 {{ Math.round(Number(t.form.value.final_weight) * 100) }}% = 100%
          </div>
        </el-form-item>
        <el-form-item label="课程简介">
          <el-input v-model="t.form.value.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="t.dialogVisible.value = false">取消</el-button>
        <el-button type="primary" :loading="t.saving.value" @click="t.save()">确定</el-button>
      </template>
    </el-dialog>

    <!-- 先修课程 -->
    <el-dialog v-model="preVisible" :title="`先修课程 — ${preCourse?.name}`" width="600px">
      <div class="toolbar">
        <el-select v-model="preTarget" placeholder="选择先修课程" filterable style="width: 260px">
          <el-option v-for="c in allCourses.filter(x => x.id !== preCourse?.id)"
            :key="c.id" :label="`${c.code} ${c.name}`" :value="c.id" />
        </el-select>
        <el-input-number v-model="preScore" :min="0" :max="100" :step="5"
          style="width: 130px" />
        <el-button type="primary" @click="addPrereq">添加</el-button>
      </div>
      <el-table :data="preList" size="small">
        <el-table-column prop="prerequisite_code" label="课程代码" width="120" />
        <el-table-column prop="prerequisite_name" label="课程名称" min-width="180" />
        <el-table-column prop="min_score" label="最低成绩" width="100" align="center" />
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="danger" @click="delPrereq(row)">移除</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="暂无先修课程" :image-size="60" /></template>
      </el-table>
      <el-alert type="info" :closable="false" show-icon style="margin-top: 12px"
        title="系统会自动检测先修关系环路（如 A→B→A），形成环路时将拒绝添加" />
    </el-dialog>
  </el-card>
</template>

<style scoped>
.weight-hint { font-size: 12px; color: #909399; margin-top: 4px; }
</style>
