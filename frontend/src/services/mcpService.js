import api from './api'

export const mcpService = {
  getAll: () => api.get('/mcp'),
  getById: (id) => api.get(`/mcp/${id}`),
  create: (data) => api.post('/mcp', data),
  update: (id, data) => api.put(`/mcp/${id}`, data),
  delete: (id) => api.delete(`/mcp/${id}`),
  execute: (id, params) => api.post(`/mcp/${id}/execute`, { params }),
  
  getGroups: () => api.get('/mcp-groups'),
  createGroup: (data) => api.post('/mcp-groups', data),
  updateGroup: (id, data) => api.put(`/mcp-groups/${id}`, data),
  deleteGroup: (id) => api.delete(`/mcp-groups/${id}`),
}
