<script setup lang="ts">
/** 组织机构：学院 / 专业 / 班级 / 教室，四个 Tab 共用一套 CRUD 模式。 */
import { onMounted, ref, watch } from 'vue'

import { classApi, classroomApi, collegeApi, majorApi, teacherApi } from '@/api'
import { useCrudTable } from '@/composables/useCrudTable'
import type { ClassInfo, Classroom, College, Major, Teacher } from '@/types'

const tab = ref('college')

// 下拉选项
const colleges = ref<College[]>([])
const majors = ref<Major[]>([])
const teachers = ref<Teacher[]>([])

const college = useCrudTable<College>(collegeApi, {
  entityName: '学院',
  emptyForm: () => ({ code: '', name: '', description: '', status: 'ACTIVE' }),
})
const major = useCrudTable<Major>(majorApi, {
  entityName: '专业',
  emptyForm: () => ({
    code: '',
    name: '',
    college_id: undefined,
    degree_type: 'BACHELOR',
    duration_years: 4,
    status: 'ACTIVE',
  }),
})
const klass = useCrudTable<ClassInfo>(classApi, {
  entityName: '班级',
  emptyForm: () => ({
    code: '',
    name: '',
    major_id: undefined,
    grade_year: new Date().getFullYear(),
    counselor_id: undefined,
    status: 'ACTIVE',
  }),
})
const room = useCrudTable<Classroom>(classroomApi, {
  entityName: '教室',
  emptyForm: () => ({
    code: '',
    building: '',
    capacity: 60,
    room_type: 'NORMAL',
    status: 'ACTIVE',
  }),
})

const DEGREE: Record<string, string> = { BACHELOR: '本科', MASTER: '硕士', DOCTOR: '博士' }
const ROOM_TYPE: Record<string, string> = {
  NORMAL: '普通教室',
  LAB: '实验室',
  MULTIMEDIA: '多媒体',
}
const ROOM_STATUS: Record<string, string> = {
  ACTIVE: '可用',
  MAINTENANCE: '维护中',
  DISABLED: '停用',
}

async function loadOptions() {
  const [c, m, t] = await Promise.allSettled([
    collegeApi.list({ page_size: 200 }),
    majorApi.list({ page_size: 200 }),
    teacherApi.list({ page_size: 200 }),
  ])
  if (c.status === 'fulfilled') colleges.value = c.value.items
  if (m.status === 'fulfilled') majors.value = m.value.items
  if (t.status === 'fulfilled') teachers.value = t.value.items
}

watch(tab, (v) => {
  if (v === 'college') college.load()
  if (v === 'major') major.load()
  if (v === 'class') klass.load()
  if (v === 'classroom') room.load()
})

onMounted(async () => {
  await loadOptions()
  await college.load()
})
</script>

