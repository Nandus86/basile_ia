import api from './api'

export const agentService = {
  getAll: () => api.get('/agents'),
  getById: (id) => api.get(`/agents/${id}`),
  create: (data) => api.post('/agents', data),
  update: (id, data) => api.put(`/agents/${id}`, data),
  delete: (id) => api.delete(`/agents/${id}`),
  
  getConfig: (id) => api.get(`/agents/${id}/config`),
  updateConfig: (id, data) => api.put(`/agents/${id}/config`, data),
  
  getPromptPreview: (id, formData) => api.get(`/agents/${id}/prompt-preview`, { params: formData }),
  
  getDocuments: (id) => api.get(`/agents/${id}/documents`),
  addDocument: (id, docId) => api.post(`/agents/${id}/documents/${docId}`),
  removeDocument: (id, docId) => api.delete(`/agents/${id}/documents/${docId}`),
  
  getMcps: (id) => api.get(`/agents/${id}/mcps`),
  addMcp: (id, mcpId) => api.post(`/agents/${id}/mcps/${mcpId}`),
  removeMcp: (id, mcpId) => api.delete(`/agents/${id}/mcps/${mcpId}`),
  
  getMcpGroups: (id) => api.get(`/agents/${id}/mcp-groups`),
  addMcpGroup: (id, groupId) => api.post(`/agents/${id}/mcp-groups/${groupId}`),
  removeMcpGroup: (id, groupId) => api.delete(`/agents/${id}/mcp-groups/${groupId}`),
  
  getSkills: (id) => api.get(`/agents/${id}/skills`),
  addSkill: (id, skillId) => api.post(`/agents/${id}/skills/${skillId}`),
  removeSkill: (id, skillId) => api.delete(`/agents/${id}/skills/${skillId}`),
  
  getInformationBases: (id) => api.get(`/agents/${id}/information-bases`),
  addInformationBase: (id, baseId) => api.post(`/agents/${id}/information-bases/${baseId}`),
  removeInformationBase: (id, baseId) => api.delete(`/agents/${id}/information-bases/${baseId}`),
  
  getVfsKnowledgeBases: (id) => api.get(`/agents/${id}/vfs-knowledge-bases`),
  addVfsKnowledgeBase: (id, vfsId) => api.post(`/agents/${id}/vfs-knowledge-bases/${vfsId}`),
  removeVfsKnowledgeBase: (id, vfsId) => api.delete(`/agents/${id}/vfs-knowledge-bases/${vfsId}`),
  
  getCollaborators: (id) => api.get(`/agents/${id}/collaborators`),
  updateCollaborators: (id, collaborators) => api.put(`/agents/${id}/collaborators`, { collaborators }),
  
  clone: (agent) => api.post('/agents', agent),
}

export const modelsService = {
  getAvailable: () => api.get('/models/available'),
}

export const emotionalProfilesService = {
  getAll: () => api.get('/emotional-profiles'),
}
