import api from './api'

export const skillService = {
  getAll: () => api.get('/skills/'),
  getById: (id) => api.get(`/skills/${id}`),
  create: (data) => api.post('/skills/', data),
  update: (id, data) => api.put(`/skills/${id}`, data),
  delete: (id) => api.delete(`/skills/${id}`),
}
