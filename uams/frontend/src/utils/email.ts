/** 邮箱输入前端辅助（FIX-001）。
 *
 * 前端只做“空值转 null + 常见格式提示”，最终校验仍以后端为准。
 */

const EMAIL_RE =
  /^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}$/

export function normalizeEmailInput(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const email = value.trim()
  return email || null
}

export function isValidEmail(email: string): boolean {
  return email.length <= 100 && EMAIL_RE.test(email)
}
