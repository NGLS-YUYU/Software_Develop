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
        meta: { title: '首页', desc: '本学期课表、成绩与待办', icon: 'HomeFilled' },
      },
      {
        path: 'profile',
        name: 'student-profile',
        component: () => import('@/views/student/Profile.vue'),
        meta: { title: '我的信息', desc: '个人学籍信息', icon: 'User' },
      },
      {
        path: 'schedule',
        name: 'student-schedule',
        component: () => import('@/views/student/Schedule.vue'),
        meta: { title: '我的课表', desc: '本人已选课程课表', icon: 'Calendar' },
      },
      {
        path: 'curriculum',
        name: 'student-curriculum',
        component: () => import('@/views/student/Curriculum.vue'),
        meta: { title: '培养方案', desc: '本人专业的培养方案与课程设置', icon: 'Document' },
      },
      {
        path: 'materials',
        name: 'student-materials',
        component: () => import('@/views/student/Materials.vue'),
        meta: { title: '教学资料', desc: '本人已选课程的教学资料', icon: 'Folder' },
      },
      {
        path: 'selection',
        name: 'student-selection',
        component: () => import('@/views/student/Selection.vue'),
        meta: { title: '在线选课', desc: '在线选课与退课', icon: 'Checked' },
      },
      {
        path: 'grades',
        name: 'student-grades',
        component: () => import('@/views/student/Grades.vue'),
        meta: { title: '我的成绩', desc: '已发布成绩、绩点与排名', icon: 'Trophy' },
      },
      {
        path: 'exams',
        name: 'student-exams',
        component: () => import('@/views/student/Exams.vue'),
        meta: { title: '考试安排', desc: '考试安排与考场', icon: 'EditPen' },
      },
      {
        path: 'evaluation',
        name: 'student-evaluation',
        component: () => import('@/views/student/Evaluation.vue'),
        meta: { title: '教学评价', desc: '课程教学评价', icon: 'Star' },
      },
      {
        path: 'announcements',
        name: 'student-announcements',
        component: () => import('@/views/common/Announcements.vue'),
        meta: { title: '通知公告', desc: '教务通知', icon: 'Bell' },
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
        meta: { title: '工作台', desc: '本学期教学任务与待办事项', icon: 'HomeFilled' },
      },
      {
        path: 'courses',
        name: 'teacher-courses',
        component: () => import('@/views/teacher/MyCourses.vue'),
        meta: { title: '我的课程', desc: '本人授课的教学班与学生', icon: 'Reading' },
      },
      {
        path: 'materials',
        name: 'teacher-materials',
        component: () => import('@/views/teacher/Materials.vue'),
        meta: { title: '教学资料', desc: '本人授课教学班的资料上传与下载', icon: 'Folder' },
      },
      {
        path: 'schedule',
        name: 'teacher-schedule',
        component: () => import('@/views/teacher/Schedule.vue'),
        meta: { title: '我的课表', desc: '本人授课课表', icon: 'Calendar' },
      },
      {
        path: 'grades/:classId?',
        name: 'teacher-grades',
        component: () => import('@/views/teacher/GradeEntry.vue'),
        meta: { title: '成绩录入', desc: '成绩录入、保存草稿与提交审核', icon: 'EditPen' },
      },
      {
        path: 'adjustments',
        name: 'teacher-adjustments',
        component: () => import('@/views/teacher/Adjustments.vue'),
        meta: { title: '调停课申请', desc: '调课、停课与补课申请', icon: 'Refresh' },
      },
      {
        path: 'evaluation',
        name: 'teacher-evaluation',
        component: () => import('@/views/teacher/Evaluation.vue'),
        meta: { title: '教学评价', desc: '学生评教结果', icon: 'Star' },
      },
      {
        path: 'announcements',
        name: 'teacher-announcements',
        component: () => import('@/views/common/Announcements.vue'),
        meta: { title: '通知公告', desc: '教务通知', icon: 'Bell' },
      },
    ],
  },

  // --- 教务端 ---
  {
    path: '/admin',
    component: () => import('@/layouts/MainLayout.vue'),
    // 允许「账号类别为 ADMIN」或「持有 ACADEMIC_ADMIN 角色」的账号进入教务端
    meta: { roles: ['ADMIN', 'ACADEMIC_ADMIN'] },
    children: [
      { path: '', redirect: '/admin/dashboard' },
      {
        path: 'dashboard',
        name: 'admin-dashboard',
        component: () => import('@/views/admin/Dashboard.vue'),
        meta: { title: '工作台', desc: '全校教学运行概览与待办', icon: 'HomeFilled' },
      },
      {
        path: 'colleges',
        name: 'admin-colleges',
        component: () => import('@/views/admin/Organization.vue'),
        meta: { title: '组织机构', desc: '学院、专业、班级与教室等基础组织数据', icon: 'OfficeBuilding' },
      },
      {
        path: 'students',
        name: 'admin-students',
        component: () => import('@/views/admin/Students.vue'),
        meta: { title: '学生管理', desc: '学生档案与学籍信息', icon: 'User' },
      },
      {
        path: 'teachers',
        name: 'admin-teachers',
        component: () => import('@/views/admin/Teachers.vue'),
        meta: { title: '教师管理', desc: '教师档案与任课信息', icon: 'Avatar' },
      },
      {
        path: 'courses',
        name: 'admin-courses',
        component: () => import('@/views/admin/Courses.vue'),
        meta: { title: '课程管理', desc: '课程库、学时与先修关系', icon: 'Reading' },
      },
      {
        path: 'curriculum',
        name: 'admin-curriculum',
        component: () => import('@/views/admin/Curriculum.vue'),
        meta: { title: '培养方案', desc: '各专业培养方案与课程设置', icon: 'Document' },
      },
      {
        path: 'teaching',
        name: 'admin-teaching',
        component: () => import('@/views/admin/Teaching.vue'),
        meta: { title: '开课排课', desc: '教学任务、教学班与排课安排', icon: 'Grid' },
      },
      {
        path: 'adjustments',
        name: 'admin-adjustments',
        component: () => import('@/views/admin/Adjustments.vue'),
        meta: { title: '调停课审核', desc: '教师调课/停课/补课申请的审核', icon: 'Refresh' },
      },
      {
        path: 'selection',
        name: 'admin-selection',
        component: () => import('@/views/admin/SelectionManage.vue'),
        meta: { title: '选课管理', desc: '选课开放与选课结果管理', icon: 'Checked' },
      },
      {
        path: 'admins',
        name: 'admin-admins',
        component: () => import('@/views/admin/AdminManage.vue'),
        meta: { title: '管理员管理', icon: 'Key', desc: '管理员账号创建、教师授权与权限变更记录' },
      },
      {
        path: 'terms',
        name: 'admin-terms',
        component: () => import('@/views/admin/Terms.vue'),
        meta: { title: '学期管理', desc: '学期建立、激活与结束', icon: 'Calendar' },
      },
      {
        path: 'audit-logs',
        name: 'admin-audit-logs',
        component: () => import('@/views/admin/AuditLogs.vue'),
        meta: { title: '操作日志', desc: '关键业务操作审计查询', icon: 'Document' },
      },
      {
        path: 'imports',
        name: 'admin-imports',
        component: () => import('@/views/admin/ImportCenter.vue'),
        meta: { title: '批量导入', desc: '学生 / 教师 / 课程 / 成绩的 Excel 批量导入', icon: 'Upload' },
      },
      {
        path: 'grades',
        name: 'admin-grades',
        component: () => import('@/views/admin/GradeApproval.vue'),
        meta: { title: '成绩审核', desc: '教师提交成绩的审核与发布', icon: 'Stamp' },
      },
      {
        path: 'evaluations',
        name: 'admin-evaluations',
        component: () => import('@/views/admin/Evaluations.vue'),
        meta: { title: '教学评价', desc: '评价任务的创建与开放', icon: 'Star' },
      },
      {
        path: 'exams',
        name: 'admin-exams',
        component: () => import('@/views/admin/Exams.vue'),
        meta: { title: '考试管理', desc: '考试安排与考场座位', icon: 'EditPen' },
      },
      {
        path: 'announcements',
        name: 'admin-announcements',
        component: () => import('@/views/admin/AnnouncementManage.vue'),
        meta: { title: '公告管理', desc: '面向学生与教师的通知发布', icon: 'Bell' },
      },
      {
        path: 'statistics',
        name: 'admin-statistics',
        component: () => import('@/views/admin/Statistics.vue'),
        meta: { title: '数据统计', desc: '选课热度与成绩分布统计', icon: 'TrendCharts' },
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

  // 访问身份 = user_type ∪ 角色代码：教师兼任管理员时 user_type 仍为 TEACHER，
  // 但其拥有 ACADEMIC_ADMIN 角色，应当允许进入教务端（后端权限仍是最终裁判）。
  const allowed = to.matched.find((r) => r.meta.roles)?.meta.roles as string[] | undefined
  if (allowed && !allowed.some((r) => auth.identities.includes(r))) {
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
