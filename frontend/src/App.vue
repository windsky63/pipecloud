<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useLocale, useTheme } from 'vuetify'
import AppSidebar from './components/AppSidebar.vue'
import UiMessageCenter from './components/UiMessageCenter.vue'
import {
  language,
  lastRun,
  loadSummary,
  showRunLog,
  summary,
  t,
  uiTheme,
} from './services/pipecloudState'
import { projectGateMessage, selectedProjectId } from './services/projectState'
import { loadLibraries } from './services/weldLibraryState'
import { clearUiMessages, publishUiMessage, uiMessageHistory } from './services/uiMessages'

const vuetifyTheme = useTheme()
const vuetifyLocale = useLocale()
const runLogCollapsedStorageKey = 'pipecloud.runLogCollapsed'
const runLogTogglePositionStorageKey = 'pipecloud.runLogTogglePosition'
const runLogToggleSize = 42
const runLogCollapsed = ref(
  typeof window === 'undefined'
    ? false
    : window.localStorage.getItem(runLogCollapsedStorageKey) === 'true',
)
const runLogTogglePosition = ref(readRunLogTogglePosition())
let runLogDragState = null
let suppressRunLogToggleClick = false
const runLogText = computed(() => {
  if (!lastRun.value) return t('runLogEmpty')
  return [lastRun.value.stdout, lastRun.value.stderr].filter(Boolean).join('\n') || t('runLogNoOutput')
})
const runLogMeta = computed(() => {
  if (!lastRun.value) return t('runLogNotRun')
  return t('runLogMeta', { name: lastRun.value.name, code: lastRun.value.returnCode })
})
const runLogToggleStyle = computed(() => {
  if (!runLogTogglePosition.value) {
    return { right: '24px', bottom: '24px' }
  }
  return {
    left: `${runLogTogglePosition.value.x}px`,
    top: `${runLogTogglePosition.value.y}px`,
  }
})

function readRunLogTogglePosition() {
  if (typeof window === 'undefined') return null
  try {
    const value = JSON.parse(window.localStorage.getItem(runLogTogglePositionStorageKey) || 'null')
    if (typeof value?.x === 'number' && typeof value?.y === 'number') {
      return value
    }
  } catch {
    return null
  }
  return null
}

function clampRunLogTogglePosition(x, y) {
  if (typeof window === 'undefined') return { x, y }
  const margin = 8
  return {
    x: Math.max(margin, Math.min(x, window.innerWidth - runLogToggleSize - margin)),
    y: Math.max(margin, Math.min(y, window.innerHeight - runLogToggleSize - margin)),
  }
}

function persistRunLogTogglePosition() {
  if (typeof window === 'undefined' || !runLogTogglePosition.value) return
  window.localStorage.setItem(runLogTogglePositionStorageKey, JSON.stringify(runLogTogglePosition.value))
}

function startRunLogToggleDrag(event) {
  if (event.button !== undefined && event.button !== 0) return
  const rect = event.currentTarget.getBoundingClientRect()
  runLogDragState = {
    offsetX: event.clientX - rect.left,
    offsetY: event.clientY - rect.top,
    startX: event.clientX,
    startY: event.clientY,
    moved: false,
  }
  window.addEventListener('pointermove', moveRunLogToggle)
  window.addEventListener('pointerup', stopRunLogToggleDrag, { once: true })
}

function moveRunLogToggle(event) {
  if (!runLogDragState) return
  const nextPosition = clampRunLogTogglePosition(
    event.clientX - runLogDragState.offsetX,
    event.clientY - runLogDragState.offsetY,
  )
  runLogTogglePosition.value = nextPosition
  const distance = Math.hypot(event.clientX - runLogDragState.startX, event.clientY - runLogDragState.startY)
  if (distance > 4) {
    runLogDragState.moved = true
  }
}

function stopRunLogToggleDrag() {
  if (!runLogDragState) return
  suppressRunLogToggleClick = runLogDragState.moved
  if (runLogDragState.moved) {
    persistRunLogTogglePosition()
  }
  runLogDragState = null
  window.removeEventListener('pointermove', moveRunLogToggle)
}

function openRunLogFromToggle() {
  if (suppressRunLogToggleClick) {
    suppressRunLogToggleClick = false
    return
  }
  runLogCollapsed.value = false
}

watch(runLogCollapsed, (value) => {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(runLogCollapsedStorageKey, value ? 'true' : 'false')
  }
})

watch(uiTheme, (themeName) => {
  vuetifyTheme.global.name.value = themeName
  document.documentElement.dataset.theme = themeName === 'pipecloudDark'
    ? 'dark'
    : themeName === 'pipecloudGray'
      ? 'gray'
      : 'light'
}, { immediate: true })

watch(language, (locale) => {
  document.documentElement.lang = locale
  vuetifyLocale.current.value = locale === 'zh-CN' ? 'zhHans' : 'en'
}, { immediate: true })

watch(selectedProjectId, async (projectId) => {
  await loadLibraries()
  if (!projectId) return
  await loadSummary()
})

watch(projectGateMessage, (message) => {
  publishUiMessage('project-gate', 'warning', message)
}, { immediate: true })

