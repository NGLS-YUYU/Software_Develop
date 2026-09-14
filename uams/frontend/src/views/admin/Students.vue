<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { classApi, collegeApi, majorApi, studentApi } from '@/api'
import { useCrudTable } from '@/composables/useCrudTable'
import type { ClassInfo, College, Major, Student } from '@/types'

const colleges = ref<College[]>([])
const majors = ref<Major[]>([])
const classes = ref<ClassInfo[]>([])

const t = useCrudTable<Student>(studentApi as never, {
  entityName: '学生',
  emptyForm: () => ({
    student_no: '',
    real_name: '',
    class_id: undefined,
    gender: 'UNKNOWN',
    birth_date: undefined,
    enrollment_year: new Date().getFullYear(),
    email: '',
    phone: '',
    password: '',
  }),
})

const GENDER: Record<string, string> = { MALE: '男', FEMALE: '女', UNKNOWN: '-' }
const STATUS: Record<string, string> = {
  ENROLLED: '在读', SUSPENDED: '休学', GRADUATED: '毕业', WITHDRAWN: '退学',
}
const STATUS_TYPE: Record<string, string> = {
  ENROLLED: 'success', SUSPENDED: 'warning', GRADUATED: 'info', WITHDRAWN: 'danger',
}

/** 新增时不传空密码，让后端用「默认密码=学号」的规则。 */
function payload() {
  const f = { ...t.form.value }
  if (!f.password) delete f.password
  if (t.dialogMode.value === 'edit') {
    delete f.student_no
    delete f.password
  }
  return f
}

onMounted(async () => {
  const [c, m, k] = await Promise.allSettled([
    collegeApi.list({ page_size: 200 }),
    majorApi.list({ page_size: 200 }),
    classApi.list({ page_size: 200 }),
  ])
  if (c.status === 'fulfilled') colleges.value = c.value.items
  if (m.status === 'fulfilled') majors.value = m.value.items
  if (k.status === 'fulfilled') classes.value = k.value.items
  await t.load()
})
</script>

<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-select v-model="t.query.college_id" placeholder="全部学院" clearable
        style="width: 180px" @change="t.search">
        <el-option v-for="c in colleges" :key="c.id" :label="c.name" :value="c.id" />
      </el-select>
      <el-select v-model="t.query.major_id" placeholder="全部专业" clearable
        style="width: 180px" @change="t.search">
        <el-option v-for="m in majors" :key="m.id" :label="m.name" :value="m.id" />
      </el-select>
      <el-select v-model="t.query.class_id" placeholder="全部班级" clearable
        style="width: 180px" @change="t.search">
        <el-option v-for="k in classes" :key="k.id" :label="k.name" :value="k.id" />
      </el-select>
      <el-input v-model="t.query.keyword" placeholder="学号或姓名" style="width: 180px"
        clearable @keyup.enter="t.search" @clear="t.search" />
      <el-button type="primary" @click="t.search">查询</el-button>
      <div class="spacer" />
      <el-button type="primary" :icon="'Plus'" @click="t.openCreate">新增学生</el-button>
    </div>

    <el-table v-loading="t.loading.value" :data="t.rows.value" stripe>
      <el-table-column prop="student_no" label="学号" width="130" />
      <el-table-column prop="real_name" label="姓名" width="100" />
      <el-table-column label="性别" width="70" align="center">
        <template #default="{ row }">{{ GENDER[row.gender] }}</template>
      </el-table-column>
      <el-table-column prop="class_name" label="班级" min-width="150" />
      <el-table-column prop="major_name" label="专业" min-width="150" />
      <el-table-column prop="enrollment_year" label="入学年份" width="100" align="center" />
      <el-table-column label="学籍" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="STATUS_TYPE[row.academic_status] as any" size="small">
            {{ STATUS[row.academic_status] }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="学分" width="80" align="center">
        <template #default="{ row }">{{ row.total_credits }}</template>
      </el-table-column>
      <el-table-column label="绩点" width="80" align="center">
        <template #default="{ row }">{{ row.gpa ?? '-' }}</template>
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
        :page-size="t.query.page_size" :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next" @current-change="t.load" @size-change="t.load" />
    </div>

    <el-dialog v-model="t.dialogVisible.value"
      :title="t.dialogMode.value === 'create' ? '新增学生' : '编辑学生'" width="520px">
      <el-form label-width="100px">
        <el-form-item label="学号" required>
          <el-input v-model="t.form.value.student_no" :disabled="t.dialogMode.value === 'edit'"
            maxlength="30" />
        </el-form-item>
        <el-form-item label="姓名" required>
          <el-input v-model="t.form.value.real_name" maxlength="50" />
        </el-form-item>
        <el-form-item label="班级" required>
          <el-select v-model="t.form.value.class_id" style="width: 100%">
            <el-option v-for="k in classes" :key="k.id" :label="k.name" :value="k.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="性别">
          <el-radio-group v-model="t.form.value.gender">
            <el-radio value="MALE">男</el-radio>
            <el-radio value="FEMALE">女</el-radio>
            <el-radio value="UNKNOWN">未填写</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="出生日期">
          <el-date-picker v-model="t.form.value.birth_date" type="date"
            value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item v-if="t.dialogMode.value === 'create'" label="入学年份" required>
          <el-input-number v-model="t.form.value.enrollment_year" :min="1900" :max="2200" />
        </el-form-item>
        <el-form-item v-if="t.dialogMode.value === 'edit'" label="学籍状态">
          <el-select v-model="t.form.value.academic_status" style="width: 100%">
            <el-option label="在读" value="ENROLLED" />
            <el-option label="休学" value="SUSPENDED" />
            <el-option label="毕业" value="GRADUATED" />
            <el-option label="退学" value="WITHDRAWN" />
          </el-select>
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="t.form.value.email" maxlength="100" />
        </el-form-item>
        <el-form-item label="手机">
          <el-input v-model="t.form.value.phone" maxlength="20" />
        </el-form-item>
        <el-form-item v-if="t.dialogMode.value === 'create'" label="初始密码">
          <el-input v-model="t.form.value.password" placeholder="留空则默认为学号" />
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
