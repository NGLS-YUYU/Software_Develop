<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { selectionApi } from '@/api'
import { currentSemester, semesterOptions } from '@/composables/useSemester'
import type { Selection, SelectionPeriod, TeachingClass } from '@/types'

const semester = ref(currentSemester())
const keyword = ref('')
const available = ref<TeachingClass[]>([])
const mine = ref<Selection[]>([])
const periods = ref<SelectionPeriod[]>([])
const loading = ref(false)
const tab = ref('available')

const totalCredits = computed(() =>
  mine.value.reduce((sum, s) => sum + Number(s.credits ?? 0), 0),
)

/** 选课是否开放：由后端时间窗口决定，这里只做提示。 */
const openPeriod = computed(() => {
  const now = Date.now()
  return periods.value.find(
    (p) =>
      p.status === 'ACTIVE' &&
      new Date(p.start_time).getTime() <= now &&
      now <= new Date(p.end_time).getTime(),
  )
})

/** 空列表原因：区分“不在选课时间”和“选课已开放但没有可选课程”。
 *  不在这里断言“教务未配置”，因为“已选完所有选修课”也会得到空列表；
 *  配置诊断由教务端完成（/course-selections/selectable-summary）。 */
const emptyHint = computed(() =>
  openPeriod.value
    ? '当前没有可自主选择的选修教学班：可能本学期未开设已开放选课的选修教学班，或你已选完所有可选课程。必修课由教务处统一预安排，可在「我的课表」查看。'
    : '当前不在选课时间内。选课开放后，已开放选课的选修教学班会显示在这里。',
)

async function load() {
  loading.value = true
  try {
    const [a, m, p] = await Promise.allSettled([
      selectionApi.available(semester.value, keyword.value || undefined),
      selectionApi.mine(semester.value),
      selectionApi.periods(semester.value),
    ])
    if (a.status === 'fulfilled') available.value = a.value
    if (m.status === 'fulfilled') mine.value = m.value
    if (p.status === 'fulfilled') periods.value = p.value
  } finally {
    loading.value = false
  }
}

function scheduleText(tc: TeachingClass) {
  const DAY = ['', '周一', '周二', '周三', '周四', '周五', '周六', '周日']
  if (!tc.schedules?.length) return '未排课'
  return tc.schedules
    .map((s) => {
      const wk =
        s.week_type === 'ODD' ? '单' : s.week_type === 'EVEN' ? '双' : ''
      return `${DAY[s.day_of_week]} ${s.start_period}-${s.end_period}节 ${s.classroom_code ?? ''} (${s.start_week}-${s.end_week}周${wk})`
    })
    .join('；')
}

async function doSelect(tc: TeachingClass) {
  try {
    await ElMessageBox.confirm(
      `确认选择《${tc.course_name}》（${tc.code}）？\n${scheduleText(tc)}`,
      '确认选课',
      { type: 'info' },
    )
  } catch {
    return
  }
  // 失败原因（已满/冲突/先修不满足等）由后端返回，拦截器统一提示
  await selectionApi.select(tc.id)
  ElMessage.success('选课成功')
  await load()
}

