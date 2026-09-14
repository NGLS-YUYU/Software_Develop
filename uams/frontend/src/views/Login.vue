<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const form = ref({ username: '', password: '' })
const loading = ref(false)

async function submit() {
  if (!form.value.username || !form.value.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const res = await auth.login(form.value.username, form.value.password)
    ElMessage.success(`欢迎回来，${res.user.real_name}`)
    const redirect = route.query.redirect as string | undefined
    router.push(redirect || res.home_route)
  } finally {
    loading.value = false
  }
}

/** 演示账号，方便验收时快速切换角色。 */
const demoAccounts = [
  { label: '教务', username: 'admin', password: 'admin123' },
  { label: '教师', username: 'T001', password: 'T001' },
  { label: '学生', username: '20260001', password: '20260001' },
]

function fill(a: { username: string; password: string }) {
  form.value.username = a.username
  form.value.password = a.password
}
</script>

<template>
  <div class="login-page">
    <div class="login-box">
      <div class="brand">
        <h1>高校教务教学管理系统</h1>
        <p>University Academic Affairs &amp; Teaching Management System</p>
      </div>

      <el-form class="form" @submit.prevent="submit">
        <el-form-item>
          <el-input
            v-model="form.username"
            size="large"
            placeholder="学号 / 工号 / 用户名"
            :prefix-icon="'User'"
            clearable
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="form.password"
            size="large"
            type="password"
            placeholder="密码"
            :prefix-icon="'Lock'"
            show-password
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button
          type="primary"
          size="large"
          class="submit"
          :loading="loading"
          @click="submit"
        >
          登 录
        </el-button>
      </el-form>

      <div class="demo">
        <span>演示账号：</span>
        <el-link
          v-for="a in demoAccounts"
          :key="a.username"
          type="primary"
          :underline="false"
          @click="fill(a)"
        >
          {{ a.label }}
        </el-link>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1f4e79 0%, #2d6ca2 60%, #4a90c4 100%);
}

.login-box {
  width: 400px;
  padding: 36px 36px 28px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 8px 28px rgb(0 0 0 / 18%);
}

.brand {
  text-align: center;
  margin-bottom: 26px;

  h1 {
    margin: 0 0 6px;
    font-size: 21px;
    color: #1f4e79;
    letter-spacing: 1px;
  }

  p {
    margin: 0;
    font-size: 11px;
    color: #909399;
  }
}

.submit {
  width: 100%;
}

.demo {
  margin-top: 18px;
  text-align: center;
  font-size: 12px;
  color: #909399;
  display: flex;
  justify-content: center;
  gap: 10px;
  align-items: center;
}
</style>
