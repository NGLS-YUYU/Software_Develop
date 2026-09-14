<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { collegeApi, teacherApi } from '@/api'
import { useCrudTable } from '@/composables/useCrudTable'
import type { College, Teacher } from '@/types'

const colleges = ref<College[]>([])

const t = useCrudTable<Teacher>(teacherApi as never, {
  entityName: '教师',
  emptyForm: () => ({
    teacher_no: '', real_name: '', college_id: undefined, title: undefined,
    gender: 'UNKNOWN', hire_date: undefined, email: '', phone: '', password: '',
  }),
})

const TITLE: Record<string, string> = {
  ASSISTANT: '助教', LECTURER: '讲师',
  ASSOCIATE_PROFESSOR: '副教授', PROFESSOR: '教授',
}
const GENDER: Record<string, string> = { MALE: '男', FEMALE: '女', UNKNOWN: '-' }
const STATUS: Record<string, string> = { ACTIVE: '在职', LEAVE: '离岗', RETIRED: '退休' }

function payload() {
  const f = { ...t.form.value }
  if (!f.password) delete f.password
  if (t.dialogMode.value === 'edit') {
    delete f.teacher_no
    delete f.password
  }
  return f
}

onMounted(async () => {
  const c = await collegeApi.list({ page_size: 200 })
  colleges.value = c.items
  await t.load()
})
</script>

<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-select v-model="t.query.college_id" placeholder="全部学院" clearable
        style="width: 200px" @change="t.search">
        <el-option v-for="c in colleges" :key="c.id" :label="c.name" :value="c.id" />
      </el-select>
      <el-input v-model="t.query.keyword" placeholder="工号或姓名" style="width: 200px"
        clearable @keyup.enter="t.search" @clear="t.search" />
      <el-button type="primary" @click="t.search">查询</el-button>
      <div class="spacer" />
      <el-button type="primary" :icon="'Plus'" @click="t.openCreate">新增教师</el-button>
    </div>

    <el-table v-loading="t.loading.value" :data="t.rows.value" stripe>
      <el-table-column prop="teacher_no" label="工号" width="120" />
      <el-table-column prop="real_name" label="姓名" width="110" />
      <el-table-column label="性别" width="70" align="center">
        <template #default="{ row }">{{ GENDER[row.gender] }}</template>
      </el-table-column>
      <el-table-column prop="college_name" label="所属学院" min-width="180" />
      <el-table-column label="职称" width="100">
        <template #default="{ row }">{{ TITLE[row.title] ?? '-' }}</template>
      </el-table-column>
      <el-table-column prop="hire_date" label="入职日期" width="120" />
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === 'ACTIVE' ? 'success' : 'info'" size="small">
            {{ STATUS[row.status] }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="130" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click="t.openEdit(row)">编辑</el-button>
          <el-button size="small" link type="danger" @click="t.remove(row, row.real_name)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination v-model:current-page="t.query.page" :total="t.total.value"
        :page-size="t.query.page_size" layout="total, prev, pager, next" @current-change="t.load" />
    </div>

    <el-dialog v-model="t.dialogVisible.value"
      :title="t.dialogMode.value === 'create' ? '新增教师' : '编辑教师'" width="520px">
      <el-form label-width="100px">
        <el-form-item label="工号" required>
          <el-input v-model="t.form.value.teacher_no" :disabled="t.dialogMode.value === 'edit'"
            maxlength="30" />
        </el-form-item>
        <el-form-item label="姓名" required>
          <el-input v-model="t.form.value.real_name" maxlength="50" />
        </el-form-item>
        <el-form-item label="所属学院" required>
          <el-select v-model="t.form.value.college_id" style="width: 100%">
            <el-option v-for="c in colleges" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="职称">
          <el-select v-model="t.form.value.title" clearable style="width: 100%">
            <el-option label="助教" value="ASSISTANT" />
            <el-option label="讲师" value="LECTURER" />
            <el-option label="副教授" value="ASSOCIATE_PROFESSOR" />
            <el-option label="教授" value="PROFESSOR" />
          </el-select>
        </el-form-item>
        <el-form-item label="性别">
          <el-radio-group v-model="t.form.value.gender">
            <el-radio value="MALE">男</el-radio>
            <el-radio value="FEMALE">女</el-radio>
            <el-radio value="UNKNOWN">未填写</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="入职日期">
          <el-date-picker v-model="t.form.value.hire_date" type="date"
            value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item v-if="t.dialogMode.value === 'edit'" label="状态">
          <el-select v-model="t.form.value.status" style="width: 100%">
            <el-option label="在职" value="ACTIVE" />
            <el-option label="离岗" value="LEAVE" />
            <el-option label="退休" value="RETIRED" />
          </el-select>
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="t.form.value.email" maxlength="100" />
        </el-form-item>
        <el-form-item label="手机">
          <el-input v-model="t.form.value.phone" maxlength="20" />
        </el-form-item>
        <el-form-item v-if="t.dialogMode.value === 'create'" label="初始密码">
          <el-input v-model="t.form.value.password" placeholder="留空则默认为工号" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="t.dialogVisible.value = false">取消</el-button>
        <el-button type="primary" :loading="t.saving.value" @click="t.save(payload())">
          确定
        </el-button>
      </template>
    </el-dialog>
  </el-card>
</template>
