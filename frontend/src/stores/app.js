import { defineStore } from 'pinia'

export const useAppStore = defineStore('app', {
  state: () => ({
    shallContentShowOverlay: false,
  }),
  actions: {
    toggleContentOverlay(value) {
      this.shallContentShowOverlay = value !== undefined ? value : !this.shallContentShowOverlay
    },
  },
})
