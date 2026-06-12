import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const detail = err.response?.data?.detail
    let msg = err.message || '请求失败'
    if (typeof detail === 'string') {
      const zhMap = {
        'Username or email already exists': '用户名或邮箱已存在',
        '用户名已存在': '用户名已存在',
        '邮箱已被使用': '邮箱已被使用',
        '用户名已存在或邮箱已被使用': '用户名已存在或邮箱已被使用',
        '访问密钥回答错误': '访问密钥回答错误',
        'Invalid credentials': '账号或密码错误',
      }
      msg = zhMap[detail] || detail
    } else if (Array.isArray(detail) && detail.length) {
      const item = detail[0]
      const field = item.loc?.[item.loc.length - 1]
      if (field === 'username' && item.type === 'string_too_short') {
        msg = '用户名至少 2 个字符'
      } else if (field === 'password' && item.type === 'string_too_short') {
        msg = '密码至少 6 位'
      } else if (field === 'email') {
        msg = '邮箱格式不正确'
      } else {
        msg = item.msg || item.message || msg
      }
    }
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      if (!window.location.pathname.includes('/login')) {
        window.location.href = '/login'
      }
    } else if (!err.config?.skipErrorToast) {
      ElMessage.error(msg)
    }
    return Promise.reject(err)
  }
)

export default api
