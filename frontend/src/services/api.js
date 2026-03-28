import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 300000,
  headers: {
    'Content-Type': 'application/json'
  }
})

api.interceptors.request.use(
  config => {
    const accessToken = localStorage.getItem('accessToken')
    if (accessToken) {
      config.headers.Authorization = `Bearer ${accessToken}`
    }
    return config
  },
  error => Promise.reject(error)
)

api.interceptors.response.use(
  response => response,
  error => {
    const message = error.response?.data?.message 
      || error.response?.data?.error 
      || error.message 
      || 'Erro na requisição'
    
    if (error.response?.status === 401) {
      console.error('Unauthorized - Token may be expired')
    } else if (error.response?.status === 403) {
      console.error('Forbidden - Access denied')
    } else if (error.response?.status === 404) {
      console.error('Resource not found')
    } else if (error.response?.status >= 500) {
      console.error('Server error')
    }
    
    return Promise.reject(error)
  }
)

export function handleApiError(error) {
  if (error.response) {
    return error.response.data?.message || error.response.data?.error || 'Erro do servidor'
  } else if (error.request) {
    return 'Sem resposta do servidor. Verifique sua conexão.'
  } else {
    return error.message || 'Erro desconhecido'
  }
}

export default api
