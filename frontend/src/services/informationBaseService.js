import api from './api'

export const informationBaseService = {
  getAll: () => api.get('/information-bases'),
  getById: (id) => api.get(`/information-bases/${id}`),
  create: (data) => api.post('/information-bases', data),
  update: (id, data) => api.put(`/information-bases/${id}`, data),
  delete: (id) => api.delete(`/information-bases/${id}`),
}
