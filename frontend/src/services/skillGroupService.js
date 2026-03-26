import api from './api'

export const skillGroupService = {
  list: () => api.get('/skill-groups'),
  create: (data) => api.post('/skill-groups', data),
  update: (id, data) => api.put(`/skill-groups/${id}`, data),
  delete: (id) => api.delete(`/skill-groups/${id}`),
}
