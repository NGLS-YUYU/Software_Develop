/**
 * 轻量请求竞态守卫：只允许最近一次查询写回响应式状态。
 *
 * 用法：
 *   const guard = createLatestGuard()
 *   async function load() {
 *     const seq = guard.next()
 *     const res = await api.list()
 *     if (!guard.isCurrent(seq)) return
 *     rows.value = res.items
 *   }
 */
export function createLatestGuard() {
  let current = 0
  return {
    next(): number {
      current += 1
      return current
    },
    isCurrent(seq: number): boolean {
      return seq === current
    },
  }
}
