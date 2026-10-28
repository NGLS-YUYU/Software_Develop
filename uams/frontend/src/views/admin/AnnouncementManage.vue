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
  <el-card shadow="never" class="page-card">
    <!-- 筛选 + 主操作：查询在左，发布在右 -->
    <div class="toolbar">
      <el-input
        v-model="t.query.keyword"
        class="toolbar__search"
        placeholder="搜索公告标题"
        clearable
        @keyup.enter="t.search"
        @clear="t.search"
      />
      <el-button type="primary" @click="t.search">查询</el-button>
      <div class="spacer" />
      <el-button type="primary" :icon="'Plus'" @click="t.openCreate">发布公告</el-button>
    </div>

    <div v-loading="t.loading.value">
      <!-- 桌面端：表格 -->
      <div class="table-wrap">
        <el-table :data="t.rows.value" stripe>
          <el-table-column label="标题" min-width="260">
            <template #default="{ row }">
              <div class="cell-title">
                <el-tag v-if="row.is_top" type="danger" size="small" effect="light">置顶</el-tag>
                <span class="cell-title__text">{{ row.title }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="面向" width="90" align="center">
            <template #default="{ row }">
              <span class="cell-muted">{{ TARGET[row.target_type] }}</span>
            </template>
          </el-table-column>
          <el-table-column label="发布人" width="120">
            <template #default="{ row }">
              <span :class="{ 'cell-muted': !row.publisher_name }">
                {{ row.publisher_name || '—' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="发布时间" width="170">
            <template #default="{ row }">
              <span class="cell-muted">
                {{ row.published_at?.slice(0, 16).replace('T', ' ') ?? '-' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="STATUS_TYPE[row.status] as any" size="small">
                {{ STATUS[row.status] }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="210" align="center" fixed="right">
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
          <template #empty>
            <el-empty
              description="暂时还没有公告。点击右上角「发布公告」创建第一条通知，或调整标题关键词后重新查询。"
              :image-size="96"
            />
          </template>
        </el-table>
      </div>

      <!-- 移动端：卡片列表 -->
      <div class="notice-cards">
        <el-empty
          v-if="!t.rows.value.length"
          description="暂时还没有公告。点击右上角「发布公告」创建第一条通知。"
          :image-size="88"
        />
        <article v-for="row in t.rows.value" :key="row.id" class="ncard">
          <header class="ncard__head">
            <div class="ncard__title">
              <span class="ncard__name">{{ row.title }}</span>
              <span class="ncard__sub">
                <el-tag v-if="row.is_top" type="danger" size="small" effect="light">置顶</el-tag>
                面向 {{ TARGET[row.target_type] }}
              </span>
            </div>
            <el-tag :type="STATUS_TYPE[row.status] as any" size="small">
              {{ STATUS[row.status] }}
            </el-tag>
          </header>

          <dl class="ncard__meta">
            <div>
              <dt>发布人</dt>
              <dd>{{ row.publisher_name || '—' }}</dd>
            </div>
            <div>
              <dt>发布时间</dt>
              <dd>{{ row.published_at?.slice(0, 16).replace('T', ' ') ?? '-' }}</dd>
            </div>
          </dl>

          <div class="ncard__actions">
            <el-button v-if="row.status !== 'PUBLISHED'" size="small" link type="success"
              @click="publish(row)">发布</el-button>
            <el-button v-else size="small" link type="warning" @click="withdraw(row)">撤回</el-button>
            <el-button size="small" link type="primary" @click="t.openEdit(row)">编辑</el-button>
            <el-button size="small" link type="danger" @click="t.remove(row, row.title)">
              删除
            </el-button>
          </div>
        </article>
      </div>
    </div>

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
        <el-form-item label="面向对象" for="announcement-target">
          <el-radio-group v-model="t.form.value.target_type" v-control-id="'announcement-target'">
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

<style scoped lang="scss">
/* ------------------------------------------------------------ 筛选区 */
.toolbar__search {
  width: 240px;
}

/* -------------------------------------------------------- 表格单元格 */
.cell-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;

  &__text {
    font-weight: 500;
    color: var(--uams-text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.cell-muted {
  color: var(--uams-text-3);
}

/* --------------------------------------------------- 移动端卡片列表 */
.notice-cards {
  display: none;
  flex-direction: column;
  gap: 12px;
}

.ncard {
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
    display: block;
    font-weight: 600;
    line-height: 1.4;
    color: var(--uams-text);
  }

  &__sub {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 4px;
    font-size: 12px;
    color: var(--uams-text-3);
  }

  &__meta {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    margin: 0;
    padding: 12px 14px 0;

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
      color: var(--uams-text);
      word-break: break-word;
    }
  }

  &__actions {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 4px;
    margin-top: 12px;
    padding: 8px 10px;
    border-top: 1px solid var(--uams-border);

    .el-button {
      margin-left: 0;
      padding: 4px 10px;
      height: auto;
    }
  }
}

/* ------------------------------------------------------------- 响应式 */
@media (max-width: 768px) {
  .toolbar__search {
    width: 100%;
  }

  /* 表格换成卡片列表 */
  .table-wrap {
    display: none;
  }

  .notice-cards {
    display: flex;
  }
}
</style>
