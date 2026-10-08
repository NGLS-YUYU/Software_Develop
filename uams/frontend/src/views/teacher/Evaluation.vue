<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { evaluationApi } from '@/api'
import type { EvaluationStats } from '@/types'

const stats = ref<EvaluationStats[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    stats.value = await evaluationApi.statistics()
  } finally {
    loading.value = false
  }
}

function level(avg?: number | null) {
  const v = Number(avg ?? 0)
  if (v >= 90) return { text: '优秀', type: 'success' }
  if (v >= 80) return { text: '良好', type: '' }
  if (v >= 70) return { text: '合格', type: 'warning' }
  return { text: '待改进', type: 'danger' }
}

// 纯展示用：仅对返回结果做计数汇总，不自行定义新的评价口径。
// 平均分一律展示后端每门课给出的 average（权威值），前端不做加权合成。
const overall = computed(() => {
  const count = stats.value.reduce((sum, s) => sum + s.count, 0)
  return { count, courses: stats.value.length }
})

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="eval">
    <el-alert
      title="学生评价匿名提交，此处仅展示聚合结果，无法查看具体评价人"
      type="info"
      :closable="false"
      show-icon
      class="notice"
    />

    <el-empty v-if="!stats.length" description="暂无评价数据" />

    <template v-else>
      <!-- 总览：综合平均分突出 + 各教学班评分分布 -->
      <el-card class="page-card overview" shadow="never">
        <template #header>
          <div class="card-head">
            <span class="card-head__title">
              <el-icon><component :is="'Trophy'" /></el-icon> 评教总览
            </span>
            <span class="muted card-head__hint">满分 100 分</span>
          </div>
        </template>

        <div class="hero">
          <div class="hero__score">
            <div class="hero__label muted">评价概览</div>
            <div class="hero__value">
              {{ overall.count }}<span class="hero__unit">份评价</span>
            </div>
            <span class="muted hero__hint">分数以各教学班为准（下表）</span>
          </div>

          <div class="hero__stats">
            <div class="hero__stat">
              <span class="hero__stat-icon"><el-icon><component :is="'Reading'" /></el-icon></span>
              <span class="hero__stat-body">
                <span class="hero__stat-num">{{ stats.length }}</span>
                <span class="hero__stat-label muted">教学班</span>
              </span>
            </div>
            <div class="hero__stat">
              <span class="hero__stat-icon"><el-icon><component :is="'User'" /></el-icon></span>
              <span class="hero__stat-body">
                <span class="hero__stat-num">{{ overall.count }}</span>
                <span class="hero__stat-label muted">评价份数</span>
              </span>
            </div>
          </div>
        </div>

        <div class="dist">
          <div class="section-title">各教学班评分分布</div>
          <ul class="dist__list">
            <li v-for="s in stats" :key="s.teaching_class_id" class="dist__row">
              <span class="dist__name">{{ s.course_name }}</span>
              <el-progress
                class="dist__bar"
                :percentage="Math.round(Number(s.average ?? 0))"
                :stroke-width="8"
                :show-text="false"
              />
              <span class="dist__val">{{ Number(s.average ?? 0).toFixed(1) }}</span>
            </li>
          </ul>
        </div>
      </el-card>

      <!-- 逐教学班明细 -->
      <div class="grid">
        <el-card
          v-for="s in stats"
          :key="s.teaching_class_id"
          class="page-card cls"
          shadow="never"
        >
          <template #header>
            <div class="cls__head">
              <div class="cls__title-wrap">
                <span class="cls__title">{{ s.course_name }}</span>
                <span class="cls__code muted">{{ s.teaching_class_code }}</span>
              </div>
              <div class="cls__tags">
                <el-tag size="small" type="info" effect="plain">{{ s.count }} 人评价</el-tag>
                <el-tag size="small" :type="level(s.average).type as any" effect="light">
                  {{ level(s.average).text }}
                </el-tag>
              </div>
            </div>
          </template>

          <div class="cls__score">
            <div class="cls__avg">
              <span class="cls__avg-num">{{ Number(s.average ?? 0).toFixed(2) }}</span>
              <span class="cls__avg-unit muted">平均分</span>
            </div>
            <el-progress
              class="cls__prog"
              :percentage="Math.round(Number(s.average ?? 0))"
              :stroke-width="10"
              :show-text="false"
            />
          </div>

          <div v-if="s.comments.length" class="cls__comments">
            <div class="section-title">学生评语</div>
            <ul class="comments">
              <li v-for="(c, i) in s.comments" :key="i">
                <el-icon class="comments__icon"><component :is="'ChatDotSquare'" /></el-icon>
                <span class="comments__text">{{ c }}</span>
              </li>
            </ul>
          </div>
          <div v-else class="cls__empty muted">该教学班暂无文字评语</div>
        </el-card>
      </div>
    </template>
  </div>
