<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { roleHome } from '@/router'

const router = useRouter()
const auth = useAuthStore()
</script>

<template>
  <el-result icon="warning" title="403" sub-title="您没有权限访问该页面">
    <template #extra>
      <el-button type="primary" @click="router.push(roleHome(auth.user?.user_type))">
        返回首页
      </el-button>
    </template>
  </el-result>
</template>
