import { defineStore } from 'pinia'
import themeConfig from '@themeConfig'

export const useAppConfigStore = defineStore('appConfig', {
  state: () => ({
    app: {
      contentLayoutNav: themeConfig.app.contentLayoutNav,
      routeTransition: themeConfig.app.routeTransition,
      skinVariant: localStorage.getItem('materio-skin-variant')
        ? localStorage.getItem('materio-skin-variant')
        : themeConfig.app.skinVariant,
      contentWidth: themeConfig.app.contentWidth,
    },
    menu: {
      isMenuHidden: themeConfig.menu.isMenuHidden,
      isVerticalNavMini: themeConfig.menu.isVerticalNavMini,
    },
    appBar: {
      type: themeConfig.appBar.type,
      isBlurred: themeConfig.appBar.isBlurred,
    },
    footer: {
      type: themeConfig.footer.type,
    },
    themes: themeConfig.themes,
  }),
  actions: {
    updateAppRouteTransition(value) {
      this.app.routeTransition = value
    },
    updateContentLayoutNav(value) {
      this.app.contentLayoutNav = value
    },
    updateAppSkinVariant(value) {
      this.app.skinVariant = value
    },
    updateAppContentWidth(value) {
      this.app.contentWidth = value
    },
    toggleMenuHidden(value) {
      this.menu.isMenuHidden = value !== undefined ? value : !this.menu.isMenuHidden
    },
    toggleVerticalNavMini(value) {
      this.menu.isVerticalNavMini = value !== undefined ? value : !this.menu.isVerticalNavMini
    },
    updateAppBarType(value) {
      this.appBar.type = value
    },
    updateAppBarIsBlurred(value) {
      this.appBar.isBlurred = value
    },
    updateFooterType(value) {
      this.footer.type = value
    },
    updateThemes(value) {
      this.themes = value
    },
  },
})
