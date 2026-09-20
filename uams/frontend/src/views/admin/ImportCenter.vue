<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { UploadFile, UploadInstance } from 'element-plus'

import { importApi, teachingApi } from '@/api'
import type { ImportKind, ImportResult, TeachingClass } from '@/types'

/**
 * 批量导入中心（FIX-005）。
 *
 * 每个 Tab 都是同一条闭环：下载模板 → 填写 → 上传 → 后端校验 → 结果与错误明细。
 * 模板与校验规则全部来自后端，前端不重复实现任何业务判断。
 */
const KINDS: { key: ImportKind; label: string; hint: string }[] = [
  {
    key: 'students',
    label: '学生',
    hint: '学院 / 专业 / 行政班必须已存在且层级匹配；学号即登录名。',
  },
  {
    key: 'teachers',
    label: '教师',
    hint: '工号即登录名，初始密码为工号；职称可填 教授/副教授/讲师/助教。',
  },
  {
    key: 'courses',
    label: '课程',
    hint: '理论学时 + 实践学时必须等于总学时；考核方式由总学时自动决定，无需填写。',
  },
  {
    key: 'grades',
    label: '成绩',
    hint: '模板按教学班自动带出学生名单与课程考核结构，老师只需填写成绩列。',
  },
]

const active = ref<ImportKind>('students')
const file = ref<File | null>(null)
const uploader = ref<UploadInstance>()
const result = ref<ImportResult | null>(null)
const importing = ref(false)
const downloading = ref(false)

const classes = ref<TeachingClass[]>([])
const classId = ref<number | undefined>(undefined)

const current = computed(() => KINDS.find((k) => k.key === active.value)!)
const isGrade = computed(() => active.value === 'grades')

/** 错误列名（后端字段名）→ 中文，便于教务对照 Excel 列。 */
const FIELD_LABEL: Record<string, string> = {
  student_no: '学号', name: '姓名', username: '登录名', college: '学院',
  major: '专业', class_name: '行政班', teacher_no: '工号', title: '职称',
  gender: '性别', phone: '联系电话', course_code: '课程代码',
  course_name: '课程名称', credits: '学分', total_hours: '总学时',
  theory_hours: '理论学时', practice_hours: '实践学时', course_type: '课程性质',
  teaching_class_code: '教学班', regular_score: '平时成绩', mid_score: '期中成绩',
  mid_theory_score: '期中理论', mid_practice_score: '期中实践',
  final_score: '期末成绩', final_theory_score: '期末理论',
  final_practice_score: '期末实践', theory_makeup_score: '理论补考',
  practice_makeup_score: '实践补考',
}

function fieldLabel(field: string) {
  return FIELD_LABEL[field] ?? field
}

async function switchTab() {
  file.value = null
  result.value = null
  uploader.value?.clearFiles()
  if (isGrade.value) await loadClasses()
}

async function loadClasses() {
  if (classes.value.length) return
  const res = await teachingApi.classes({ page_size: 200 })
  classes.value = res.items
  if (!classId.value) classId.value = res.items[0]?.id
}

async function downloadTemplate() {
  if (isGrade.value) {
    await loadClasses()
    if (!classId.value) {
      ElMessage.warning('请先选择教学班')
      return
    }
  }
  downloading.value = true
  try {
    await importApi.template(active.value, isGrade.value ? classId.value : undefined)
    ElMessage.success('模板已开始下载，请按「填写说明」工作表填写')
  } finally {
    downloading.value = false
  }
}

function onFileChange(f: UploadFile) {
  file.value = (f.raw as File) ?? null
  result.value = null
}

async function startImport() {
  if (!file.value) {
    ElMessage.warning('请先选择要上传的 Excel 文件')
    return
  }
  importing.value = true
  try {
    result.value = await importApi.upload(active.value, file.value)
    const r = result.value
    if (r.failed === 0) {
      ElMessage.success(`导入完成：成功 ${r.success} 条`)
    } else {
      ElMessage.warning(`导入完成：成功 ${r.success} 条，失败 ${r.failed} 条`)
    }
    // 导入结束后清空已选文件，方便接着上传下一个（例如修正后的文件）
    uploader.value?.clearFiles()
    file.value = null
  } finally {
    importing.value = false
  }
}
</script>

<template>
  <div>
    <el-card shadow="never" class="page-card">
      <template #header>
        <div class="head">
          <span>批量导入</span>
          <el-text size="small" type="info">
            下载模板 → 填写 → 上传，系统逐行校验后返回结果
          </el-text>
        </div>
      </template>

      <el-tabs v-model="active" @tab-change="switchTab">
        <el-tab-pane
          v-for="k in KINDS"
          :key="k.key"
          :label="`${k.label}导入`"
          :name="k.key"
        />
      </el-tabs>

      <el-steps :active="result ? 3 : file ? 2 : 1" simple style="margin-bottom: 16px">
        <el-step title="下载模板" />
        <el-step title="填写 Excel" />
        <el-step title="上传文件" />
        <el-step title="查看结果" />
      </el-steps>

      <el-alert :title="current.hint" type="info" :closable="false" show-icon />

      <div class="toolbar">
        <el-select
          v-if="isGrade"
          v-model="classId"
          filterable
          placeholder="选择教学班（决定名单与考核结构）"
          style="width: 340px"
        >
          <el-option
            v-for="c in classes"
            :key="c.id"
            :label="`${c.course_name}（${c.code}）`"
            :value="c.id"
          />
        </el-select>
        <el-button :loading="downloading" @click="downloadTemplate">
          ① 下载模板
        </el-button>
        <el-upload
          ref="uploader"
          :auto-upload="false"
          :limit="1"
          accept=".xlsx"
          :on-change="onFileChange"
          :on-exceed="() => ElMessage.warning('一次只能上传 1 个文件，请先移除已选文件')"
        >
          <el-button>② 选择 Excel 文件</el-button>
        </el-upload>
        <el-button
          type="primary"
          :loading="importing"
          :disabled="!file"
          @click="startImport"
        >
          ③ 开始导入
        </el-button>
      </div>
    </el-card>

    <el-card v-if="result" shadow="never" class="page-card">
      <template #header><span>导入结果</span></template>

      <div class="stat-grid">
        <el-statistic title="总行数" :value="result.total" />
        <el-statistic title="成功" :value="result.success" />
        <el-statistic title="失败" :value="result.failed" />
      </div>

      <el-alert
        v-if="result.failed === 0"
        type="success"
        :title="`全部导入成功，共 ${result.success} 条`"
        :closable="false"
        show-icon
        style="margin-top: 12px"
      />
      <el-alert
        v-else
        type="warning"
        :title="`成功 ${result.success} 条，失败 ${result.failed} 条。下方为失败明细，修正后重新上传即可（已成功的行不会重复导入）。`"
        :closable="false"
        show-icon
        style="margin-top: 12px"
      />

      <el-table
        v-if="result.errors.length"
        :data="result.errors"
        stripe
        border
        size="small"
        style="margin-top: 12px"
      >
        <el-table-column prop="row" label="Excel 行号" width="110" align="center" />
        <el-table-column label="出错列" width="140">
          <template #default="{ row }">{{ fieldLabel(row.field) }}</template>
        </el-table-column>
        <el-table-column prop="message" label="原因" />
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.head {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 16px;
}
.stat-grid {
  display: flex;
  gap: 48px;
}
</style>
