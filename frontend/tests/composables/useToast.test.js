import { describe, it, expect } from 'vitest'
import { useToast } from '@/composables/useToast'

describe('useToast Composable', () => {
  it('should create toast with default values', () => {
    const { toasts, show } = useToast()
    
    const id = show('Test message')
    
    expect(toasts.value.length).toBe(1)
    expect(toasts.value[0].message).toBe('Test message')
    expect(toasts.value[0].type).toBe('error')
    expect(typeof id).toBe('number')
  })

  it('should create toast with custom type', () => {
    const { toasts, show } = useToast()
    
    show('Success message', 'success')
    
    expect(toasts.value[0].type).toBe('success')
  })

  it('should remove toast by id', () => {
    const { toasts, show, remove } = useToast()
    
    const id = show('Test message')
    expect(toasts.value.length).toBe(1)
    
    remove(id)
    expect(toasts.value.length).toBe(0)
  })

  it('should have helper methods', () => {
    const { success, error, warning, info } = useToast()
    
    expect(typeof success).toBe('function')
    expect(typeof error).toBe('function')
    expect(typeof warning).toBe('function')
    expect(typeof info).toBe('function')
  })

  it('should create success toast with helper', () => {
    const { toasts, success } = useToast()
    
    success('Operation successful')
    
    expect(toasts.value[0].type).toBe('success')
    expect(toasts.value[0].message).toBe('Operation successful')
  })
})
