/** 分页表格通用逻辑：加载、搜索、分页、增删改对话框。
 *
 * 教务端 11 个页面结构高度相似，抽出来避免重复。
 */
import { reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import type { BatchDeleteResult, PageQuery, PageResult } from '@/types'

interface CrudApi<T> {
  list: (q: PageQuery & Record<string, unknown>) => Promise<PageResult<T>>
  create?: (b: Record<string, unknown>) => Promise<T>
  update?: (id: number, b: Record<string, unknown>) => Promise<T>
  remove?: (id: number) => Promise<unknown>
  batchRemove?: (ids: number[]) => Promise<BatchDeleteResult>
}

export function useCrudTable<T extends { id: number }>(
  api: CrudApi<T>,
  options: {
    entityName?: string
    defaultFilters?: Record<string, unknown>
    emptyForm: () => Record<string, unknown>
    /** 写入/删除成功后，刷新与当前资源关联的下拉、统计或跨 Tab 数据。 */
    afterMutation?: () => void | Promise<void>
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
  const selectedRows = ref<T[]>([])
  const batchDeleting = ref(false)
  /** 查询序号：较早发出的请求即使晚返回，也不能覆盖较新的结果。 */
  let loadSeq = 0

  const name = options.entityName ?? '记录'

  async function load() {
    const seq = ++loadSeq
    loading.value = true
    try {
      const res = await api.list({ ...query })
      if (seq !== loadSeq) return
      rows.value = res.items
      total.value = res.total
      // 删除当前页最后一条（或筛选后当前页已空）时回退一页，避免停在空页。
      const currentPage = query.page ?? 1
      if (!res.items.length && currentPage > 1) {
        query.page = currentPage - 1
        await load()
      }
    } finally {
      if (seq === loadSeq) loading.value = false
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
    if (saving.value) return false
    const body = payload ?? { ...form.value }
    const isCreate = dialogMode.value === 'create'
    saving.value = true
    try {
      let created: T | undefined
      if (isCreate) {
        if (!api.create) throw new Error(`${name}不支持新增`)
        created = await api.create(body)
        // 先回到第一页；若新记录因分页未出现，再定位到包含它的末页。
        query.page = 1
        ElMessage.success(`${name}已创建`)
      } else if (editingId.value != null) {
        if (!api.update) throw new Error(`${name}不支持修改`)
        await api.update(editingId.value, body)
        ElMessage.success(`${name}已更新`)
      }
      dialogVisible.value = false
      await load()
      if (isCreate && created?.id != null && !rows.value.some((r) => r.id === created!.id)) {
        const pageSize = Number(query.page_size ?? 20)
        const lastPage = Math.max(1, Math.ceil(total.value / pageSize))
        if (lastPage !== (query.page ?? 1)) {
          query.page = lastPage
          await load()
        }
      }
      try {
        await options.afterMutation?.()
      } catch {
        // 关联数据刷新失败由拦截器提示；本次写入本身已成功
      }
      return true
    } catch {
      // 错误信息由 axios 拦截器统一提示；保留弹窗数据便于重试
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
      if (!api.remove) throw new Error(`${name}不支持删除`)
      await api.remove(row.id)
      ElMessage.success(`${name}已删除`)
      await load()
      try {
        await options.afterMutation?.()
      } catch {
        // 关联数据刷新失败由拦截器提示
      }
    } catch {
      // 被引用时后端返回 409，拦截器已提示
    }
  }

  function onSelectionChange(rowsSelected: T[]) {
    selectedRows.value = rowsSelected
  }

  async function batchRemoveSelected() {
    if (batchDeleting.value) return
    if (!selectedRows.value.length) {
      ElMessage.warning(`请先选择要删除的${name}`)
      return
    }
    if (!api.batchRemove) {
      ElMessage.error(`${name}不支持批量删除`)
      return
    }
    const ids = selectedRows.value.map((r) => r.id)
    try {
      await ElMessageBox.confirm(
        `确认删除选中的 ${ids.length} 条${name}？此操作不可撤销。`,
        '批量删除',
        { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
    batchDeleting.value = true
    try {
      const res = await api.batchRemove(ids)
      if (res.failed.length) {
        ElMessage.warning(
          `已删除 ${res.deleted.length} 条，失败 ${res.failed.length} 条：` +
            res.failed.slice(0, 3).map((f) => `#${f.id} ${f.reason}`).join('；'),
        )
      } else {
        ElMessage.success(`已删除 ${res.deleted.length} 条${name}`)
      }
      selectedRows.value = []
      await load()
      try {
        await options.afterMutation?.()
      } catch {
        // 关联刷新失败由拦截器提示
      }
    } finally {
      batchDeleting.value = false
    }
  }

  return {
    rows,
    total,
    loading,
    query,
    selectedRows,
    batchDeleting,
    onSelectionChange,
    batchRemoveSelected,
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