async function doDrop(s: Selection) {
  try {
    await ElMessageBox.confirm(`确认退选《${s.course_name}》？`, '确认退课', {
      type: 'warning',
    })
  } catch {
    return
  }
  await selectionApi.drop(s.id)
  ElMessage.success('已退课')
  await load()
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="selection">
    <!-- 选课窗口状态提示 -->
    <el-alert
      v-if="openPeriod"
      :title="`选课开放中：${openPeriod.name}（截止 ${openPeriod.end_time.slice(0, 16).replace('T', ' ')}）`"
      type="success"
      :closable="false"
      show-icon
      class="selection__banner"
    />
    <el-alert
      v-else
      title="当前不在选课时间内，仅可查看"
      type="warning"
      :closable="false"
      show-icon
      class="selection__banner"
    />
    <el-alert
      v-if="openPeriod && !available.length && !loading"
      title="选课开放中，但当前没有可自主选择的选修教学班"
      type="warning"
      :closable="false"
      show-icon
      class="selection__banner"
    >
      可能是本学期未开设已开放选课的选修教学班，或你已选完所有可选课程。必修课由教务处统一预安排，可在「我的课表」查看。
    </el-alert>

    <el-card shadow="never" class="page-card">
      <!-- 筛选区 + 选课汇总 -->
      <div class="toolbar">
        <el-select v-model="semester" style="width: 170px" @change="load">
          <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
        </el-select>
        <el-input
          v-model="keyword"
          placeholder="搜索课程名称或代码"
          style="width: 240px"
          clearable
          @keyup.enter="load"
          @clear="load"
        />
        <el-button type="primary" @click="load">查询</el-button>
        <div class="spacer" />
        <div class="summary">
          <span class="summary__item">已选 <b>{{ mine.length }}</b> 门</span>
          <span class="summary__dot" />
          <span class="summary__item"><b>{{ totalCredits }}</b> 学分</span>
        </div>
      </div>

      <el-tabs v-model="tab" class="selection__tabs">
        <!-- 信息区一：可选课程 -->
        <el-tab-pane name="available">
          <template #label>
            <span class="tab-label">
              可选课程
              <span class="tab-label__count">{{ available.length }}</span>
            </span>
          </template>

          <el-empty v-if="!available.length" :description="emptyHint" />
          <div v-else class="course-grid">
            <article
              v-for="c in available"
              :key="c.id"
              class="course-card"
              :class="{ 'is-full': c.remaining <= 0 }"
            >
              <header class="course-card__top">
                <span class="course-card__code">{{ c.course_code }}</span>
                <el-tag
                  v-if="c.remaining <= 0"
                  type="danger"
                  size="small"
                  effect="light"
                  round
                >
                  已满
                </el-tag>
                <el-tag
                  v-else-if="c.remaining <= 5"
                  type="warning"
                  size="small"
                  effect="light"
                  round
                >
                  余位紧张
                </el-tag>
                <el-tag v-else type="success" size="small" effect="light" round>
                  可选
                </el-tag>
              </header>

              <h3 class="course-card__name">{{ c.course_name }}</h3>

              <div class="course-card__meta">
                <span class="meta">
                  <el-icon><component :is="'User'" /></el-icon>
                  {{ c.teacher_name || '待定' }}
                </span>
                <span class="meta">
                  <el-icon><component :is="'Collection'" /></el-icon>
                  {{ c.credits ?? 0 }} 学分
                </span>
              </div>

              <div class="course-card__sched">
                <el-icon class="sched__icon"><component :is="'Clock'" /></el-icon>
                <span class="sched__text">{{ scheduleText(c) }}</span>
              </div>

              <footer class="course-card__foot">
                <div class="seats">
                  <span
                    class="seats__num"
                    :class="{
                      'is-danger': c.remaining <= 0,
                      'is-warn': c.remaining > 0 && c.remaining <= 5,
                    }"
                  >
                    {{ c.remaining }}
                  </span>
                  <span class="seats__text">
                    <span class="seats__label">
                      {{ c.remaining > 0 ? '剩余名额' : '名额已满' }}
                    </span>
                    <span class="seats__total">
                      已选 {{ c.selected_count }} / {{ c.capacity }}
                    </span>
                  </span>
                </div>
                <el-button
                  type="primary"
                  :disabled="c.remaining <= 0"
                  @click="doSelect(c)"
                >
                  选课
                </el-button>
              </footer>
            </article>
          </div>
        </el-tab-pane>

        <!-- 信息区二：我的选课 -->
        <el-tab-pane name="mine">
          <template #label>
            <span class="tab-label">
              我的选课
              <span class="tab-label__count">{{ mine.length }}</span>
            </span>
          </template>

          <el-empty v-if="!mine.length" description="尚未选课" />
          <div v-else class="mine">
            <div class="mine__head">
              <span class="muted">共 {{ mine.length }} 门课程</span>
              <el-tag type="success" effect="light" round>合计 {{ totalCredits }} 学分</el-tag>
            </div>

            <ul class="mine__list">
              <li v-for="s in mine" :key="s.id" class="mine-item">
                <div class="mine-item__main">
                  <div class="mine-item__head">
                    <span class="mine-item__name">{{ s.course_name }}</span>
                    <span class="mine-item__code">{{ s.course_code }}</span>
                  </div>
                  <div class="mine-item__meta">
                    <span class="meta">
                      <el-icon><component :is="'User'" /></el-icon>
                      {{ s.teacher_name || '待定' }}
                    </span>
                    <span class="meta">
                      <el-icon><component :is="'Collection'" /></el-icon>
                      {{ s.credits ?? 0 }} 学分
                    </span>
                    <span class="meta">
                      <el-icon><component :is="'Ticket'" /></el-icon>
                      {{ s.teaching_class_code }}
                    </span>
                    <span class="meta">
                      <el-icon><component :is="'Clock'" /></el-icon>
                      {{ s.selected_at?.slice(0, 16).replace('T', ' ') }}
                    </span>
                  </div>
                </div>
                <el-button type="danger" plain @click="doDrop(s)">退课</el-button>
              </li>
            </ul>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<style scoped lang="scss">
.selection {
  display: flex;
  flex-direction: column;
  gap: var(--uams-gap);
}

.selection__banner {
  border-radius: var(--uams-radius);
  overflow: hidden;
}

/* ----------------------------------------------------------- 工具栏汇总 */
.summary {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 6px 14px;
  border-radius: var(--uams-radius-sm);
  background: var(--uams-primary-soft);
  color: var(--uams-text-2);
  font-size: 13px;

  b {
    color: var(--uams-primary-dark);
    font-size: 15px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }

  &__dot {
    width: 3px;
    height: 3px;
    border-radius: 50%;
    background: var(--uams-primary-light);
  }
}

