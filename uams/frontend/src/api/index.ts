/** 按业务模块组织的 API 调用。 */

import { del, download, get, post, put, upload, uploadForm } from './request'
import type {
  Adjustment,
  AdminAccount,
  Announcement,
  ClassInfo,
  ClassRosterStudent,
  AuditLog,
  Classroom,
  College,
  Course,
  CurriculumCourse,
  CurriculumPlan,
  EvaluationStats,
  EvaluationTask,
  Exam,
  ExamRoom,
  Grade,
  GradeChangeLog,
  GradeStatistics,
  GradeSummary,
  ImportKind,
  ImportResult,
  LoginResponse,
  Major,
  Material,
  Overview,
  PageQuery,
  PageResult,
  PendingEvaluation,
  Prerequisite,
  Schedule,
  ScheduleItem,
  Selection,
  SelectionPeriod,
  SelectionWindowStatus,
  RequiredAssignResult,
  Student,
  StudentGradeOverview,
  Teacher,
  TeachingClass,
  TeachingTask,
  Term,
  UserInfo,
} from '@/types'

// --- 认证 ---
export const authApi = {
  login: (username: string, password: string) =>
    post<LoginResponse>('/auth/login', { username, password }),
  me: () =>
    get<{ user: UserInfo; roles: string[]; permissions: string[] }>('/auth/me'),
  changePassword: (old_password: string, new_password: string) =>
    post<void>('/auth/change-password', { old_password, new_password }),
  logout: () => post<void>('/auth/logout'),
}

// --- 基础数据 ---
export const collegeApi = {
  list: (q?: PageQuery & { status?: string }) => get<PageResult<College>>('/colleges', q),
  get: (id: number) => get<College>(`/colleges/${id}`),
  create: (b: Partial<College>) => post<College>('/colleges', b),
  update: (id: number, b: Partial<College>) => put<College>(`/colleges/${id}`, b),
  remove: (id: number) => del(`/colleges/${id}`),
}

export const majorApi = {
  list: (q?: PageQuery & { college_id?: number }) => get<PageResult<Major>>('/majors', q),
  create: (b: Partial<Major>) => post<Major>('/majors', b),
  update: (id: number, b: Partial<Major>) => put<Major>(`/majors/${id}`, b),
  remove: (id: number) => del(`/majors/${id}`),
}

export const classApi = {
  list: (q?: PageQuery & { major_id?: number; grade_year?: number }) =>
    get<PageResult<ClassInfo>>('/classes', q),
  create: (b: Partial<ClassInfo>) => post<ClassInfo>('/classes', b),
  update: (id: number, b: Partial<ClassInfo>) => put<ClassInfo>(`/classes/${id}`, b),
  remove: (id: number) => del(`/classes/${id}`),
}

export const classroomApi = {
  list: (q?: PageQuery & { building?: string; room_type?: string }) =>
    get<PageResult<Classroom>>('/classrooms', q),
  create: (b: Partial<Classroom>) => post<Classroom>('/classrooms', b),
  update: (id: number, b: Partial<Classroom>) => put<Classroom>(`/classrooms/${id}`, b),
  remove: (id: number) => del(`/classrooms/${id}`),
}

// --- 人员 ---
export const studentApi = {
  list: (q?: PageQuery & { class_id?: number; major_id?: number; college_id?: number }) =>
    get<PageResult<Student>>('/students', q),
  me: () => get<Student>('/students/me'),
  get: (id: number) => get<Student>(`/students/${id}`),
  create: (b: Record<string, unknown>) => post<Student>('/students', b),
  update: (id: number, b: Record<string, unknown>) => put<Student>(`/students/${id}`, b),
  remove: (id: number) => del(`/students/${id}`),
}

export const teacherApi = {
  list: (q?: PageQuery & { college_id?: number; title?: string }) =>
    get<PageResult<Teacher>>('/teachers', q),
  me: () => get<Teacher>('/teachers/me'),
  create: (b: Record<string, unknown>) => post<Teacher>('/teachers', b),
  update: (id: number, b: Record<string, unknown>) => put<Teacher>(`/teachers/${id}`, b),
  remove: (id: number) => del(`/teachers/${id}`),
}

