/**
 * Axios Plugin for Vue 3
 */
import axios from 'axios'

// Create axios instance
const axiosInstance = axios.create({
  baseURL: '/api',
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json'
  }
})

const SESSION_MAX_AGE_MS = 2 * 60 * 60 * 1000 // 2 horas

// Request interceptor
axiosInstance.interceptors.request.use(
  config => {
    const accessToken = localStorage.getItem('accessToken')
    const loginTimestamp = localStorage.getItem('loginTimestamp')

    if (accessToken) {
      // Validação do timer de 2 horas
      if (loginTimestamp && (Date.now() - parseInt(loginTimestamp, 10)) > SESSION_MAX_AGE_MS) {
        localStorage.removeItem('accessToken')
        localStorage.removeItem('loginTimestamp')
        if (window.location.pathname !== '/login') {
          window.location.href = '/login?expired=1'
        }
        return Promise.reject(new Error('Sessão expirada após 2 horas'))
      }
      config.headers.Authorization = `Bearer ${accessToken}`
    }
    return config
  },
  error => Promise.reject(error)
)

// Response interceptor
axiosInstance.interceptors.response.use(
  response => response,
  error => {
    console.error('API Error:', error.response?.data || error.message)
    if (error.response && (error.response.status === 401 || error.response.status === 403)) {
      const isLoginRequest = error.config?.url?.includes('/auth/login')
      if (!isLoginRequest) {
        localStorage.removeItem('accessToken')
        localStorage.removeItem('loginTimestamp')
        if (window.location.pathname !== '/login') {
          window.location.href = '/login?expired=1'
        }
      }
    }
    return Promise.reject(error)
  }
)

// Export for use
export default axiosInstance

// Plugin install function for Vue 3
export function setupAxios(app) {
  app.config.globalProperties.$axios = axiosInstance
  app.config.globalProperties.$http = axiosInstance
}
