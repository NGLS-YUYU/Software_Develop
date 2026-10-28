<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { termApi } from '@/api'
import { setActiveSemester } from '@/composables/useSemester'
import { useCrudTable } from '@/composables/useCrudTable'
import type { Term } from '@/types'

/**
 * 学期管理（FIX-006）。
 *
 * 所有状态都来自后端 `/terms`：本页不维护「当前学期」，激活/结束后一律重新拉取列表，
 * 状态流转规则（单激活、单向 PLANNED → ACTIVE → ENDED）以后端为准，
 * 前端只按真实状态决定按钮是否可点。
 */
const t = useCrudTable<Term>(termApi as never, {
  entityName: '学期',
  emptyForm: () => ({
    name: '',
    academic_year: '',
    semester: 1,
    start_date: '',
    end_date: '',
  }),
  // 创建/编辑/删除后都重新同步全局 ACTIVE 学期。
  afterMutation: syncActiveSemester,
})

/** 纯展示：进行中的学期整行浅紫底，便于一眼定位当前学期。 */
function activeRowClass({ row }: { row: Term }): string {
  return row.status === 'ACTIVE' ? 'row-active' : ''
}

const STATUS_LABEL: Record<string, string> = {
  PLANNED: '未开始',
  ACTIVE: '进行中',
  ENDED: '已结束',
}
const STATUS_TYPE: Record<string, string> = {
  PLANNED: 'info',
  ACTIVE: 'success',
  ENDED: 'warning',
}

/** 学期序号展示：1 → 第一学期，2 → 第二学期。 */
function semesterLabel(n: number) {
  return n === 1 ? '第一学期' : '第二学期'
}

/** 新增/编辑提交：只提交后端 Schema 认识的字段，状态一律走激活/结束接口。 */
function payload() {
  const f = { ...t.form.value }
  delete f.id
  delete f.status
  delete f.teaching_class_count
  return f
}

/** 前端基础校验（后端 Schema 仍会做最终校验）。 */
function validate(): string | null {
  const f = t.form.value
  if (!f.name) return '请填写学期名称'
  if (!f.academic_year) return '请填写学年'
  if (!f.start_date || !f.end_date) return '请选择开始日期与结束日期'
  if (String(f.end_date) <= String(f.start_date)) return '结束日期必须晚于开始日期'
  return null
}

async function syncActiveSemester() {
  try {
    const active = await termApi.active()
    activeTerm.value = active
    setActiveSemester(`${active.academic_year}-${active.semester}`)
  } catch {
    activeTerm.value = null
    setActiveSemester(null)
  }
}

async function submit() {
  const err = validate()
  if (err) {
    ElMessage.warning(err)
    return
  }
  const ok = await t.save(payload())
  if (ok) await syncActiveSemester()
}

