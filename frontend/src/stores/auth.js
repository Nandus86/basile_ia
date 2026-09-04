import { defineStore } from 'pinia'
import axios from '@/plugins/axios'

export const SESSION_MAX_AGE_MS = 2 * 60 * 60 * 1000 // 2 horas obrigatórias

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('accessToken') || null,
    loginTimestamp: localStorage.getItem('loginTimestamp') ? parseInt(localStorage.getItem('loginTimestamp'), 10) : null,
    user: null,
  }),
  getters: {
    isExpired: (state) => {
      if (!state.loginTimestamp) return false
      return (Date.now() - state.loginTimestamp) > SESSION_MAX_AGE_MS
    },
    isAuthenticated: (state) => !!state.token && !state.isExpired,
  },
  actions: {
    async login(email, password) {
      const formData = new URLSearchParams()
      formData.append('username', email)
      formData.append('password', password)

      try {
        const response = await axios.post('/auth/login', formData, {
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded'
          }
        })
        this.token = response.data.access_token
        this.loginTimestamp = Date.now()
        localStorage.setItem('accessToken', this.token)
        localStorage.setItem('loginTimestamp', this.loginTimestamp.toString())
        return true
      } catch (error) {
        console.error('Login error', error)
        throw error
      }
    },
    logout(redirect = false, reason = null) {
      this.token = null
      this.loginTimestamp = null
      this.user = null
      localStorage.removeItem('accessToken')
      localStorage.removeItem('loginTimestamp')
      if (redirect) {
        const query = reason ? `?${reason}=1` : ''
        if (window.location.pathname !== '/login') {
          window.location.href = `/login${query}`
        }
      }
    },
    checkSession() {
      if (this.token && this.isExpired) {
        this.logout(true, 'expired')
        return false
      }
      return !!this.token
    }
  }
})
