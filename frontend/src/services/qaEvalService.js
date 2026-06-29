import api from './api'

export const qaEvalService = {
  getPairs: (params) => api.get('/qa-eval/pairs', { params }),
  getEvaluations: (params) => api.get('/qa-eval/evaluations', { params }),
  createEvaluation: (data) => api.post('/qa-eval/evaluations', data),
  updateEvaluation: (id, data) => api.put(`/qa-eval/evaluations/${id}`, data),
  deleteEvaluation: (id) => api.delete(`/qa-eval/evaluations/${id}`),
  getStats: (params) => api.get('/qa-eval/stats', { params }),
  getTopics: () => api.get('/qa-eval/topics'),
  exportData: (params) => api.get('/qa-eval/export', { params, responseType: 'blob' }),
}
