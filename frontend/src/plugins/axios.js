/**
 * Axios Plugin for Vue 3
 */
import axios from 'axios'

// Create axios instance
const axiosInstance = axios.create({
  baseURL: '/api',
  timeout: 300000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Request interceptor
axiosInstance.interceptors.request.use(
  config => {
    const accessToken = localStorage.getItem('accessToken')
    if (accessToken) {
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
