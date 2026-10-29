/** 认证状态。
 *
 * 注意：前端权限仅用于菜单与路由控制，
 * 真正的权限校验在后端（CLAUDE.md §9 / PRD §4.2）。
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { authApi, termApi } from '@/api'
import { setForbiddenHandler, setUnauthorizedHandler } from '@/api/request'
import { setActiveSemester } from '@/composables/useSemester'
import type { UserInfo } from '@/types'

const TOKEN_KEY = 'uams_token'
/** 管理员角色代码：前端判定管理员身份的唯一依据（与后端一致） */
const ADMIN_ROLE = 'ACADEMIC_ADMIN'
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
  /** 管理员**只看角色**：教师被授予 ACADEMIC_ADMIN 后算管理员；
   *  反过来，user_type 为 ADMIN 但角色被撤销后**不再**算管理员（权限本就来自角色）。 */
  const isAdmin = computed(() => roles.value.includes('ACADEMIC_ADMIN'))
  /** 访问身份集合 = 端身份(user_type，排除 ADMIN) ∪ 角色代码，供路由守卫判断能否进入某端。
   *  'ADMIN' 不作为身份来源：否则 user_type=ADMIN 且角色被撤销的账号仍能进入教务端，
   *  进去后每个接口都 403，界面与真实权限不一致。 */
  const identities = computed(() => [
    ...(user.value?.user_type && user.value.user_type !== 'ADMIN'
      ? [user.value.user_type]
      : []),
    ...roles.value,
  ])
  /** 教师兼任管理员：同时具备教师端与教务端身份 */
  const isDualRole = computed(() => isTeacher.value && isAdmin.value)

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

  /** 登录/刷新后同步后端 ACTIVE 学期（F-05）。失败时回退浏览器推断。 */
  async function syncActiveTerm() {
    try {
      const t = await termApi.active()
      setActiveSemester(`${t.academic_year}-${t.semester}`)
    } catch {
      setActiveSemester(null)
    }
  }

  async function login(username: string, real_name: string, password: string) {
    const res = await authApi.login(username, real_name, password)
    // 后端返回 200 但没有有效凭证时，绝不能进入系统。
    if (
      !res?.access_token ||
      !res?.user?.id ||
      !res?.home_route ||
      !Array.isArray(res.roles) ||
      !Array.isArray(res.permissions)
    ) {
      clear()
      throw new Error('INVALID_LOGIN_RESPONSE')
    }
    token.value = res.access_token
    user.value = res.user
    roles.value = res.roles
    permissions.value = res.permissions
    homeRoute.value = res.home_route
    persist()
    await syncActiveTerm()
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
    await syncActiveTerm()
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

  /** 403 处理：只在「确认管理员权限已被撤销」时才调整界面，普通业务越权不打扰登录态。 */
  let reconciling = false
  setForbiddenHandler(async () => {
    // 以「角色」判定：本地从未持有管理员角色 → 属普通业务越权（如学生调教师接口），
    // 只提示，绝不清理登录态、绝不跳转。
    if (!roles.value.includes(ADMIN_ROLE) || reconciling) return
    reconciling = true
    try {
      await refresh() // 重新拉取当前用户真实角色/权限（后端为最终裁判）
    } catch {
      // 刷新失败（如 401）会由 401 分支处理，这里不重复动作
      return
    } finally {
      reconciling = false
    }
    if (roles.value.includes(ADMIN_ROLE)) return // 角色仍在 → 瞬态 403，交给调用方
    ElMessage.warning('你的管理员权限已被撤销，正在切换到当前身份')
    redirectToHomeByIdentity()
  })

  /** 按当前真实身份回到对应工作台；无任何有效身份则清理登录态回登录页。 */
  function redirectToHomeByIdentity() {
    if (isTeacher.value) {
      location.assign('/teacher/dashboard')
    } else if (isStudent.value) {
      location.assign('/student/dashboard')
    } else if (user.value?.user_type === 'ADMIN') {
      // 账号类别仍是管理员但已无管理员角色：无任何可用工作台
      clear()
      location.assign('/login')
    } else {
      clear()
      location.assign('/login')
    }
  }

  /** 多标签页一致性：其他标签页登录/退出后，本页重新对齐（避免旧身份界面与新 Token 不一致）。 */
  window.addEventListener('storage', (e) => {
    if (e.key !== TOKEN_KEY) return
    const next = e.newValue ?? ''
    if (next === token.value) return
    if (!next) {
      // 其他标签页已退出 → 本页同步清理（避免仍用旧身份展示界面）
      clear()
      location.assign('/login')
    } else {
      // 其他标签页切换了登录身份 → 回到入口按新身份重新分发工作台，
      // 避免「旧角色界面 + 新 Token」的不一致状态
      location.assign('/')
    }
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
    identities,
    isDualRole,
    has,
    hasAny,
    login,
    logout,
    refresh,
    clear,
  }
})
