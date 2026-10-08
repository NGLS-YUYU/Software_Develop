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

/** 演示账号，方便验收时快速切换角色。 
const demoAccounts = [
  { label: '教务', username: 'admin', password: 'admin123' },
  { label: '教师', username: 'T001', password: 'T001' },
  { label: '学生', username: '20260001', password: '20260001' },
]
*/

function fill(a: { username: string; password: string }) {
  form.value.username = a.username
  form.value.password = a.password
}
</script>

<template>
  <div class="login-page">
    <div class="login-shell">
      <!-- 品牌侧：桌面显示为左栏，手机折叠为顶部小标题 -->
      <aside class="brand-panel">
        <div class="brand-panel__mark">U</div>
        <h1 class="brand-panel__name">高校教务教学管理系统</h1>
        <p class="brand-panel__sub">University Academic Affairs &amp; Teaching Management System</p>
        <ul class="brand-panel__points">
          <li><el-icon><component is="Reading" /></el-icon>课程 · 教学班 · 排课一体化管理</li>
          <li><el-icon><component is="DataLine" /></el-icon>成绩录入、审核与绩点排名</li>
          <li><el-icon><component is="UserFilled" /></el-icon>学生 / 教师 / 教务分角色协同</li>
        </ul>
      </aside>

      <section class="form-panel">
        <header class="form-panel__head">
          <h2>登录</h2>
          <p>请使用学号 / 工号 / 用户名登录</p>
        </header>

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

        <!-- 演示账号 
        <div class="demo">
          <span class="demo__label">演示账号</span>
          <div class="demo__list">
            <el-link
              v-for="a in demoAccounts"
              :key="a.username"
              type="primary"
              underline="never"
              @click="fill(a)"
            >
              {{ a.label }}
            </el-link>
          </div>
        </div>
        -->
      </section>
    </div>
  </div>
</template>

<style scoped lang="scss">
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px;
  background: var(--uams-bg);
  /* 柔和的淡紫氛围光，不使用高饱和渐变块 */
  background-image:
    radial-gradient(900px 460px at 12% 8%, rgba(108, 92, 224, 0.1), transparent 62%),
    radial-gradient(760px 420px at 88% 92%, rgba(138, 124, 234, 0.09), transparent 60%);
}

.login-shell {
  width: 100%;
  max-width: 920px;
  display: grid;
  grid-template-columns: 1.05fr 1fr;
  background: var(--uams-surface);
  border: 1px solid var(--uams-border);
  border-radius: 18px;
  box-shadow: var(--uams-shadow-lg);
  overflow: hidden;
}

/* ------------------------------------------------------------ 品牌侧 */
.brand-panel {
  padding: 44px 38px;
  color: #fff;
  background: linear-gradient(150deg, var(--uams-primary) 0%, #7a6ae6 55%, #8f83ec 100%);
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 10px;

  &__mark {
    width: 44px;
    height: 44px;
    border-radius: 12px;
    display: grid;
    place-items: center;
    font-size: 20px;
    font-weight: 700;
    background: rgba(255, 255, 255, 0.18);
    border: 1px solid rgba(255, 255, 255, 0.3);
  }

  &__name {
    margin: 12px 0 0;
    font-size: 22px;
    line-height: 1.4;
    font-weight: 700;
    letter-spacing: 0.5px;
  }

  &__sub {
    margin: 0;
    font-size: 11px;
    line-height: 1.6;
    color: rgba(255, 255, 255, 0.75);
  }

  &__points {
    list-style: none;
    margin: 22px 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 12px;

    li {
      display: flex;
      align-items: center;
      gap: 9px;
      font-size: 13px;
      color: rgba(255, 255, 255, 0.92);
    }
  }
}

/* ------------------------------------------------------------ 表单侧 */
.form-panel {
  padding: 44px 38px;
  display: flex;
  flex-direction: column;
  justify-content: center;

  &__head {
    margin-bottom: 22px;

    h2 {
      margin: 0 0 6px;
      font-size: 20px;
      font-weight: 600;
      color: var(--uams-text);
    }

    p {
      margin: 0;
      font-size: 13px;
      color: var(--uams-text-3);
    }
  }
}

.submit {
  width: 100%;
  margin-top: 4px;
  height: 42px;
  font-weight: 600;
  letter-spacing: 2px;
}

.demo {
  margin-top: 22px;
  padding-top: 16px;
  border-top: 1px dashed var(--uams-border-strong);
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;

  &__label {
    color: var(--uams-text-3);
    flex: 0 0 auto;
  }

  &__list {
    display: flex;
    gap: 14px;
    flex-wrap: wrap;
  }
}

/* ---------------------------------------------------------- 响应式 */
@media (max-width: 768px) {
  .login-page {
    padding: 16px;
    align-items: flex-start;
    padding-top: 40px;
  }

  .login-shell {
    /* 手机端单列：品牌区收成紧凑头部，不再占满半屏 */
    grid-template-columns: 1fr;
    border-radius: 14px;
  }

  .brand-panel {
    padding: 22px 20px;

    &__mark,
    &__points,
    &__sub {
      display: none;
    }

    &__name {
      margin: 0;
      font-size: 17px;
    }
  }

  .form-panel {
    padding: 22px 20px 26px;
  }

  .demo {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
}
</style>
