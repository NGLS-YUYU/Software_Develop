<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { announcementApi } from '@/api'
import type { Announcement } from '@/types'

const list = ref<Announcement[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const loading = ref(false)

const detail = ref<Announcement | null>(null)
const dialog = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await announcementApi.list({ page: page.value, page_size: pageSize.value })
    list.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

function open(a: Announcement) {
  detail.value = a
  dialog.value = true
}

onMounted(load)
</script>

<template>
  <el-card shadow="never" v-loading="loading">
    <el-empty v-if="!list.length" description="暂无通知公告" />
    <div v-else class="ann-list">
      <div v-for="a in list" :key="a.id" class="item" @click="open(a)">
        <div class="head">
          <el-tag v-if="a.is_top" type="danger" size="small">置顶</el-tag>
          <span class="title">{{ a.title }}</span>
        </div>
        <div class="meta">
          <span>{{ a.publisher_name }}</span>
          <span>{{ a.published_at?.slice(0, 16).replace('T', ' ') }}</span>
        </div>
      </div>
    </div>

    <div class="pager">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @current-change="load"
        @size-change="load"
      />
    </div>

    <el-dialog v-model="dialog" :title="detail?.title" width="640px">
      <div class="detail-meta">
        {{ detail?.publisher_name }} · {{ detail?.published_at?.slice(0, 16).replace('T', ' ') }}
      </div>
      <div class="detail-content">{{ detail?.content }}</div>
    </el-dialog>
  </el-card>
</template>

<style scoped>
.ann-list .item {
  padding: 14px 4px;
  border-bottom: 1px solid #ebeef5;
  cursor: pointer;
}
.ann-list .item:hover .title {
  color: #1f6feb;
}
.head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.title {
  font-size: 15px;
  font-weight: 500;
}
.meta {
  margin-top: 6px;
  display: flex;
  gap: 16px;
  color: #909399;
  font-size: 12px;
}
.detail-meta {
  color: #909399;
  font-size: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #ebeef5;
  margin-bottom: 14px;
}
.detail-content {
  white-space: pre-wrap;
  line-height: 1.8;
}
</style>
