<template>
  <div class="page">
    <div class="tm-card">
      <div class="tm-card-header">
        <span class="title">用户管理</span>
        <div class="header-actions">
          <button v-if="auth.isSuperAdmin" class="tm-btn-ghost" @click="openGateDialog">访问密钥</button>
          <button class="tm-btn-primary" @click="openCreate">创建用户</button>
        </div>
      </div>
      <div class="tm-card-body" style="padding-top:0">
        <p v-if="auth.isTierAdmin" class="tier-hint">您可新增「管理员」或「普通用户」账号，并修改自己创建账号的角色与密码。</p>
        <el-table :data="users" v-loading="loading" stripe>
          <el-table-column prop="username" label="用户名" />
          <el-table-column prop="email" label="邮箱">
            <template #default="{ row }">{{ row.email || '—' }}</template>
          </el-table-column>
          <el-table-column prop="role" label="角色" width="120">
            <template #default="{ row }">
              <span class="tm-tag" :class="roleTagClass(row.role)">{{ roleLabel(row.role) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="is_active" label="状态" width="90">
            <template #default="{ row }">
              <span class="tm-tag" :class="row.is_active ? 'blue' : 'daily-hot'">
                {{ row.is_active ? '正常' : '禁用' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column v-if="auth.isUserManager" label="操作" width="180">
            <template #default="{ row }">
              <template v-if="canManageUser(row)">
                <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
                <el-button v-if="auth.isSuperAdmin" link type="danger" @click="removeUser(row)">删除</el-button>
              </template>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <el-dialog
      v-model="showForm"
      :title="editing ? '编辑用户' : '创建用户'"
      width="440px"
      append-to-body
      @opened="onFormOpened"
      @closed="formReadonly = true"
    >
      <el-form autocomplete="off" label-width="100px">
        <el-form-item v-if="!editing" label="用户名">
          <el-input
            v-model="form.username"
            autocomplete="off"
            name="admin-create-username"
            :readonly="formReadonly"
            @focus="formReadonly = false"
          />
        </el-form-item>
        <el-form-item v-if="showEmailField" label="邮箱">
          <el-input
            v-model="form.email"
            autocomplete="off"
            name="admin-create-email"
            placeholder="选填"
            :readonly="formReadonly && !editing"
            @focus="formReadonly = false"
          />
        </el-form-item>
        <el-form-item :label="editing ? '新密码' : '密码'">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            autocomplete="new-password"
            name="admin-create-password"
            :placeholder="editing ? '留空则不修改' : ''"
            :readonly="formReadonly"
            @focus="formReadonly = false"
          />
        </el-form-item>
        <el-form-item v-if="showRoleField" label="角色">
          <el-select v-model="form.role" style="width: 100%">
            <el-option label="管理员" value="admin" />
            <el-option label="普通用户" value="user" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="auth.isSuperAdmin && !auth.isTierAdmin" label="状态"><el-switch v-model="form.is_active" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showForm = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveUser">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showGate" title="访问密钥设置" width="480px" append-to-body @open="loadGateConfig">
      <p class="gate-hint">登录与注册需正确回答密钥问题。仅超级管理员可修改。</p>
      <el-form label-width="88px">
        <el-form-item label="密钥问题">
          <el-input v-model="gateForm.question" type="textarea" :rows="2" placeholder="例如：本系统的内部代号是？" />
        </el-form-item>
        <el-form-item label="密钥答案">
          <el-input
            v-model="gateForm.answer"
            type="password"
            show-password
            :placeholder="gateConfig.has_answer ? '留空则保留原答案' : '请设置答案'"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showGate = false">取消</el-button>
        <el-button type="primary" :loading="gateSaving" @click="saveGate">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const users = ref([])
const loading = ref(false)
const showForm = ref(false)
const editing = ref(null)
const saving = ref(false)
const formReadonly = ref(true)
const showGate = ref(false)
const gateSaving = ref(false)
const gateConfig = ref({ enabled: false, question: null, has_answer: false })
const gateForm = ref({ question: '', answer: '' })

const ROLE_LABELS = {
  super_admin: '超级管理员',
  admin: '管理员',
  user: '普通用户',
}

function roleLabel(role) {
  return ROLE_LABELS[role] || role
}

function roleTagClass(role) {
  if (role === 'super_admin') return 'purple'
  if (role === 'admin') return 'blue'
  return 'dark'
}

const defaultForm = () => ({
  username: '',
  email: '',
  password: '',
  role: 'user',
  is_active: true,
})

const form = ref(defaultForm())

const showRoleField = computed(() => {
  if (auth.isTierAdmin) return true
  if (!auth.isSuperAdmin) return false
  if (!editing.value) return true
  return editing.value.role !== 'super_admin'
})

const showEmailField = computed(() => {
  if (auth.isTierAdmin && editing.value) return false
  return true
})

function canManageUser(row) {
  if (row.role === 'super_admin') return false
  if (auth.isSuperAdmin) return true
  if (auth.isTierAdmin) return true
  return false
}

async function loadUsers() {
  loading.value = true
  try {
    const { data } = await api.get('/users')
    users.value = data
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  form.value = defaultForm()
  formReadonly.value = true
  showForm.value = true
}

function onFormOpened() {
  formReadonly.value = true
  form.value.password = ''
  if (!editing.value) {
    form.value = defaultForm()
  }
}

function openEdit(row) {
  editing.value = row
  form.value = {
    username: row.username,
    email: row.email || '',
    password: '',
    role: row.role,
    is_active: row.is_active,
  }
  formReadonly.value = true
  showForm.value = true
}

function validateForm(isEdit) {
  if (!isEdit) {
    const username = form.value.username?.trim()
    if (!username) return '请输入用户名'
    if (username.length < 2) return '用户名至少 2 个字符'
    if (username.length > 50) return '用户名不能超过 50 个字符'
  }
  const email = form.value.email?.trim()
  if (showEmailField.value && email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return '邮箱格式不正确'
  const password = form.value.password?.trim()
  if (!isEdit) {
    if (!password) return '请输入密码'
    if (password.length < 6) return '密码至少 6 位'
  } else if (password && password.length < 6) {
    return '密码至少 6 位'
  }
  return null
}

function buildCreatePayload() {
  const payload = {
    username: form.value.username.trim(),
    password: form.value.password,
    role: form.value.role,
    is_active: form.value.is_active,
  }
  const email = form.value.email?.trim()
  if (email) payload.email = email
  return payload
}

async function saveUser() {
  const isEdit = !!editing.value
  const error = validateForm(isEdit)
  if (error) {
    ElMessage.warning(error)
    return
  }
  saving.value = true
  try {
    if (isEdit) {
      const payload = {}
      if (auth.isSuperAdmin && !auth.isTierAdmin) {
        payload.email = form.value.email?.trim() || null
        payload.is_active = form.value.is_active
      }
      if (showRoleField.value) payload.role = form.value.role
      if (form.value.password?.trim()) payload.password = form.value.password
      await api.put(`/admin/users/${editing.value.id}`, payload)
      ElMessage.success('用户已更新')
    } else {
      await api.post('/admin/users', buildCreatePayload())
      ElMessage.success('用户已创建')
    }
    showForm.value = false
    await loadUsers()
  } catch {
    // 错误提示由 api 拦截器处理
  } finally {
    saving.value = false
  }
}

async function removeUser(row) {
  await ElMessageBox.confirm(`确定删除用户 ${row.username}？`, '确认')
  await api.delete(`/admin/users/${row.id}`)
  ElMessage.success('已删除')
  await loadUsers()
}

function openGateDialog() {
  showGate.value = true
}

async function loadGateConfig() {
  const { data } = await api.get('/admin/access-gate')
  gateConfig.value = data
  gateForm.value = { question: data.question || '', answer: '' }
}

async function saveGate() {
  const question = gateForm.value.question?.trim()
  if (!question) {
    ElMessage.warning('请输入密钥问题')
    return
  }
  const answer = gateForm.value.answer?.trim()
  if (!gateConfig.value.has_answer && !answer) {
    ElMessage.warning('请设置密钥答案')
    return
  }
  gateSaving.value = true
  try {
    const payload = { question }
    if (answer) payload.answer = answer
    await api.put('/admin/access-gate', payload)
    ElMessage.success('访问密钥已更新')
    showGate.value = false
  } catch {
    // api 拦截器处理
  } finally {
    gateSaving.value = false
  }
}

onMounted(loadUsers)
</script>

<style scoped>
.page { animation: fadeIn 0.4s ease; }
.tier-hint, .form-hint, .gate-hint {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--tm-text-muted);
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
