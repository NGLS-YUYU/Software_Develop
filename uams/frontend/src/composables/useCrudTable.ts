/** 分页表格通用逻辑：加载、搜索、分页、增删改对话框。
 *
 * 教务端 11 个页面结构高度相似，抽出来避免重复。
 */
import { reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import type { PageQuery, PageResult } from '@/types'

interface CrudApi<T> {
  list: (q: PageQuery & Record<string, unknown>) => Promise<PageResult<T>>
  create?: (b: Record<string, unknown>) => Promise<T>
  update?: (id: number, b: Record<string, unknown>) => Promise<T>
  remove?: (id: number) => Promise<unknown>
}

export function useCrudTable<T extends { id: number }>(
  api: CrudApi<T>,
  options: {
    entityName?: string
    defaultFilters?: Record<string, unknown>
    emptyForm: () => Record<string, unknown>
  },
) {
  const rows = ref<T[]>([])
  const total = ref(0)
  const loading = ref(false)
  const query = reactive<PageQuery & Record<string, unknown>>({
    page: 1,
    page_size: 20,
    keyword: '',
    ...(options.defaultFilters ?? {}),
  })

  const dialogVisible = ref(false)
  const dialogMode = ref<'create' | 'edit'>('create')
  const form = ref<Record<string, unknown>>(options.emptyForm())
  const editingId = ref<number | null>(null)
  const saving = ref(false)

  const name = options.entityName ?? '记录'

  async function load() {
    loading.value = true
    try {
      const res = await api.list({ ...query })
      rows.value = res.items
      total.value = res.total
    } finally {
      loading.value = false
    }
  }

  function search() {
    query.page = 1
    return load()
  }

  function openCreate() {
    dialogMode.value = 'create'
    form.value = options.emptyForm()
    editingId.value = null
    dialogVisible.value = true
  }

  function openEdit(row: T) {
    dialogMode.value = 'edit'
    form.value = { ...(row as unknown as Record<string, unknown>) }
    editingId.value = row.id
    dialogVisible.value = true
  }

  async function save(payload?: Record<string, unknown>) {
    const body = payload ?? { ...form.value }
    saving.value = true
    try {
      if (dialogMode.value === 'create') {
        await api.create?.(body)
        ElMessage.success(`${name}已创建`)
      } else if (editingId.value != null) {
        await api.update?.(editingId.value, body)
        ElMessage.success(`${name}已更新`)
      }
      dialogVisible.value = false
      await load()
      return true
    } catch {
      // 错误信息由 axios 拦截器统一提示
      return false
    } finally {
      saving.value = false
    }
  }

  async function remove(row: T, label?: string) {
    try {
      await ElMessageBox.confirm(
        `确认删除${name}「${label ?? row.id}」？该操作不可撤销。`,
        '确认删除',
        { type: 'warning' },
      )
    } catch {
      return
    }
    try {
      await api.remove?.(row.id)
      ElMessage.success(`${name}已删除`)
      await load()
    } catch {
      // 被引用时后端返回 409，拦截器已提示
    }
  }

  return {
    rows,
    total,
    loading,
    query,
    dialogVisible,
    dialogMode,
    form,
    editingId,
    saving,
    load,
    search,
    openCreate,
    openEdit,
    save,
    remove,
  }
}
