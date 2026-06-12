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

          <h1 class="title">Create account</h1>
          <p class="subtitle">Sign up to get started</p>

          <form class="login-form" @submit.prevent="handleRegister">
            <div class="field">
              <label>Username</label>
              <input v-model="form.username" type="text" placeholder="your name" @focus="focusField = 'username'" @blur="focusField = ''" />
              <span class="underline" :class="{ focused: focusField === 'username' }"></span>
            </div>

            <div class="field">
              <label>Email</label>
              <input v-model="form.email" type="email" placeholder="you@example.com（选填）" @focus="focusField = 'email'" @blur="focusField = ''" />
              <span class="underline" :class="{ focused: focusField === 'email' }"></span>
            </div>

            <div class="field">
              <label>Password</label>
              <input v-model="form.password" :type="showPassword ? 'text' : 'password'" placeholder="••••••••" @focus="focusField = 'password'" @blur="focusField = ''" />
              <span class="underline" :class="{ focused: focusField === 'password' }"></span>
            </div>

            <div v-if="gate.enabled" class="field">
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

            <button type="submit" class="btn-login" :disabled="loading">
              <span v-if="loading" class="spinner"></span>
              <span v-else>Sign Up</span>
            </button>
          </form>

          <p class="signup-hint">
            Already have an account?
            <router-link to="/login">Log In</router-link>
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/utils/api'
import { useAuthStore } from '@/stores/auth'
import LoginIllustration from '@/components/LoginIllustration.vue'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const showPassword = ref(false)
const focusField = ref('')
const gate = ref({ enabled: false, question: null })
const form = ref({ username: '', email: '', password: '', gate_answer: '' })

async function loadGate() {
  try {
    const { data } = await api.get('/auth/access-gate')
    gate.value = data
  } catch {
    gate.value = { enabled: false, question: null }
  }
}

async function handleRegister() {
  if (!form.value.username?.trim() || !form.value.password) {
    ElMessage.warning('请填写用户名和密码')
    return
  }
  if (gate.value.enabled && !form.value.gate_answer?.trim()) {
    ElMessage.warning('请输入密钥')
    return
  }
  loading.value = true
  try {
    const payload = {
      username: form.value.username.trim(),
      password: form.value.password,
      gate_answer: form.value.gate_answer?.trim() || null,
    }
    const email = form.value.email?.trim()
    if (email) payload.email = email
    await auth.register(payload)
    ElMessage.success('注册成功，请登录')
    router.push('/login')
  } catch {} finally {
    loading.value = false
  }
}

onMounted(loadGate)
</script>

<style scoped>
@import '@/styles/auth.css';
</style>
