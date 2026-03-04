import themeConfig from '@themeConfig'

require('@resources/sass/preset/overrides.scss')

// Skins
require('@resources/sass/preset/skins/bordered.scss')
require('@resources/sass/preset/skins/semi-dark.scss')

export default {
  theme: {
    themes: {
      ...themeConfig.themes,
    },
    dark:
      localStorage.getItem('materio-active-theme') === null
        ? themeConfig.app.isDark
        : localStorage.getItem('materio-active-theme') === 'dark',
  },
  rtl: themeConfig.app.isRtl,
}
