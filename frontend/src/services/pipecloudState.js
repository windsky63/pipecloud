import { computed, ref } from 'vue'
import { i18n, languageOptions, languageStorageKey, messages, setI18nLocale } from '../i18n'
import { cancelInitializationTask, fetchSummary, runWorkflowAction } from '../api/workflow'
import { ensureSelectedProject, selectedProjectParams } from './projectState'


export const loading = ref(false)
export const runningKey = ref('')
export const summary = ref({ modules: [], actions: [] })
export const lastRun = ref(null)
export const errorMessage = ref('')
export const initializationTaskId = ref('')
let runningActionController = null
let summaryRequestId = 0

const showRunLogStorageKey = 'pipecloud.showRunLog'
const sidebarCollapsedStorageKey = 'pipecloud.sidebarCollapsed'
const navigationVisibilityStorageKey = 'pipecloud.navigationVisibility'
const navigationRouteVisibilityStorageKey = 'pipecloud.navigationRouteVisibility'
const homeComponentVisibilityStorageKey = 'pipecloud.homeComponentVisibility'
const dashboardVisibilityStorageKey = 'pipecloud.dashboardVisibility'
const uiThemeStorageKey = 'pipecloud.uiTheme'
const developerModeStorageKey = 'pipecloud.developerMode'
const uiMessagePositionStorageKey = 'pipecloud.uiMessagePosition'

export const navigationVisibilityDefaults = {
  home: true,
  prefab: true,
  plans: true,
  weldLibraries: true,
  parser: true,
  spoolCheck: true,
  factory: true,
}

export const navigationVisibilityKeys = Object.keys(navigationVisibilityDefaults)

export const homeComponentVisibilityDefaults = {
  initializationDashboard: true,
  antiCorrosionDashboard: false,
  cuttingDashboard: false,
  weldingDashboard: false,
  arrivalDashboard: true,
  projectData: true,
  projectWeldInfo: true,
}

export const homeComponentVisibilityKeys = Object.keys(homeComponentVisibilityDefaults)

export const dashboardVisibilityDefaults = {
  initialization: true,
  arrival: true,
  antiCorrosion: true,
  cutting: true,
  welding: true,
  futureAntiCorrosion: true,
  futureCutting: true,
  futureWelding: true,
}

export const dashboardVisibilityKeys = Object.keys(dashboardVisibilityDefaults)

export const uiThemeOptions = [
  { titleKey: 'themePipecloud', value: 'pipecloud' },
  { titleKey: 'themePipecloudGray', value: 'pipecloudGray' },
  { titleKey: 'themePipecloudDark', value: 'pipecloudDark' },
]

export { languageOptions, messages as translations }
const translations = messages

function getInitialShowRunLog() {
  if (typeof window === 'undefined') return true
  return window.localStorage.getItem(showRunLogStorageKey) !== 'false'
}

export const showRunLog = ref(getInitialShowRunLog())

function getInitialHomeComponentVisibility() {
  const defaults = { ...homeComponentVisibilityDefaults }
  if (typeof window === 'undefined') return defaults
  try {
    const value = JSON.parse(window.localStorage.getItem(homeComponentVisibilityStorageKey) || '{}')
    const result = homeComponentVisibilityKeys.reduce((items, key) => {
      items[key] = typeof value[key] === 'boolean' ? value[key] : homeComponentVisibilityDefaults[key]
      return items
    }, {})
    return result
  } catch {
    return defaults
  }
}

export const homeComponentVisibility = ref(getInitialHomeComponentVisibility())

function getInitialDashboardVisibility() {
  if (typeof window === 'undefined') return { ...dashboardVisibilityDefaults }
  try {
    const value = JSON.parse(window.localStorage.getItem(dashboardVisibilityStorageKey) || '{}')
    return dashboardVisibilityKeys.reduce((result, key) => {
      result[key] = typeof value[key] === 'boolean' ? value[key] : dashboardVisibilityDefaults[key]
      return result
    }, {})
  } catch {
    return { ...dashboardVisibilityDefaults }
  }
}

export const dashboardVisibility = ref(getInitialDashboardVisibility())

