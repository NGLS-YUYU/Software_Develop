<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { authApi } from '@/api'
import { currentSemester } from '@/composables/useSemester'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const collapsed = ref(false)
/** 手机端抽屉菜单开关（≤768px 时侧边栏改为抽屉） */
const drawer = ref(false)
/** 当前学期：沿用既有客户端推断（V2.1 已知技术债，本阶段不重构语义） */
const semester = currentSemester()

const roleLabel = computed(() => {
  const t = auth.user?.user_type
  if (t === 'STUDENT') return '学生'
  if (t === 'TEACHER') return '教师'
  if (t === 'ADMIN') return '教务管理员'
  return ''
})

/** 当前角色首页路径（Logo 点击回到本角色工作台） */
const homePath = computed(() => {
  const base = route.matched[0]?.path ?? ''
  return `${base}/dashboard`.replace(/\/+/g, '/')
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

/** 当前页面标题/说明（来自路由 meta，页面无需重复写标题） */
const pageTitle = computed(() => (route.meta.title as string) || '')
const pageDesc = computed(() => (route.meta.desc as string) || '')

// 手机端点击菜单后自动收起抽屉
watch(() => route.fullPath, () => {
  drawer.value = false
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
    <!-- 桌面侧边栏 -->
    <el-aside :width="collapsed ? '66px' : '216px'" class="aside">
      <div class="brand" :class="{ 'is-collapsed': collapsed }" @click="router.push(homePath)">
        <div class="brand__mark">U</div>
        <div v-if="!collapsed" class="brand__text">
          <span class="brand__name">UAMS</span>
          <span class="brand__sub">教务教学管理平台</span>
        </div>
      </div>
      <el-scrollbar class="aside__scroll">
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
      </el-scrollbar>
    </el-aside>

    <el-container class="body">
      <el-header class="header">
        <div class="left">
          <el-icon class="icon-btn desktop-only" @click="collapsed = !collapsed">
            <component :is="collapsed ? 'Expand' : 'Fold'" />
          </el-icon>
          <el-icon class="icon-btn mobile-only" @click="drawer = true">
            <component is="Menu" />
          </el-icon>
          <span class="crumb">{{ roleLabel }}</span>
        </div>
        <div class="right">
          <el-tag class="semester-chip" size="small" effect="plain">
            {{ semester }}
          </el-tag>
          <el-tag size="small" type="info" effect="plain">{{ roleLabel }}</el-tag>
          <el-dropdown>
            <span class="user">
              <span class="avatar">{{ (auth.user?.real_name || '?').slice(0, 1) }}</span>
              <span class="user__name">{{ auth.user?.real_name }}</span>
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
        <!-- 统一页面标题区：标题 + 说明，建立层级（页面无需重复写标题） -->
        <div class="page-header">
          <div>
            <h1 class="page-header__title">{{ pageTitle }}</h1>
            <p v-if="pageDesc" class="page-header__desc">{{ pageDesc }}</p>
          </div>
          <slot name="actions" />
        </div>
        <router-view v-slot="{ Component }">
          <keep-alive :max="5">
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </el-main>
    </el-container>

    <!-- 手机端抽屉菜单 -->
    <el-drawer v-model="drawer" direction="ltr" size="240px" :with-header="false" class="nav-drawer">
      <div class="brand brand--drawer">
        <div class="brand__mark">U</div>
        <div class="brand__text">
          <span class="brand__name">UAMS</span>
          <span class="brand__sub">教务教学管理平台</span>
        </div>
      </div>
      <el-menu
        :default-active="activeMenu"
        router
        class="menu menu--drawer"
      >
        <el-menu-item v-for="m in menus" :key="m.path" :index="m.path">
          <el-icon><component :is="m.icon" /></el-icon>
          <template #title>{{ m.title }}</template>
        </el-menu-item>
      </el-menu>
    </el-drawer>

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
  background: var(--uams-bg);
}

/* ------------------------------------------------------------- 侧边栏 */
.aside {
  background: var(--uams-surface);
  border-right: 1px solid var(--uams-border);
  transition: width 0.2s ease;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.aside__scroll {
  flex: 1;
}

.brand {
  height: 60px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  cursor: pointer;
  border-bottom: 1px solid var(--uams-border);
  white-space: nowrap;

  &.is-collapsed {
    justify-content: center;
    padding: 0;
  }

  &__mark {
    width: 32px;
    height: 32px;
    flex: 0 0 32px;
    border-radius: 9px;
    display: grid;
    place-items: center;
    font-weight: 700;
    color: #fff;
    font-size: 16px;
    background: linear-gradient(135deg, var(--uams-primary), var(--uams-primary-light));
    box-shadow: 0 4px 12px rgba(108, 92, 224, 0.28);
  }

  &__text {
    display: flex;
    flex-direction: column;
    line-height: 1.25;
  }

  &__name {
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 0.6px;
    color: var(--uams-text);
  }

  &__sub {
    font-size: 11px;
    color: var(--uams-text-3);
  }

  &--drawer {
    border-bottom: 1px solid var(--uams-border);
  }
}

/* 菜单：白底 + 淡紫选中，去掉 Element 默认边框与深色块 */
.menu {
  border-right: none;
  background: transparent;
  padding: 8px;

  :deep(.el-menu-item) {
    height: 42px;
    line-height: 42px;
    margin-bottom: 4px;
    border-radius: var(--uams-radius-sm);
    color: var(--uams-text-2);
    font-size: 14px;

    &:hover {
      background: var(--uams-primary-softer);
      color: var(--uams-primary-dark);
    }

    &.is-active {
      background: var(--uams-primary-soft);
      color: var(--uams-primary-dark);
      font-weight: 600;
    }
  }

  &--drawer {
    padding: 8px;
  }
}

/* --------------------------------------------------------------- 顶栏 */
.header {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--uams-surface);
  border-bottom: 1px solid var(--uams-border);
  padding: 0 18px;

  .left {
    display: flex;
    align-items: center;
    gap: 12px;
    min-width: 0;
  }

  .crumb {
    font-size: 13px;
    color: var(--uams-text-3);
  }

  .icon-btn {
    font-size: 36px;
    cursor: pointer;
    color: var(--uams-text-2);
    padding: 6px;
    border-radius: var(--uams-radius-xs);

    &:hover {
      background: var(--uams-primary-softer);
      color: var(--uams-primary-dark);
    }
  }

  .right {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .semester-chip {
    border-color: var(--uams-primary-light);
    color: var(--uams-primary-dark);
    background: var(--uams-primary-softer);
  }

  .user {
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--uams-text);
    outline: none;
    padding: 4px 6px;
    border-radius: var(--uams-radius-sm);

    &:hover {
      background: var(--uams-primary-softer);
    }
  }

  .avatar {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    font-size: 13px;
    font-weight: 600;
    color: #fff;
    background: linear-gradient(135deg, var(--uams-primary), var(--uams-primary-light));
  }

  .user__name {
    font-size: 13px;
    font-weight: 500;
  }
}

/* --------------------------------------------------------------- 内容 */
.main {
  background: var(--uams-bg);
  padding: 20px;
  overflow-y: auto;
}

/* 显示/隐藏工具类 */
.mobile-only {
  display: none;
}

@media (max-width: 768px) {
  .aside {
    display: none;
  }

  .desktop-only {
    display: none;
  }

  .mobile-only {
    display: inline-flex;
  }

  .header {
    height: 56px;
    padding: 0 12px;

    .crumb,
    .semester-chip {
      display: none;
    }

    .user__name {
      display: none;
    }
  }

  .main {
    padding: 12px;
  }
}
</style>
