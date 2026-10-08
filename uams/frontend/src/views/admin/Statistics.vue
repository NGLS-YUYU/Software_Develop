<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import { statsApi } from '@/api'
import { currentSemester, semesterOptions } from '@/composables/useSemester'
import type { GradeStatistics, Overview } from '@/types'

const semester = ref(currentSemester())
const overview = ref<Overview | null>(null)
const dist = ref<GradeStatistics | null>(null)
const ranking = ref<{ course_name: string; selected: number }[]>([])
const loading = ref(false)

const OVERVIEW_ITEMS = [
  { key: 'colleges', label: '学院' }, { key: 'majors', label: '专业' },
  { key: 'classes', label: '班级' }, { key: 'students', label: '学生' },
  { key: 'teachers', label: '教师' }, { key: 'courses', label: '课程' },
  { key: 'teaching_classes', label: '教学班' }, { key: 'selections', label: '选课记录' },
] as const

async function load() {
  loading.value = true
  try {
    const [o, d, r] = await Promise.allSettled([
      statsApi.overview(),
      statsApi.gradeDistribution(semester.value),
      statsApi.selectionRanking(semester.value, 10),
    ])
    if (o.status === 'fulfilled') overview.value = o.value
    if (d.status === 'fulfilled') dist.value = d.value
    if (r.status === 'fulfilled') ranking.value = r.value
  } finally {
    loading.value = false
  }
}

watch(semester, load)
onMounted(load)
</script>

<template>
  <div v-loading="loading" class="stats">
    <!-- 顶栏 + 全校概览：紧凑指标条（非一组同质数字卡） -->
    <section class="page-card">
      <div class="toolbar">
        <el-select v-model="semester" style="width: 180px">
          <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
        </el-select>
        <el-button type="primary" @click="load">刷新</el-button>
        <div class="spacer" />
        <span class="muted toolbar-hint">切换学期查看对应统计</span>
      </div>

      <p class="section-title">全校概览</p>
      <div class="metric-strip">
        <div
          v-for="i in OVERVIEW_ITEMS"
          :key="i.key"
          class="metric"
          :class="{ 'is-hero': i.key === 'students' }"
        >
          <span class="metric__value">{{ overview?.[i.key] ?? 0 }}</span>
          <span class="metric__label">{{ i.label }}</span>
        </div>
      </div>
    </section>

    <!-- 成绩分布 | 选课热度排行 -->
    <div class="analysis-row">
      <el-card shadow="never" class="page-card">
        <template #header>
          <div class="card-head">
            <span>成绩分布</span>
            <el-tag size="small" type="info" effect="plain">{{ semester }}</el-tag>
          </div>
        </template>

        <el-empty v-if="!dist?.count" description="该学期暂无成绩数据" :image-size="70" />
        <template v-else>
          <div class="mini-stats">
            <div class="mini">
              <span class="mini__value">{{ dist.count }}</span>
              <span class="mini__label">成绩条数</span>
            </div>
            <div class="mini">
              <span class="mini__value">{{ (dist.average ?? 0).toFixed(2) }}</span>
              <span class="mini__label">平均分</span>
            </div>
            <div class="mini">
              <span class="mini__value">{{ dist.pass_rate ?? 0 }}<i>%</i></span>
              <span class="mini__label">及格率</span>
            </div>
          </div>

          <div class="bars">
            <div v-for="(n, k) in dist.distribution" :key="k" class="bar-row">
              <span class="bar-row__label">{{ k }}</span>
              <div class="bar">
                <span
                  class="bar__fill"
                  :style="{ width: (dist.count ? Math.round((n / dist.count) * 100) : 0) + '%' }"
                />
              </div>
              <span class="bar-row__count">
                {{ n }}
                <em>{{ dist.count ? Math.round((n / dist.count) * 100) : 0 }}%</em>
              </span>
            </div>
          </div>
        </template>
      </el-card>

      <el-card shadow="never" class="page-card">
        <template #header>
          <div class="card-head">
            <span>选课热度 Top 10</span>
            <el-tag size="small" type="info" effect="plain">{{ semester }}</el-tag>
          </div>
        </template>

        <el-empty v-if="!ranking.length" description="该学期暂无选课数据" :image-size="70" />
        <ol v-else class="rank-list">
          <li v-for="(r, i) in ranking" :key="r.course_name" class="rank-row">
            <span class="rank-badge" :class="{ 'is-top': i < 3 }">{{ i + 1 }}</span>
            <span class="rank-name" :title="r.course_name">{{ r.course_name }}</span>
            <div class="bar bar--rank">
              <span
                class="bar__fill"
                :style="{ width: Math.round((r.selected / (ranking[0]?.selected || 1)) * 100) + '%' }"
              />
            </div>
            <span class="rank-count">{{ r.selected }}<em>人</em></span>
          </li>
        </ol>
      </el-card>
    </div>
  </div>
