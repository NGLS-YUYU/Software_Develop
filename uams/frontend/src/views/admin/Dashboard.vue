<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { gradeApi, statsApi } from '@/api'
import { currentSemester } from '@/composables/useSemester'
import type { Grade, GradeStatistics, Overview } from '@/types'

const router = useRouter()
const overview = ref<Overview | null>(null)
const dist = ref<GradeStatistics | null>(null)
const ranking = ref<{ course_name: string; selected: number }[]>([])
const pending = ref<Grade[]>([])
const loading = ref(true)

const CARDS = [
  { key: 'students', label: '学生总数', icon: 'User', color: '#1f6feb', to: '/admin/students' },
  { key: 'teachers', label: '教师总数', icon: 'Avatar', color: '#1f9254', to: '/admin/teachers' },
  { key: 'courses', label: '课程总数', icon: 'Reading', color: '#c76a15', to: '/admin/courses' },
  { key: 'teaching_classes', label: '教学班', icon: 'Grid', color: '#7d3cc4', to: '/admin/teaching' },
  { key: 'selections', label: '选课记录', icon: 'Checked', color: '#11808c', to: '/admin/selection' },
  { key: 'pending_grades', label: '待审成绩', icon: 'Stamp', color: '#c0392b', to: '/admin/grades' },
] as const