// --- 课程 ---
export const courseApi = {
  list: (q?: PageQuery & { college_id?: number; course_type?: string }) =>
    get<PageResult<Course>>('/courses', q),
  get: (id: number) => get<Course>(`/courses/${id}`),
  create: (b: Partial<Course>) => post<Course>('/courses', b),
  update: (id: number, b: Partial<Course>) => put<Course>(`/courses/${id}`, b),
  remove: (id: number) => del(`/courses/${id}`),
  prerequisites: (id: number) => get<Prerequisite[]>(`/courses/${id}/prerequisites`),
  addPrerequisite: (id: number, prerequisite_course_id: number, min_score = 60) =>
    post<Prerequisite>(`/courses/${id}/prerequisites`, {
      prerequisite_course_id,
      min_score,
    }),
  removePrerequisite: (id: number, rowId: number) =>
    del(`/courses/${id}/prerequisites/${rowId}`),
}

export const curriculumApi = {
  list: (q?: PageQuery & { major_id?: number; grade_year?: number }) =>
    get<PageResult<CurriculumPlan>>('/curriculum-plans', q),
  get: (id: number) => get<CurriculumPlan>(`/curriculum-plans/${id}`),
  create: (b: Partial<CurriculumPlan>) => post<CurriculumPlan>('/curriculum-plans', b),
  update: (id: number, b: Partial<CurriculumPlan>) =>
    put<CurriculumPlan>(`/curriculum-plans/${id}`, b),
  remove: (id: number) => del(`/curriculum-plans/${id}`),
  courses: (id: number) => get<CurriculumCourse[]>(`/curriculum-plans/${id}/courses`),
  addCourse: (id: number, course_id: number, suggested_semester: number, is_required = true) =>
    post<CurriculumCourse>(`/curriculum-plans/${id}/courses`, {
      course_id,
      suggested_semester,
      is_required,
    }),
  removeCourse: (id: number, rowId: number) =>
    del(`/curriculum-plans/${id}/courses/${rowId}`),
}

// --- 开课排课 ---
export const teachingApi = {
  tasks: (q?: PageQuery & { semester?: string; course_id?: number }) =>
    get<PageResult<TeachingTask>>('/teaching-tasks', q),
  createTask: (b: Record<string, unknown>) => post<TeachingTask>('/teaching-tasks', b),
  updateTask: (id: number, b: Record<string, unknown>) =>
    put<TeachingTask>(`/teaching-tasks/${id}`, b),
  removeTask: (id: number) => del(`/teaching-tasks/${id}`),

  classes: (q?: PageQuery & {
    semester?: string
    course_id?: number
    teacher_id?: number
    selection_status?: string
  }) => get<PageResult<TeachingClass>>('/teaching-classes', q),
  getClass: (id: number) => get<TeachingClass>(`/teaching-classes/${id}`),
  createClass: (b: Record<string, unknown>) => post<TeachingClass>('/teaching-classes', b),
  updateClass: (id: number, b: Record<string, unknown>) =>
    put<TeachingClass>(`/teaching-classes/${id}`, b),
  removeClass: (id: number) => del(`/teaching-classes/${id}`),
  toggleSelection: (id: number, open: boolean) =>
    post<TeachingClass>(`/teaching-classes/${id}/selection?open=${open}`),

  schedules: (id: number) => get<Schedule[]>(`/teaching-classes/${id}/schedules`),
  addSchedule: (id: number, b: Record<string, unknown>) =>
    post<Schedule>(`/teaching-classes/${id}/schedules`, b),
  removeSchedule: (id: number, sid: number) =>
    del(`/teaching-classes/${id}/schedules/${sid}`),

  /** 教学班当前名单（含来源、安排时间；FIX-002）。 */
  students: (id: number) =>
    get<ClassRosterStudent[]>(`/teaching-classes/${id}/students`),
  /** 必修课预安排：preview=true 只预览，false 正式提交（FIX-002）。 */
  assignRequired: (id: number, body: Record<string, unknown>, preview = false) =>
    post<RequiredAssignResult>(
      `/teaching-classes/${id}/assign-required?preview=${preview}`,
      body,
    ),
  /** 教务手动添加学生（FIX-002）。 */
  addStudent: (id: number, studentId: number) =>
    post<{ selection_id: number; student_id: number; message: string }>(
      `/teaching-classes/${id}/students`,
      { student_id: studentId },
    ),
  /** 教务手动移除学生（FIX-002；已有成绩时后端 409）。 */
  removeStudent: (id: number, studentId: number) =>
    del(`/teaching-classes/${id}/students/${studentId}`),
}

