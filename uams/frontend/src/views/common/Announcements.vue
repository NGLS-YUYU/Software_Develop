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
  <el-card shadow="never" class="page-card" v-loading="loading">
    <el-empty v-if="!list.length" description="暂无通知公告">
      <template #description>
        <p class="muted">当前没有面向你的通知，教务发布后会在这里显示。</p>
      </template>
    </el-empty>

    <div v-else class="ann-list">
      <article v-for="a in list" :key="a.id" class="item" @click="open(a)">
        <div class="item__main">
          <div class="item__head">
            <el-tag v-if="a.is_top" type="danger" size="small" effect="light">置顶</el-tag>
            <span class="item__title">{{ a.title }}</span>
          </div>
          <div class="item__meta">
            <span class="item__publisher">{{ a.publisher_name }}</span>
            <span>{{ a.published_at?.slice(0, 16).replace('T', ' ') }}</span>
          </div>
        </div>
        <el-icon class="item__arrow"><component is="ArrowRight" /></el-icon>
      </article>
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

<style scoped lang="scss">
.ann-list {
  display: flex;
  flex-direction: column;
}

.item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 15px 12px;
  margin: 0 -12px;
  border-radius: var(--uams-radius-sm);
  border-bottom: 1px solid var(--uams-border);
  cursor: pointer;
  transition: background-color 0.16s ease;

  &:last-child {
    border-bottom: none;
  }

  &:hover {
    background: var(--uams-primary-softer);

    .item__title {
      color: var(--uams-primary-dark);
    }

    .item__arrow {
      opacity: 1;
      transform: translateX(2px);
    }
  }

  &__main {
    min-width: 0;
    flex: 1;
  }

  &__head {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  &__title {
    font-size: 15px;
    font-weight: 500;
    color: var(--uams-text);
    transition: color 0.16s ease;
  }

  &__meta {
    margin-top: 6px;
    display: flex;
    gap: 16px;
    color: var(--uams-text-3);
    font-size: 12px;
  }

  &__publisher {
    color: var(--uams-text-2);
  }

  &__arrow {
    flex: 0 0 auto;
    color: var(--uams-text-3);
    opacity: 0.5;
    transition: opacity 0.16s ease, transform 0.16s ease;
  }
}

.detail-meta {
  color: var(--uams-text-3);
  font-size: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--uams-border);
  margin-bottom: 14px;
}

.detail-content {
  white-space: pre-wrap;
  line-height: 1.85;
  color: var(--uams-text-2);
}

@media (max-width: 768px) {
  .item {
    padding: 13px 8px;
    margin: 0 -8px;

    &__title {
      font-size: 14px;
    }

    &__meta {
      gap: 10px;
      flex-wrap: wrap;
    }
  }
}
</style>
