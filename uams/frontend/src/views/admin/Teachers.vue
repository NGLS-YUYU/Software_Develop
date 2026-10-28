<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { collegeApi, teacherApi } from '@/api'
import { useCrudTable } from '@/composables/useCrudTable'
import type { College, Teacher } from '@/types'
import { isValidEmail, normalizeEmailInput } from '@/utils/email'

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

function payload(): Record<string, unknown> | null {
  const f = { ...t.form.value }

  // FIX-001：空白邮箱统一为 null；非空邮箱先做一次前端格式提示。
  const email = normalizeEmailInput(f.email)
  if (email && !isValidEmail(email)) {
    ElMessage.warning('邮箱格式不正确')
    return null
  }
  f.email = email

  if (!f.password) delete f.password
  if (t.dialogMode.value === 'edit') {
    delete f.teacher_no
    delete f.password
  }
  return f
}

function save() {
  const body = payload()
  if (body) t.save(body)
}

onMounted(async () => {
  const c = await collegeApi.list({ page_size: 200 })
  colleges.value = c.items
  await t.load()
})
</script>

<template>
  <el-card shadow="never" class="page-card">
    <!-- 筛选区：条件在左，主操作在右 -->
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

    <!-- 桌面端：表格 -->
    <div v-loading="t.loading.value" class="table-wrap">
      <el-table :data="t.rows.value" stripe>
        <el-table-column prop="teacher_no" label="工号" width="140">
          <template #default="{ row }">
            <span class="cell-no">{{ row.teacher_no }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="real_name" label="姓名" width="120">
          <template #default="{ row }">
            <span class="cell-name">{{ row.real_name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="性别" width="70" align="center">
          <template #default="{ row }">
            <span class="cell-dim">{{ GENDER[row.gender] }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="college_name" label="所属学院" min-width="180">
          <template #default="{ row }">
            <span class="cell-college">{{ row.college_name || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="职称" width="110" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.title" size="small" effect="plain"
              :type="row.title === 'PROFESSOR' || row.title === 'ASSOCIATE_PROFESSOR'
                ? 'primary' : 'info'">
              {{ TITLE[row.title] }}
            </el-tag>
            <span v-else class="cell-dim">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="hire_date" label="入职日期" width="120">
          <template #default="{ row }">
            <span class="cell-dim">{{ row.hire_date || '—' }}</span>
          </template>
        </el-table-column>
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

        <template #empty>
          <el-empty
            description="没有符合条件的教师，试试调整筛选条件或新增教师档案"
            :image-size="80" />
        </template>
      </el-table>
    </div>

    <!-- 窄屏：卡片列表 -->
    <div v-loading="t.loading.value" class="teacher-cards">
      <el-empty
        v-if="!t.rows.value.length"
        description="没有符合条件的教师，试试调整筛选条件或新增教师档案"
        :image-size="80" />
      <article v-for="row in t.rows.value" :key="row.id" class="tcard">
        <header class="tcard__head">
          <div class="tcard__id">
            <span class="cell-name">{{ row.real_name }}</span>
            <span class="cell-no">{{ row.teacher_no }}</span>
          </div>
          <el-tag :type="row.status === 'ACTIVE' ? 'success' : 'info'" size="small">
            {{ STATUS[row.status] }}
          </el-tag>
        </header>

        <dl class="tcard__dl">
          <div>
            <dt>职称</dt>
            <dd>
              <el-tag v-if="row.title" size="small" effect="plain"
                :type="row.title === 'PROFESSOR' || row.title === 'ASSOCIATE_PROFESSOR'
                  ? 'primary' : 'info'">
                {{ TITLE[row.title] }}
              </el-tag>
              <span v-else class="cell-dim">—</span>
            </dd>
          </div>
          <div>
            <dt>性别</dt>
            <dd class="cell-dim">{{ GENDER[row.gender] }}</dd>
          </div>
          <div class="tcard__dl-wide">
            <dt>所属学院</dt>
            <dd class="cell-college">{{ row.college_name || '—' }}</dd>
          </div>
          <div class="tcard__dl-wide">
            <dt>入职日期</dt>
            <dd class="cell-dim">{{ row.hire_date || '—' }}</dd>
          </div>
        </dl>

        <footer class="tcard__foot">
          <el-button size="small" type="primary" plain @click="t.openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" plain @click="t.remove(row, row.real_name)">
            删除
          </el-button>
        </footer>
      </article>
    </div>

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
        <el-form-item label="性别" for="teacher-gender">
          <el-radio-group v-model="t.form.value.gender" v-control-id="'teacher-gender'">
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
        <el-button type="primary" :loading="t.saving.value" @click="save">
          确定
        </el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<style scoped lang="scss">
/* ------------------------------------------------------------- 单元格层级 */
/* 工号：淡紫药丸，作为次要但清晰的标识 */
.cell-no {
  display: inline-block;
  padding: 1px 8px;
  border-radius: var(--uams-radius-xs);
  background: var(--uams-primary-soft);
  color: var(--uams-primary-dark);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.2px;
  font-variant-numeric: tabular-nums;
}

/* 姓名：主字段，加重强调 */
.cell-name {
  font-weight: 600;
  color: var(--uams-text);
}

/* 学院等次要文字：弱化到次要色 */
.cell-college {
  color: var(--uams-text-2);
}

/* 日期/性别等弱信息 */
.cell-dim {
  color: var(--uams-text-3);
  font-variant-numeric: tabular-nums;
}

/* --------------------------------------------------------- 移动端卡片布局 */
.teacher-cards {
  display: none;
  flex-direction: column;
  gap: 12px;
}

.tcard {
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface);
  overflow: hidden;

  &__head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
    padding: 12px 14px;
    background: var(--uams-surface-sunken);
    border-bottom: 1px solid var(--uams-border);
  }

  &__id {
    display: flex;
    flex-direction: column;
    gap: 5px;
    min-width: 0;
  }

  /* 主字段成对：职称 / 性别；学院与日期各占整行 */
  &__dl {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    margin: 0;
    padding: 14px;

    > div {
      display: flex;
      flex-direction: column;
      gap: 3px;
      min-width: 0;
      padding: 8px 10px;
      border-radius: var(--uams-radius-xs);
      background: var(--uams-surface-sunken);
      border: 1px solid var(--uams-border);
    }

    dt {
      font-size: 12px;
      color: var(--uams-text-3);
    }

    dd {
      margin: 0;
      font-size: 14px;
      font-weight: 500;
      color: var(--uams-text);
    }
  }

  &__dl-wide {
    grid-column: 1 / -1;
  }

  &__foot {
    display: flex;
    gap: 10px;
    padding: 0 14px 14px;

    .el-button {
      flex: 1;
      margin-left: 0;
    }
  }
}

/* ---------------------------------------------------------------- 响应式 */
@media (max-width: 768px) {
  /* 宽表格换成卡片列表，避免横向溢出且操作可达 */
  .table-wrap {
    display: none;
  }

  .teacher-cards {
    display: flex;
  }
}
</style>
