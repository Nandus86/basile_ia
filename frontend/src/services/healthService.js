import api from './api'

export const healthService = {
  getDependencies: () => api.get('/health/dependencies'),
}
