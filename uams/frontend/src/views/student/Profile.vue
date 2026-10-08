<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { gradeApi, studentApi } from '@/api'
import type { GradeSummary, Student } from '@/types'

const profile = ref<Student | null>(null)
const summary = ref<GradeSummary | null>(null)
const loading = ref(true)

const GENDER: Record<string, string> = { MALE: '男', FEMALE: '女', UNKNOWN: '未填写' }
const STATUS: Record<string, string> = {
  ENROLLED: '在读',
  SUSPENDED: '休学',
  GRADUATED: '毕业',
  WITHDRAWN: '退学',
}

onMounted(async () => {
  try {
    profile.value = await studentApi.me()
    summary.value = await gradeApi.mySummary()
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div v-loading="loading" class="profile">
    <!-- 身份条：首字头像 + 姓名 + 学号 + 学院/专业/班级 -->
    <el-card class="page-card hero" shadow="never">
      <div class="hero__id">
        <div class="hero__avatar">{{ (profile?.real_name || '同').slice(0, 1) }}</div>
        <div class="hero__who">
          <div class="hero__name">
            <span>{{ profile?.real_name || '同学' }}</span>
            <el-tag
              size="small"
              effect="plain"
              :type="
                profile?.academic_status === 'ENROLLED'
                  ? 'success'
                  : profile?.academic_status === 'SUSPENDED'
                    ? 'warning'
                    : profile?.academic_status === 'WITHDRAWN'
                      ? 'danger'
                      : 'info'
              "
            >
              {{ STATUS[profile?.academic_status ?? ''] ?? '—' }}
            </el-tag>
          </div>
          <div class="hero__line muted">学号 {{ profile?.student_no || '—' }}</div>
          <div class="hero__line muted">
            <span>{{ profile?.college_name || '—' }}</span>
            <span class="hero__dot">·</span>
            <span>{{ profile?.major_name || '—' }}</span>
            <span class="hero__dot">·</span>
            <span>{{ profile?.class_name || '—' }}</span>
          </div>
        </div>
      </div>
    </el-card>

    <div class="grid">
      <!-- 学籍信息（只读键值对） -->
      <el-card class="page-card" shadow="never">
        <div class="section-title">学籍信息</div>
        <dl class="fields">
          <div class="field">
            <dt class="field__label">学号</dt>
            <dd class="field__value">{{ profile?.student_no || '—' }}</dd>
          </div>
          <div class="field">
            <dt class="field__label">姓名</dt>
            <dd class="field__value">{{ profile?.real_name || '—' }}</dd>
          </div>
          <div class="field">
            <dt class="field__label">性别</dt>
            <dd class="field__value">{{ GENDER[profile?.gender ?? ''] ?? '—' }}</dd>
          </div>
          <div class="field">
            <dt class="field__label">入学年份</dt>
            <dd class="field__value">{{ profile?.enrollment_year ?? '—' }}</dd>
          </div>
          <div class="field">
            <dt class="field__label">出生日期</dt>
            <dd class="field__value">{{ profile?.birth_date || '—' }}</dd>
          </div>
          <div class="field">
            <dt class="field__label">学籍状态</dt>
            <dd class="field__value">
              {{ STATUS[profile?.academic_status ?? ''] ?? '—' }}
            </dd>
          </div>
        </dl>
      </el-card>

      <!-- 联系方式（只读键值对） -->
      <el-card class="page-card" shadow="never">
        <div class="section-title">联系方式</div>
        <dl class="fields">
          <div class="field">
            <dt class="field__label">邮箱</dt>
            <dd class="field__value">{{ profile?.email || '—' }}</dd>
          </div>
          <div class="field">
            <dt class="field__label">手机</dt>
            <dd class="field__value">{{ profile?.phone || '—' }}</dd>
          </div>
        </dl>
      </el-card>

      <!-- 学业情况 -->
      <el-card class="page-card span-2" shadow="never">
        <div class="section-title">学业情况</div>
        <div class="stat-grid">
          <div class="stat">
            <span class="stat__label">已修学分</span>
            <span class="stat__value">
              {{ summary?.total_credits ?? 0 }}<span class="stat__unit">分</span>
            </span>
          </div>
          <div class="stat stat--gpa">
            <span class="stat__label">平均绩点</span>
            <span class="stat__value">
              {{ summary?.gpa != null ? Number(summary.gpa).toFixed(2) : '—' }}
            </span>
          </div>
          <div class="stat">
            <span class="stat__label">已修课程</span>
            <span class="stat__value">
              {{ summary?.total_courses ?? 0 }}<span class="stat__unit">门</span>
            </span>
          </div>
          <div class="stat" :class="{ 'is-warn': Number(summary?.failed_courses ?? 0) > 0 }">
            <span class="stat__label">不及格课程</span>
            <span class="stat__value">
              {{ summary?.failed_courses ?? 0 }}<span class="stat__unit">门</span>
            </span>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<style scoped lang="scss">
.profile {
  display: flex;
  flex-direction: column;
  gap: var(--uams-gap);
}

/* --------------------------------------------------------------- 身份条 */
.hero__id {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
}

.hero__avatar {
  width: 56px;
  height: 56px;
  flex: 0 0 56px;
  border-radius: 16px;
  display: grid;
  place-items: center;
  font-size: 22px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, var(--uams-primary), var(--uams-primary-light));
  box-shadow: 0 8px 20px color-mix(in srgb, var(--uams-primary) 24%, transparent);
}

.hero__who {
  min-width: 0;
}

.hero__name {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 20px;
  font-weight: 600;
  line-height: 1.3;
  color: var(--uams-text);
}

.hero__line {
  font-size: 13px;
  margin-top: 4px;
  overflow-wrap: anywhere;
}

.hero__dot {
  margin: 0 6px;
  color: var(--uams-border-strong);
}

/* ------------------------------------------------------------- 主体网格 */
.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: start;
  gap: var(--uams-gap);

  /* 网格内用 gap 控制间距，抵消全局 .page-card + .page-card 的外边距 */
  > .page-card {
    margin-top: 0;
  }
}

.span-2 {
  grid-column: 1 / -1;
}

/* 卡片主体内的区块标题紧贴上边、留出下间距 */
.grid .section-title {
  margin: 0 0 14px;
}

/* --------------------------------------------------------- 只读键值对 */
.fields {
  margin: 0;
}

.field {
  display: grid;
  grid-template-columns: 84px minmax(0, 1fr);
  align-items: baseline;
  gap: 12px;
  padding: 11px 0;
  border-bottom: 1px dashed var(--uams-border);

  &:first-child {
    padding-top: 0;
  }

  &:last-child {
    padding-bottom: 0;
    border-bottom: none;
  }
}

.field__label {
  margin: 0;
  font-size: 13px;
  color: var(--uams-text-3);
}

.field__value {
  margin: 0;
  font-size: 14px;
  color: var(--uams-text);
  overflow-wrap: anywhere;
}

/* ------------------------------------------------------------- 学业情况 */
.stat {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface-sunken);

  &__label {
    font-size: 12px;
    color: var(--uams-text-3);
  }

  &__value {
    font-size: 26px;
    font-weight: 700;
    line-height: 1.1;
    color: var(--uams-text);
    font-variant-numeric: tabular-nums;
  }

  &__unit {
    margin-left: 3px;
    font-size: 12px;
    font-weight: 500;
    color: var(--uams-text-3);
  }

  &.stat--gpa {
    background: linear-gradient(165deg, var(--uams-primary-softer) 0%, var(--uams-surface) 70%);

    .stat__value {
      color: var(--uams-primary-dark);
    }
  }

  &.is-warn .stat__value {
    color: var(--uams-warning);
  }
}

/* ------------------------------------------------------------- 响应式 */
@media (max-width: 1024px) {
  .grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .span-2 {
    grid-column: auto;
  }
}

@media (max-width: 768px) {
  .profile {
    gap: 12px;
  }

  .grid {
    gap: 12px;
  }

  .hero__id {
    gap: 12px;
    align-items: flex-start;
  }

  .hero__avatar {
    width: 48px;
    height: 48px;
    flex-basis: 48px;
    border-radius: 14px;
    font-size: 19px;
  }

  .hero__name {
    font-size: 18px;
  }

  /* 单列：标签在上、值在下 */
  .field {
    grid-template-columns: minmax(0, 1fr);
    gap: 2px;
    padding: 10px 0;
  }

  .field__label {
    font-size: 12px;
  }

  .stat__value {
    font-size: 22px;
  }
}

@media (max-width: 420px) {
  .stat {
    padding: 12px 14px;
  }
}
</style>