</template>

<style scoped lang="scss">
.toolbar-hint {
  font-size: 12px;
}

/* --------------------------------------------------- 全校概览：紧凑指标条 */
.metric-strip {
  display: grid;
  grid-template-columns: repeat(8, minmax(0, 1fr));
  gap: 1px;
  background: var(--uams-border);
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  overflow: hidden;
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  padding: 14px 16px;
  background: var(--uams-surface);

  &__value {
    font-size: 24px;
    font-weight: 700;
    line-height: 1.1;
    letter-spacing: -0.3px;
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

  /* 学生数为全校头号指标，做轻微强调 */
  &.is-hero {
    background: var(--uams-primary-softer);

    .metric__value {
      color: var(--uams-primary-dark);
    }
  }
}

/* ------------------------------------------------------------ 通用头部 */
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

/* ------------------------------------------------------------ 左右分析区 */
.analysis-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--uams-gap);
  margin-top: var(--uams-gap);

  > .page-card + .page-card {
    margin-top: 0;
  }
}

/* 成绩分布的三个关键值：横向紧凑格 */
.mini-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 18px;
}

.mini {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 12px 14px;
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface-sunken);
  border: 1px solid var(--uams-border);

  &__value {
    font-size: 22px;
    font-weight: 700;
    line-height: 1.15;
    color: var(--uams-text);
    font-variant-numeric: tabular-nums;

    i {
      margin-left: 1px;
      font-size: 13px;
      font-weight: 500;
      font-style: normal;
      color: var(--uams-text-3);
    }
  }

  &__label {
    font-size: 12px;
    color: var(--uams-text-3);
  }
}

/* 纯 CSS 条形：统一轨道 + 主色填充 */
.bar {
  height: 10px;
  border-radius: 999px;
  background: var(--uams-surface-sunken);
  border: 1px solid var(--uams-border);
  overflow: hidden;

  &__fill {
    display: block;
    height: 100%;
    border-radius: 999px;
    background: var(--uams-primary);
    transition: width 0.3s ease;
  }

  &--rank {
    height: 8px;
  }
}

.bars {
  display: flex;
  flex-direction: column;
  gap: 11px;
}

.bar-row {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr) 78px;
  align-items: center;
  gap: 12px;

  &__label {
    font-size: 13px;
    color: var(--uams-text-2);
    font-variant-numeric: tabular-nums;
  }

  &__count {
    display: flex;
    align-items: baseline;
    justify-content: flex-end;
    gap: 6px;
    font-size: 13px;
    font-weight: 600;
    color: var(--uams-text);
    font-variant-numeric: tabular-nums;

    em {
      font-style: normal;
      font-size: 11px;
      font-weight: 500;
      color: var(--uams-text-3);
    }
  }
}

/* 选课热度：带序号的排行列表 */
.rank-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rank-row {
  display: grid;
  grid-template-columns: 24px minmax(0, 1.2fr) minmax(0, 1fr) 56px;
  align-items: center;
  gap: 12px;
}

.rank-badge {
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  border-radius: var(--uams-radius-xs);
  font-size: 12px;
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

.rank-name {
  min-width: 0;
  font-size: 13px;
  color: var(--uams-text-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rank-count {
  font-size: 13px;
  font-weight: 600;
  color: var(--uams-text);
  text-align: right;
  font-variant-numeric: tabular-nums;

  em {
    margin-left: 2px;
    font-style: normal;
    font-size: 11px;
    font-weight: 500;
    color: var(--uams-text-3);
  }
}

/* ------------------------------------------------------------- 响应式 */
@media (max-width: 1024px) {
  .metric-strip {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .analysis-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .toolbar-hint {
    display: none;
  }

  .metric-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .metric {
    padding: 12px 14px;

    &.is-hero .metric__value {
      font-size: 26px;
    }
  }

  .mini-stats {
    gap: 8px;
  }

  .mini {
    padding: 10px;

    &__value {
      font-size: 19px;
    }
  }

  .bar-row {
    grid-template-columns: 52px minmax(0, 1fr) 60px;
    gap: 8px;
  }

  /* 排行：课程名独占首行，条形与人数次行，避免横向挤压 */
  .rank-row {
    grid-template-columns: 24px minmax(0, 1fr) auto;
    row-gap: 6px;
  }

  .rank-name {
    grid-column: 2 / -1;
  }

  .bar--rank {
    grid-column: 2;
  }

  .rank-count {
    grid-column: 3;
  }
}
</style>
