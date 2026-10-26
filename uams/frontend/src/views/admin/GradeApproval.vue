<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { exportApi, gradeApi } from '@/api'
import { semesterOptions } from '@/composables/useSemester'
import type { Grade, GradeChangeLog } from '@/types'

const semester = ref<string | undefined>(undefined)
const mode = ref<'pending' | 'approved'>('pending')
const rows = ref<Grade[]>([])
const approvedRows = ref<Grade[]>([])
const selected = ref<Grade[]>([])
const loading = ref(false)

const correctVisible = ref(false)
const correctSaving = ref(false)
const correctTarget = ref<Grade | null>(null)
const correctForm = ref<Record<string, number | string | undefined>>({})
const historyVisible = ref(false)
const historyRows = ref<GradeChangeLog[]>([])
const historyTarget = ref<Grade | null>(null)

const SCORE_FIELDS = [
  'regular_score', 'mid_score', 'mid_theory_score', 'mid_practice_score',
  'final_score', 'final_theory_score', 'final_practice_score',
  'theory_makeup_score', 'practice_makeup_score',
] as const

/** 按教学班分组，教务通常整班审核。 */
const grouped = computed(() => {
  const source = mode.value === 'pending' ? rows.value : approvedRows.value
  const map = new Map<number, Grade[]>()
  for (const g of source) {
    const arr = map.get(g.teaching_class_id) ?? []
    arr.push(g)
    map.set(g.teaching_class_id, arr)
  }
  return [...map.values()]
})

async function load() {
  loading.value = true
  try {
    if (mode.value === 'pending') {
      rows.value = await gradeApi.pending(semester.value)
      selected.value = []
    } else {
      approvedRows.value = await gradeApi.approved(semester.value)
      selected.value = []
    }
  } finally {
    loading.value = false
  }
}

function switchMode(value: 'pending' | 'approved') {
  mode.value = value
  load()
}

const FIELD_LABELS: Record<string, string> = {
  regular_score: '平时成绩',
  mid_score: '期中成绩',
  mid_theory_score: '期中理论',
  mid_practice_score: '期中实践',
  final_score: '期末成绩',
  final_theory_score: '期末理论',
  final_practice_score: '期末实践',
  theory_makeup_score: '理论补考',
  practice_makeup_score: '实践补考',
}

/** 按课程考核结构禁用无效字段：实践课不直接改合并分，非实践课不改拆分分。 */
function fieldDisabled(f: string): boolean {
  const t = correctTarget.value
  if (!t) return false
  if (!t.has_midterm && f.startsWith('mid')) return true
  if (t.has_practice) return f === 'mid_score' || f === 'final_score'
  if (f === 'practice_makeup_score') return true
  return f.endsWith('_theory_score') || f.endsWith('_practice_score')
}

function openCorrect(row: Grade) {
  correctTarget.value = row
  correctForm.value = { reason: '' }
  for (const f of SCORE_FIELDS) correctForm.value[f] = undefined
  correctVisible.value = true
}

async function submitCorrect() {
  if (!correctTarget.value) return
  const reason = String(correctForm.value.reason || '').trim()
  if (!reason) {
    ElMessage.warning('请填写更正原因')
    return
  }
  const updates: Record<string, number> = {}
  for (const f of SCORE_FIELDS) {
    const v = correctForm.value[f]
    if (v !== undefined && v !== null && v !== '') updates[f] = Number(v)
  }
  if (!Object.keys(updates).length) {
    ElMessage.warning('至少填写一项需要更正的分数')
    return
  }
  correctSaving.value = true
  try {
    await gradeApi.correct(correctTarget.value.id, { reason, ...updates })
    ElMessage.success('成绩已更正，历史记录已保存')
    correctVisible.value = false
    await load()
  } finally {
    correctSaving.value = false
  }
}

async function unapprove(row: Grade) {
  let reason = ''
  try {
    const { value } = await ElMessageBox.prompt(
      '撤销审核后教师可重新修改并提交；请填写原因。',
      '撤销审核',
      { inputPlaceholder: '如：教务复核发现录入错误', inputValidator: (v) => (v && v.trim() ? true : '原因不能为空') },
    )
    reason = value
  } catch {
    return
  }
  await gradeApi.unapprove(row.id, reason)
  ElMessage.success('已撤销审核，教师可重新修改')
  await load()
}

async function openHistory(row: Grade) {
  historyTarget.value = row
  historyRows.value = await gradeApi.history(row.id)
  historyVisible.value = true
}

function snapshotValue(raw: string, key: string) {
  try {
    const obj = JSON.parse(raw)
    return obj[key] ?? '—'
  } catch {
    return '—'
  }
}

