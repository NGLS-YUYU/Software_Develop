/** 路由与角色守卫。
 *
 * 前端守卫只负责体验（不展示无权菜单、不进入无权页面），
 * 真正的权限校验在后端（CLAUDE.md §15）。
 */

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true, title: '登录' },
  },

  // --- 学生端 ---
  {
    path: '/student',
    component: () => import('@/layouts/MainLayout.vue'),
    meta: { roles: ['STUDENT'] },
    children: [
      { path: '', redirect: '/student/dashboard' },
      {
        path: 'dashboard',
        name: 'student-dashboard',
        component: () => import('@/views/student/Dashboard.vue'),
        meta: { title: '首页', icon: 'HomeFilled' },
      },
      {
        path: 'profile',
        name: 'student-profile',
        component: () => import('@/views/student/Profile.vue'),
        meta: { title: '我的信息', icon: 'User' },
      },
      {
        path: 'schedule',
        name: 'student-schedule',
        component: () => import('@/views/student/Schedule.vue'),
        meta: { title: '我的课表', icon: 'Calendar' },
      },
      {
        path: 'selection',
        name: 'student-selection',
        component: () => import('@/views/student/Selection.vue'),
        meta: { title: '在线选课', icon: 'Checked' },
      },
      {
        path: 'grades',
        name: 'student-grades',
        component: () => import('@/views/student/Grades.vue'),
        meta: { title: '我的成绩', icon: 'Trophy' },
      },
      {
        path: 'exams',
        name: 'student-exams',
        component: () => import('@/views/student/Exams.vue'),
        meta: { title: '考试安排', icon: 'EditPen' },
      },
      {
        path: 'evaluation',
        name: 'student-evaluation',
        component: () => import('@/views/student/Evaluation.vue'),
        meta: { title: '教学评价', icon: 'Star' },
      },
      {
        path: 'announcements',
        name: 'student-announcements',
        component: () => import('@/views/common/Announcements.vue'),
        meta: { title: '通知公告', icon: 'Bell' },
      },
    ],
  },

  // --- 教师端 ---
  {
    path: '/teacher',
    component: () => import('@/layouts/MainLayout.vue'),
    meta: { roles: ['TEACHER'] },
    children: [
      { path: '', redirect: '/teacher/dashboard' },
      {
        path: 'dashboard',
        name: 'teacher-dashboard',
        component: () => import('@/views/teacher/Dashboard.vue'),
        meta: { title: '工作台', icon: 'HomeFilled' },
      },
      {
        path: 'courses',
        name: 'teacher-courses',
        component: () => import('@/views/teacher/MyCourses.vue'),
        meta: { title: '我的课程', icon: 'Reading' },
      },
      {
        path: 'schedule',
        name: 'teacher-schedule',
        component: () => import('@/views/teacher/Schedule.vue'),
        meta: { title: '我的课表', icon: 'Calendar' },
      },
      {
        path: 'grades/:classId?',
        name: 'teacher-grades',
        component: () => import('@/views/teacher/GradeEntry.vue'),
        meta: { title: '成绩录入', icon: 'EditPen' },
      },
      {
        path: 'evaluation',
        name: 'teacher-evaluation',
        component: () => import('@/views/teacher/Evaluation.vue'),
        meta: { title: '教学评价', icon: 'Star' },
      },
      {
        path: 'announcements',
        name: 'teacher-announcements',
        component: () => import('@/views/common/Announcements.vue'),
        meta: { title: '通知公告', icon: 'Bell' },
      },
    ],
  },

  // --- 教务端 ---
  {
    path: '/admin',
    component: () => import('@/layouts/MainLayout.vue'),
    meta: { roles: ['ADMIN'] },
    children: [
      { path: '', redirect: '/admin/dashboard' },
      {
        path: 'dashboard',
        name: 'admin-dashboard',
        component: () => import('@/views/admin/Dashboard.vue'),
        meta: { title: '工作台', icon: 'HomeFilled' },
      },
      {
        path: 'colleges',
        name: 'admin-colleges',
        component: () => import('@/views/admin/Organization.vue'),
        meta: { title: '组织机构', icon: 'OfficeBuilding' },
      },
      {
        path: 'students',
        name: 'admin-students',
        component: () => import('@/views/admin/Students.vue'),
        meta: { title: '学生管理', icon: 'User' },
      },
      {
        path: 'teachers',
        name: 'admin-teachers',
        component: () => import('@/views/admin/Teachers.vue'),
        meta: { title: '教师管理', icon: 'Avatar' },
      },
      {
        path: 'courses',
        name: 'admin-courses',
        component: () => import('@/views/admin/Courses.vue'),
        meta: { title: '课程管理', icon: 'Reading' },
      },
      {
        path: 'curriculum',
        name: 'admin-curriculum',
        component: () => import('@/views/admin/Curriculum.vue'),
        meta: { title: '培养方案', icon: 'Document' },
      },
      {
        path: 'teaching',
        name: 'admin-teaching',
        component: () => import('@/views/admin/Teaching.vue'),
        meta: { title: '开课排课', icon: 'Grid' },
      },
      {
        path: 'selection',
        name: 'admin-selection',
        component: () => import('@/views/admin/SelectionManage.vue'),
        meta: { title: '选课管理', icon: 'Checked' },
      },
      {
        path: 'grades',
        name: 'admin-grades',
        component: () => import('@/views/admin/GradeApproval.vue'),
        meta: { title: '成绩审核', icon: 'Stamp' },
      },
      {
        path: 'exams',
        name: 'admin-exams',
        component: () => import('@/views/admin/Exams.vue'),
        meta: { title: '考试管理', icon: 'EditPen' },
      },
      {
        path: 'announcements',
        name: 'admin-announcements',
        component: () => import('@/views/admin/AnnouncementManage.vue'),
        meta: { title: '公告管理', icon: 'Bell' },
      },
      {
        path: 'statistics',
        name: 'admin-statistics',
        component: () => import('@/views/admin/Statistics.vue'),
        meta: { title: '数据统计', icon: 'TrendCharts' },
      },
    ],
  },

  { path: '/', redirect: '/login' },
  {
    path: '/403',
    name: 'forbidden',
    component: () => import('@/views/common/Forbidden.vue'),
    meta: { public: true, title: '无权访问' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/common/NotFound.vue'),
    meta: { public: true, title: '页面不存在' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  document.title = to.meta.title ? `${to.meta.title} - UAMS` : 'UAMS 高校教务教学管理系统'

  if (to.meta.public) {
    // 已登录用户访问登录页，直接回各自首页
    if (to.path === '/login' && auth.isLoggedIn) {
      return roleHome(auth.user?.user_type)
    }
    return true
  }

  if (!auth.isLoggedIn) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  // 刷新页面后权限为空，需要向后端重新拉取
  if (auth.permissions.length === 0) {
    try {
      await auth.refresh()
    } catch {
      return { path: '/login' }
    }
  }

  const allowed = to.matched.find((r) => r.meta.roles)?.meta.roles as string[] | undefined
  if (allowed && !allowed.includes(auth.user?.user_type ?? '')) {
    return { path: '/403' }
  }
  return true
})

function roleHome(type?: string) {
  if (type === 'STUDENT') return '/student/dashboard'
  if (type === 'TEACHER') return '/teacher/dashboard'
  if (type === 'ADMIN') return '/admin/dashboard'
  return '/login'
}

export { roleHome }
export default router
