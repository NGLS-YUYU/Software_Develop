<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { evaluationApi } from '@/api'
import { currentSemester } from '@/composables/useSemester'
import type { EvaluationTask, PendingEvaluation } from '@/types'

const tasks = ref<EvaluationTask[]>([])
const taskId = ref<number | undefined>(undefined)
const pending = ref<PendingEvaluation[]>([])
const loading = ref(false)

const dialog = ref(false)
const current = ref<PendingEvaluation | null>(null)
const form = ref({ score: 90, comment: '' })
const submitting = ref(false)

function isOpen(t: EvaluationTask) {
  const now = Date.now()
  return (
    t.status === 'ACTIVE' &&
    new Date(t.start_time).getTime() <= now &&
    now <= new Date(t.end_time).getTime()
  )
}

async function loadTasks() {
  tasks.value = await evaluationApi.tasks(currentSemester())
  const open = tasks.value.find(isOpen)
  taskId.value = open?.id ?? tasks.value[0]?.id
}

async function loadPending() {
  if (!taskId.value) return
  loading.value = true
  try {
    pending.value = await evaluationApi.pending(taskId.value)
  } finally {
    loading.value = false
  }
}

function open(row: PendingEvaluation) {
  current.value = row
  form.value = { score: 90, comment: '' }
  dialog.value = true
}

async function submit() {
  if (!current.value || !taskId.value) return
  submitting.value = true
  try {
    await evaluationApi.submit({
      task_id: taskId.value,
      teaching_class_id: current.value.teaching_class_id,
      score: form.value.score,
      comment: form.value.comment || undefined,
    })
    ElMessage.success('评价已提交')
    dialog.value = false
    await loadPending()
  } finally {
    submitting.value = false
  }
}

watch(taskId, loadPending)
onMounted(async () => {
  await loadTasks()
  await loadPending()
})
</script>

<template>
  <div class="eval-page">
    <!-- 第一部分：待评价课程列表 -->
    <el-card class="page-card" shadow="never" v-loading="loading">
      <div class="toolbar">
        <el-select v-model="taskId" placeholder="选择评价任务" class="task-select">
          <el-option v-for="t in tasks" :key="t.id" :label="t.name" :value="t.id">
            <span>{{ t.name }}</span>
            <el-tag v-if="isOpen(t)" type="success" size="small" class="opt-tag">
              进行中
            </el-tag>
          </el-option>
        </el-select>
        <div class="spacer" />
        <span class="anon-note">
          <el-icon><component :is="'Lock'" /></el-icon>
          评价内容匿名提交，教师无法看到评价人
        </span>
      </div>

      <div class="card-head">
        <span class="section-title">待评价课程</span>
        <span class="muted">共 {{ pending.length }} 门</span>
      </div>

      <el-empty v-if="!pending.length" description="暂无待评价课程" />

      <div v-else class="eval-grid">
        <article
          v-for="row in pending"
          :key="row.teaching_class_id"
          class="eval-item"
          :class="{ 'is-done': row.evaluated }"
        >
          <div class="eval-item__head">
            <h4 class="eval-item__name">{{ row.course_name }}</h4>
            <el-tag :type="row.evaluated ? 'success' : 'warning'" size="small">
              {{ row.evaluated ? '已评价' : '待评价' }}
            </el-tag>
          </div>

          <div class="eval-item__meta">
            <span class="meta-row">
              <el-icon><component :is="'User'" /></el-icon>{{ row.teacher_name }}
            </span>
            <span class="meta-row">
              <el-icon><component :is="'Collection'" /></el-icon>{{ row.teaching_class_code }}
            </span>
          </div>

          <div class="eval-item__foot">
            <el-button type="primary" :disabled="row.evaluated" @click="open(row)">
              {{ row.evaluated ? '已完成' : '去评价' }}
            </el-button>
          </div>
        </article>
      </div>
    </el-card>

    <!-- 第二部分：评价表单 -->
    <el-dialog v-model="dialog" title="教学评价" width="520px">
      <div class="eval-target">
        <div class="eval-target__name">{{ current?.course_name }}</div>
        <div class="eval-target__meta">
          <span>{{ current?.teacher_name }}</span>
          <span class="dot">·</span>
          <span>{{ current?.teaching_class_code }}</span>
        </div>
      </div>

      <el-form label-position="top">
        <el-form-item label="评分">
          <div class="rating">
            <div class="rating__value">
              <span class="rating__num">{{ form.score }}</span>
              <span class="rating__unit">分</span>
            </div>
            <el-slider v-model="form.score" :min="0" :max="100" show-input />
            <div class="rating__hint muted">0 - 100 分，拖动滑块或直接输入</div>
          </div>
        </el-form-item>
        <el-form-item label="评语">
          <el-input
            v-model="form.comment"
            type="textarea"
            :rows="4"
            maxlength="1000"
            show-word-limit
            placeholder="选填，对教学的建议"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
