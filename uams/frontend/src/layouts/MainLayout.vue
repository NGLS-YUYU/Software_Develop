<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { authApi } from '@/api'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const collapsed = ref(false)

const roleLabel = computed(() => {
  const t = auth.user?.user_type
  if (t === 'STUDENT') return '学生'
  if (t === 'TEACHER') return '教师'
  if (t === 'ADMIN') return '教务管理员'
  return ''
})

/** 菜单由当前角色的路由表动态生成（CLAUDE.md §15）。 */
const menus = computed(() => {
  const base = route.matched[0]?.path ?? ''
  const parent = router.getRoutes().find((r) => r.path === base && r.children?.length)
  const children = parent?.children ?? []
  return children
    .filter((c) => c.meta?.title)
    .map((c) => ({
      path: `${base}/${String(c.path).replace(/\/:.*$/, '')}`.replace(/\/+/g, '/'),
      title: c.meta!.title as string,
      icon: (c.meta!.icon as string) || 'Menu',
    }))
})

const activeMenu = computed(() => {
  // 带参数的路由（如 /teacher/grades/3）要高亮到其基础路径
  const found = menus.value.find((m) => route.path.startsWith(m.path))
  return found?.path ?? route.path
})

const pwdVisible = ref(false)
const pwdForm = ref({ old_password: '', new_password: '', confirm: '' })
const pwdLoading = ref(false)

async function changePassword() {
  if (pwdForm.value.new_password.length < 6) {
    ElMessage.warning('新密码至少 6 位')
    return
  }
  if (pwdForm.value.new_password !== pwdForm.value.confirm) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  pwdLoading.value = true
  try {
    await authApi.changePassword(pwdForm.value.old_password, pwdForm.value.new_password)
    ElMessage.success('密码已修改，请重新登录')
    pwdVisible.value = false
    await auth.logout()
    router.push('/login')
  } finally {
    pwdLoading.value = false
  }
}

async function handleLogout() {
  await ElMessageBox.confirm('确定要退出登录吗？', '提示', { type: 'warning' })
  await auth.logout()
  router.push('/login')
}
</script>

<template>
  <el-container class="layout">
    <el-aside :width="collapsed ? '64px' : '210px'" class="aside">
      <div class="logo">
        <span v-if="!collapsed">UAMS 教务系统</span>
        <span v-else>U</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        :collapse="collapsed"
        :collapse-transition="false"
        router
        class="menu"
      >
        <el-menu-item v-for="m in menus" :key="m.path" :index="m.path">
          <el-icon><component :is="m.icon" /></el-icon>
          <template #title>{{ m.title }}</template>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="left">
          <el-icon class="collapse-btn" @click="collapsed = !collapsed">
            <component :is="collapsed ? 'Expand' : 'Fold'" />
          </el-icon>
          <span class="page-title">{{ route.meta.title }}</span>
        </div>
        <div class="right">
          <el-tag size="small" type="info">{{ roleLabel }}</el-tag>
          <el-dropdown>
            <span class="user">
              {{ auth.user?.real_name }}
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="pwdVisible = true">修改密码</el-dropdown-item>
                <el-dropdown-item divided @click="handleLogout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="main">
        <router-view v-slot="{ Component }">
          <keep-alive :max="5">
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </el-main>
    </el-container>

    <el-dialog v-model="pwdVisible" title="修改密码" width="420px">
      <el-form label-width="90px">
        <el-form-item label="原密码">
          <el-input v-model="pwdForm.old_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="pwdForm.new_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input v-model="pwdForm.confirm" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdVisible = false">取消</el-button>
        <el-button type="primary" :loading="pwdLoading" @click="changePassword">
          确定
        </el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<style scoped lang="scss">
.layout {
  height: 100vh;
}

.aside {
  background: #304156;
  transition: width 0.2s;
  overflow-x: hidden;
}

.logo {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 1px;
  background: #2b3a4d;
  white-space: nowrap;
}

.menu {
  border-right: none;
  background: #304156;

  :deep(.el-menu-item) {
    color: #bfcbd9;

    &:hover {
      background: #263445;
      color: #fff;
    }

    &.is-active {
      background: #1f6feb;
      color: #fff;
    }
  }
}

.header {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;

  .left {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .collapse-btn {
    font-size: 18px;
    cursor: pointer;
    color: #606266;
  }

  .page-title {
    font-size: 16px;
    font-weight: 600;
    color: #303133;
  }

  .right {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .user {
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 4px;
    color: #303133;
    outline: none;
  }
}

.main {
  background: #f0f2f5;
  padding: 16px;
}
</style>
