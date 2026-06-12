<template>
  <div class="auth-page">
    <div class="auth-shell">
      <div class="auth-visual">
        <LoginIllustration />
      </div>

      <div class="auth-form-panel">
        <div class="form-inner">
          <div class="logo-mark">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
              <path d="M12 2L14.5 9.5L22 12L14.5 14.5L12 22L9.5 14.5L2 12L9.5 9.5L12 2Z" fill="#111"/>
            </svg>
          </div>

          <h1 class="title">Welcome back!</h1>
          <p class="subtitle">Please enter your details</p>

          <form class="login-form" @submit.prevent="handleLogin">
            <div class="field">
              <label>账号</label>
              <input
                v-model="form.username"
                type="text"
                placeholder="用户名 / admin"
                autocomplete="username"
                @focus="focusField = 'username'"
                @blur="focusField = ''"
              />
              <span class="underline" :class="{ focused: focusField === 'username' }"></span>
            </div>

            <div class="field">
              <label>Password</label>
              <div class="password-wrap">
                <input
                  v-model="form.password"
                  :type="showPassword ? 'text' : 'password'"
                  placeholder="••••••••"
                  autocomplete="current-password"
                  @focus="focusField = 'password'"
                  @blur="focusField = ''"
                />
                <button type="button" class="eye-btn" @click="showPassword = !showPassword" tabindex="-1">
                  <svg v-if="!showPassword" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
                  </svg>
                  <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                    <line x1="1" y1="1" x2="23" y2="23"/>
                  </svg>
                </button>
              </div>
              <span class="underline" :class="{ focused: focusField === 'password' }"></span>
            </div>

            <div v-if="showGateField" class="field">
              <label>密钥</label>
              <input
                v-model="form.gate_answer"
                type="text"
                placeholder="请输入密钥"
                autocomplete="off"
                @focus="focusField = 'gate'"
                @blur="focusField = ''"
              />
              <span class="underline" :class="{ focused: focusField === 'gate' }"></span>
            </div>

            <label class="remember">
              <input v-model="remember" type="checkbox" />
              <span class="check-box"></span>
              <span>Remember for 30 days</span>
            </label>

            <button type="submit" class="btn-login" :disabled="loading">
              <span v-if="loading" class="spinner"></span>
              <span v-else>Log In</span>
            </button>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/utils/api'
import { useAuthStore } from '@/stores/auth'
import LoginIllustration from '@/components/LoginIllustration.vue'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const showPassword = ref(false)
const remember = ref(false)
const focusField = ref('')
const gate = ref({ enabled: false, question: null })
const form = ref({ username: '', password: '', gate_answer: '' })

const showGateField = computed(() => {
  if (!gate.value.enabled) return false
  return form.value.username.trim().toLowerCase() !== 'admin'
})

async function loadGate() {
  try {
    const { data } = await api.get('/auth/access-gate')
    gate.value = data
  } catch {
    gate.value = { enabled: false, question: null }
  }
}

async function handleLogin() {
  if (!form.value.username || !form.value.password) {
    ElMessage.warning('请输入账号和密码')
    return
  }
  if (showGateField.value && !form.value.gate_answer?.trim()) {
    ElMessage.warning('请输入密钥')
    return
  }
  loading.value = true
  try {
    const gateAnswer = showGateField.value ? form.value.gate_answer?.trim() || null : null
    await auth.login(form.value.username, form.value.password, gateAnswer)
    if (remember.value) {
      localStorage.setItem('remember_user', form.value.username)
    } else {
      localStorage.removeItem('remember_user')
    }
    ElMessage.success('登录成功')
    router.push('/dashboard')
  } catch {} finally {
    loading.value = false
  }
}

onMounted(loadGate)

const saved = localStorage.getItem('remember_user')
if (saved) {
  form.value.username = saved
  remember.value = true
}
</script>

<style scoped>
@import '@/styles/auth.css';
</style>
