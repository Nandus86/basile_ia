import api from './api'

export const memoryService = {
  stm: {
    getKeys: (params) => api.get('/memory/stm/keys', { params }),
    getKey: (key) => api.get(`/memory/stm/keys/${key}`),
    deleteKey: (key) => api.delete(`/memory/stm/keys/${key}`),
    deleteKeys: (keys) => api.delete('/memory/stm/keys', { data: keys }),
  },
  
  vector: {
    getMemories: (params) => api.get('/memory/vector/memories', { params }),
    getAgentMemories: (params) => api.get('/memory/vector/agent-memories', { params }),
    getCollections: () => api.get('/memory/vector/collections'),
    deleteMemory: (uuid) => api.delete(`/memory/vector/memories/${uuid}`),
    deleteAgentMemory: (uuid) => api.delete(`/memory/vector/agent-memories/${uuid}`),
    deleteMemories: (memories) => api.delete('/memory/vector/memories', { data: memories }),
  },
  
  mtm: {
    getSessions: (params) => api.get('/memory/mtm/sessions', { params }),
    getSession: (sessionId) => api.get(`/memory/mtm/sessions/${sessionId}`),
    deleteSession: (sessionId) => api.delete(`/memory/mtm/sessions/${sessionId}`),
    deleteSessions: (sessionIds) => api.delete('/memory/mtm/sessions', { data: sessionIds }),
  },
}
