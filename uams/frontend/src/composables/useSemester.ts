/** 当前学期推断与选项。
 *
 * 学期格式 YYYY-YYYY-N（DATABASE.md §1.7），全系统一致。
 */
import { ref } from 'vue'

export function currentSemester(): string {
  const now = new Date()
  const y = now.getFullYear()
  const m = now.getMonth() + 1
  // 9 月 ~ 次年 1 月为第一学期，2 月 ~ 8 月为第二学期
  if (m >= 9) return `${y}-${y + 1}-1`
  if (m <= 1) return `${y - 1}-${y}-1`
  return `${y - 1}-${y}-2`
}

export function semesterOptions(span = 3): string[] {
  const now = new Date()
  const y = now.getFullYear()
  const out: string[] = []
  for (let i = 0; i < span; i++) {
    const s = y - i
    out.push(`${s}-${s + 1}-2`, `${s}-${s + 1}-1`)
  }
  return out
}

export function useSemester() {
  const semester = ref(currentSemester())
  return { semester, options: semesterOptions() }
}
