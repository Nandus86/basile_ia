import { useAppConfigStore } from '@/stores/appConfig'
import { getVuetify } from '@core/utils'
import { computed } from '@vue/composition-api'

export default function useAppConfig() {
  const appConfigStore = useAppConfigStore()
  const $vuetify = getVuetify()

  const appContentLayoutNav = computed({
    get: () => appConfigStore.app.contentLayoutNav,
    set: value => {
      appConfigStore.updateContentLayoutNav(value)
    },
  })

  const appRouteTransition = computed({
    get: () => appConfigStore.app.routeTransition,
    set: value => {
      appConfigStore.updateAppRouteTransition(value)
    },
  })

  const appSkinVariant = computed({
    get: () => appConfigStore.app.skinVariant,
    set: value => {
      appConfigStore.updateAppSkinVariant(value)
      localStorage.setItem('materio-skin-variant', value)
    },
  })

  const appContentWidth = computed({
    get: () => appConfigStore.app.contentWidth,
    set: value => {
      appConfigStore.updateAppContentWidth(value)
    },
  })

  const menuIsMenuHidden = computed({
    get: () => appConfigStore.menu.isMenuHidden,
    set: value => {
      appConfigStore.toggleMenuHidden(value)
    },
  })

  const menuIsVerticalNavMini = computed({
    get: () => appConfigStore.menu.isVerticalNavMini,
    set: value => {
      appConfigStore.toggleVerticalNavMini(value)
    },
  })

  const appBarType = computed({
    get: () => appConfigStore.appBar.type,
    set: value => {
      appConfigStore.updateAppBarType(value)
    },
  })

  const appBarIsBlurred = computed({
    get: () => appConfigStore.appBar.isBlurred,
    set: value => {
      appConfigStore.updateAppBarIsBlurred(value)
    },
  })

  const footerType = computed({
    get: () => appConfigStore.footer.type,
    set: value => {
      appConfigStore.updateFooterType(value)
    },
  })

  const isDark = computed({
    get: () => $vuetify.theme.dark,
    set: value => {
      $vuetify.theme.dark = value
      localStorage.setItem('materio-active-theme', value ? 'dark' : 'light')
    },
  })

  const isRtl = computed({
    get: () => $vuetify.rtl,
    set: value => {
      $vuetify.rtl = value
    },
  })

  const themes = computed({
    get: () => $vuetify.theme.themes,
    set: value => {
      appConfigStore.updateThemes(value)
      $vuetify.theme.themes.light = value.light
      $vuetify.theme.themes.dark = value.dark
    },
  })

  return {
    appContentLayoutNav,
    appRouteTransition,
    appSkinVariant,
    appContentWidth,
    menuIsMenuHidden,
    menuIsVerticalNavMini,
    appBarType,
    appBarIsBlurred,
    footerType,
    isDark,
    isRtl,
    themes,
  }
}
