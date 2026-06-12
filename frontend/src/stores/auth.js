import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/utils/api'

const ROLE_LABELS = {
  super_admin: '超级管理员',
  admin: '管理员',
  user: '普通用户',
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const token = ref(localStorage.getItem('token') || '')

  const role = computed(() => user.value?.role || 'user')
  const isLoggedIn = computed(() => !!token.value)
  const isSuperAdmin = computed(() => role.value === 'super_admin')
  const isTierAdmin = computed(() => role.value === 'admin')
  const isUserManager = computed(() => isSuperAdmin.value || isTierAdmin.value)
  const isAdmin = computed(() => isUserManager.value)
  const canAccessMonitorAdmin = computed(() => isSuperAdmin.value)
  const roleLabel = computed(() => ROLE_LABELS[role.value] || role.value)

  async function login(username, password, gateAnswer = null) {
    const { data } = await api.post('/auth/login', {
      username,
      password,
      gate_answer: gateAnswer,
    })
    token.value = data.access_token
    localStorage.setItem('token', data.access_token)
    await fetchUser()
  }

  async function register(form) {
    await api.post('/auth/register', form)
  }

  async function fetchUser() {
    if (!token.value) return
    const { data } = await api.get('/users/me')
    user.value = data
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
  }

  return {
    user,
    token,
    role,
    roleLabel,
    isLoggedIn,
    isSuperAdmin,
    isTierAdmin,
    isUserManager,
    isAdmin,
    canAccessMonitorAdmin,
    login,
    register,
    fetchUser,
    logout,
  }
})
