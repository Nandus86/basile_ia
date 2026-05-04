import { defineStore } from 'pinia'
import axios from '@/plugins/axios'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('accessToken') || null,
    user: null,
  }),
  getters: {
    isAuthenticated: (state) => !!state.token,
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
        localStorage.setItem('accessToken', this.token)
        return true
      } catch (error) {
        console.error('Login error', error)
        throw error
      }
    },
    logout() {
      this.token = null
      this.user = null
      localStorage.removeItem('accessToken')
    }
  }
})
