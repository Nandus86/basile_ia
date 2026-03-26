import api from './api'

export const agentGroupService = {
  list: (parentId = null) => api.get('/agent-groups', { params: parentId ? { parent_id: parentId } : {} }),
  tree: () => api.get('/agent-groups/tree'),
  create: (data) => api.post('/agent-groups', data),
  update: (id, data) => api.put(`/agent-groups/${id}`, data),
  delete: (id) => api.delete(`/agent-groups/${id}`),
}
