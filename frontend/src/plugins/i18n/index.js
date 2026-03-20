import messages from '@/plugins/i18n/locales/pt-BR'
import Vue from 'vue'
import VueI18n from 'vue-i18n'

Vue.use(VueI18n)

export const i18n = new VueI18n({
  locale: localStorage.getItem('locale') || 'pt-BR',
  fallbackLocale: 'pt-BR',
  messages: {
    'pt-BR': messages,
  },
})

const loadedLanguages = ['pt-BR']

function setI18nLanguage(lang) {
  i18n.locale = lang
  document.querySelector('html').setAttribute('lang', lang)
  localStorage.setItem('locale', lang)
  
  return lang
}

export function loadLanguageAsync(lang) {
  if (i18n.locale === lang) {
    return Promise.resolve(setI18nLanguage(lang))
  }

  if (loadedLanguages.includes(lang)) {
    return Promise.resolve(setI18nLanguage(lang))
  }

  return import(/* webpackChunkName: "lang-[request]" */ '@/plugins/i18n/locales/' + lang + '.js').then(msgs => {
    i18n.setLocaleMessage(lang, msgs.default)
    loadedLanguages.push(lang)

    return setI18nLanguage(lang)
  }).catch(() => {
    return Promise.resolve(setI18nLanguage('pt-BR'))
  })
}

export default i18n