async function activate(row: Term) {
  try {
    await ElMessageBox.confirm(
      `确定将「${row.name}」设为当前激活学期吗？激活后该学期进入进行中状态。`,
      '激活学期',
      { type: 'warning', confirmButtonText: '激活', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await termApi.activate(row.id)
    ElMessage.success('已激活')
    await t.load()
    await syncActiveSemester()
  } catch {
    // 409 等业务错误由 axios 拦截器统一提示（例如已存在进行中的学期）
  }
}

async function endTerm(row: Term) {
  try {
    await ElMessageBox.confirm(
      `确定结束「${row.name}」吗？结束后的学期不能再被激活或修改状态。`,
      '结束学期',
      { type: 'warning', confirmButtonText: '结束', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await termApi.end(row.id)
    ElMessage.success('已结束')
    await t.load()
    await syncActiveSemester()
  } catch {
    // 后端拒绝（如该学期不是进行中）时拦截器已提示
  }
}

const activeTerm = ref<Term | null>(null)

async function load() {
  await t.load()
  await syncActiveSemester()
}

onMounted(load)
</script>

<template>
  <div class="terms">
    <!-- 当前激活学期状态条：一眼看清系统正在使用哪个学期 -->
    <section class="active-bar page-card" :class="{ 'is-empty': !activeTerm }">
      <el-icon class="active-bar__icon"><component :is="'Calendar'" /></el-icon>
      <div class="active-bar__main">
        <span class="active-bar__label">当前激活学期</span>
        <span class="active-bar__name">
          {{ activeTerm ? activeTerm.name : '暂无进行中的学期' }}
        </span>
      </div>
      <template v-if="activeTerm">
        <div class="active-bar__meta">
          <span>{{ activeTerm.academic_year }} · {{ semesterLabel(activeTerm.semester) }}</span>
          <span class="muted">{{ activeTerm.start_date }} ~ {{ activeTerm.end_date }}</span>
        </div>
        <el-tag type="success" size="small" effect="dark" round>进行中</el-tag>
      </template>
      <p v-else class="active-bar__hint muted">
        可在下方列表中激活一个「未开始」的学期，激活后该学期进入进行中状态。
      </p>
    </section>

    <el-card shadow="never" class="page-card">
      <div class="toolbar">
        <el-input
          v-model="t.query.keyword"
          placeholder="搜索学期名称 / 学年"
          class="toolbar__search"
          style="width: 220px"
          clearable
          @keyup.enter="t.search"
          @clear="t.search"
        />
        <el-select
          v-model="t.query.status"
          placeholder="全部状态"
          clearable
          style="width: 140px"
          @change="t.search"
        >
          <el-option label="未开始" value="PLANNED" />
          <el-option label="进行中" value="ACTIVE" />
          <el-option label="已结束" value="ENDED" />
        </el-select>
        <el-button type="primary" @click="t.search">查询</el-button>
        <div class="spacer" />
        <el-button type="primary" @click="t.openCreate">新增学期</el-button>
      </div>

      <!-- 桌面端：表格 -->
      <div class="table-wrap">
        <el-table
          v-loading="t.loading.value"
          :data="t.rows.value"
          stripe
          border
          size="small"
          :row-class-name="activeRowClass"
        >
          <el-table-column prop="name" label="学期名称" min-width="200">
            <template #default="{ row }">
              <div class="cell-name">
                <span
                  class="dot"
                  :class="{ 'dot--active': row.status === 'ACTIVE' }"
                  aria-hidden="true"
                />
                <span class="cell-name__text">{{ row.name }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="academic_year" label="学年" width="120" align="center" />
          <el-table-column label="学期" width="100" align="center">
            <template #default="{ row }">{{ semesterLabel(row.semester) }}</template>
          </el-table-column>
          <el-table-column prop="start_date" label="开始日期" width="120" align="center" />
          <el-table-column prop="end_date" label="结束日期" width="120" align="center" />
          <el-table-column prop="teaching_class_count" label="教学班数" width="100" align="center" />
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag
                :type="STATUS_TYPE[row.status] as any"
                size="small"
                :effect="row.status === 'ACTIVE' ? 'dark' : 'light'"
              >
                {{ STATUS_LABEL[row.status] }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="230" align="center" fixed="right">
            <template #default="{ row }">
              <!-- 按钮只按后端真实状态机显示：未开始才可激活，进行中才可结束 -->
              <el-button
                v-if="row.status === 'PLANNED'"
                size="small"
                link
                type="success"
                @click="activate(row)"
              >
                激活
              </el-button>
              <el-button
                v-if="row.status === 'ACTIVE'"
                size="small"
                link
                type="warning"
                @click="endTerm(row)"
              >
                结束
              </el-button>
              <el-button size="small" link type="primary" @click="t.openEdit(row)">编辑</el-button>
              <el-button size="small" link type="danger" @click="t.remove(row, row.name)">
                删除
              </el-button>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty
              description="暂无学期数据，点击右上角「新增学期」创建第一个学年学期"
              :image-size="70"
            />
          </template>
        </el-table>
      </div>

      <!-- 移动端：卡片列表 -->
      <div v-loading="t.loading.value" class="term-cards">
        <article
          v-for="row in t.rows.value"
          :key="row.id"
          class="tcard"
          :class="{ 'is-active': row.status === 'ACTIVE' }"
        >
          <header class="tcard__head">
            <div class="tcard__title">
              <span class="cell-name">
                <span
                  class="dot"
                  :class="{ 'dot--active': row.status === 'ACTIVE' }"
                  aria-hidden="true"
                />
                <span class="cell-name__text">{{ row.name }}</span>
              </span>
              <span class="tcard__sub">
                {{ row.academic_year }} · {{ semesterLabel(row.semester) }}
              </span>
            </div>
            <el-tag
              :type="STATUS_TYPE[row.status] as any"
              size="small"
              :effect="row.status === 'ACTIVE' ? 'dark' : 'light'"
            >
              {{ STATUS_LABEL[row.status] }}
            </el-tag>
          </header>

          <dl class="tcard__meta">
            <div>
              <dt>开始日期</dt>
              <dd>{{ row.start_date }}</dd>
            </div>
            <div>
              <dt>结束日期</dt>
              <dd>{{ row.end_date }}</dd>
            </div>
            <div>
              <dt>教学班数</dt>
              <dd>{{ row.teaching_class_count }}</dd>
            </div>
          </dl>

          <div class="tcard__actions">
            <el-button
              v-if="row.status === 'PLANNED'"
              size="small"
              link
              type="success"
              @click="activate(row)"
            >
              激活
            </el-button>
            <el-button
              v-if="row.status === 'ACTIVE'"
              size="small"
              link
              type="warning"
              @click="endTerm(row)"
            >
              结束
            </el-button>
            <el-button size="small" link type="primary" @click="t.openEdit(row)">编辑</el-button>
            <el-button size="small" link type="danger" @click="t.remove(row, row.name)">
              删除
            </el-button>
          </div>
        </article>

        <el-empty
          v-if="!t.rows.value.length"
          description="暂无学期数据，点击上方「新增学期」创建第一个学年学期"
          :image-size="70"
        />
      </div>

      <div class="pager">
        <el-pagination
          v-model:current-page="t.query.page"
          :total="t.total.value"
          :page-size="t.query.page_size"
          layout="total, prev, pager, next"
          @current-change="t.load"
        />
      </div>
    </el-card>

    <el-dialog
      v-model="t.dialogVisible.value"
      :title="t.dialogMode.value === 'create' ? '新增学期' : '编辑学期'"
      width="520px"
    >
      <el-form label-width="90px">
        <el-form-item label="学期名称" required>
          <el-input
            v-model="t.form.value.name as string"
            maxlength="50"
            placeholder="如 2026-2027学年第一学期"
          />
        </el-form-item>
        <el-form-item label="学年" required>
          <el-input
            v-model="t.form.value.academic_year as string"
            maxlength="9"
            placeholder="如 2026-2027"
          />
        </el-form-item>
        <el-form-item label="学期序号" required>
          <el-radio-group v-model="t.form.value.semester">
            <el-radio :value="1">第一学期</el-radio>
            <el-radio :value="2">第二学期</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="开始日期" required>
          <el-date-picker
            v-model="t.form.value.start_date as string"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择开始日期"
          />
        </el-form-item>
        <el-form-item label="结束日期" required>
          <el-date-picker
            v-model="t.form.value.end_date as string"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择结束日期"
          />
        </el-form-item>
        <el-text size="small" type="info">
          同一学年 + 学期序号唯一；结束日期必须晚于开始日期（后端会再次校验）。
        </el-text>
      </el-form>
      <template #footer>
        <el-button @click="t.dialogVisible.value = false">取消</el-button>
        <el-button type="primary" :loading="t.saving.value" @click="submit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
/* --------------------------------------------------- 激活学期状态条 */
.active-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 18px;
  background: linear-gradient(120deg, var(--uams-primary-softer) 0%, var(--uams-surface) 78%);
  border-color: var(--uams-primary-soft);

  &__icon {
    flex: 0 0 40px;
    width: 40px;
    height: 40px;
    border-radius: var(--uams-radius-sm);
    display: grid;
    place-items: center;
    font-size: 20px;
    color: var(--uams-primary-dark);
    background: color-mix(in srgb, var(--uams-primary) 12%, transparent);
  }

  &__main {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  &__label {
    font-size: 12px;
    color: var(--uams-text-3);
  }

  &__name {
    font-size: 17px;
    font-weight: 600;
    line-height: 1.35;
    color: var(--uams-text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__meta {
    margin-left: auto;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 2px;
    font-size: 12px;
    color: var(--uams-text-2);
    font-variant-numeric: tabular-nums;

    .muted {
      font-size: 12px;
    }
  }

  &__hint {
    margin: 0;
    font-size: 13px;
  }

  &.is-empty {
    background: var(--uams-surface);
    border-color: var(--uams-border);

    .active-bar__icon {
      color: var(--uams-text-3);
      background: var(--uams-surface-sunken);
    }
  }
}

/* ------------------------------------------------------- 列表与状态点 */
.cell-name {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.cell-name__text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dot {
  flex: 0 0 7px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--uams-border-strong);

  &--active {
    background: var(--uams-primary);
    box-shadow: 0 0 0 4px color-mix(in srgb, var(--uams-primary) 16%, transparent);
  }
}

/* 进行中的学期整行浅紫底，突出当前学期 */
:deep(.el-table__row.row-active) > td.el-table__cell {
  background: var(--uams-primary-softer);
}

:deep(.el-table__row.row-active:hover) > td.el-table__cell {
  background: var(--uams-primary-soft);
}

/* --------------------------------------------------------- 移动端卡片 */
.term-cards {
  display: none;
  flex-direction: column;
  gap: 12px;
}

.tcard {
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius-sm);
  background: var(--uams-surface);
  overflow: hidden;

  &.is-active {
    border-color: var(--uams-primary-soft);
    background: var(--uams-primary-softer);
  }

  &__head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
    padding: 12px 14px;
    border-bottom: 1px solid var(--uams-border);
  }

  &__title {
    display: flex;
    flex-direction: column;
    gap: 3px;
    min-width: 0;
  }

  &__sub {
    font-size: 12px;
    color: var(--uams-text-3);
  }

  &__meta {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px;
    margin: 0;
    padding: 12px 14px;

    > div {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    dt {
      font-size: 12px;
      color: var(--uams-text-3);
    }

    dd {
      margin: 0;
      font-size: 13px;
      font-weight: 600;
      color: var(--uams-text);
      font-variant-numeric: tabular-nums;
    }
  }

  &__actions {
    display: flex;
    align-items: center;
    gap: 4px;
    flex-wrap: wrap;
    padding: 8px 10px;
    border-top: 1px solid var(--uams-border);
    background: var(--uams-surface);
  }
}

/* ------------------------------------------------------------- 响应式 */
@media (max-width: 768px) {
  .table-wrap {
    display: none;
  }

  .term-cards {
    display: flex;
  }

  /* 状态条竖向排布，信息不挤压 */
  .active-bar {
    flex-wrap: wrap;
    align-items: flex-start;
    gap: 10px;
    padding: 14px;

    &__icon {
      flex: 0 0 34px;
      width: 34px;
      height: 34px;
      font-size: 17px;
    }

    &__main {
      flex: 1 1 auto;
    }

    &__name {
      font-size: 15px;
    }

    &__meta {
      flex: 1 1 100%;
      margin-left: 0;
      align-items: flex-start;
      flex-direction: row;
      flex-wrap: wrap;
      gap: 4px 14px;
      padding-left: 44px;
    }

    &__hint {
      flex: 1 1 100%;
      padding-left: 44px;
    }
  }
}

@media (max-width: 420px) {
  .tcard__meta {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
