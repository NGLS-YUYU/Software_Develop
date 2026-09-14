/** 按业务模块组织的 API 调用。 */

import { del, get, post, put } from './request'
import type {
  Announcement,
  ClassInfo,
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
  GradeStatistics,
  GradeSummary,
  LoginResponse,
  Major,
  Overview,
  PageQuery,
  PageResult,
  PendingEvaluation,
  Prerequisite,
  Schedule,
  ScheduleItem,
  Selection,
  SelectionPeriod,
  Student,
  Teacher,
  TeachingClass,
  TeachingTask,
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

  students: (id: number) =>
    get<{ student_id: number; student_no: string; real_name: string; class_name?: string }[]>(
      `/teaching-classes/${id}/students`,
    ),
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
  createPeriod: (b: Record<string, unknown>) =>
    post<SelectionPeriod>('/selection-periods', b),
  updatePeriod: (id: number, b: Record<string, unknown>) =>
    put<SelectionPeriod>(`/selection-periods/${id}`, b),
}

// --- 课表 ---
export const scheduleApi = {
  mine: (semester: string, week?: number) =>
    get<ScheduleItem[]>('/schedules/mine', { semester, week }),
  student: (studentId: number, semester: string, week?: number) =>
    get<ScheduleItem[]>(`/schedules/students/${studentId}`, { semester, week }),
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
  approve: (grade_ids: number[]) =>
    post<{ approved: number; message: string }>('/grades/approve', { grade_ids }),
  reject: (grade_ids: number[], reason: string) =>
    post<{ rejected: number; message: string }>('/grades/reject', { grade_ids, reason }),
  statistics: (classId: number) =>
    get<GradeStatistics>(`/grades/teaching-classes/${classId}/statistics`),
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
  assign: (id: number) => post<{ assigned: number }>(`/exams/${id}/assign`),
  publish: (id: number) => post<Exam>(`/exams/${id}/publish`),
}

// --- 评价 ---
export const evaluationApi = {
  tasks: (semester?: string) => get<EvaluationTask[]>('/evaluations/tasks', { semester }),
  createTask: (b: Record<string, unknown>) =>
    post<EvaluationTask>('/evaluations/tasks', b),
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
