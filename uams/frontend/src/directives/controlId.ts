import type { Directive } from 'vue'

/**
 * 为 Element Plus 复合控件（radio-group / slider 等）内部的真实 input 分配 id。
 *
 * 这些组件的根节点是 div，Element Plus 默认会把 el-form-item 的 label for
 * 指向根 div，浏览器会报 “Incorrect use of <label for=FORM_ELEMENT>”。
 * 这里把 label 指向组内第一个可聚焦表单控件，既消除无效关联，也保证点击标签可聚焦。
 *
 * 用法：
 *   <el-form-item label="性别" for="student-gender">
 *     <el-radio-group v-control-id="'student-gender'" ...>
 */
export const controlId: Directive<HTMLElement, string> = {
  mounted(el, binding) {
    apply(el, binding.value)
  },
  updated(el, binding) {
    apply(el, binding.value)
  },
}

function apply(el: HTMLElement, id: string | undefined) {
  if (!id) return
  const target = el.querySelector<HTMLElement>('input, textarea, select')
  if (target) target.id = id
}
