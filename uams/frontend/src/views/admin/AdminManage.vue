<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { adminApi, teacherApi } from '@/api'
import type { AdminAccount, AuditLog, Teacher } from '@/types'

/**
 * 管理员管理（V3.0）。
 *
 * 判定依据是**角色**（ACADEMIC_ADMIN），不是 user_type：
 * 教师被授予管理员后仍是 TEACHER，教学班/课表/成绩等归属完全不变；
 * 撤销只删角色关联，不删除账号、不动教学数据。
 */
const rows = ref<AdminAccount[]>([])
const teachers = ref<Teacher[]>([])
const loading = ref(false)

const ADMIN_ROLE = 'ACADEMIC_ADMIN'
const ACTION_LABEL: Record<string, string> = {
  ADMIN_GRANT: '授予管理员',
  ADMIN_REVOKE: '撤销管理员',
  ADMIN_ENABLE: '启用账号',
  ADMIN_DISABLE: '停用账号',
}

function isAdminAccount(u: AdminAccount) {
  return u.roles.includes(ADMIN_ROLE)
}
/** 独立管理员（账号本身即 ADMIN）还是教师兼任（user_type 仍为 TEACHER） */
function accountKind(u: AdminAccount) {
  return u.user_type === 'ADMIN' ? '独立管理员' : '教师兼任'
}

async function load() {
  loading.value = true
  try {
    rows.value = await adminApi.list()
  } finally {
    loading.value = false
  }
}

async function loadTeachers() {
  if (teachers.value.length) return
  const res = await teacherApi.list({ page_size: 200 })
  teachers.value = res.items
}

// --- 新建独立管理员 ---
const createVisible = ref(false)
const createSaving = ref(false)
const createForm = ref({ username: '', real_name: '', password: '' })

function openCreate() {
  createForm.value = { username: '', real_name: '', password: '' }
  createVisible.value = true
}

async function submitCreate() {
  const f = createForm.value
  if (!f.username || !f.real_name) {
    ElMessage.warning('请填写登录名与姓名')
    return
  }
  if (f.password.length < 6) {
    ElMessage.warning('密码至少 6 位')
    return
  }
  createSaving.value = true
  try {
    await adminApi.create({
      username: f.username.trim(),
      real_name: f.real_name.trim(),
      user_type: 'ADMIN',
      password: f.password,
    })
    ElMessage.success('管理员账号已创建')
    createVisible.value = false
    await load()
  } catch {
    // 登录名重复等错误由拦截器提示，保留弹窗便于修改
  } finally {
    createSaving.value = false
  }
}

// --- 授权既有教师兼任管理员 ---
const grantVisible = ref(false)
const grantSaving = ref(false)
const grantTeacherId = ref<number | undefined>(undefined)

/** 还没有管理员角色的教师（已被授权的不再出现在候选里） */
const grantCandidates = computed(() =>
  teachers.value.filter(
    (t) => !rows.value.some((a) => a.username === t.teacher_no && isAdminAccount(a)),
  ),
)

async function openGrant() {
  await loadTeachers()
  grantTeacherId.value = undefined
  grantVisible.value = true
}

async function submitGrant() {
  if (!grantTeacherId.value) {
    ElMessage.warning('请选择要授予管理员权限的教师')
    return
  }
  const t = teachers.value.find((x) => x.id === grantTeacherId.value)
  grantSaving.value = true
  try {
    await adminApi.grant(t?.user_id ?? 0)
    ElMessage.success(`${t?.real_name ?? '该教师'} 已获得管理员权限（教师身份与教学数据不变）`)
    grantVisible.value = false
    await load()
  } catch {
    // 已是管理员等冲突由拦截器提示
  } finally {
    grantSaving.value = false
  }
}

