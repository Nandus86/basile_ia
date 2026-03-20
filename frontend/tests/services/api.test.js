import { describe, it, expect } from 'vitest'
import { handleApiError } from '@/services/api'

describe('API Service', () => {
  describe('handleApiError', () => {
    it('should extract message from response data', () => {
      const error = {
        response: {
          data: {
            message: 'Error message from server'
          }
        }
      }
      
      const result = handleApiError(error)
      
      expect(result).toBe('Error message from server')
    })

    it('should extract error from response data', () => {
      const error = {
        response: {
          data: {
            error: 'Error field'
          }
        }
      }
      
      const result = handleApiError(error)
      
      expect(result).toBe('Error field')
    })

    it('should extract message from error object', () => {
      const error = {
        message: 'Network error message'
      }
      
      const result = handleApiError(error)
      
      expect(result).toBe('Network error message')
    })

    it('should return default message for unknown errors', () => {
      const error = {}
      
      const result = handleApiError(error)
      
      expect(result).toBe('Erro desconhecido')
    })

    it('should handle request without response', () => {
      const error = {
        request: {}
      }
      
      const result = handleApiError(error)
      
      expect(result).toBe('Sem resposta do servidor. Verifique sua conexão.')
    })
  })
})
