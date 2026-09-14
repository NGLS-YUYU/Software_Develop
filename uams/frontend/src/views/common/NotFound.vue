<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { roleHome } from '@/router'

const router = useRouter()
const auth = useAuthStore()
</script>

<template>
  <el-result icon="info" title="404" sub-title="页面不存在">
    <template #extra>
      <el-button type="primary" @click="router.push(roleHome(auth.user?.user_type))">
        返回首页
      </el-button>
    </template>
  </el-result>
</template>