// --- 撤销 / 启停 / 重置密码 ---
async function revoke(row: AdminAccount) {
  try {
    await ElMessageBox.confirm(
      `确定撤销「${row.real_name}（${row.username}）」的管理员权限吗？\n` +
        '撤销后该账号立即失去管理员权限，但账号本身与全部教学数据（教学班、课表、成绩）均保留。',
      '撤销管理员权限',
      { type: 'warning', confirmButtonText: '撤销', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await adminApi.revoke(row.id)
    ElMessage.success('已撤销管理员权限')
    await load()
  } catch {
    // 唯一管理员保护等 409 由拦截器提示
  }
}

async function toggleStatus(row: AdminAccount) {
  const disable = row.status === 'ACTIVE'
  try {
    await ElMessageBox.confirm(
      disable
        ? `确定停用「${row.real_name}（${row.username}）」的账号吗？停用后该账号无法登录。`
        : `确定启用「${row.real_name}（${row.username}）」的账号吗？`,
      disable ? '停用账号' : '启用账号',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await adminApi.setStatus(row.id, disable ? 'DISABLED' : 'ACTIVE')
    ElMessage.success(disable ? '账号已停用' : '账号已启用')
    await load()
  } catch {
    // 唯一管理员保护等 409 由拦截器提示
  }
}

async function resetPassword(row: AdminAccount) {
  let value: string
  try {
    const r = await ElMessageBox.prompt(
      `为「${row.real_name}（${row.username}）」设置新密码（至少 6 位）。\n` +
        '系统不提供默认或通用密码，请设置后由本人自行修改。',
      '重置密码',
      {
        inputType: 'password',
        inputPattern: /^.{6,128}$/,
        inputErrorMessage: '密码长度需为 6~128 位',
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      },
    )
    value = r.value
  } catch {
    return
  }
  try {
    await adminApi.resetPassword(row.id, value)
    ElMessage.success('密码已重置')
  } catch {
    // 拦截器已提示
  }
}

// --- 权限变更记录 ---
const logVisible = ref(false)
const logLoading = ref(false)
const logs = ref<AuditLog[]>([])
const logTarget = ref<AdminAccount | null>(null)

async function openLogs(row: AdminAccount) {
  logTarget.value = row
  logVisible.value = true
  logLoading.value = true
  try {
    const res = await adminApi.auditLogs({
      resource_type: 'user',
      resource_id: row.id,
      page_size: 50,
    })
    logs.value = res.items
  } finally {
    logLoading.value = false
  }
}

const STAT: Record<string, string> = { ACTIVE: '正常', DISABLED: '已停用', LOCKED: '已锁定' }
const STAT_TYPE: Record<string, string> = {
  ACTIVE: 'success',
  DISABLED: 'danger',
  LOCKED: 'warning',
}

onMounted(load)
</script>

<template>
  <div>
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="hint"
      title="管理员身份以角色为准：教师被授予管理员后仍保留教师身份与全部教学数据；撤销后立即失去管理员权限，但账号与教学数据不受影响。"
    />

    <el-card shadow="never" class="page-card">
      <div class="toolbar">
        <span class="muted">共 {{ rows.length }} 个管理员账号</span>
        <div class="spacer" />
        <el-button @click="openGrant">从教师中授权</el-button>
        <el-button type="primary" @click="openCreate">新建管理员账号</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" stripe>
        <el-table-column label="姓名 / 登录名" min-width="180">
          <template #default="{ row }">
            <div class="who">
              <span class="who__name">{{ row.real_name }}</span>
              <span class="who__sub">{{ row.username }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="账号类型" width="120" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.user_type === 'ADMIN' ? 'primary' : 'info'" effect="plain">
              {{ accountKind(row) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="角色" min-width="170">
          <template #default="{ row }">
            <el-tag
              v-for="r in row.roles"
              :key="r"
              size="small"
              :type="r === ADMIN_ROLE ? 'success' : 'info'"
              effect="plain"
              class="role-tag"
            >
              {{ r === ADMIN_ROLE ? '教务管理员' : r === 'TEACHER' ? '教师' : r }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="STAT_TYPE[row.status] as any" size="small">
              {{ STAT[row.status] ?? row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最后登录" width="160">
          <template #default="{ row }">
            {{ row.last_login_at?.slice(0, 16).replace('T', ' ') ?? '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="290" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openLogs(row)">
              变更记录
            </el-button>
            <el-button size="small" link type="warning" @click="resetPassword(row)">
              重置密码
            </el-button>
            <el-button size="small" link @click="toggleStatus(row)">
              {{ row.status === 'ACTIVE' ? '停用' : '启用' }}
            </el-button>
            <el-button
              size="small"
              link
              type="danger"
              :disabled="!isAdminAccount(row)"
              @click="revoke(row)"
            >
              撤销权限
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无管理员账号" :image-size="70" />
        </template>
      </el-table>
    </el-card>

    <!-- 新建独立管理员 -->
    <el-dialog v-model="createVisible" title="新建管理员账号" width="460px">
      <el-form label-width="90px">
        <el-form-item label="登录名" required>
          <el-input v-model="createForm.username" maxlength="50" placeholder="用于登录，创建后不可修改" />
        </el-form-item>
        <el-form-item label="姓名" required>
          <el-input v-model="createForm.real_name" maxlength="50" />
        </el-form-item>
        <el-form-item label="初始密码" required>
          <el-input v-model="createForm.password" type="password" show-password
            placeholder="至少 6 位；无默认/通用密码" />
        </el-form-item>
      </el-form>
      <el-text size="small" type="info">
        该账号为独立管理员（不关联教师档案），拥有教务端全部权限。
      </el-text>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="createSaving" @click="submitCreate">确定</el-button>
      </template>
    </el-dialog>

    <!-- 从教师中授权 -->
    <el-dialog v-model="grantVisible" title="从教师中授权管理员" width="480px">
      <el-form label-width="90px">
        <el-form-item label="选择教师" required>
          <el-select v-model="grantTeacherId" filterable style="width: 100%"
            placeholder="按姓名或工号选择">
            <el-option v-for="t in grantCandidates" :key="t.id"
              :label="`${t.real_name}（${t.teacher_no}）`" :value="t.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <el-text size="small" type="info">
        授权后该教师同时拥有教师与管理员身份：<strong>教学班、课表、成绩等归属完全不变</strong>，
        仅额外获得教务端权限；可随时撤销。
      </el-text>
      <template #footer>
        <el-button @click="grantVisible = false">取消</el-button>
        <el-button type="primary" :loading="grantSaving" @click="submitGrant">确定授权</el-button>
      </template>
    </el-dialog>

    <!-- 权限变更记录 -->
    <el-dialog v-model="logVisible" :title="`权限变更记录 — ${logTarget?.real_name ?? ''}`" width="680px">
      <el-table v-loading="logLoading" :data="logs" size="small" stripe>
        <el-table-column label="时间" width="160">
          <template #default="{ row }">{{ row.created_at?.slice(0, 16).replace('T', ' ') }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ ACTION_LABEL[row.action] ?? row.action }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="操作人" width="110" />
        <el-table-column prop="detail" label="说明" min-width="220" />
        <template #empty>
          <el-empty description="该账号暂无权限变更记录" :image-size="60" />
        </template>
      </el-table>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.hint {
  margin-bottom: var(--uams-gap);
  border-radius: var(--uams-radius);
}

.who {
  display: flex;
  flex-direction: column;
  line-height: 1.4;

  &__name {
    font-weight: 500;
    color: var(--uams-text);
  }

  &__sub {
    font-size: 12px;
    color: var(--uams-text-3);
  }
}

.role-tag + .role-tag {
  margin-left: 6px;
}

@media (max-width: 768px) {
  .toolbar {
    flex-wrap: wrap;
  }
}
</style>
