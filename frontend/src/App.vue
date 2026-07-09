<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useTheme } from 'vuetify'
import AppSidebar from './components/AppSidebar.vue'
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

const vuetifyTheme = useTheme()
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
const projectGateVisible = computed({
  get: () => Boolean(projectGateMessage.value),
  set: (value) => {
    if (!value) {
      projectGateMessage.value = ''
    }
  },
})
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
}, { immediate: true })

watch(selectedProjectId, async (projectId) => {
  await loadLibraries()
  if (!projectId) return
  await loadSummary()
})

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
            <pre>{{ runLogText }}</pre>
          </div>
        </v-navigation-drawer>
      </template>

      <v-snackbar v-model="projectGateVisible" color="warning" timeout="2600">
        {{ projectGateMessage }}
      </v-snackbar>
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
  grid-template-rows: auto minmax(0, 1fr);
  height: 100%;
  padding: 16px;
  background: var(--panel);
}

.run-log-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
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

.run-log-panel pre {
  min-height: 0;
  margin: 0;
  overflow: auto;
  padding: 14px;
  border-radius: 6px;
  background: #111827;
  color: #d1fae5;
  font-family: Consolas, "Courier New", monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
}
</style>
