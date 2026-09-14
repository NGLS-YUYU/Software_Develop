<script setup lang="ts">
import { onMounted } from 'vue'
import { ElMessage } from 'element-plus'

import { announcementApi } from '@/api'
import { useCrudTable } from '@/composables/useCrudTable'
import type { Announcement } from '@/types'

const t = useCrudTable<Announcement>(announcementApi as never, {
  entityName: '公告',
  emptyForm: () => ({
    title: '', content: '', target_type: 'ALL', is_top: false, status: 'DRAFT',
  }),
})

const TARGET: Record<string, string> = { ALL: '全体', STUDENT: '学生', TEACHER: '教师' }
const STATUS: Record<string, string> = { DRAFT: '草稿', PUBLISHED: '已发布', WITHDRAWN: '已撤回' }
const STATUS_TYPE: Record<string, string> = { DRAFT: 'info', PUBLISHED: 'success', WITHDRAWN: 'warning' }

async function publish(row: Announcement) {
  await announcementApi.update(row.id, { status: 'PUBLISHED' })
  ElMessage.success('已发布')
  await t.load()
}

async function withdraw(row: Announcement) {
  await announcementApi.update(row.id, { status: 'WITHDRAWN' })
  ElMessage.success('已撤回')
  await t.load()
}

function payload() {
  const f = { ...t.form.value }
  delete f.publisher_id
  delete f.publisher_name
  delete f.published_at
  delete f.created_at
  delete f.id
  return f
}

onMounted(t.load)
</script>

<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-input v-model="t.query.keyword" placeholder="搜索标题" style="width: 220px"
        clearable @keyup.enter="t.search" @clear="t.search" />
      <el-button type="primary" @click="t.search">查询</el-button>
      <div class="spacer" />
      <el-button type="primary" :icon="'Plus'" @click="t.openCreate">发布公告</el-button>
    </div>

    <el-table v-loading="t.loading.value" :data="t.rows.value" stripe>
      <el-table-column label="标题" min-width="240">
        <template #default="{ row }">
          <el-tag v-if="row.is_top" type="danger" size="small" style="margin-right: 6px">
            置顶
          </el-tag>
          {{ row.title }}
        </template>
      </el-table-column>
      <el-table-column label="面向" width="90" align="center">
        <template #default="{ row }">{{ TARGET[row.target_type] }}</template>
      </el-table-column>
      <el-table-column prop="publisher_name" label="发布人" width="110" />
      <el-table-column label="发布时间" width="170">
        <template #default="{ row }">
          {{ row.published_at?.slice(0, 16).replace('T', ' ') ?? '-' }}
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="STATUS_TYPE[row.status] as any" size="small">
            {{ STATUS[row.status] }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" align="center" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.status !== 'PUBLISHED'" size="small" link type="success"
            @click="publish(row)">发布</el-button>
          <el-button v-else size="small" link type="warning" @click="withdraw(row)">
            撤回
          </el-button>
          <el-button size="small" link type="primary" @click="t.openEdit(row)">编辑</el-button>
          <el-button size="small" link type="danger" @click="t.remove(row, row.title)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination v-model:current-page="t.query.page" :total="t.total.value"
        :page-size="t.query.page_size" layout="total, prev, pager, next"
        @current-change="t.load" />
    </div>

    <el-dialog v-model="t.dialogVisible.value"
      :title="t.dialogMode.value === 'create' ? '发布公告' : '编辑公告'" width="620px">
      <el-form label-width="90px">
        <el-form-item label="标题" required>
          <el-input v-model="t.form.value.title" maxlength="200" show-word-limit />
        </el-form-item>
        <el-form-item label="面向对象">
          <el-radio-group v-model="t.form.value.target_type">
            <el-radio value="ALL">全体</el-radio>
            <el-radio value="STUDENT">学生</el-radio>
            <el-radio value="TEACHER">教师</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="置顶">
          <el-switch v-model="t.form.value.is_top" />
        </el-form-item>
        <el-form-item label="内容" required>
          <el-input v-model="t.form.value.content" type="textarea" :rows="8" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="t.dialogVisible.value = false">取消</el-button>
        <el-button type="primary" :loading="t.saving.value" @click="t.save(payload())">
          确定
        </el-button>
      </template>
    </el-dialog>
  </el-card>
</template>