async function approve(ids: number[]) {
  if (!ids.length) {
    ElMessage.warning('请先选择要审核的成绩')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认通过 ${ids.length} 条成绩？通过后学生即可查询，教师不能再直接修改。`,
      '确认审核',
      { type: 'warning' },
    )
  } catch {
    return
  }
  const res = await gradeApi.approve(ids)
  ElMessage.success(res.message)
  await load()
}

async function reject(ids: number[]) {
  if (!ids.length) {
    ElMessage.warning('请先选择要驳回的成绩')
    return
  }
  let reason = ''
  try {
    const { value } = await ElMessageBox.prompt('请输入驳回原因', '驳回成绩', {
      inputPlaceholder: '如：平时成绩偏高，请复核',
      inputValidator: (v) => (v && v.trim() ? true : '驳回原因不能为空'),
    })
    reason = value
  } catch {
    return
  }
  const res = await gradeApi.reject(ids, reason)
  ElMessage.success(res.message)
  await load()
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="grade-approval">
    <!-- 筛选与批量操作 -->
    <el-card shadow="never" class="page-card">
      <div class="toolbar">
        <el-select
          v-model="semester"
          clearable
          placeholder="全部学期"
          class="semester-select"
          style="width: 180px"
          @change="load"
        >
          <el-option v-for="s in semesterOptions()" :key="s" :label="s" :value="s" />
        </el-select>
        <el-button type="primary" @click="load">刷新</el-button>
        <el-button @click="exportApi.grades(semester)">导出已通过成绩</el-button>
        <el-button
          :type="mode === 'pending' ? 'primary' : 'default'"
          @click="switchMode('pending')"
        >待审核</el-button>
        <el-button
          :type="mode === 'approved' ? 'primary' : 'default'"
          @click="switchMode('approved')"
        >已通过</el-button>
        <div class="spacer" />
        <el-tag class="pending-tag" :type="mode === 'pending' ? 'warning' : 'success'" effect="light">
          {{ mode === 'pending' ? '待审核' : '已通过' }}
          {{ (mode === 'pending' ? rows : approvedRows).length }} 条
        </el-tag>
        <span v-if="mode === 'pending'" class="hide-on-mobile batch-actions">
          <el-button
            class="batch-approve"
            type="success"
            :disabled="!selected.length"
            @click="approve(selected.map(s => s.id))"
          >
            批量通过 ({{ selected.length }})
          </el-button>
          <el-button
            class="batch-reject"
            type="danger"
            plain
            :disabled="!selected.length"
            @click="reject(selected.map(s => s.id))"
          >
            批量驳回
          </el-button>
        </span>
      </div>
    </el-card>

    <!-- 空状态 -->
    <el-card v-if="!grouped.length" shadow="never" class="page-card">
      <el-empty :description="mode === 'pending' ? '暂无待审核的成绩' : '暂无已通过的成绩'">
        <template #description>
          <p class="empty-title">
            {{ mode === 'pending' ? '当前没有待审核的成绩' : '当前没有已通过的成绩' }}
          </p>
          <p class="empty-hint muted">
            {{ mode === 'pending'
              ? '教师提交成绩后会出现在这里，可切换学期或点击「刷新」查看。'
              : '教务审核通过后会出现在这里，可在此更正或撤销审核。' }}
          </p>
        </template>
      </el-empty>
    </el-card>

    <!-- 按教学班分组审核 -->
    <template v-else>
      <el-card
        v-for="group in grouped"
        :key="group[0].teaching_class_id"
        shadow="never"
        class="page-card group-card"
      >
      <template #header>
        <div class="group-head">
          <div class="group-head__title">
            <span class="group-course">{{ group[0].course_name || '未命名课程' }}</span>
            <el-tag size="small" type="info" effect="plain">
              {{ group.length }} 人
            </el-tag>
            <span class="sem muted">{{ group[0].semester }}</span>
          </div>
          <div class="group-head__ops">
            <el-button size="small" type="success"
              @click="approve(group.map(g => g.id))">整班通过</el-button>
            <el-button size="small" type="danger" plain
              @click="reject(group.map(g => g.id))">整班驳回</el-button>
          </div>
        </div>
      </template>

      <!-- 桌面端：表格（选中后可批量审核，操作列固定右侧） -->
      <div class="table-wrap">
        <el-table :data="group" size="small" stripe
          @selection-change="(v: Grade[]) => selected = v">
          <el-table-column v-if="mode === 'pending'" type="selection" width="45" />
          <el-table-column prop="student_no" label="学号" width="130" />
          <el-table-column prop="student_name" label="姓名" width="100" />
          <el-table-column label="平时" width="80" align="center">
            <template #default="{ row }">
              <span class="cell-dim">{{ row.regular_score ?? '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末" width="80" align="center">
            <template #default="{ row }">
              <span class="cell-dim">{{ row.final_score ?? '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="总评" width="92" align="center">
            <template #default="{ row }">
              <el-tag class="cell-total" :type="Number(row.total_score) >= 60 ? '' : 'danger'"
                size="small">
                {{ row.total_score ?? '—' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="绩点" width="80" align="center">
            <template #default="{ row }">
              <span class="cell-gp">{{ row.grade_point ?? '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="credits" label="学分" width="80" align="center" />
          <el-table-column label="提交时间" min-width="160">
            <template #default="{ row }">
              <span class="cell-time">
                {{ row.submitted_at ? row.submitted_at.slice(0, 16).replace('T', ' ') : '—' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="操作" :width="mode === 'pending' ? 128 : 220" align="center" fixed="right">
            <template #default="{ row }">
              <template v-if="mode === 'pending'">
                <el-button link type="success" size="small"
                  @click="approve([row.id])">通过</el-button>
                <el-button link type="danger" size="small"
                  @click="reject([row.id])">驳回</el-button>
              </template>
              <template v-else>
                <el-button link type="primary" size="small"
                  @click="openCorrect(row)">更正</el-button>
                <el-button link type="warning" size="small"
                  @click="unapprove(row)">撤销审核</el-button>
                <el-button link type="info" size="small"
                  @click="openHistory(row)">历史</el-button>
              </template>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 移动端：每条成绩一张卡片，操作可达 -->
      <div class="stu-cards">
        <article v-for="row in group" :key="row.id" class="scard">
          <header class="scard__head">
            <div class="scard__who">
              <span class="scard__name">{{ row.student_name || '—' }}</span>
              <span class="scard__no muted">{{ row.student_no || '—' }}</span>
            </div>
            <el-tag class="cell-total" :type="Number(row.total_score) >= 60 ? '' : 'danger'"
              size="small">
              {{ row.total_score ?? '—' }}
            </el-tag>
          </header>

          <div class="scard__scores">
            <div class="sbox is-total">
              <span class="sbox__num">{{ row.total_score ?? '—' }}</span>
              <span class="sbox__label">成绩总评</span>
            </div>
            <div class="sbox is-gp">
              <span class="sbox__num">{{ row.grade_point ?? '—' }}</span>
              <span class="sbox__label">绩点</span>
            </div>
          </div>

          <dl class="scard__dl">
            <div><dt>平时</dt><dd>{{ row.regular_score ?? '—' }}</dd></div>
            <div><dt>期末</dt><dd>{{ row.final_score ?? '—' }}</dd></div>
            <div><dt>学分</dt><dd>{{ row.credits }}</dd></div>
            <div><dt>提交时间</dt>
              <dd>{{ row.submitted_at ? row.submitted_at.slice(0, 16).replace('T', ' ') : '—' }}</dd>
            </div>
          </dl>

          <div class="scard__foot">
            <template v-if="mode === 'pending'">
              <el-button type="success" size="small" @click="approve([row.id])">通过</el-button>
              <el-button type="danger" plain size="small" @click="reject([row.id])">驳回</el-button>
            </template>
            <template v-else>
              <el-button type="primary" plain size="small" @click="openCorrect(row)">更正</el-button>
              <el-button type="warning" plain size="small" @click="unapprove(row)">撤销审核</el-button>
              <el-button type="info" plain size="small" @click="openHistory(row)">历史</el-button>
            </template>
          </div>
        </article>
      </div>
      </el-card>
    </template>
    <!-- 成绩更正 -->
    <el-dialog v-model="correctVisible" title="更正已审核成绩" width="560px">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="更正会写入成绩变更历史（操作人、时间、原因、改前/改后完整快照），不会无痕覆盖。"
        style="margin-bottom: 12px"
      />
      <el-form label-width="100px">
        <el-form-item label="更正原因" required>
          <el-input v-model="correctForm.reason as string" type="textarea" :rows="2" maxlength="500" show-word-limit />
        </el-form-item>
        <el-form-item
          v-for="f in SCORE_FIELDS"
          :key="f"
          :label="FIELD_LABELS[f] || f"
        >
          <el-input-number
            v-model="correctForm[f] as number | undefined"
            :min="0"
            :max="100"
            :precision="2"
            :disabled="fieldDisabled(f)"
            :placeholder="fieldDisabled(f) ? '本课程不适用' : '不修改'"
            style="width: 180px"
          />
          <span class="muted" style="margin-left: 8px">
            当前：{{ (correctTarget as Grade | null)?.[f] ?? '—' }}
          </span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="correctVisible = false">取消</el-button>
        <el-button type="primary" :loading="correctSaving" @click="submitCorrect">确认更正</el-button>
      </template>
    </el-dialog>

    <!-- 成绩变更历史 -->
    <el-dialog v-model="historyVisible" title="成绩变更历史" width="820px">
      <div class="muted" style="margin-bottom: 10px">
        {{ historyTarget?.student_no }} {{ historyTarget?.student_name }} · {{ historyTarget?.course_name }}
      </div>
      <el-table :data="historyRows" size="small" stripe max-height="420">
        <el-table-column prop="action" label="动作" width="120" />
        <el-table-column prop="reason" label="原因" min-width="160" />
        <el-table-column label="改前总评" width="100" align="center">
          <template #default="{ row }">{{ snapshotValue(row.before_snapshot, 'total_score') }}</template>
        </el-table-column>
        <el-table-column label="改后总评" width="100" align="center">
          <template #default="{ row }">{{ snapshotValue(row.after_snapshot, 'total_score') }}</template>
        </el-table-column>
        <el-table-column label="改前状态" width="100" align="center">
          <template #default="{ row }">{{ snapshotValue(row.before_snapshot, 'status') }}</template>
        </el-table-column>
        <el-table-column label="改后状态" width="100" align="center">
          <template #default="{ row }">{{ snapshotValue(row.after_snapshot, 'status') }}</template>
        </el-table-column>
        <el-table-column prop="operated_by" label="操作人ID" width="90" align="center" />
        <el-table-column label="时间" width="150">
          <template #default="{ row }">{{ row.operated_at?.slice(0, 16).replace('T', ' ') }}</template>
        </el-table-column>
        <template #empty><el-empty description="暂无变更历史" :image-size="60" /></template>
      </el-table>
      <template #footer><el-button @click="historyVisible = false">关闭</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
/* ------------------------------------------------------------- 工具条 */
.semester-select {
  width: 180px;
}

.pending-tag {
  font-weight: 600;
}

/* ------------------------------------------------------------- 空状态 */
.empty-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--uams-text-2);
}

.empty-hint {
  margin: 6px 0 0;
  font-size: 13px;
}

/* ------------------------------------------------------------- 分组头 */
.group-card + .group-card {
  margin-top: var(--uams-gap);
}

.group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.group-head__title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.group-course {
  font-size: 15px;
  font-weight: 600;
  color: var(--uams-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.group-head__ops {
  flex: 0 0 auto;
  display: flex;
  gap: 8px;
}

.sem {
  font-size: 12px;
  white-space: nowrap;
}

/* --------------------------------------------------- 表格单元格强调 */
/* 次要数字：弱化色调，避免与总评抢视线 */
.cell-dim {
  color: var(--uams-text-3);
  font-variant-numeric: tabular-nums;
}

.cell-time {
  font-size: 12.5px;
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

/* ------------------------------------------------------- 移动端卡片 */
.stu-cards {
  display: none;
  flex-direction: column;
  gap: 12px;
}

.scard {
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface);
  overflow: hidden;

  &__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 12px 14px;
    background: var(--uams-surface-sunken);
    border-bottom: 1px solid var(--uams-border);
  }

  &__who {
    min-width: 0;
    display: flex;
    flex-direction: column;
  }

  &__name {
    font-weight: 600;
    color: var(--uams-text);
  }

  &__no {
    font-size: 12px;
  }

  /* 卡片主视觉：成绩总评 + 绩点 */
  &__scores {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    padding: 14px;
  }

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

  &__foot {
    display: flex;
    gap: 10px;
    padding: 12px 14px;
    border-top: 1px solid var(--uams-border);

    .el-button {
      flex: 1;
      margin-left: 0;
    }
  }
}

.sbox {
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

  &__num {
    font-size: 26px;
    font-weight: 700;
    line-height: 1.1;
    color: var(--uams-text);
    font-variant-numeric: tabular-nums;
  }

  &.is-total &__num,
  &.is-gp &__num {
    color: var(--uams-primary-dark);
  }

  &__label {
    font-size: 12px;
    color: var(--uams-text-3);
  }
}

/* ------------------------------------------------------------- 响应式 */
@media (max-width: 768px) {
  /* 工具条换行成两列网格，筛选与批量操作各自占满整行，避免拥挤 */
  .toolbar {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .toolbar > .spacer {
    display: none;
  }

  .toolbar > .semester-select,
  .toolbar > .pending-tag,
  .toolbar > .el-button {
    grid-column: 1 / -1;
  }

  .toolbar > .pending-tag {
    justify-self: start;
  }

  /* 分组操作整行等宽 */
  .group-head {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }

  .group-head__ops .el-button {
    flex: 1;
    margin-left: 0;
  }

  /* 大表格换成卡片列表 */
  .table-wrap {
    display: none;
  }

  .stu-cards {
    display: flex;
  }
}

@media (max-width: 420px) {
  .scard__dl {
    grid-template-columns: 1fr;
  }
}
</style>