/* ------------------------------------------------------------- 分组标签 */
.selection__tabs {
  :deep(.el-tabs__header) {
    margin-bottom: 16px;
  }
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 14px;

  &__count {
    min-width: 20px;
    height: 20px;
    padding: 0 6px;
    border-radius: 999px;
    display: inline-grid;
    place-items: center;
    font-size: 12px;
    font-weight: 600;
    color: var(--uams-text-2);
    background: var(--uams-surface-sunken);
    border: 1px solid var(--uams-border);
  }
}

/* ------------------------------------------------------------- 通用条目 */
.meta {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12.5px;
  color: var(--uams-text-2);

  .el-icon {
    font-size: 13px;
    color: var(--uams-text-3);
  }
}

/* ----------------------------------------------------------- 可选课程卡 */
.course-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--uams-gap);
}

.course-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px;
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius);
  background: var(--uams-surface);
  box-shadow: var(--uams-shadow-sm);
  transition: border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;

  &:hover {
    border-color: var(--uams-primary-light);
    box-shadow: var(--uams-shadow);
    transform: translateY(-1px);
  }

  &.is-full {
    background: var(--uams-surface-sunken);
  }

  &__top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  &__code {
    font-size: 12px;
    letter-spacing: 0.02em;
    color: var(--uams-text-3);
    padding: 2px 8px;
    border-radius: var(--uams-radius-xs);
    background: var(--uams-surface);
    border: 1px solid var(--uams-border);
  }

  &__name {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    line-height: 1.35;
    color: var(--uams-text);
  }

  &__meta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 16px;
  }

  &__sched {
    display: flex;
    align-items: flex-start;
    gap: 7px;
    padding: 9px 11px;
    border-radius: var(--uams-radius-sm);
    background: var(--uams-primary-softer);
    color: var(--uams-text-2);
    font-size: 12.5px;
    line-height: 1.55;

    .sched__icon {
      flex: 0 0 auto;
      margin-top: 2px;
      font-size: 14px;
      color: var(--uams-primary);
    }

    .sched__text {
      min-width: 0;
    }
  }

  &__foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-top: auto;
    padding-top: 12px;
    border-top: 1px solid var(--uams-border);
  }
}

/* 剩余名额（重点突出） */
.seats {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;

  &__num {
    font-size: 24px;
    font-weight: 700;
    line-height: 1;
    color: var(--uams-primary-dark);
    font-variant-numeric: tabular-nums;

    &.is-warn {
      color: var(--uams-warning);
    }

    &.is-danger {
      color: var(--uams-danger);
    }
  }

  &__text {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  &__label {
    font-size: 12px;
    color: var(--uams-text-2);
  }

  &__total {
    font-size: 11.5px;
    color: var(--uams-text-3);
    font-variant-numeric: tabular-nums;
  }
}

/* ------------------------------------------------------------- 我的选课 */
.mine {
  display: flex;
  flex-direction: column;
  gap: 12px;

  &__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  &__list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
}

.mine-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 16px;
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface);
  transition: border-color 0.16s ease, box-shadow 0.16s ease;

  &:hover {
    border-color: var(--uams-primary-light);
    box-shadow: var(--uams-shadow-sm);
  }

  &__main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  &__head {
    display: flex;
    align-items: baseline;
    gap: 10px;
    flex-wrap: wrap;
  }

  &__name {
    font-size: 15px;
    font-weight: 600;
    color: var(--uams-text);
  }

  &__code {
    font-size: 12px;
    color: var(--uams-text-3);
  }

  &__meta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 16px;
  }

  > .el-button {
    flex: 0 0 auto;
  }
}

/* --------------------------------------------------------------- 响应式 */
@media (max-width: 1024px) {
  .course-grid {
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  }
}

@media (max-width: 768px) {
  .selection {
    gap: 12px;
  }

  /* 工具栏：控件整行铺满，汇总独立一行 */
  .toolbar .spacer {
    display: none;
  }

  .summary {
    width: 100%;
    justify-content: center;
  }

  /* 可选课程：单列卡片 */
  .course-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 12px;
  }

  .course-card {
    padding: 14px;

    &__foot {
      gap: 10px;

      /* 选课按钮加大，便于点按 */
      > .el-button {
        height: 42px;
        padding: 0 26px;
        font-size: 14px;
      }
    }
  }

  /* 我的选课：纵向堆叠，退课按钮整行 */
  .mine-item {
    flex-direction: column;
    align-items: stretch;
    padding: 14px;

    > .el-button {
      width: 100%;
      height: 42px;
      font-size: 14px;
    }
  }
}

@media (max-width: 420px) {
  .meta {
    font-size: 12px;
  }

  .seats__num {
    font-size: 20px;
  }

  .mine__head {
    flex-wrap: wrap;
  }
}
</style>