// --- 选课 ---
export const selectionApi = {
  available: (semester: string, keyword?: string) =>
    get<TeachingClass[]>('/course-selections/available', { semester, keyword }),
  mine: (semester?: string, include_dropped = false) =>
    get<Selection[]>('/course-selections/mine', { semester, include_dropped }),
  select: (teaching_class_id: number) =>
    post<Selection>('/course-selections', { teaching_class_id }),
  drop: (id: number) => del(`/course-selections/${id}`),

  periods: (semester?: string) => get<SelectionPeriod[]>('/selection-periods', { semester }),
  /** 当前选课/退课窗口状态（后端统一判断；FIX-003）。 */
  windowStatus: (semester: string) =>
    get<SelectionWindowStatus>('/course-selections/window', { semester }),
  createPeriod: (b: Record<string, unknown>) =>
    post<SelectionPeriod>('/selection-periods', b),
  updatePeriod: (id: number, b: Record<string, unknown>) =>
    put<SelectionPeriod>(`/selection-periods/${id}`, b),
}

// --- 课表 / 教学安排（TASK-013 平铺接口 /teaching-schedules，FIX-007 前端全量接入）---
export const scheduleApi = {
  /** 教务：教学安排列表（支持学期/教学班/教师/星期/教室过滤，过滤在数据库层完成）。 */
  list: (q?: {
    term_id?: number
    teaching_class_id?: number
    teacher_id?: number
    weekday?: number
    classroom?: string
  }) => get<Schedule[]>('/teaching-schedules', q),
  get: (id: number) => get<Schedule>(`/teaching-schedules/${id}`),
  /** 新增排课：教师/教室/教学班三类冲突由后端检测，冲突时返回 409。 */
  create: (b: Record<string, unknown>) => post<Schedule>('/teaching-schedules', b),
  /** 修改排课：改教室/时间后由后端重新检测冲突。 */
  update: (id: number, b: Record<string, unknown>) =>
    put<Schedule>(`/teaching-schedules/${id}`, b),
  remove: (id: number) => del(`/teaching-schedules/${id}`),

  /** 教师课表（身份取自 token，不接受 teacher_id）。 */
  mine: (semester?: string, week?: number) =>
    get<Schedule[]>('/teaching-schedules/mine', { semester, week }),
  /** 学生课表（仅本人已选教学班）。 */
  my: (semester?: string, week?: number) =>
    get<Schedule[]>('/teaching-schedules/my', { semester, week }),

  /** 查看指定学生课表（教务/教师用；学生只能查本人）。 */
  student: (studentId: number, semester: string, week?: number) =>
    get<ScheduleItem[]>(`/schedules/students/${studentId}`, { semester, week }),
}

// --- 管理员管理（V3.0：管理员账号与权限授予）---
export const adminApi = {
  /** 管理员列表：含独立管理员与「教师兼任」账号（判定依据是角色，不是 user_type）。 */
  list: () => get<AdminAccount[]>('/admins'),
  /** 创建独立管理员账号（复用既有 /users，user_type=ADMIN）。 */
  create: (b: Record<string, unknown>) => post<AdminAccount>('/users', b),
  /** 给既有账号授予管理员角色（典型：教师兼任），只加角色、不改 user_type。 */
  grant: (userId: number) => post<AdminAccount>(`/admins/${userId}/grant`),
  /** 撤销管理员角色：只删角色关联，不删账号、不动教学数据。 */
  revoke: (userId: number) => post<AdminAccount>(`/admins/${userId}/revoke`),
  resetPassword: (userId: number, newPassword: string) =>
    put<void>(`/users/${userId}/password`, { new_password: newPassword }),
  setStatus: (userId: number, status: 'ACTIVE' | 'DISABLED') =>
    put<AdminAccount>(`/users/${userId}/status`, { status }),
  /** 权限变更记录（管理员管理的审计展示）。 */
  auditLogs: (q?: PageQuery & { action?: string; resource_type?: string; resource_id?: number }) =>
    get<PageResult<AuditLog>>('/audit-logs', q),
}

