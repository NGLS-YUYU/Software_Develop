<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { examApi } from '@/api'
import { currentSemester, semesterOptions } from '@/composables/useSemester'
import type { Exam } from '@/types'

const semester = ref(currentSemester())
const exams = ref<Exam[]>([])
const loading = ref(false)

const TYPE: Record<string, string> = { FINAL: '期末考试', MAKEUP: '补考', RETAKE: '重修' }

function daysLeft(d: string) {
  const diff = Math.ceil(
    (new Date(d).getTime() - new Date(new Date().toDateString()).getTime()) / 86400000,
  )
  return diff
}

async function load() {
  loading.value = true
  try {
    exams.value = await examApi.mine(semester.value)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <el-card class="page-card" shadow="never" v-loading="loading">
    <div class="toolbar">
      <el-select v-model="semester" style="width: 180px" @change="load">
        <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
      </el-select>
      <div class="spacer" />
      <el-text size="small" type="info">仅显示已发布的考试安排</el-text>
    </div>

    <el-empty v-if="!exams.length" description="暂无考试安排" />

    <div v-else class="exam-groups">
      <template v-for="(row, i) in exams" :key="row.id">
        <!-- 按日期分组：数据已按考试日期升序，仅在日期变化处插入分组标题 -->
        <div
          v-if="i === 0 || exams[i - 1].exam_date !== row.exam_date"
          class="exam-date"
        >
          <span class="exam-date__dot" />
          <span class="exam-date__label">{{ row.exam_date }}</span>
          <span class="exam-date__rule" />
        </div>

        <article
          class="exam"
          :class="{
            'is-past': daysLeft(row.exam_date) < 0,
            'is-soon': daysLeft(row.exam_date) >= 0 && daysLeft(row.exam_date) <= 7,
          }"
        >
          <div class="exam__time">
            <span class="exam__clock">
              {{ row.start_time?.slice(0, 5) }}<i class="exam__sep">–</i>{{ row.end_time?.slice(0, 5) }}
            </span>
            <span class="exam__duration">{{ row.duration_minutes }} 分钟</span>
          </div>

          <div class="exam__main">
            <div class="exam__head">
              <h3 class="exam__course">{{ row.course_name }}</h3>
              <el-tag size="small" effect="plain">{{ TYPE[row.exam_type] ?? row.exam_type }}</el-tag>
            </div>
            <div class="exam__meta">
              <span class="exam__meta-item">
                <el-icon><component :is="'Location'" /></el-icon>
                <span class="exam__meta-label">考场</span>
                <span class="exam__meta-value">{{ row.classroom_code ?? '待定' }}</span>
              </span>
              <span class="exam__meta-item">
                <el-icon><component :is="'Tickets'" /></el-icon>
                <span class="exam__meta-label">座位号</span>
                <span class="exam__meta-value">{{ row.seat_no ?? '—' }}</span>
              </span>
            </div>
          </div>

          <div class="exam__countdown">
            <el-tag
              v-if="daysLeft(row.exam_date) >= 0"
              :type="daysLeft(row.exam_date) <= 7 ? 'warning' : 'info'"
              size="small"
              effect="plain"
            >
              {{ daysLeft(row.exam_date) === 0 ? '今天' : `${daysLeft(row.exam_date)} 天后` }}
            </el-tag>
            <span v-else class="exam__past">已结束</span>
          </div>
        </article>
      </template>
    </div>
  </el-card>
</template>

<style scoped>
.exam-groups {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* ---------------------------------------------------- 日期分组标题（时间线节点） */
.exam-date {
  display: flex;
  align-items: center;
  gap: 10px;
}

.exam-date:not(:first-child) {
  margin-top: 14px;
}

.exam-date__dot {
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: var(--uams-primary);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--uams-primary) 12%, transparent);
}

.exam-date__label {
  font-size: 14px;
  font-weight: 600;
  color: var(--uams-text);
  font-variant-numeric: tabular-nums;
}

.exam-date__rule {
  flex: 1;
  height: 1px;
  min-width: 12px;
  background: var(--uams-border);
}

/* ------------------------------------------------------------ 单场考试卡片 */
.exam {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr) auto;
  align-items: center;
  gap: 16px;
  padding: 14px 16px;
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface);
  box-shadow: var(--uams-shadow-sm);
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease;
}

.exam:hover {
  border-color: var(--uams-border-strong);
  box-shadow: var(--uams-shadow);
}

/* 已结束：整体降调，不喧宾夺主 */
.exam.is-past {
  opacity: 0.6;
}

/* 临近考试（≤7 天）：用 warning 轻微提亮，保持柔和 */
.exam.is-soon {
  border-color: color-mix(in srgb, var(--uams-warning) 38%, var(--uams-border));
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--uams-warning) 6%, var(--uams-surface)) 0%,
    var(--uams-surface) 70%
  );
}

/* -------------------------------------------------------------- 时间区块 */
.exam__time {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-right: 16px;
  border-right: 1px dashed var(--uams-border);
}

.exam__clock {
  font-size: 15px;
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: 0.2px;
  color: var(--uams-primary-dark);
  font-variant-numeric: tabular-nums;
}

.exam__sep {
  font-style: normal;
  margin: 0 2px;
  font-weight: 500;
  color: var(--uams-text-3);
}

.exam__duration {
  font-size: 11px;
  color: var(--uams-text-3);
}

/* ------------------------------------------------------ 课程 + 地点/座位 */
.exam__main {
  min-width: 0;
}

.exam__head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.exam__course {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--uams-text);
}

.exam__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 18px;
  margin-top: 7px;
}

.exam__meta-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
}

.exam__meta-item .el-icon {
  font-size: 15px;
  color: var(--uams-primary);
}

.exam__meta-label {
  color: var(--uams-text-3);
}

.exam__meta-value {
  color: var(--uams-text);
  font-weight: 600;
}

/* -------------------------------------------------------------- 倒计时 */
.exam__countdown {
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

.exam__past {
  font-size: 12px;
  color: var(--uams-text-3);
}

/* -------------------------------------------------------------- 响应式 */
@media (max-width: 768px) {
  .exam {
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas:
      'time count'
      'main main';
    gap: 8px 12px;
    padding: 13px 14px;
  }

  .exam__time {
    grid-area: time;
    flex-direction: row;
    align-items: baseline;
    gap: 8px;
    padding-right: 0;
    border-right: none;
  }

  .exam__main {
    grid-area: main;
  }

  .exam__countdown {
    grid-area: count;
  }

  .exam-date__label {
    font-size: 13px;
  }
}

@media (max-width: 420px) {
  .exam__meta {
    gap: 4px 14px;
  }
}
</style>