onMounted(async () => {
  try {
    const [o, d, r, p] = await Promise.allSettled([
      statsApi.overview(),
      statsApi.gradeDistribution(),
      statsApi.selectionRanking(currentSemester(), 8),
      gradeApi.pending(),
    ])
    if (o.status === 'fulfilled') overview.value = o.value
    if (d.status === 'fulfilled') dist.value = d.value
    if (r.status === 'fulfilled') ranking.value = r.value
    if (p.status === 'fulfilled') pending.value = p.value
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div v-loading="loading">
    <!-- 关键指标条：一个明显更大的主指标 + 横向紧凑指标带 -->
    <section class="page-card kpi-band">
      <div class="kpi-hero" role="button" @click="router.push('/admin/students')">
        <el-icon class="kpi-hero__icon"><component :is="'User'" /></el-icon>
        <div class="kpi-hero__body">
          <span class="kpi-hero__label">在册学生</span>
          <span class="kpi-hero__value">{{ overview?.students ?? 0 }}</span>
          <span class="kpi-hero__hint">
            {{ overview?.colleges ?? 0 }} 个学院 · {{ overview?.majors ?? 0 }} 个专业 ·
            {{ overview?.classes ?? 0 }} 个班级
          </span>
        </div>
      </div>

      <div class="kpi-strip">
        <div
          v-for="c in CARDS.filter((x) => x.key !== 'students')"
          :key="c.key"
          class="kpi-item"
          :class="`kpi-item--${c.key}`"
          role="button"
          @click="router.push(c.to)"
        >
          <el-icon class="kpi-item__icon"><component :is="c.icon" /></el-icon>
          <div class="kpi-item__text">
            <span class="kpi-item__value">{{ overview?.[c.key] ?? 0 }}</span>
            <span class="kpi-item__label">{{ c.label }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 左右分栏：待处理事项（可跳转） | 选课热度 -->
    <div class="dash-row">
      <el-card class="page-card" shadow="never">
        <template #header>
          <div class="card-head">
            <span>待处理事项</span>
            <span class="card-head__right">
              <el-tag v-if="pending.length" size="small" type="danger" effect="light" round>
                {{ pending.length }} 条待审
              </el-tag>
              <el-link type="primary" :underline="false" @click="router.push('/admin/grades')">
                去审核
              </el-link>
            </span>
          </div>
        </template>
        <el-empty
          v-if="!pending.length"
          description="暂无待审核成绩，审核队列已清空"
          :image-size="80"
        />
        <ul v-else class="task-list">
          <li
            v-for="g in pending.slice(0, 6)"
            :key="g.id"
            class="task-item"
            @click="router.push('/admin/grades')"
          >
            <span class="task-item__dot" />
            <div class="task-item__main">
              <span class="task-item__title">{{ g.course_name || '未命名课程' }}</span>
              <span class="task-item__sub">
                {{ g.student_name || '—' }} · {{ g.student_no || '—' }}
              </span>
            </div>
            <span class="task-item__meta">
              <span class="task-item__score">{{ g.total_score ?? '—' }}</span>
              <span class="task-item__time">
                {{ g.submitted_at?.slice(0, 16).replace('T', ' ') || '待提交' }}
              </span>
            </span>
          </li>
        </ul>
      </el-card>

      <el-card class="page-card" shadow="never">
        <template #header>
          <div class="card-head">
            <span>选课热度</span>
            <el-link type="primary" :underline="false" @click="router.push('/admin/statistics')">
              更多统计
            </el-link>
          </div>
        </template>
        <el-empty v-if="!ranking.length" description="本学期暂无选课数据" :image-size="80" />
        <div v-else class="rank-list">
          <div v-for="(r, i) in ranking" :key="r.course_name" class="rank-row">
            <span class="rank-name">
              <em class="rank-badge" :class="{ 'is-top': i < 3 }">{{ i + 1 }}</em>
              <span class="rank-name__text">{{ r.course_name }}</span>
            </span>
            <el-progress
              class="rank-bar"
              :percentage="Math.round((r.selected / (ranking[0]?.selected || 1)) * 100)"
              :stroke-width="10"
              :show-text="false"
            />
            <span class="rank-count">{{ r.selected }} 人</span>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 成绩概览 -->
    <el-card class="page-card overview-card" shadow="never">
      <template #header>
        <div class="card-head">
          <span>成绩概览</span>
          <el-link type="primary" :underline="false" @click="router.push('/admin/statistics')">
            数据统计
          </el-link>
        </div>
      </template>
      <el-empty v-if="!dist || !dist.count" description="暂无成绩数据" :image-size="80" />
      <template v-else>
        <div class="overview-stats">
          <div class="overview-stat">
            <span class="overview-stat__label">已发布成绩</span>
            <span class="overview-stat__value">{{ dist.count }}</span>
          </div>
          <div class="overview-stat">
            <span class="overview-stat__label">平均分</span>
            <span class="overview-stat__value">{{ (dist.average ?? 0).toFixed(2) }}</span>
          </div>
          <div class="overview-stat">
            <span class="overview-stat__label">及格率</span>
            <span class="overview-stat__value">{{ dist.pass_rate ?? 0 }}<i>%</i></span>
          </div>
        </div>

        <p class="section-title">分数段分布</p>
        <div class="dist">
          <div v-for="(n, k) in dist.distribution" :key="k" class="bar-row">
            <span class="bar-row__label">{{ k }}</span>
            <el-progress
              :percentage="dist.count ? Math.round((n / dist.count) * 100) : 0"
              :stroke-width="12"
            />
            <span class="bar-row__count">{{ n }}</span>
          </div>
        </div>
      </template>
    </el-card>
  </div>
</template>

<style scoped lang="scss">
/* ---------------------------------------------------- 关键指标条（KPI） */
.kpi-band {
  display: flex;
  align-items: stretch;
  gap: var(--uams-gap-lg);
  padding: 20px;
}

.kpi-hero {
  flex: 0 0 280px;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 18px 20px;
  border-radius: var(--uams-radius);
  background: var(--uams-primary-softer);
  border: 1px solid var(--uams-primary-soft);
  cursor: pointer;
  transition: box-shadow 0.16s ease;

  &:hover {
    box-shadow: var(--uams-shadow);
  }

  &__icon {
    flex: 0 0 46px;
    width: 46px;
    height: 46px;
    border-radius: var(--uams-radius-sm);
    display: grid;
    place-items: center;
    font-size: 24px;
    color: #fff;
    background: linear-gradient(135deg, var(--uams-primary), var(--uams-primary-light));
  }

  &__body {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  &__label {
    font-size: 13px;
    color: var(--uams-text-2);
  }

  &__value {
    font-size: 36px;
    font-weight: 700;
    line-height: 1.15;
    letter-spacing: 0.5px;
    color: var(--uams-text);
    font-variant-numeric: tabular-nums;
  }

  &__hint {
    font-size: 12px;
    color: var(--uams-text-3);
  }
}

.kpi-strip {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--uams-gap);
  align-items: center;
}

.kpi-item {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 12px 14px;
  border-radius: var(--uams-radius-sm);
  cursor: pointer;
  transition: background-color 0.16s ease, transform 0.16s ease;

  &:hover {
    background: var(--uams-surface-sunken);
    transform: translateY(-1px);
  }

  &__icon {
    flex: 0 0 34px;
    width: 34px;
    height: 34px;
    border-radius: var(--uams-radius-xs);
    display: grid;
    place-items: center;
    font-size: 17px;
    color: var(--uams-primary-dark);
    background: color-mix(in srgb, var(--uams-primary) 12%, transparent);
  }

  &__text {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  &__value {
    font-size: 20px;
    font-weight: 600;
    line-height: 1.2;
    color: var(--uams-text);
    font-variant-numeric: tabular-nums;
  }

  &__label {
    font-size: 12px;
    color: var(--uams-text-3);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

/* 每个指标用对应状态色做柔和着色（全部来自 token） */
.kpi-item--teachers .kpi-item__icon {
  color: var(--uams-success);
  background: color-mix(in srgb, var(--uams-success) 12%, transparent);
}

.kpi-item--courses .kpi-item__icon {
  color: var(--uams-warning);
  background: color-mix(in srgb, var(--uams-warning) 14%, transparent);
}

.kpi-item--teaching_classes .kpi-item__icon {
  color: var(--uams-primary-dark);
  background: color-mix(in srgb, var(--uams-primary) 12%, transparent);
}

.kpi-item--selections .kpi-item__icon {
  color: var(--uams-info);
  background: color-mix(in srgb, var(--uams-info) 12%, transparent);
}

.kpi-item--pending_grades .kpi-item__icon {
  color: var(--uams-danger);
  background: color-mix(in srgb, var(--uams-danger) 12%, transparent);
}

/* ------------------------------------------------------------ 通用头部 */
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;

  &__right {
    display: inline-flex;
    align-items: center;
    gap: 10px;
  }
}

/* --------------------------------------------------------- 左右分栏区块 */
.dash-row {
  display: grid;
  grid-template-columns: 1.35fr 1fr;
  gap: var(--uams-gap);
  margin-top: var(--uams-gap);

  /* 网格 gap 已负责间距，抵消全局相邻卡片外边距 */
  > .page-card + .page-card {
    margin-top: 0;
  }
}

/* 待处理事项列表 */
.task-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.task-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 12px;
  border-radius: var(--uams-radius-sm);
  cursor: pointer;
  transition: background-color 0.16s ease;

  &:hover {
    background: var(--uams-primary-softer);
  }

  &__dot {
    flex: 0 0 8px;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--uams-warning);
    box-shadow: 0 0 0 4px color-mix(in srgb, var(--uams-warning) 16%, transparent);
  }

  &__main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }

  &__title {
    font-size: 14px;
    font-weight: 500;
    color: var(--uams-text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  &__sub {
    font-size: 12px;
    color: var(--uams-text-3);
    margin-top: 2px;
  }

  &__meta {
    flex: 0 0 auto;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 2px;
  }

  &__score {
    font-size: 16px;
    font-weight: 600;
    color: var(--uams-text);
    font-variant-numeric: tabular-nums;
  }

  &__time {
    font-size: 11px;
    color: var(--uams-text-3);
  }
}

/* 选课热度 */
.rank-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rank-row {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr) 52px;
  align-items: center;
  gap: 12px;
}

.rank-name {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;

  &__text {
    font-size: 13px;
    color: var(--uams-text-2);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

.rank-badge {
  flex: 0 0 22px;
  width: 22px;
  height: 22px;
  border-radius: var(--uams-radius-xs);
  display: grid;
  place-items: center;
  font-size: 12px;
  font-style: normal;
  font-weight: 600;
  color: var(--uams-text-3);
  background: var(--uams-surface-sunken);
  border: 1px solid var(--uams-border);

  &.is-top {
    color: var(--uams-primary-dark);
    background: var(--uams-primary-soft);
    border-color: transparent;
  }
}

.rank-count {
  font-size: 12px;
  color: var(--uams-text-3);
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* ------------------------------------------------------------ 成绩概览 */
.overview-card {
  margin-top: var(--uams-gap);
}

.overview-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--uams-gap);
  margin-bottom: 20px;
}

.overview-stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px 16px;
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface-sunken);
  border: 1px solid var(--uams-border);

  &__label {
    font-size: 12px;
    color: var(--uams-text-3);
  }

  &__value {
    font-size: 26px;
    font-weight: 700;
    line-height: 1.15;
    color: var(--uams-text);
    font-variant-numeric: tabular-nums;

    i {
      margin-left: 2px;
      font-size: 14px;
      font-weight: 500;
      font-style: normal;
      color: var(--uams-text-3);
    }
  }
}

.bar-row {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr) 48px;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;

  &:last-child {
    margin-bottom: 0;
  }

  &__label {
    font-size: 13px;
    color: var(--uams-text-2);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  &__count {
    font-size: 12px;
    color: var(--uams-text-3);
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
}

/* ------------------------------------------------------------- 响应式 */
@media (max-width: 1024px) {
  .kpi-band {
    flex-direction: column;
    gap: var(--uams-gap);
  }

  .kpi-hero {
    flex: none;
  }

  .kpi-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .dash-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .kpi-band {
    padding: 14px;
  }

  .kpi-hero {
    padding: 16px;
  }

  .kpi-hero__value {
    font-size: 30px;
  }

  .kpi-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }

  .kpi-item {
    padding: 10px;
  }

  .overview-stats {
    gap: 10px;
  }

  .bar-row {
    grid-template-columns: 76px minmax(0, 1fr) 36px;
    gap: 8px;
  }

  /* 选课热度：课程名占整行，进度条与人数换行排布，避免横向挤压 */
  .rank-row {
    grid-template-columns: minmax(0, 1fr) auto;
    row-gap: 4px;
  }

  .rank-name {
    grid-column: 1 / -1;
  }

  .rank-bar {
    grid-column: 1;
  }

  .rank-count {
    grid-column: 2;
  }
}
</style>
