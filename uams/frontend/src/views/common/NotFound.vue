<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { roleHome } from '@/router'

const router = useRouter()
const auth = useAuthStore()
</script>

<template>
  <div class="state-page">
    <div class="state-card">
      <div class="state-card__badge">
        <el-icon><component is="Compass" /></el-icon>
      </div>
      <h2 class="state-card__title">404</h2>
      <p class="state-card__desc">您访问的页面不存在或已被移除，请检查地址是否正确。</p>
      <div class="state-card__actions">
        <el-button type="primary" @click="router.push(roleHome(auth.user?.user_type))">
          返回首页
        </el-button>
        <el-button @click="router.back()">返回上一页</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.state-page {
  min-height: 60vh;
  display: grid;
  place-items: center;
  padding: 24px;
}

.state-card {
  width: 100%;
  max-width: 440px;
  text-align: center;
  padding: 40px 28px;
  background: var(--uams-surface);
  border: 1px solid var(--uams-border);
  border-radius: var(--uams-radius);
  box-shadow: var(--uams-shadow-sm);

  &__badge {
    width: 56px;
    height: 56px;
    margin: 0 auto 16px;
    border-radius: 16px;
    display: grid;
    place-items: center;
    font-size: 26px;
    color: var(--uams-primary-dark);
    background: var(--uams-primary-soft);
  }

  &__title {
    margin: 0 0 8px;
    font-size: 30px;
    font-weight: 700;
    letter-spacing: 1px;
    color: var(--uams-text);
  }

  &__desc {
    margin: 0 0 22px;
    font-size: 13px;
    line-height: 1.7;
    color: var(--uams-text-3);
  }

  &__actions {
    display: flex;
    gap: 10px;
    justify-content: center;
    flex-wrap: wrap;
  }
}

@media (max-width: 420px) {
  .state-card {
    padding: 30px 18px;

    &__actions {
      flex-direction: column;

      :deep(.el-button) {
        width: 100%;
        margin-left: 0;
      }
    }
  }
}
</style>