// --- 成绩 ---
export const gradeApi = {
  mine: (semester?: string) => get<Grade[]>('/grades/mine', { semester }),
  mySummary: () => get<GradeSummary>('/grades/mine/summary'),
  byClass: (classId: number) => get<Grade[]>(`/grades/teaching-classes/${classId}`),
  initSheet: (classId: number) =>
    post<Grade[]>(`/grades/teaching-classes/${classId}/init`),
  save: (teaching_class_id: number, items: Record<string, unknown>[]) =>
    put<Grade[]>('/grades', { teaching_class_id, items }),
  submit: (classId: number) =>
    post<{ submitted: number; message: string }>(
      `/grades/teaching-classes/${classId}/submit`,
    ),
  pending: (semester?: string) => get<Grade[]>('/grades/pending', { semester }),
  approved: (semester?: string) => get<Grade[]>('/grades/approved', { semester }),
  history: (gradeId: number) => get<GradeChangeLog[]>(`/grades/${gradeId}/history`),
  correct: (gradeId: number, body: Record<string, unknown>) =>
    post<Grade>(`/grades/${gradeId}/correct`, body),
  unapprove: (gradeId: number, reason: string) =>
    post<Grade>(`/grades/${gradeId}/unapprove`, { reason }),
  approve: (grade_ids: number[]) =>
    post<{ approved: number; message: string }>('/grades/approve', { grade_ids }),
  reject: (grade_ids: number[], reason: string) =>
    post<{ rejected: number; message: string }>('/grades/reject', { grade_ids, reason }),
  statistics: (classId: number) =>
    get<GradeStatistics>(`/grades/teaching-classes/${classId}/statistics`),
  /** 我的成绩总览：已审核成绩 + 实时 GPA + 班级/专业排名（TASK-007）。 */
  my: () => get<StudentGradeOverview>('/grades/my'),
  /** 删除成绩草稿（仅 DRAFT；SUBMITTED/APPROVED 后端返回 409）。 */
  removeDraft: (gradeId: number) => del(`/grades/${gradeId}`),
}

// --- 学期（TASK-011 / FIX-006）---
export const termApi = {
  list: (q?: PageQuery & { academic_year?: string; status?: string }) =>
    get<PageResult<Term>>('/terms', q),
  /** 当前 ACTIVE 学期（F-05：不再依赖浏览器日期推断）。 */
  active: () => get<Term>('/terms/active'),
  get: (id: number) => get<Term>(`/terms/${id}`),
  create: (b: Record<string, unknown>) => post<Term>('/terms', b),
  update: (id: number, b: Record<string, unknown>) => put<Term>(`/terms/${id}`, b),
  remove: (id: number) => del(`/terms/${id}`),
  /** 激活学期：后端保证「最多一个 ACTIVE」，已结束学期拒绝（409）。 */
  activate: (id: number) => post<Term>(`/terms/${id}/activate`),
  /** 结束学期：仅进行中的学期可结束（409）。 */
  end: (id: number) => post<Term>(`/terms/${id}/end`),
}

// --- 批量导入（TASK-010 / FIX-005）---
export const importApi = {
  /** 下载导入模板；成绩模板按教学班动态生成，需传 teaching_class_id。 */
  template: (kind: ImportKind, teachingClassId?: number) =>
    download(
      `/imports/templates/${kind}`,
      teachingClassId ? { teaching_class_id: teachingClassId } : undefined,
      kind === 'grades' && teachingClassId
        ? `grade_import_template_${teachingClassId}.xlsx`
        : `${kind}_import_template.xlsx`,
    ),
  /** 上传 Excel 并返回逐行导入结果（部分成功策略：成功入库 + 失败明细）。 */
  upload: (kind: ImportKind, file: File) =>
    upload<ImportResult>(`/imports/${kind}`, file),
}

