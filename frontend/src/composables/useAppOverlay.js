import { useAppStore } from '@/stores/app'

export function useAppOverlay() {
  const appStore = useAppStore()

  return {
    shallContentShowOverlay: computed(() => appStore.shallContentShowOverlay),
    toggleContentOverlay: appStore.toggleContentOverlay,
  }
}
