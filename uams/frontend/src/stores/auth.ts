/** 认证状态。
 *
 * 注意：前端权限仅用于菜单与路由控制，
 * 真正的权限校验在后端（CLAUDE.md §9 / PRD §4.2）。
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { authApi } from '@/api'
import { setUnauthorizedHandler } from '@/api/request'
import type { UserInfo } from '@/types'

const TOKEN_KEY = 'uams_token'
const USER_KEY = 'uams_user'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(localStorage.getItem(TOKEN_KEY) || '')
  const user = ref<UserInfo | null>(
    localStorage.getItem(USER_KEY) ? JSON.parse(localStorage.getItem(USER_KEY)!) : null,
  )
  const roles = ref<string[]>([])
  const permissions = ref<string[]>([])
  const homeRoute = ref<string>('/')

  const isLoggedIn = computed(() => !!token.value)
  const isStudent = computed(() => user.value?.user_type === 'STUDENT')
  const isTeacher = computed(() => user.value?.user_type === 'TEACHER')
  const isAdmin = computed(() => user.value?.user_type === 'ADMIN')

  function has(permission: string) {
    return permissions.value.includes(permission)
  }

  function hasAny(...codes: string[]) {
    return codes.some((c) => permissions.value.includes(c))
  }

  function persist() {
    localStorage.setItem(TOKEN_KEY, token.value)
    if (user.value) localStorage.setItem(USER_KEY, JSON.stringify(user.value))
  }

  async function login(username: string, password: string) {
    const res = await authApi.login(username, password)
    token.value = res.access_token
    user.value = res.user
    roles.value = res.roles
    permissions.value = res.permissions
    homeRoute.value = res.home_route
    persist()
    return res
  }

  /** 刷新页面后恢复角色与权限（这些不落 localStorage，避免被篡改后误导菜单）。 */
  async function refresh() {
    if (!token.value) return
    const res = await authApi.me()
    user.value = res.user
    roles.value = res.roles
    permissions.value = res.permissions
    persist()
  }

  function clear() {
    token.value = ''
    user.value = null
    roles.value = []
    permissions.value = []
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }

  async function logout() {
    try {
      await authApi.logout()
    } catch {
      // 退出接口失败不应阻塞前端清理
    }
    clear()
  }

  setUnauthorizedHandler(() => {
    clear()
    location.href = '/login'
  })

  return {
    token,
    user,
    roles,
    permissions,
    homeRoute,
    isLoggedIn,
    isStudent,
    isTeacher,
    isAdmin,
    has,
    hasAny,
    login,
    logout,
    refresh,
    clear,
  }
})
