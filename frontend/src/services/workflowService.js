import api from './api'

export const workflowService = {
  getAll: () => api.get('/workflows'),
  getById: (id) => api.get(`/workflows/${id}`),
  create: (data) => api.post('/workflows', data),
  update: (id, data) => api.put(`/workflows/${id}`, data),
  delete: (id) => api.delete(`/workflows/${id}`),
}

export const webhookService = {
  getAll: () => api.get('/webhooks-config'),
  create: (data) => api.post('/webhooks-config', data),
  update: (id, data) => api.put(`/webhooks-config/${id}`, data),
  delete: (id) => api.delete(`/webhooks-config/${id}`),
}