<template>
  <el-card shadow="never">
    <el-tabs v-model="tab">
      <!-- 学院 -->
      <el-tab-pane label="学院" name="college">
        <div class="toolbar">
          <el-input
            v-model="college.query.keyword"
            placeholder="搜索代码或名称"
            style="width: 220px"
            clearable
            @keyup.enter="college.search"
            @clear="college.search"
          />
          <el-button type="primary" @click="college.search">查询</el-button>
          <div class="spacer" />
          <el-button type="primary" :icon="'Plus'" @click="college.openCreate">
            新增学院
          </el-button>
        </div>
        <el-table v-loading="college.loading.value" :data="college.rows.value" stripe>
          <el-table-column prop="code" label="代码" width="110" />
          <el-table-column prop="name" label="名称" min-width="180" />
          <el-table-column prop="description" label="说明" min-width="200" />
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="row.status === 'ACTIVE' ? 'success' : 'info'" size="small">
                {{ row.status === 'ACTIVE' ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="130" align="center">
            <template #default="{ row }">
              <el-button size="small" link type="primary" @click="college.openEdit(row)">
                编辑
              </el-button>
              <el-button
                size="small"
                link
                type="danger"
                @click="college.remove(row, row.name)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="pager">
          <el-pagination
            v-model:current-page="college.query.page"
            :total="college.total.value"
            :page-size="college.query.page_size"
            layout="total, prev, pager, next"
            @current-change="college.load"
          />
        </div>
      </el-tab-pane>

      <!-- 专业 -->
      <el-tab-pane label="专业" name="major">
        <div class="toolbar">
          <el-select
            v-model="major.query.college_id"
            placeholder="全部学院"
            clearable
            style="width: 200px"
            @change="major.search"
          >
            <el-option v-for="c in colleges" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
          <el-input
            v-model="major.query.keyword"
            placeholder="搜索代码或名称"
            style="width: 200px"
            clearable
            @keyup.enter="major.search"
            @clear="major.search"
          />
          <el-button type="primary" @click="major.search">查询</el-button>
          <div class="spacer" />
          <el-button type="primary" :icon="'Plus'" @click="major.openCreate">
            新增专业
          </el-button>
        </div>
        <el-table v-loading="major.loading.value" :data="major.rows.value" stripe>
          <el-table-column prop="code" label="代码" width="110" />
          <el-table-column prop="name" label="名称" min-width="170" />
          <el-table-column prop="college_name" label="所属学院" min-width="170" />
          <el-table-column label="学位" width="90" align="center">
            <template #default="{ row }">{{ DEGREE[row.degree_type] }}</template>
          </el-table-column>
          <el-table-column label="学制" width="80" align="center">
            <template #default="{ row }">{{ row.duration_years }} 年</template>
          </el-table-column>
          <el-table-column label="操作" width="130" align="center">
            <template #default="{ row }">
              <el-button size="small" link type="primary" @click="major.openEdit(row)">
                编辑
              </el-button>
              <el-button size="small" link type="danger" @click="major.remove(row, row.name)">
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="pager">
          <el-pagination
            v-model:current-page="major.query.page"
            :total="major.total.value"
            :page-size="major.query.page_size"
            layout="total, prev, pager, next"
            @current-change="major.load"
          />
        </div>
      </el-tab-pane>

      <!-- 班级 -->
      <el-tab-pane label="班级" name="class">
        <div class="toolbar">
          <el-select
            v-model="klass.query.major_id"
            placeholder="全部专业"
            clearable
            style="width: 200px"
            @change="klass.search"
          >
            <el-option v-for="m in majors" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
          <el-input
            v-model="klass.query.keyword"
            placeholder="搜索代码或名称"
            style="width: 200px"
            clearable
            @keyup.enter="klass.search"
            @clear="klass.search"
          />
          <el-button type="primary" @click="klass.search">查询</el-button>
          <div class="spacer" />
          <el-button type="primary" :icon="'Plus'" @click="klass.openCreate">
            新增班级
          </el-button>
        </div>
        <el-table v-loading="klass.loading.value" :data="klass.rows.value" stripe>
          <el-table-column prop="code" label="代码" width="150" />
          <el-table-column prop="name" label="名称" min-width="170" />
          <el-table-column prop="major_name" label="专业" min-width="160" />
          <el-table-column prop="grade_year" label="年级" width="90" align="center" />
          <el-table-column prop="student_count" label="人数" width="80" align="center" />
          <el-table-column label="操作" width="130" align="center">
            <template #default="{ row }">
              <el-button size="small" link type="primary" @click="klass.openEdit(row)">
                编辑
              </el-button>
              <el-button size="small" link type="danger" @click="klass.remove(row, row.name)">
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="pager">
          <el-pagination
            v-model:current-page="klass.query.page"
            :total="klass.total.value"
            :page-size="klass.query.page_size"
            layout="total, prev, pager, next"
            @current-change="klass.load"
          />
        </div>
      </el-tab-pane>

      <!-- 教室 -->
      <el-tab-pane label="教室" name="classroom">
        <div class="toolbar">
          <el-input
            v-model="room.query.keyword"
            placeholder="搜索代码或楼栋"
            style="width: 220px"
            clearable
            @keyup.enter="room.search"
            @clear="room.search"
          />
          <el-button type="primary" @click="room.search">查询</el-button>
          <div class="spacer" />
          <el-button type="primary" :icon="'Plus'" @click="room.openCreate">
            新增教室
          </el-button>
        </div>
        <el-table v-loading="room.loading.value" :data="room.rows.value" stripe>
          <el-table-column prop="code" label="教室号" width="130" />
          <el-table-column prop="building" label="楼栋" min-width="130" />
          <el-table-column prop="capacity" label="容量" width="90" align="center" />
          <el-table-column label="类型" width="120">
            <template #default="{ row }">{{ ROOM_TYPE[row.room_type] }}</template>
          </el-table-column>
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="row.status === 'ACTIVE' ? 'success' : 'warning'" size="small">
                {{ ROOM_STATUS[row.status] }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="130" align="center">
            <template #default="{ row }">
              <el-button size="small" link type="primary" @click="room.openEdit(row)">
                编辑
              </el-button>
              <el-button size="small" link type="danger" @click="room.remove(row, row.code)">
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="pager">
          <el-pagination
            v-model:current-page="room.query.page"
            :total="room.total.value"
            :page-size="room.query.page_size"
            layout="total, prev, pager, next"
            @current-change="room.load"
          />
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 学院表单 -->
    <el-dialog
      v-model="college.dialogVisible.value"
      :title="college.dialogMode.value === 'create' ? '新增学院' : '编辑学院'"
      width="480px"
    >
      <el-form label-width="90px">
        <el-form-item label="学院代码" required>
          <el-input v-model="college.form.value.code" maxlength="20" />
        </el-form-item>
        <el-form-item label="学院名称" required>
          <el-input v-model="college.form.value.name" maxlength="100" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="college.form.value.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="college.form.value.status">
            <el-radio value="ACTIVE">启用</el-radio>
            <el-radio value="INACTIVE">停用</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="college.dialogVisible.value = false">取消</el-button>
        <el-button type="primary" :loading="college.saving.value" @click="college.save()">
          确定
        </el-button>
      </template>
    </el-dialog>

    <!-- 专业表单 -->
    <el-dialog
      v-model="major.dialogVisible.value"
      :title="major.dialogMode.value === 'create' ? '新增专业' : '编辑专业'"
      width="480px"
    >
      <el-form label-width="90px">
        <el-form-item label="专业代码" required>
          <el-input v-model="major.form.value.code" maxlength="20" />
        </el-form-item>
        <el-form-item label="专业名称" required>
          <el-input v-model="major.form.value.name" maxlength="100" />
        </el-form-item>
        <el-form-item label="所属学院" required>
          <el-select v-model="major.form.value.college_id" style="width: 100%">
            <el-option v-for="c in colleges" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="学位类型">
          <el-select v-model="major.form.value.degree_type" style="width: 100%">
            <el-option label="本科" value="BACHELOR" />
            <el-option label="硕士" value="MASTER" />
            <el-option label="博士" value="DOCTOR" />
          </el-select>
        </el-form-item>
        <el-form-item label="学制（年）">
          <el-input-number v-model="major.form.value.duration_years" :min="1" :max="10" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="major.dialogVisible.value = false">取消</el-button>
        <el-button type="primary" :loading="major.saving.value" @click="major.save()">
          确定
        </el-button>
      </template>
    </el-dialog>

    <!-- 班级表单 -->
    <el-dialog
      v-model="klass.dialogVisible.value"
      :title="klass.dialogMode.value === 'create' ? '新增班级' : '编辑班级'"
      width="480px"
    >
      <el-form label-width="90px">
        <el-form-item label="班级代码" required>
          <el-input v-model="klass.form.value.code" maxlength="30" />
        </el-form-item>
        <el-form-item label="班级名称" required>
          <el-input v-model="klass.form.value.name" maxlength="60" />
        </el-form-item>
        <el-form-item label="所属专业" required>
          <el-select v-model="klass.form.value.major_id" style="width: 100%">
            <el-option v-for="m in majors" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="年级" required>
          <el-input-number v-model="klass.form.value.grade_year" :min="1900" :max="2200" />
        </el-form-item>
        <el-form-item label="辅导员">
          <el-select
            v-model="klass.form.value.counselor_id"
            clearable
            style="width: 100%"
          >
            <el-option
              v-for="t in teachers"
              :key="t.id"
              :label="`${t.real_name}（${t.teacher_no}）`"
              :value="t.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="klass.dialogVisible.value = false">取消</el-button>
        <el-button type="primary" :loading="klass.saving.value" @click="klass.save()">
          确定
        </el-button>
      </template>
    </el-dialog>

    <!-- 教室表单 -->
    <el-dialog
      v-model="room.dialogVisible.value"
      :title="room.dialogMode.value === 'create' ? '新增教室' : '编辑教室'"
      width="480px"
    >
      <el-form label-width="90px">
        <el-form-item label="教室号" required>
          <el-input v-model="room.form.value.code" maxlength="30" />
        </el-form-item>
        <el-form-item label="楼栋" required>
          <el-input v-model="room.form.value.building" maxlength="50" />
        </el-form-item>
        <el-form-item label="容量" required>
          <el-input-number v-model="room.form.value.capacity" :min="1" :max="2000" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="room.form.value.room_type" style="width: 100%">
            <el-option label="普通教室" value="NORMAL" />
            <el-option label="实验室" value="LAB" />
            <el-option label="多媒体教室" value="MULTIMEDIA" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="room.form.value.status" style="width: 100%">
            <el-option label="可用" value="ACTIVE" />
            <el-option label="维护中" value="MAINTENANCE" />
            <el-option label="停用" value="DISABLED" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="room.dialogVisible.value = false">取消</el-button>
        <el-button type="primary" :loading="room.saving.value" @click="room.save()">
          确定
        </el-button>
      </template>
    </el-dialog>
  </el-card>
</template>
