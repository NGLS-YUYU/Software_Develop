/** 与后端 Schema 对应的类型定义。 */

export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface PageQuery {
  page?: number
  page_size?: number
  keyword?: string
  order_by?: string
  order_desc?: boolean
}

export interface ApiError {
  code: string
  message: string
  errors?: { field: string; msg: string }[]
}

// --- 认证 ---
export interface UserInfo {
  id: number
  username: string
  real_name: string
  user_type: 'STUDENT' | 'TEACHER' | 'ADMIN'
  email?: string | null
  phone?: string | null
  status: string
  last_login_at?: string | null
}

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: UserInfo
  roles: string[]
  permissions: string[]
  home_route: string
}

// --- 基础数据 ---
export interface College {
  id: number
  code: string
  name: string
  description?: string | null
  status: string
}

export interface Major {
  id: number
  code: string
  name: string
  college_id: number
  college_name?: string | null
  degree_type: string
  duration_years: number
  status: string
}

export interface ClassInfo {
  id: number
  code: string
  name: string
  major_id: number
  major_name?: string | null
  grade_year: number
  counselor_id?: number | null
  student_count: number
  status: string
}

export interface Classroom {
  id: number
  code: string
  building: string
  capacity: number
  room_type: string
  status: string
}

// --- 人员 ---
export interface Student {
  id: number
  student_no: string
  real_name: string
  class_id: number
  class_name?: string | null
  major_id: number
  major_name?: string | null
  college_id: number
  college_name?: string | null
  gender: string
  birth_date?: string | null
  enrollment_year: number
  academic_status: string
  total_credits: number
  gpa?: number | null
  email?: string | null
  phone?: string | null
}

export interface Teacher {
  id: number
  teacher_no: string
  real_name: string
  college_id: number
  college_name?: string | null
  title?: string | null
  gender: string
  hire_date?: string | null
  status: string
  email?: string | null
  phone?: string | null
}

// --- 课程 ---
export interface Course {
  id: number
  code: string
  name: string
  college_id: number
  college_name?: string | null
  course_type: string
  credits: number
  total_hours: number
  theory_hours: number
  practice_hours: number
  assessment_type?: string | null
  exam_type: string
  description?: string | null
  status: string
}

export interface Prerequisite {
  id: number
  course_id: number
  prerequisite_course_id: number
  min_score: number
  prerequisite_code?: string | null
  prerequisite_name?: string | null
}

export interface CurriculumPlan {
  id: number
  code: string
  name: string
  major_id: number
  major_name?: string | null
  grade_year: number
  total_credits_required: number
  required_credits: number
  elective_credits: number
  status: string
}

export interface CurriculumCourse {
  id: number
  plan_id: number
  course_id: number
  suggested_semester: number
  is_required: boolean
  course_code?: string | null
  course_name?: string | null
  credits?: number | null
}

// --- 开课排课 ---
export interface TeachingTask {
  id: number
  semester: string
  course_id: number
  course_code?: string | null
  course_name?: string | null
  college_id: number
  college_name?: string | null
  planned_classes: number
  status: string
  class_count: number
}

/** 教学安排（后端 `ScheduleOut`，TASK-013 平铺接口 /teaching-schedules）。 */
export interface Schedule {
  id: number
  teaching_class_id: number
  teaching_class_code?: string | null
  teaching_class_name?: string | null
  course_id?: number | null
  course_code?: string | null
  course_name?: string | null
  teacher_id?: number | null
  teacher_name?: string | null
  term_id?: number | null
  term_name?: string | null
  classroom_id: number
  classroom_code?: string | null
  building?: string | null
  day_of_week: number
  start_period: number
  end_period: number
  start_week: number
  end_week: number
  week_type: string
  semester: string
}

export interface TeachingClass {
  id: number
  code: string
  task_id: number
  course_id: number
  course_code?: string | null
  course_name?: string | null
  credits?: number | null
  total_hours?: number | null
  theory_hours?: number | null
  practice_hours?: number | null
  assessment_type?: string | null
  has_midterm?: boolean | null
  has_practice?: boolean | null
  semester: string
  teacher_id?: number | null
  teacher_name?: string | null
  capacity: number
  selected_count: number
  remaining: number
  selection_status: string
  status: string
  schedules: Schedule[]
}

// --- 选课 ---
export interface Selection {
  id: number
  student_id: number
  teaching_class_id: number
  teaching_class_code?: string | null
  course_id: number
  course_code?: string | null
  course_name?: string | null
  credits?: number | null
  teacher_name?: string | null
  semester: string
  status: string
  selected_at?: string | null
}

