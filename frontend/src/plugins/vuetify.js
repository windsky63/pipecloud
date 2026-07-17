import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as labsComponents from 'vuetify/labs/components'
import * as directives from 'vuetify/directives'
import { en, zhHans } from 'vuetify/locale'
import { i18n } from '../i18n'

const THEME_STORAGE_KEY = 'pipecloud.uiTheme'
const DEFAULT_THEME = 'pipecloud'
const AVAILABLE_THEMES = new Set(['pipecloud', 'pipecloudGray', 'pipecloudDark'])

function readInitialTheme() {
  if (typeof window === 'undefined') return DEFAULT_THEME
  const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY)
  return AVAILABLE_THEMES.has(storedTheme) ? storedTheme : DEFAULT_THEME
}

/**
 * UI 框架配置集中在插件层，避免应用入口同时承担主题、组件注册和挂载职责。
 * 主题名称属于持久化协议；修改名称时需要同步迁移 localStorage 中的旧值。
 */
export const vuetify = createVuetify({
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
    defaultTheme: readInitialTheme(),
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
