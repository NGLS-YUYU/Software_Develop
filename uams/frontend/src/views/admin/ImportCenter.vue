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
  <div class="import-center">
    <!-- 导入引导：类型选择 → 四步流程 → 当前步骤说明 → 操作区 -->
    <el-card shadow="never" class="page-card">
      <el-tabs v-model="active" class="kind-tabs" @tab-change="switchTab">
        <el-tab-pane
          v-for="k in KINDS"
          :key="k.key"
          :label="`${k.label}导入`"
          :name="k.key"
        />
      </el-tabs>

      <!-- 四步流程图：随进度点亮，窄屏自动换行 -->
      <ol class="steps">
        <li
          class="step"
          :class="{ 'is-active': !file && !result, 'is-done': file || result }"
        >
          <span class="step__no">
            <el-icon v-if="file || result"><component :is="'Check'" /></el-icon>
            <template v-else>1</template>
          </span>
          <span class="step__body">
            <span class="step__title">下载模板</span>
            <span class="step__desc">选好类型后下载标准 Excel 模板</span>
          </span>
        </li>

        <li class="step" :class="{ 'is-done': file || result }">
          <span class="step__no">
            <el-icon v-if="file || result"><component :is="'Check'" /></el-icon>
            <template v-else>2</template>
          </span>
          <span class="step__body">
            <span class="step__title">填写 Excel</span>
            <span class="step__desc">按「填写说明」工作表逐列填写</span>
          </span>
        </li>

        <li class="step" :class="{ 'is-active': file && !result, 'is-done': !!result }">
          <span class="step__no">
            <el-icon v-if="result"><component :is="'Check'" /></el-icon>
            <template v-else>3</template>
          </span>
          <span class="step__body">
            <span class="step__title">上传文件</span>
            <span class="step__desc">一次上传一个 .xlsx 文件</span>
          </span>
        </li>

        <li class="step" :class="{ 'is-active': !!result }">
          <span class="step__no">4</span>
          <span class="step__body">
            <span class="step__title">查看结果</span>
            <span class="step__desc">逐行校验，核对成功与失败明细</span>
          </span>
        </li>
      </ol>

      <!-- 当前类型「这一步要做什么」 -->
      <div class="guide">
        <el-icon class="guide__icon"><component :is="'InfoFilled'" /></el-icon>
        <div class="guide__body">
          <span class="guide__label">这一步要做什么</span>
          <p class="guide__text">{{ current.hint }}</p>
        </div>
      </div>

      <!-- 操作区：下载模板 / 上传并导入 -->
      <div class="flow">
        <div v-if="isGrade" class="flow-item flow-item--wide">
          <div class="flow-item__meta">
            <span class="flow-item__kicker">成绩导入前置</span>
            <span class="flow-item__title">选择教学班</span>
            <span class="flow-item__hint muted">模板会按该教学班带出学生名单与考核结构</span>
          </div>
          <el-select
            v-model="classId"
            class="flow-item__control"
            filterable
            placeholder="选择教学班（决定名单与考核结构）"
          >
            <el-option
              v-for="c in classes"
              :key="c.id"
              :label="`${c.course_name}（${c.code}）`"
              :value="c.id"
            />
          </el-select>
        </div>

        <div class="flow-item">
          <div class="flow-item__meta">
            <span class="flow-item__kicker">第 1 步</span>
            <span class="flow-item__title">下载模板</span>
            <span class="flow-item__hint muted">模板内含「填写说明」工作表，请勿改动表头</span>
          </div>
          <div class="toolbar ops">
            <el-button :loading="downloading" @click="downloadTemplate">
              <el-icon><component :is="'Download'" /></el-icon>
              <span>下载模板</span>
            </el-button>
          </div>
        </div>

        <div class="flow-item">
          <div class="flow-item__meta">
            <span class="flow-item__kicker">第 2 - 3 步</span>
            <span class="flow-item__title">上传并导入</span>
            <span class="flow-item__hint muted">系统会逐行校验，成功的行直接入库</span>
          </div>
          <div class="toolbar ops">
            <el-upload
              ref="uploader"
              :auto-upload="false"
              :limit="1"
              accept=".xlsx"
              :on-change="onFileChange"
              :on-exceed="() => ElMessage.warning('一次只能上传 1 个文件，请先移除已选文件')"
            >
              <el-button>
                <el-icon><component :is="'UploadFilled'" /></el-icon>
                <span>选择 Excel 文件</span>
              </el-button>
            </el-upload>
            <el-button
              type="primary"
              :loading="importing"
              :disabled="!file"
              @click="startImport"
            >
              开始导入
            </el-button>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 导入结果 -->
    <el-card v-if="result" shadow="never" class="page-card">
      <template #header>
        <div class="result-head">
          <span>导入结果</span>
          <el-tag
            size="small"
            effect="light"
            round
            :type="result.failed ? 'warning' : 'success'"
          >
            {{ result.failed ? `失败 ${result.failed} 条` : '全部成功' }}
          </el-tag>
        </div>
      </template>

      <div class="result-stats">
        <div class="rstat">
          <span class="rstat__value">{{ result.total }}</span>
          <span class="rstat__label">总行数</span>
        </div>
        <div class="rstat is-success">
          <span class="rstat__value">{{ result.success }}</span>
          <span class="rstat__label">成功导入</span>
        </div>
        <div class="rstat" :class="result.failed ? 'is-danger' : 'is-idle'">
          <span class="rstat__value">{{ result.failed }}</span>
          <span class="rstat__label">失败</span>
        </div>
      </div>

      <el-alert
        v-if="result.failed === 0"
        class="result-alert"
        type="success"
        :title="`全部导入成功，共 ${result.success} 条`"
        :closable="false"
        show-icon
      />
      <el-alert
        v-else
        class="result-alert"
        type="warning"
        :title="`成功 ${result.success} 条，失败 ${result.failed} 条。下方为失败明细，修正后重新上传即可（已成功的行不会重复导入）。`"
        :closable="false"
        show-icon
      />

      <div v-if="result.errors.length" class="errors">
        <p class="section-title">错误明细</p>

        <!-- 桌面端：表格 -->
        <div class="table-wrap">
          <el-table :data="result.errors" stripe border size="small">
            <el-table-column label="Excel 行号" width="120" align="center">
              <template #default="{ row }">
                <span class="row-no">{{ row.row }}</span>
              </template>
            </el-table-column>
            <el-table-column label="出错列" width="140">
              <template #default="{ row }">{{ fieldLabel(row.field) }}</template>
            </el-table-column>
            <el-table-column prop="message" label="原因" />
          </el-table>
        </div>

        <!-- 移动端：逐条卡片 -->
        <ul class="err-cards">
          <li v-for="(e, i) in result.errors" :key="i" class="err-card">
            <div class="err-card__head">
              <span class="row-no">第 {{ e.row }} 行</span>
              <el-tag size="small" effect="plain">{{ fieldLabel(e.field) }}</el-tag>
            </div>
            <p class="err-card__msg">{{ e.message }}</p>
          </li>
        </ul>
      </div>
    </el-card>
  </div>