onMounted(() => {
  if (!summary.value.modules.length) {
    loadSummary()
  }
  if (selectedProjectId.value) {
    loadLibraries()
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('pointermove', moveRunLogToggle)
})
</script>

<template>
  <v-app>
    <UiMessageCenter />
    <v-layout class="app-shell">
      <AppSidebar />

      <v-main class="workspace">
        <div class="workspace-content">
          <router-view />
        </div>
      </v-main>

      <template v-if="showRunLog">
        <v-btn
          v-if="runLogCollapsed"
          class="run-log-toggle"
          :style="runLogToggleStyle"
          icon="mdi-console-line"
          color="primary"
          variant="flat"
          size="42"
          rounded="circle"
          :aria-label="t('expandRunLog')"
          @pointerdown="startRunLogToggleDrag"
          @click="openRunLogFromToggle"
        />
        <v-navigation-drawer
          v-else
          class="global-run-log"
          location="right"
          temporary
          :model-value="true"
          width="420"
          :scrim="false"
          @update:model-value="runLogCollapsed = true"
        >
          <div class="run-log-panel">
            <div class="run-log-head">
              <div>
                <h2>{{ t('runLog') }}</h2>
                <span>{{ runLogMeta }}</span>
              </div>
              <v-btn
                icon="mdi-chevron-right"
                variant="text"
                :aria-label="t('collapseRunLog')"
                @click="runLogCollapsed = true"
              />
            </div>
            <section class="run-log-section run-log-messages">
              <div class="run-log-section-head">
                <strong>{{ t('messageCenter') }}</strong>
                <v-btn
                  v-if="uiMessageHistory.length"
                  size="x-small"
                  variant="text"
                  prepend-icon="mdi-delete-sweep-outline"
                  @click="clearUiMessages"
                >
                  {{ t('clearMessages') }}
                </v-btn>
              </div>
              <div v-if="uiMessageHistory.length" class="run-log-message-list">
                <div v-for="message in uiMessageHistory" :key="message.id" :class="['run-log-message', `is-${message.type}`]">
                  <v-icon :icon="message.type === 'error' ? 'mdi-alert-circle-outline' : message.type === 'warning' ? 'mdi-alert-outline' : message.type === 'success' ? 'mdi-check-circle-outline' : 'mdi-information-outline'" size="16" />
                  <span>{{ message.text }}</span>
                  <time>{{ new Date(message.timestamp).toLocaleTimeString(language, { hour12: false }) }}</time>
                </div>
              </div>
              <div v-else class="run-log-message-empty">{{ t('noMessages') }}</div>
            </section>
            <section class="run-log-section run-log-backend">
              <div class="run-log-section-head">
                <strong>{{ t('backendMessages') }}</strong>
              </div>
              <pre>{{ runLogText }}</pre>
            </section>
          </div>
        </v-navigation-drawer>
      </template>

    </v-layout>
  </v-app>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: var(--soft);
}

.workspace {
  background: var(--soft);
}

.workspace-content {
  padding: 24px;
}

.global-run-log {
  position: fixed !important;
  top: 0 !important;
  right: 0 !important;
  bottom: 0 !important;
  height: 100dvh !important;
  max-height: 100dvh !important;
  border-left: 1px solid var(--line);
  background: var(--panel);
}

.global-run-log :deep(.v-navigation-drawer__content) {
  height: 100%;
  overflow: hidden;
}

.run-log-toggle {
  position: fixed;
  z-index: 1200;
  opacity: .8;
  width: 42px;
  height: 42px;
  min-width: 42px;
  border-radius: 50% !important;
  box-shadow: 0 12px 28px rgba(15, 23, 42, .18);
  cursor: grab;
  touch-action: none;
  user-select: none;
}

.run-log-toggle:active {
  cursor: grabbing;
}

.run-log-panel {
  display: grid;
  grid-template-rows: auto repeat(2, minmax(0, 1fr));
  gap: 12px;
  height: 100%;
  padding: 16px;
  background: var(--panel);
}

.run-log-section {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--soft);
}

.run-log-section-head {
  display: flex;
  min-height: 38px;
  padding: 5px 8px 5px 12px;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--line);
  color: var(--strong);
  font-size: 13px;
}

.run-log-message-list {
  display: grid;
  gap: 7px;
  padding: 8px;
  overflow-y: auto;
}

.run-log-message {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) auto;
  gap: 7px;
  align-items: start;
  padding: 8px;
  border-left: 3px solid #64748b;
  border-radius: 5px;
  background: var(--panel);
  color: var(--text);
  font-size: 12px;
}

.run-log-message.is-error { border-left-color: #dc2626; }
.run-log-message.is-warning { border-left-color: #d97706; }
.run-log-message.is-success { border-left-color: #16a34a; }
.run-log-message.is-info { border-left-color: #2563eb; }

.run-log-message span {
  line-height: 1.45;
}

.run-log-message time {
  color: var(--muted);
  font-size: 10px;
}

.run-log-message-empty {
  display: grid;
  min-height: 72px;
  place-items: center;
  color: var(--muted);
  font-size: 12px;
}

.run-log-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.run-log-head h2 {
  margin: 0 0 4px;
  color: var(--strong);
  font-size: 18px;
}

.run-log-head span {
  color: var(--muted);
  font-size: 12px;
}

.run-log-backend pre {
  min-height: 0;
  margin: 0;
  overflow: auto;
  padding: 14px;
  background: #111827;
  color: #d1fae5;
  font-family: Consolas, "Courier New", monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
}
</style>
