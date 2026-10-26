<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { gradeApi } from '@/api'
import { semesterOptions } from '@/composables/useSemester'
import type { Grade, GradeSummary, StudentGradeOverview } from '@/types'

const semester = ref<string | undefined>(undefined)
const grades = ref<Grade[]>([])
const summary = ref<GradeSummary | null>(null)
const ranks = ref<Pick<StudentGradeOverview, 'class_rank' | 'major_rank'>>({
  class_rank: null,
  major_rank: null,
})
const loading = ref(false)

/** 按学期分组展示，便于查看每学期表现。 */
const grouped = computed(() => {
  const map = new Map<string, Grade[]>()
  for (const g of grades.value) {
    const arr = map.get(g.semester) ?? []
    arr.push(g)
    map.set(g.semester, arr)
  }
  return [...map.entries()].sort((a, b) => b[0].localeCompare(a[0]))
})

function semesterCredits(rows: Grade[]) {
  return rows.filter((r) => r.is_passed).reduce((s, r) => s + Number(r.credits), 0)
}

function scoreType(g: Grade) {
  const s = Number(g.total_score ?? 0)
  if (s >= 90) return 'success'
  if (s >= 60) return ''
  return 'danger'
}

async function load() {
  loading.value = true
  try {
    const [mine, sum, overview] = await Promise.all([
      gradeApi.mine(semester.value),
      gradeApi.mySummary(),
      gradeApi.my(),
    ])
    grades.value = mine
    summary.value = sum
    ranks.value = {
      class_rank: overview.class_rank,
      major_rank: overview.major_rank,
    }
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="grades">
    <!-- 成绩概览：GPA / 已修学分 / 班级排名 / 专业排名 -->
    <el-card shadow="never" class="page-card overview">
      <div class="overview__grid">
        <div class="ov">
          <span class="ov__value is-primary">
            {{ summary?.gpa != null ? Number(summary.gpa).toFixed(2) : '—' }}
          </span>
          <span class="ov__label">平均绩点 GPA</span>
        </div>
        <div class="ov">
          <span class="ov__value">{{ summary ? summary.total_credits : '—' }}</span>
          <span class="ov__label">已修学分</span>
        </div>
        <div class="ov">
          <span class="ov__value">{{ ranks.class_rank ?? '—' }}</span>
          <span class="ov__label">班级排名</span>
        </div>
        <div class="ov">
          <span class="ov__value">{{ ranks.major_rank ?? '—' }}</span>
          <span class="ov__label">专业排名</span>
        </div>
      </div>
      <div class="overview__meta muted">
        <span>已修课程 <b>{{ summary?.total_courses ?? 0 }}</b> 门</span>
        <span>通过 <b>{{ summary?.passed_courses ?? 0 }}</b> 门</span>
        <span>不及格 <b>{{ summary?.failed_courses ?? 0 }}</b> 门</span>
      </div>
    </el-card>

    <!-- 成绩明细 -->
    <el-card shadow="never" class="page-card">
      <div class="toolbar">
        <el-select
          v-model="semester"
          clearable
          placeholder="全部学期"
          style="width: 180px"
          @change="load"
        >
          <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
        </el-select>
        <div class="spacer" />
        <el-text size="small" type="info">仅显示教务审核通过的成绩</el-text>
      </div>

      <el-empty v-if="!grades.length" description="暂无已发布的成绩" />

      <div v-for="[sem, rows] in grouped" :key="sem" class="sem-block">
        <div class="sem-head">
          <span class="section-title">{{ sem }}</span>
          <el-tag size="small" type="info" effect="plain">
            {{ rows.length }} 门 · {{ semesterCredits(rows) }} 学分
          </el-tag>
        </div>

        <!-- 桌面端：表格（课程 → 原始成绩 → 计算结果 → 总评/绩点 → 结果） -->
        <div class="table-wrap">
          <el-table :data="rows" stripe size="small">
            <el-table-column label="课程" min-width="160" fixed>
              <template #default="{ row }">
                <div class="cell-course">
                  <span class="cell-course__name">{{ row.course_name }}</span>
                  <span class="cell-course__meta">
                    {{ row.course_code }} · {{ row.credits }} 学分
                  </span>
                </div>
              </template>
            </el-table-column>

            <el-table-column label="原始成绩" align="center">
              <el-table-column label="平时" width="60" align="center">
                <template #default="{ row }">
                  <span class="cell-dim">{{ row.regular_score ?? '—' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="期中理论" width="72" align="center">
                <template #default="{ row }">
                  <span class="cell-dim">{{ row.mid_theory_score ?? row.mid_score ?? '—' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="期中实践" width="72" align="center">
                <template #default="{ row }">
                  <span class="cell-dim">{{ row.mid_practice_score ?? '—' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="期末理论" width="72" align="center">
                <template #default="{ row }">
                  <span class="cell-dim">{{ row.final_theory_score ?? row.final_score ?? '—' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="期末实践" width="72" align="center">
                <template #default="{ row }">
                  <span class="cell-dim">{{ row.final_practice_score ?? '—' }}</span>
                </template>
              </el-table-column>
            </el-table-column>

            <el-table-column label="计算结果" align="center">
              <el-table-column label="理论总评" width="74" align="center">
                <template #default="{ row }">
                  <span class="cell-mid">{{ row.theory_total_score ?? '—' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="实践总评" width="74" align="center">
                <template #default="{ row }">
                  <span class="cell-mid">{{ row.practice_total_score ?? '—' }}</span>
                </template>
              </el-table-column>
            </el-table-column>

            <el-table-column label="补考" align="center">
              <el-table-column label="理论" width="58" align="center">
                <template #default="{ row }">
                  <span class="cell-dim">{{ row.theory_makeup_score ?? '—' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="实践" width="58" align="center">
                <template #default="{ row }">
                  <span class="cell-dim">{{ row.practice_makeup_score ?? '—' }}</span>
                </template>
              </el-table-column>
            </el-table-column>

            <el-table-column label="总评" width="82" align="center">
              <template #default="{ row }">
                <el-tag class="cell-total" :type="scoreType(row)" size="small">
                  {{ row.total_score ?? '—' }}
                </el-tag>
              </template>
            </el-table-column>

            <el-table-column label="绩点" width="70" align="center">
              <template #default="{ row }">
                <span class="cell-gp">{{ row.grade_point ?? '—' }}</span>
              </template>
            </el-table-column>

            <el-table-column label="结果" width="82" align="center">
              <template #default="{ row }">
                <el-tag :type="row.is_passed ? 'success' : 'danger'" size="small">
                  {{ row.is_passed ? '通过' : '不及格' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 移动端：每门课一张卡片 -->
        <div class="grade-cards">
          <article v-for="row in rows" :key="row.id" class="gcard">
            <header class="gcard__head">
              <div class="gcard__title">
                <span class="gcard__name">{{ row.course_name }}</span>
                <span class="gcard__sub">{{ row.course_code }} · {{ row.credits }} 学分</span>
              </div>
              <el-tag :type="row.is_passed ? 'success' : 'danger'" size="small">
                {{ row.is_passed ? '通过' : '不及格' }}
              </el-tag>
            </header>

            <div class="gcard__scores">
              <div class="gcard__score is-total">
                <span class="gcard__score-num">{{ row.total_score ?? '—' }}</span>
                <span class="gcard__score-label">成绩总评</span>
              </div>
              <div class="gcard__score is-gp">
                <span class="gcard__score-num">{{ row.grade_point ?? '—' }}</span>
                <span class="gcard__score-label">绩点</span>
              </div>
            </div>

            <dl class="gcard__dl">
              <div><dt>平时</dt><dd>{{ row.regular_score ?? '—' }}</dd></div>
              <div><dt>期中理论</dt><dd>{{ row.mid_theory_score ?? row.mid_score ?? '—' }}</dd></div>
              <div><dt>期中实践</dt><dd>{{ row.mid_practice_score ?? '—' }}</dd></div>
              <div><dt>期末理论</dt><dd>{{ row.final_theory_score ?? row.final_score ?? '—' }}</dd></div>
              <div><dt>期末实践</dt><dd>{{ row.final_practice_score ?? '—' }}</dd></div>
              <div><dt>理论总评</dt><dd>{{ row.theory_total_score ?? '—' }}</dd></div>
              <div><dt>实践总评</dt><dd>{{ row.practice_total_score ?? '—' }}</dd></div>
              <div><dt>理论补考</dt><dd>{{ row.theory_makeup_score ?? '—' }}</dd></div>
              <div><dt>实践补考</dt><dd>{{ row.practice_makeup_score ?? '—' }}</dd></div>
            </dl>
          </article>
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped lang="scss">
/* ------------------------------------------------------------- 概览条 */
.overview {
  background: linear-gradient(160deg, var(--uams-primary-softer) 0%, var(--uams-surface) 62%);
}

.overview__grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.ov {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 4px 20px;
  border-left: 1px solid var(--uams-border);

  &:first-child {
    padding-left: 0;
    border-left: none;
  }

  &__value {
    font-size: 30px;
    font-weight: 700;
    line-height: 1.05;
    letter-spacing: -0.5px;
    color: var(--uams-text);
    font-variant-numeric: tabular-nums;

    &.is-primary {
      color: var(--uams-primary-dark);
    }
  }

  &__label {
    font-size: 12px;
    color: var(--uams-text-3);
  }
}

.overview__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 20px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--uams-border);
  font-size: 13px;

  b {
    color: var(--uams-text);
  }
}

/* ------------------------------------------------------------- 明细区 */
.sem-block + .sem-block {
  margin-top: 24px;
}

.sem-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;

  .section-title {
    margin: 0;
  }
}

/* 课程单元格：名称主、代码/学分次 */
.cell-course {
  display: flex;
  flex-direction: column;
  line-height: 1.35;

  &__name {
    font-weight: 600;
    color: var(--uams-text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__meta {
    font-size: 12px;
    color: var(--uams-text-3);
  }
}

/* 次要数字：弱化色调，避免与总评抢视线 */
.cell-dim {
  color: var(--uams-text-3);
  font-variant-numeric: tabular-nums;
}

/* 计算结果：中等强调 */
.cell-mid {
  color: var(--uams-text-2);
  font-variant-numeric: tabular-nums;
}

/* 总评：重点突出 */
.cell-total {
  font-size: 14px;
  font-weight: 700;
  padding: 3px 10px;
}

/* 绩点：淡紫药丸 */
.cell-gp {
  display: inline-block;
  min-width: 38px;
  padding: 2px 8px;
  border-radius: var(--uams-radius-xs);
  background: var(--uams-primary-soft);
  color: var(--uams-primary-dark);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

/* --------------------------------------------------------- 移动端卡片 */
.grade-cards {
  display: none;
  flex-direction: column;
  gap: 12px;
}

.gcard {
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

  &__title {
    min-width: 0;
  }

  &__name {
    font-weight: 600;
    color: var(--uams-text);
  }

  &__sub {
    display: block;
    margin-top: 2px;
    font-size: 12px;
    color: var(--uams-text-3);
  }

  /* 卡片主视觉：成绩总评 + 绩点 */
  &__scores {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    padding: 14px;
  }

  &__score {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 10px;
    border-radius: var(--uams-radius-sm);
    background: var(--uams-surface-sunken);
    border: 1px solid var(--uams-border);

    &.is-total {
      background: var(--uams-primary-soft);
      border-color: transparent;
    }

    &-num {
      font-size: 26px;
      font-weight: 700;
      line-height: 1.1;
      color: var(--uams-text);
      font-variant-numeric: tabular-nums;
    }

    &.is-total &-num,
    &.is-gp &-num {
      color: var(--uams-primary-dark);
    }

    &-label {
      font-size: 12px;
      color: var(--uams-text-3);
    }
  }

  /* 明细：小标签 + 数字，成对分格 */
  &__dl {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    margin: 0;
    padding: 0 14px 14px;

    > div {
      display: flex;
      flex-direction: column;
      gap: 2px;
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
      font-weight: 600;
      color: var(--uams-text);
      font-variant-numeric: tabular-nums;
    }
  }
}

/* ------------------------------------------------------------- 响应式 */
@media (max-width: 1024px) {
  .ov {
    padding: 4px 14px;

    &__value {
      font-size: 26px;
    }
  }
}

@media (max-width: 768px) {
  /* 概览改为一格一卡，弱化分隔线 */
  .overview__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }

  .ov {
    padding: 12px;
    border: 1px solid var(--uams-border);
    border-radius: var(--uams-radius-sm);
    background: var(--uams-surface);

    &:first-child {
      padding: 12px;
    }

    &__value {
      font-size: 24px;
    }
  }

  /* 表格换成卡片列表 */
  .table-wrap {
    display: none;
  }

  .grade-cards {
    display: flex;
  }

  .sem-block + .sem-block {
    margin-top: 20px;
  }
}

@media (max-width: 420px) {
  .overview__grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