</template>

<style scoped lang="scss">
/* ------------------------------------------------------------- 类型切换 */
.kind-tabs :deep(.el-tabs__header) {
  margin-bottom: 4px;
}

/* ------------------------------------------------------------- 步骤条 */
.steps {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 16px 0 0;
  padding: 0;
  list-style: none;
}

.step {
  flex: 1 1 180px;
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 11px 14px;
  border-radius: var(--uams-radius-sm);
  border: 1px solid var(--uams-border);
  background: var(--uams-surface-sunken);
  transition: background-color 0.16s ease, border-color 0.16s ease;

  &__no {
    flex: 0 0 28px;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    font-size: 13px;
    font-weight: 600;
    color: var(--uams-text-3);
    background: var(--uams-surface);
    border: 1px solid var(--uams-border-strong);
    font-variant-numeric: tabular-nums;

    .el-icon {
      font-size: 15px;
    }
  }

  &__body {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  &__title {
    font-size: 13px;
    font-weight: 600;
    color: var(--uams-text-2);
  }

  &__desc {
    font-size: 12px;
    color: var(--uams-text-3);
    line-height: 1.45;
  }

  /* 当前步骤：淡紫高亮 */
  &.is-active {
    background: var(--uams-primary-softer);
    border-color: color-mix(in srgb, var(--uams-primary) 32%, transparent);

    .step__no {
      color: #fff;
      background: var(--uams-primary);
      border-color: transparent;
    }

    .step__title {
      color: var(--uams-primary-dark);
    }
  }

  /* 已完成步骤：绿色对勾 */
  &.is-done {
    .step__no {
      color: #fff;
      background: var(--uams-success);
      border-color: transparent;
    }

    .step__title {
      color: var(--uams-text);
    }
  }
}

/* --------------------------------------------------------- 当前步骤说明 */
.guide {
  display: flex;
  gap: 12px;
  margin-top: 14px;
  padding: 13px 16px;
  border-radius: var(--uams-radius-sm);
  background: var(--uams-primary-softer);
  border: 1px solid var(--uams-primary-soft);

  &__icon {
    flex: 0 0 auto;
    margin-top: 2px;
    font-size: 17px;
    color: var(--uams-primary);
  }

  &__body {
    min-width: 0;
  }

  &__label {
    font-size: 12px;
    font-weight: 600;
    color: var(--uams-primary-dark);
  }

  &__text {
    margin: 3px 0 0;
    font-size: 13px;
    line-height: 1.6;
    color: var(--uams-text-2);
  }
}

/* ------------------------------------------------------------- 操作区 */
.flow {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--uams-gap);
  margin-top: 16px;
}