</template>

<style scoped>
.eval {
  display: block;
}

/* ------------------------------------------------------------------ 匿名提示 */
.notice {
  margin-bottom: var(--uams-gap);
  border-radius: var(--uams-radius);
}

/* ---------------------------------------------------------------- 卡片头统一 */
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.card-head__title {
  display: inline-flex;
  align-items: center;
  gap: 6px;

  .el-icon {
    color: var(--uams-primary);
  }
}

.card-head__hint {
  font-size: 12px;
  font-weight: 400;
}

/* -------------------------------------------------------------------- 总览 */
.hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--uams-gap-lg);
}

.hero__label {
  font-size: 12px;
}

.hero__value {
  font-size: 44px;
  font-weight: 700;
  line-height: 1.1;
  letter-spacing: -0.5px;
  color: var(--uams-primary-dark);
  margin: 2px 0 8px;
}

.hero__hint {
    display: block;
    margin-top: 6px;
    font-size: 12px;
  }

.hero__unit {
  font-size: 15px;
  font-weight: 500;
  color: var(--uams-text-3);
  margin-left: 4px;
}

.hero__stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(120px, 1fr));
  gap: var(--uams-gap);
}

.hero__stat {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface-sunken);
}

.hero__stat-icon {
  width: 36px;
  height: 36px;
  flex: 0 0 36px;
  border-radius: var(--uams-radius-xs);
  display: grid;
  place-items: center;
  font-size: 18px;
  color: var(--uams-primary-dark);
  background: var(--uams-primary-soft);
}

.hero__stat-body {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
  min-width: 0;
}

.hero__stat-num {
  font-size: 20px;
  font-weight: 700;
  color: var(--uams-text);
}

.hero__stat-label {
  font-size: 12px;
  white-space: nowrap;
}

.hero__bar {
  margin-top: var(--uams-gap-lg);
}

/* ------------------------------------------------------------ 评分分布条形 */
.dist {
  margin-top: var(--uams-gap-lg);
  padding-top: var(--uams-gap);
  border-top: 1px solid var(--uams-border);
}

.dist__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dist__row {
  display: grid;
  grid-template-columns: minmax(96px, 190px) minmax(0, 1fr) 46px;
  align-items: center;
  gap: var(--uams-gap);
}

.dist__name {
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
  color: var(--uams-text-2);
}

.dist__val {
  font-size: 13px;
  font-weight: 600;
  color: var(--uams-primary-dark);
  text-align: right;
}

/* ------------------------------------------------------------ 教学班明细网格 */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: var(--uams-gap);
  margin-top: var(--uams-gap);
}

.cls__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.cls__title-wrap {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}

.cls__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--uams-text);
}

.cls__code {
  font-size: 12px;
}

.cls__tags {
  display: inline-flex;
  gap: 8px;
  flex: 0 0 auto;
}

.cls__score {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: var(--uams-gap);
}

.cls__avg {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
  flex: 0 0 auto;
}

.cls__avg-num {
  font-size: 30px;
  font-weight: 700;
  line-height: 1;
  color: var(--uams-primary-dark);
}

.cls__avg-unit {
  font-size: 12px;
}

.cls__comments {
  margin-top: var(--uams-gap);
}

.cls__comments .section-title {
  margin-bottom: 10px;
}

.comments {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.comments li {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface-sunken);
  border: 1px solid var(--uams-border);
  font-size: 13px;
  line-height: 1.6;
  color: var(--uams-text-2);
}

.comments__icon {
  flex: 0 0 auto;
  margin-top: 3px;
  color: var(--uams-primary-light);
}

.comments__text {
  min-width: 0;
  word-break: break-word;
}

.cls__empty {
  margin-top: var(--uams-gap);
  font-size: 13px;
}

/* -------------------------------------------------------------------- 响应式 */
@media (max-width: 768px) {
  .hero {
    grid-template-columns: 1fr;
    gap: var(--uams-gap);
  }

  .hero__value {
    font-size: 38px;
  }

  .hero__stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .hero__bar {
    margin-top: var(--uams-gap);
  }

  .dist {
    margin-top: var(--uams-gap);
  }

  /* 分布行：名称/分数一行，进度条整行铺满，避免横向挤压 */
  .dist__row {
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas:
      'name val'
      'bar bar';
    gap: 4px 10px;
  }

  .dist__name {
    grid-area: name;
  }

  .dist__val {
    grid-area: val;
  }

  .dist__bar {
    grid-area: bar;
  }

  .grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 420px) {
  .hero__stats {
    grid-template-columns: 1fr;
  }

  .cls__avg-num {
    font-size: 26px;
  }
}
</style>
