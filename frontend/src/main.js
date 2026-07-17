import { createApp } from 'vue'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as labsComponents from 'vuetify/labs/components'
import * as directives from 'vuetify/directives'
import { en, zhHans } from 'vuetify/locale'
import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import './style.css'
import App from './App.vue'
import InfoTooltip from './components/InfoTooltip.vue'
import { i18n } from './i18n'
import router from './router'

const storedTheme = typeof window === 'undefined' ? 'pipecloud' : window.localStorage.getItem('pipecloud.uiTheme')
const defaultTheme = ['pipecloud', 'pipecloudGray', 'pipecloudDark'].includes(storedTheme) ? storedTheme : 'pipecloud'

const vuetify = createVuetify({
  components: {
    ...components,
    ...labsComponents,
  },
  directives,
  defaults: {
    VBtn: { rounded: 'sm' },
    VCard: { rounded: 'sm' },
    VTextField: { rounded: 'sm' },
    VSelect: { rounded: 'sm' },
    VDialog: { rounded: 'sm' },
    VSheet: { rounded: 'sm' },
    VChip: { rounded: 'm' },
  },
  icons: {
    defaultSet: 'mdi',
  },
  locale: {
    locale: i18n.global.locale.value === 'zh-CN' ? 'zhHans' : 'en',
    fallback: 'en',
    messages: { en, zhHans },
  },
  theme: {
    defaultTheme,
    themes: {
      pipecloud: {
        dark: false,
        colors: {
          primary: '#2563eb',
          secondary: '#475569',
          success: '#0f9f6e',
          error: '#dc2626',
          warning: '#d97706',
          surface: '#ffffff',
          background: '#f4f7fb',
        },
      },
      pipecloudGray: {
        dark: false,
        colors: {
          primary: '#3f6b8f',
          secondary: '#5f6f7d',
          success: '#3c7a63',
          error: '#b65b5b',
          warning: '#9a7440',
          surface: '#eef1f4',
          background: '#dfe5ea',
        },
      },
      pipecloudDark: {
        dark: true,
        colors: {
          primary: '#60a5fa',
          secondary: '#94a3b8',
          success: '#34d399',
          error: '#f87171',
          warning: '#fbbf24',
          surface: '#1f2937',
          background: '#111827',
        },
      },
    },
  },
})

createApp(App).component('InfoTooltip', InfoTooltip).use(i18n).use(vuetify).use(router).mount('#app')