function getInitialSidebarCollapsed() {
  if (typeof window === 'undefined') return false
  return window.localStorage.getItem(sidebarCollapsedStorageKey) === 'true'
}

export const sidebarCollapsed = ref(getInitialSidebarCollapsed())

function getInitialDeveloperMode() {
  if (typeof window === 'undefined') return false
  return window.localStorage.getItem(developerModeStorageKey) === 'true'
}

export const developerMode = ref(getInitialDeveloperMode())

function getInitialNavigationVisibility() {
  if (typeof window === 'undefined') return { ...navigationVisibilityDefaults }
  try {
    const value = JSON.parse(window.localStorage.getItem(navigationVisibilityStorageKey) || '{}')
    return navigationVisibilityKeys.reduce((result, key) => {
      result[key] = typeof value[key] === 'boolean' ? value[key] : navigationVisibilityDefaults[key]
      return result
    }, {})
  } catch {
    return { ...navigationVisibilityDefaults }
  }
}

export const navigationVisibility = ref(getInitialNavigationVisibility())

function getInitialNavigationRouteVisibility() {
  if (typeof window === 'undefined') return {}
  try {
    const value = JSON.parse(window.localStorage.getItem(navigationRouteVisibilityStorageKey) || '{}')
    return Object.keys(value).reduce((result, key) => {
      if (typeof value[key] === 'boolean') {
        result[key] = value[key]
      }
      return result
    }, {})
  } catch {
    return {}
  }
}

export const navigationRouteVisibility = ref(getInitialNavigationRouteVisibility())

export function isNavigationRouteVisible(routeKey) {
  return navigationRouteVisibility.value[routeKey] !== false
}

function getInitialUiTheme() {
  if (typeof window === 'undefined') return 'pipecloud'
  const value = window.localStorage.getItem(uiThemeStorageKey)
  return uiThemeOptions.some((item) => item.value === value) ? value : 'pipecloud'
}

export const uiTheme = ref(getInitialUiTheme())

function getInitialUiMessagePosition() {
  if (typeof window === 'undefined') return 'top'
  return window.localStorage.getItem(uiMessagePositionStorageKey) === 'bottom' ? 'bottom' : 'top'
}

export const uiMessagePosition = ref(getInitialUiMessagePosition())

function getInitialLanguage() {
  if (typeof window === 'undefined') return 'zh-CN'
  const value = window.localStorage.getItem(languageStorageKey)
  return languageOptions.some((item) => item.value === value) ? value : 'zh-CN'
}

export const language = ref(getInitialLanguage())

export const currentMessages = computed(() => translations[language.value] || translations['zh-CN'])

export function t(key, ...args) {
  return i18n.global.t(key, ...args)
}

export function setShowRunLog(value) {
  showRunLog.value = Boolean(value)
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(showRunLogStorageKey, showRunLog.value ? 'true' : 'false')
  }
}

export function setHomeComponentVisibility(key, value) {
  if (!homeComponentVisibilityKeys.includes(key)) return
  homeComponentVisibility.value = {
    ...homeComponentVisibility.value,
    [key]: Boolean(value),
  }
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(homeComponentVisibilityStorageKey, JSON.stringify(homeComponentVisibility.value))
  }
}

export function setDashboardVisibility(key, value) {
  if (!dashboardVisibilityKeys.includes(key)) return
  dashboardVisibility.value = { ...dashboardVisibility.value, [key]: Boolean(value) }
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(dashboardVisibilityStorageKey, JSON.stringify(dashboardVisibility.value))
  }
}

export function setSidebarCollapsed(value) {
  sidebarCollapsed.value = Boolean(value)
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(sidebarCollapsedStorageKey, sidebarCollapsed.value ? 'true' : 'false')
  }
}

export function setDeveloperMode(value) {
  developerMode.value = Boolean(value)
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(developerModeStorageKey, developerMode.value ? 'true' : 'false')
  }
}

export function setNavigationVisibility(key, value) {
  if (!navigationVisibilityKeys.includes(key)) return
  navigationVisibility.value = {
    ...navigationVisibility.value,
    [key]: Boolean(value),
  }
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(navigationVisibilityStorageKey, JSON.stringify(navigationVisibility.value))
  }
}

