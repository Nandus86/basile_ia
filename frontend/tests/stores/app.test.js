import { describe, it, expect } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAppConfigStore } from '@/stores/appConfig'
import { useAppStore } from '@/stores/app'

describe('AppConfig Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should have default state', () => {
    const store = useAppConfigStore()
    
    expect(store.app).toBeDefined()
    expect(store.menu).toBeDefined()
    expect(store.appBar).toBeDefined()
    expect(store.footer).toBeDefined()
    expect(store.themes).toBeDefined()
  })

  it('should update content layout nav', () => {
    const store = useAppConfigStore()
    const newLayout = 'horizontal'
    
    store.updateContentLayoutNav(newLayout)
    
    expect(store.app.contentLayoutNav).toBe(newLayout)
  })

  it('should toggle menu hidden', () => {
    const store = useAppConfigStore()
    const initialValue = store.menu.isMenuHidden
    
    store.toggleMenuHidden()
    
    expect(store.menu.isMenuHidden).toBe(!initialValue)
  })

  it('should toggle vertical nav mini', () => {
    const store = useAppConfigStore()
    const initialValue = store.menu.isVerticalNavMini
    
    store.toggleVerticalNavMini()
    
    expect(store.menu.isVerticalNavMini).toBe(!initialValue)
  })

  it('should update app bar type', () => {
    const store = useAppConfigStore()
    const newType = 'static'
    
    store.updateAppBarType(newType)
    
    expect(store.appBar.type).toBe(newType)
  })

  it('should update footer type', () => {
    const store = useAppConfigStore()
    const newType = 'hidden'
    
    store.updateFooterType(newType)
    
    expect(store.footer.type).toBe(newType)
  })
})

describe('App Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should have default shallContentShowOverlay as false', () => {
    const store = useAppStore()
    
    expect(store.shallContentShowOverlay).toBe(false)
  })

  it('should toggle content overlay', () => {
    const store = useAppStore()
    
    store.toggleContentOverlay()
    
    expect(store.shallContentShowOverlay).toBe(true)
  })

  it('should set content overlay to specific value', () => {
    const store = useAppStore()
    
    store.toggleContentOverlay(true)
    expect(store.shallContentShowOverlay).toBe(true)
    
    store.toggleContentOverlay(false)
    expect(store.shallContentShowOverlay).toBe(false)
  })
})