export interface SelectionPeriod {
  id: number
  semester: string
  name: string
  start_time: string
  end_time: string
  target_grade_year?: number | null
  status: string
}

// --- 课表 ---
export interface ScheduleItem {
  schedule_id: number
  teaching_class_id: number
  teaching_class_code: string
  course_code?: string | null
  course_name?: string | null
  teacher_name?: string | null
  classroom_code?: string | null
  building?: string | null
  day_of_week: number
  day_name: string
  start_period: number
  end_period: number
  start_week: number
  end_week: number
  week_type: string
  semester: string
}

// --- 成绩 ---
export interface Grade {
  id: number
  student_id: number
  student_no?: string | null
  student_name?: string | null
  teaching_class_id: number
  course_id: number
  course_code?: string | null
  course_name?: string | null
  assessment_type?: string | null
  has_midterm?: boolean | null
  has_practice?: boolean | null
  course_total_hours?: number | null
  course_theory_hours?: number | null
  course_practice_hours?: number | null
  semester: string
  regular_score?: number | null
  mid_score?: number | null
  mid_theory_score?: number | null
  mid_practice_score?: number | null
  final_score?: number | null
  final_theory_score?: number | null
  final_practice_score?: number | null
  theory_makeup_score?: number | null
  practice_makeup_score?: number | null
  theory_total_score?: number | null
  practice_total_score?: number | null
  total_score?: number | null
  grade_point?: number | null
  credits: number
  is_passed?: boolean | null
  status: 'DRAFT' | 'SUBMITTED' | 'APPROVED' | 'REJECTED'
  reject_reason?: string | null
  submitted_at?: string | null
  approved_at?: string | null
}

export interface GradeSummary {
  total_courses: number
  passed_courses: number
  failed_courses: number
  total_credits: number
  gpa?: number | null
}

export interface GradeStatistics {
  count: number
  average?: number
  max?: number
  min?: number
  pass_rate?: number
  distribution?: Record<string, number>
}

// --- 考试 ---
export interface ExamRoom {
  id: number
  exam_id: number
  classroom_id: number
  classroom_code?: string | null
  building?: string | null
  capacity: number
  assigned_count: number
}

export interface Exam {
  id: number
  teaching_class_id: number
  teaching_class_code?: string | null
  course_id: number
  course_code?: string | null
  course_name?: string | null
  semester: string
  exam_type: string
  exam_date: string
  start_time: string
  end_time: string
  duration_minutes: number
  status: string
  rooms: ExamRoom[]
  classroom_code?: string | null
  seat_no?: number | null
}

// --- 评价 ---
export interface EvaluationTask {
  id: number
  name: string
  semester: string
  start_time: string
  end_time: string
  status: string
}

export interface PendingEvaluation {
  teaching_class_id: number
  teaching_class_code: string
  course_name?: string | null
  teacher_name?: string | null
  evaluated: boolean
}

export interface EvaluationStats {
  teaching_class_id: number
  teaching_class_code?: string | null
  course_name?: string | null
  teacher_name?: string | null
  count: number
  average?: number | null
  comments: string[]
}

// --- 公告 ---
export interface Announcement {
  id: number
  title: string
  content: string
  target_type: string
  is_top: boolean
  status: string
  publisher_id: number
  publisher_name?: string | null
  published_at?: string | null
  created_at?: string | null
}

// --- 统计 ---
export interface Overview {
  colleges: number
  majors: number
  classes: number
  students: number
  teachers: number
  courses: number
  teaching_classes: number
  selections: number
  pending_grades: number
}

// --- 学生成绩总览（后端 /grades/my，含实时 GPA 与排名）---
export interface StudentGradeOverview {
  items: Grade[]
  gpa: number | null
  class_rank: number | null
  major_rank: number | null
}

// --- 学期（TASK-011 / FIX-006）---
export type TermStatusValue = 'PLANNED' | 'ACTIVE' | 'ENDED'

/** 对应后端 `schemas/term.py::TermOut`。 */
export interface Term {
  id: number
  name: string
  /** 学年，如 2026-2027 */
  academic_year: string
  /** 学期序号：1 或 2 */
  semester: number
  start_date: string
  end_date: string
  status: TermStatusValue
  teaching_class_count: number
}

// --- 批量导入（TASK-010 / FIX-005）---
export type ImportKind = 'students' | 'teachers' | 'courses' | 'grades'

/** 单行错误：行号 + 出错列（后端字段名）+ 可读原因。 */
export interface ImportRowError {
  row: number
  field: string
  message: string
}

export interface ImportResult {
  total: number
  success: number
  failed: number
  errors: ImportRowError[]
}