// --- 考试 ---
export const examApi = {
  list: (q?: PageQuery & { semester?: string; status?: string }) =>
    get<PageResult<Exam>>('/exams', q),
  mine: (semester?: string) => get<Exam[]>('/exams/mine', { semester }),
  create: (b: Record<string, unknown>) => post<Exam>('/exams', b),
  update: (id: number, b: Record<string, unknown>) => put<Exam>(`/exams/${id}`, b),
  remove: (id: number) => del(`/exams/${id}`),
  addRoom: (id: number, b: Record<string, unknown>) =>
    post<ExamRoom>(`/exams/${id}/rooms`, b),
  updateRoom: (id: number, roomId: number, b: Record<string, unknown>) =>
    put<ExamRoom>(`/exams/${id}/rooms/${roomId}`, b),
  removeRoom: (id: number, roomId: number) =>
    del(`/exams/${id}/rooms/${roomId}`),
  assign: (id: number) => post<{ assigned: number }>(`/exams/${id}/assign`),
  publish: (id: number) => post<Exam>(`/exams/${id}/publish`),
}

// --- 评价 ---
export const evaluationApi = {
  tasks: (semester?: string) => get<EvaluationTask[]>('/evaluations/tasks', { semester }),
  createTask: (b: Record<string, unknown>) =>
    post<EvaluationTask>('/evaluations/tasks', b),
  updateTask: (id: number, b: Record<string, unknown>) =>
    put<EvaluationTask>(`/evaluations/tasks/${id}`, b),
  pending: (task_id: number) =>
    get<PendingEvaluation[]>('/evaluations/pending', { task_id }),
  submit: (b: Record<string, unknown>) => post<{ message: string }>('/evaluations', b),
  statistics: (q?: { task_id?: number; teaching_class_id?: number }) =>
    get<EvaluationStats[]>('/evaluations/statistics', q),
}

// --- 公告 ---
export const announcementApi = {
  list: (q?: PageQuery) => get<PageResult<Announcement>>('/announcements', q),
  create: (b: Record<string, unknown>) => post<Announcement>('/announcements', b),
  update: (id: number, b: Record<string, unknown>) =>
    put<Announcement>(`/announcements/${id}`, b),
  remove: (id: number) => del(`/announcements/${id}`),
}

// --- 统计 ---
export const statsApi = {
  overview: () => get<Overview>('/statistics/overview'),
  gradeDistribution: (semester?: string) =>
    get<GradeStatistics>('/statistics/grade-distribution', { semester }),
  selectionRanking: (semester: string, limit = 10) =>
    get<{ course_name: string; selected: number }[]>('/statistics/selection-ranking', {
      semester,
      limit,
    }),
}
// --- Excel 导出（F-17）---
export const exportApi = {
  students: () => download('/exports/students', undefined, 'students.xlsx'),
  courses: () => download('/exports/courses', undefined, 'courses.xlsx'),
  grades: (semester?: string) =>
    download('/exports/grades', semester ? { semester } : undefined, 'grades.xlsx'),
  selections: (semester?: string) =>
    download('/exports/selections', semester ? { semester } : undefined, 'selections.xlsx'),
}
// --- 教学资料（F-21）---
export const materialApi = {
  list: (teachingClassId: number) =>
    get<Material[]>('/materials', { teaching_class_id: teachingClassId }),
  my: () => get<Material[]>('/materials/my'),
  upload: (teachingClassId: number, title: string, file: File) => {
    const form = new FormData()
    form.append('teaching_class_id', String(teachingClassId))
    form.append('title', title)
    form.append('file', file)
    return uploadForm<Material>('/materials', form)
  },
  remove: (id: number) => del(`/materials/${id}`),
  download: (id: number, fileName: string) =>
    download(`/materials/${id}/download`, undefined, fileName),
}
// --- 调停课（F-22）---
export const adjustmentApi = {
  mine: () => get<Adjustment[]>('/schedule-adjustments/mine'),
  list: (status?: string) =>
    get<Adjustment[]>('/schedule-adjustments', status ? { status } : undefined),
  create: (b: Record<string, unknown>) =>
    post<Adjustment>('/schedule-adjustments', b),
  approve: (id: number) =>
    post<Adjustment>(`/schedule-adjustments/${id}/approve`),
  reject: (id: number, reason: string) =>
    post<Adjustment>(`/schedule-adjustments/${id}/reject`, { reason }),
}
