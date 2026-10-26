<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { teacherApi, teachingApi } from '@/api'
import { currentSemester, semesterOptions } from '@/composables/useSemester'
import type { TeachingClass } from '@/types'

const router = useRouter()
const semester = ref(currentSemester())
const classes = ref<TeachingClass[]>([])
const loading = ref(false)

const rosterVisible = ref(false)
const roster = ref<{ student_id: number; student_no: string; real_name: string; class_name?: string | null }[]>([])
const rosterTitle = ref('')

const DAY = ['', '周一', '周二', '周三', '周四', '周五', '周六', '周日']

function scheduleText(tc: TeachingClass) {
  if (!tc.schedules?.length) return '未排课'
  return tc.schedules
    .map((s) => `${DAY[s.day_of_week]} ${s.start_period}-${s.end_period}节 ${s.classroom_code ?? ''}`)
    .join('；')
}

async function load() {
  loading.value = true
  try {
    const me = await teacherApi.me()
    const res = await teachingApi.classes({
      teacher_id: me.id,
      semester: semester.value,
      page_size: 100,
    })
    classes.value = res.items
  } finally {
    loading.value = false
  }
}

async function showRoster(tc: TeachingClass) {
  roster.value = await teachingApi.students(tc.id)
  rosterTitle.value = `${tc.course_name} — 学生名单（${roster.value.length} 人）`
  rosterVisible.value = true
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="my-courses">
    <!-- 顶部：本学期筛选 + 教学班计数 -->
    <div class="toolbar">
      <el-select v-model="semester" style="width: 180px" @change="load">
        <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
      </el-select>
      <div class="spacer" />
      <el-tag type="info" effect="plain">共 {{ classes.length }} 个教学班</el-tag>
    </div>

    <el-empty
      v-if="!classes.length"
      description="本学期暂无授课安排，可切换其他学期查看"
    />

    <!-- 教学班卡片列表 -->
    <div v-else class="course-grid">
      <article v-for="tc in classes" :key="tc.id" class="course page-card">
        <header class="course__head">
          <span class="course__mark">
            <el-icon><component :is="'Reading'" /></el-icon>
          </span>
          <div class="course__title">
            <h3 class="course__name">{{ tc.course_name }}</h3>
            <span class="course__code muted">{{ tc.course_code }}</span>
          </div>
          <el-tag class="course__term" size="small" effect="plain">
            {{ tc.semester }}
          </el-tag>
        </header>

        <ul class="course__facts">
          <li class="fact">
            <el-icon class="fact__icon"><component :is="'Collection'" /></el-icon>
            <span class="fact__body">
              <span class="fact__label muted">教学班</span>
              <span class="fact__value">{{ tc.code }}</span>
            </span>
          </li>
          <li class="fact">
            <el-icon class="fact__icon"><component :is="'Tickets'" /></el-icon>
            <span class="fact__body">
              <span class="fact__label muted">学分 / 学时</span>
              <span class="fact__value">
                {{ tc.credits ?? '—' }} 学分 · {{ tc.total_hours ?? '—' }} 学时
              </span>
            </span>
          </li>
          <li class="fact">
            <el-icon class="fact__icon"><component :is="'Clock'" /></el-icon>
            <span class="fact__body">
              <span class="fact__label muted">上课安排</span>
              <span class="fact__value">{{ scheduleText(tc) }}</span>
            </span>
          </li>
        </ul>

        <div class="course__enroll">
          <div class="enroll__head">
            <span class="enroll__label muted">选课人数</span>
            <span class="enroll__count">
              <b>{{ tc.selected_count }}</b>
              <span class="muted"> / {{ tc.capacity }}</span>
            </span>
          </div>
          <el-progress
            :percentage="
              tc.capacity
                ? Math.min(100, Math.round((tc.selected_count / tc.capacity) * 100))
                : 0
            "
            :stroke-width="6"
            :show-text="false"
          />
        </div>

        <footer class="course__foot">
          <el-button size="small" @click="showRoster(tc)">学生名单</el-button>
          <el-button
            size="small"
            type="primary"
            @click="router.push(`/teacher/grades/${tc.id}`)"
          >
            录入成绩
          </el-button>
        </footer>
      </article>
    </div>

    <el-dialog v-model="rosterVisible" :title="rosterTitle" width="560px">
      <el-empty v-if="!roster.length" description="暂无学生选课" :image-size="70" />
      <el-table v-else :data="roster" max-height="420" stripe size="small">
        <el-table-column type="index" label="#" width="55" align="center" />
        <el-table-column prop="student_no" label="学号" width="140" />
        <el-table-column prop="real_name" label="姓名" width="110" />
        <el-table-column prop="class_name" label="班级" min-width="150" />
      </el-table>
    </el-dialog>
  </div>
</template>

<style scoped>
.my-courses {
  display: block;
}

/* ------------------------------------------------------------ 卡片网格 */
.course-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--uams-gap);
}

/* 卡片间距由 grid 的 gap 控制，覆盖全局 .page-card + .page-card 的外边距 */
.course-grid .course + .course {
  margin-top: 0;
}

.course {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px 18px;
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
}

.course:hover {
  border-color: var(--uams-border-strong);
  box-shadow: var(--uams-shadow);
}

/* --------------------------------------------------------------- 卡片头 */
.course__head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.course__mark {
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  border-radius: var(--uams-radius-sm);
  display: grid;
  place-items: center;
  font-size: 18px;
  color: var(--uams-primary-dark);
  background: var(--uams-primary-soft);
}

.course__title {
  flex: 1;
  min-width: 0;
}

.course__name {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--uams-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.course__code {
  display: block;
  font-size: 12px;
  margin-top: 2px;
}

.course__term {
  flex: 0 0 auto;
  border-color: var(--uams-primary-light);
  color: var(--uams-primary-dark);
  background: var(--uams-primary-softer);
}

/* ------------------------------------------------------------- 信息列表 */
.course__facts {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.fact {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.fact__icon {
  margin-top: 2px;
  flex: 0 0 auto;
  font-size: 15px;
  color: var(--uams-primary);
}

.fact__body {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.4;
}

.fact__label {
  font-size: 12px;
}

.fact__value {
  font-size: 13px;
  color: var(--uams-text);
  word-break: break-word;
}

/* ------------------------------------------------------------ 选课进度 */
.course__enroll {
  margin-top: auto;
}

.enroll__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 6px;
}

.enroll__label {
  font-size: 12px;
}

.enroll__count {
  font-size: 13px;
  color: var(--uams-text-2);
}

.enroll__count b {
  font-size: 15px;
  color: var(--uams-text);
  font-variant-numeric: tabular-nums;
}

/* -------------------------------------------------------------- 操作区 */
.course__foot {
  display: flex;
  gap: 10px;
  padding-top: 12px;
  border-top: 1px solid var(--uams-border);
}

.course__foot .el-button {
  flex: 1;
  margin-left: 0;
}

/* -------------------------------------------------------------- 响应式 */
@media (max-width: 768px) {
  .course-grid {
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .course {
    padding: 14px;
    gap: 12px;
  }

  /* 触控目标：按钮加高，避免过小 */
  .course__foot .el-button {
    height: 38px;
  }
}
</style>