export function setNavigationRouteVisibility(routeKey, value) {
  if (routeKey === '/settings') return
  navigationRouteVisibility.value = {
    ...navigationRouteVisibility.value,
    [routeKey]: Boolean(value),
  }
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(navigationRouteVisibilityStorageKey, JSON.stringify(navigationRouteVisibility.value))
  }
}

export function setUiTheme(value) {
  uiTheme.value = uiThemeOptions.some((item) => item.value === value) ? value : 'pipecloud'
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(uiThemeStorageKey, uiTheme.value)
  }
}

export function setUiMessagePosition(value) {
  uiMessagePosition.value = value === 'bottom' ? 'bottom' : 'top'
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(uiMessagePositionStorageKey, uiMessagePosition.value)
  }
}

export function setLanguage(value) {
  language.value = setI18nLocale(value)
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(languageStorageKey, language.value)
  }
}

export function formatTime(timestamp) {
  if (!timestamp) return t('notGenerated')
  return new Date(timestamp * 1000).toLocaleString(language.value, { hour12: false })
}

export function formatSize(size) {
  if (!size) return '-'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

export function displayDataPath(path, fallback = '') {
  const value = String(path || '').trim()
  return value.toLowerCase().startsWith('database://') ? fallback : value
}

export async function loadSummary(options = {}) {
  const requestOptions = options?.signal ? options : {}
  const requestId = ++summaryRequestId
  loading.value = true
  errorMessage.value = ''
  try {
    const payload = await fetchSummary(selectedProjectParams(), requestOptions)
    if (requestOptions.signal?.aborted || requestId !== summaryRequestId) return
    summary.value = payload
  } catch (error) {
    if (error?.name === 'AbortError' || requestId !== summaryRequestId) return
    errorMessage.value = t('backendStatusReadFailed', { message: error.message })
  } finally {
    if (requestId === summaryRequestId) {
      loading.value = false
    }
  }
}

export async function runAction(actionKey, options = {}) {
  if (runningKey.value) return false
  runningKey.value = actionKey
  errorMessage.value = ''
  try {
    await ensureSelectedProject()
    runningActionController = new AbortController()
    const actionOptions = { ...options }
    if (actionKey === 'prefab-weld-library') {
      initializationTaskId.value = globalThis.crypto?.randomUUID?.() || `initialization-${Date.now()}`
      actionOptions.taskId = initializationTaskId.value
    }
    const payload = await runWorkflowAction(
      actionKey,
      selectedProjectParams(),
      actionOptions,
      { signal: runningActionController.signal },
    )
    lastRun.value = payload
    if (!payload.ok) {
      const detail = payload.stderr || payload.stdout || t('scriptReturnedCode', { code: payload.returnCode })
      throw new Error(detail)
    }
    summary.value.modules = payload.summary
    return true
  } catch (error) {
    const payload = error.payload || {}
    const action = summary.value.actions.find((item) => item.key === actionKey)
    lastRun.value = {
      key: payload.key || actionKey,
      name: payload.name || action?.name || actionKey,
      ok: false,
      returnCode: payload.returnCode ?? 1,
      stdout: payload.stdout || '',
      stderr: payload.stderr || payload.error || error.message,
      summary: payload.summary || summary.value.modules,
    }
    if (payload.summary) {
      summary.value.modules = payload.summary
    }
    errorMessage.value = t('actionRunFailed', { message: error.message })
    return true
  } finally {
    runningActionController = null
    initializationTaskId.value = ''
    runningKey.value = ''
  }
}

export async function cancelRunningInitialization() {
  const taskId = initializationTaskId.value
  if (!taskId || runningKey.value !== 'prefab-weld-library') return false
  try {
    await cancelInitializationTask(taskId)
  } finally {
    runningActionController?.abort()
  }
  return true
}

export function beaconCancelRunningInitialization() {
  const taskId = initializationTaskId.value
  if (!taskId || typeof navigator === 'undefined') return false
  return navigator.sendBeacon(
    '/api/pipecloud/initialization/cancel/',
    new Blob([JSON.stringify({ taskId })], { type: 'application/json' }),
  )
}
