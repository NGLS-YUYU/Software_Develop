<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { termApi } from '@/api'
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
})

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

async function submit() {
  const err = validate()
  if (err) {
    ElMessage.warning(err)
    return
  }
  await t.save(payload())
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
  } catch {
    // 后端拒绝（如该学期不是进行中）时拦截器已提示
  }
}

const activeTerm = ref<Term | null>(null)

async function load() {
  await t.load()
  activeTerm.value = t.rows.value.find((r) => r.status === 'ACTIVE') ?? null
}

onMounted(load)
</script>

<template>
  <div>
    <el-card shadow="never" class="page-card">
      <div class="toolbar">
        <el-input
          v-model="t.query.keyword"
          placeholder="搜索学期名称 / 学年"
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
        <el-text size="small" type="info">
          当前激活学期：{{ activeTerm ? activeTerm.name : '无' }}
        </el-text>
        <el-button type="primary" @click="t.openCreate">新增学期</el-button>
      </div>

      <el-table v-loading="t.loading.value" :data="t.rows.value" stripe border size="small">
        <el-table-column prop="name" label="学期名称" min-width="200" />
        <el-table-column prop="academic_year" label="学年" width="120" align="center" />
        <el-table-column label="学期" width="100" align="center">
          <template #default="{ row }">{{ semesterLabel(row.semester) }}</template>
        </el-table-column>
        <el-table-column prop="start_date" label="开始日期" width="120" align="center" />
        <el-table-column prop="end_date" label="结束日期" width="120" align="center" />
        <el-table-column prop="teaching_class_count" label="教学班数" width="100" align="center" />
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="STATUS_TYPE[row.status] as any" size="small">
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
          <el-empty description="暂无学期数据，请先新增学期" :image-size="70" />
        </template>
      </el-table>

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