.flow-item {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border-radius: var(--uams-radius-sm);
  border: 1px solid var(--uams-border);
  background: var(--uams-surface);

  &--wide {
    grid-column: 1 / -1;
  }

  &__meta {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  &__kicker {
    font-size: 12px;
    font-weight: 600;
    color: var(--uams-primary-dark);
  }

  &__title {
    margin-top: 2px;
    font-size: 15px;
    font-weight: 600;
    color: var(--uams-text);
  }

  &__hint {
    margin-top: 2px;
    font-size: 12px;
    line-height: 1.5;
  }

  &__control {
    width: 100%;
  }
}

/* 操作按钮行：复用 .toolbar，再收掉其默认下边距 */
.toolbar.ops {
  margin-bottom: 0;
  margin-top: auto;
  align-items: stretch;

  > .el-button {
    flex: 0 0 auto;
  }
}

/* ------------------------------------------------------------- 结果概览 */
.result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.result-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--uams-gap);
}

.rstat {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px 16px;
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface-sunken);
  border: 1px solid var(--uams-border);

  &__value {
    font-size: 30px;
    font-weight: 700;
    line-height: 1.1;
    letter-spacing: -0.5px;
    color: var(--uams-text);
    font-variant-numeric: tabular-nums;
  }

  &__label {
    font-size: 12px;
    color: var(--uams-text-3);
  }

  /* 成功 / 失败用状态色强调，让关键数字跳出来 */
  &.is-success {
    background: color-mix(in srgb, var(--uams-success) 10%, transparent);
    border-color: color-mix(in srgb, var(--uams-success) 24%, transparent);

    .rstat__value {
      color: var(--uams-success);
    }
  }

  &.is-danger {
    background: color-mix(in srgb, var(--uams-danger) 10%, transparent);
    border-color: color-mix(in srgb, var(--uams-danger) 24%, transparent);

    .rstat__value {
      color: var(--uams-danger);
    }
  }
}

.result-alert {
  margin-top: 16px;
}

/* ------------------------------------------------------------- 错误明细 */
.errors {
  margin-top: 20px;
}

.row-no {
  font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas,
    'Liberation Mono', monospace;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: var(--uams-text-2);
}

/* 移动端错误卡片：默认隐藏，窄屏接管 */
.err-cards {
  display: none;
  margin: 0;
  padding: 0;
  list-style: none;
}

.err-card {
  padding: 12px 14px;
  border-radius: var(--uams-radius-sm);
  border: 1px solid var(--uams-border);
  background: var(--uams-surface-sunken);

  + .err-card {
    margin-top: 10px;
  }

  &__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }

  &__msg {
    margin: 8px 0 0;
    font-size: 13px;
    line-height: 1.6;
    color: var(--uams-text-2);
  }
}

/* ------------------------------------------------------------- 响应式 */
@media (max-width: 1024px) {
  .flow {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 768px) {
  /* 步骤条：两列换行，隐藏次要说明，保持清爽 */
  .steps {
    gap: 8px;
    margin-top: 12px;
  }

  .step {
    flex: 1 1 calc(50% - 8px);
    padding: 10px 12px;
    gap: 8px;

    &__no {
      flex: 0 0 26px;
      width: 26px;
      height: 26px;
      font-size: 12px;
    }

    &__desc {
      display: none;
    }
  }

  /* 结果卡片单列，数值与标题并排，节省纵向空间 */
  .result-stats {
    grid-template-columns: minmax(0, 1fr);
    gap: 10px;
  }

  .rstat {
    flex-direction: row;
    align-items: baseline;
    justify-content: space-between;
    padding: 12px 14px;

    &__value {
      font-size: 24px;
    }
  }

  /* 表格换成卡片列表 */
  .table-wrap {
    display: none;
  }

  .err-cards {
    display: block;
  }

  .flow-item {
    padding: 14px;
  }
}

@media (max-width: 420px) {
  .flow-item .toolbar.ops > .el-button {
    flex: 1 1 auto;
  }
}
</style>