/* ----------------------------------------------------------- 工具条与标题 */
.task-select {
  width: 280px;
}

.opt-tag {
  margin-left: 8px;
}

.anon-note {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--uams-text-3);

  .el-icon {
    color: var(--uams-primary);
  }
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;

  .section-title {
    margin: 0;
  }
}

/* --------------------------------------------------------- 课程卡片网格 */
.eval-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--uams-gap);
}

.eval-item {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface);
  transition: border-color 0.16s ease, box-shadow 0.16s ease;

  &:hover {
    border-color: var(--uams-primary-light);
    box-shadow: var(--uams-shadow-sm);
  }

  &.is-done {
    background: var(--uams-surface-sunken);
  }

  &__head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
  }

  &__name {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    line-height: 1.4;
    color: var(--uams-text);
    word-break: break-word;
  }

  &__meta {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 16px;
    font-size: 13px;
    color: var(--uams-text-2);
  }

  &__foot {
    display: flex;
    justify-content: flex-end;
    margin-top: auto;
    padding-top: 4px;
  }
}

.meta-row {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;

  .el-icon {
    color: var(--uams-text-3);
  }
}

/* --------------------------------------------------------- 评价表单弹窗 */
.eval-target {
  padding: 14px 16px;
  margin-bottom: 18px;
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  background: var(--uams-primary-softer);

  &__name {
    font-size: 16px;
    font-weight: 600;
    color: var(--uams-text);
  }

  &__meta {
    margin-top: 4px;
    font-size: 13px;
    color: var(--uams-text-2);

    .dot {
      margin: 0 6px;
      color: var(--uams-text-3);
    }
  }
}

.rating {
  width: 100%;

  &__value {
    display: flex;
    align-items: baseline;
    gap: 4px;
    margin-bottom: 4px;
  }

  &__num {
    font-size: 30px;
    font-weight: 700;
    line-height: 1;
    color: var(--uams-primary-dark);
    font-variant-numeric: tabular-nums;
  }

  &__unit {
    font-size: 13px;
    color: var(--uams-text-3);
  }

  &__hint {
    margin-top: 6px;
    font-size: 12px;
  }

  /* 放大滑块，便于点击 */
  :deep(.el-slider) {
    --el-slider-height: 8px;
    --el-slider-button-size: 22px;
    --el-slider-button-wrapper-size: 40px;
  }

  :deep(.el-slider__button) {
    border-width: 3px;
    border-color: var(--uams-primary);
  }

  :deep(.el-slider__input) {
    width: 96px;
  }
}

/* ---------------------------------------------------------------- 响应式 */
@media (max-width: 768px) {
  /* 单列、评价项之间留足间距 */
  .eval-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 14px;
  }

  .eval-item {
    padding: 14px;
  }

  .task-select {
    width: 100%;
  }

  /* 匿名说明换行展示，避免与选择框挤在一行 */
  .anon-note {
    width: 100%;
  }

  .eval-item__foot {
    justify-content: stretch;

    .el-button {
      width: 100%;
    }
  }

  .eval-target {
    padding: 12px 14px;
    margin-bottom: 16px;
  }

  .rating__num {
    font-size: 26px;
  }

  .rating :deep(.el-slider__input) {
    width: 84px;
  }
}
</style>
