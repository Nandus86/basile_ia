import api from './api'

export const vfsKnowledgeService = {
  getAll: () => api.get('/vfs-knowledge-bases'),
  getById: (id) => api.get(`/vfs-knowledge-bases/${id}`),
  create: (data) => api.post('/vfs-knowledge-bases', data),
  update: (id, data) => api.put(`/vfs-knowledge-bases/${id}`, data),
  delete: (id) => api.delete(`/vfs-knowledge-bases/${id}`),
  
  getFiles: (kbId) => api.get(`/vfs-knowledge-bases/${kbId}/files`),
  getFile: (kbId, fileId) => api.get(`/vfs-knowledge-bases/${kbId}/files/${fileId}`),
  createFile: (kbId, data) => api.post(`/vfs-knowledge-bases/${kbId}/files/create`, data),
  updateFile: (kbId, fileId, data) => api.put(`/vfs-knowledge-bases/${kbId}/files/${fileId}`, data),
  uploadFile: (kbId, data) => api.post(`/vfs-knowledge-bases/${kbId}/files`, data, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }),
  deleteFile: (kbId, fileId) => api.delete(`/vfs-knowledge-bases/${kbId}/files/${fileId}`),
}
