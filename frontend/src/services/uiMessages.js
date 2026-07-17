import { computed, ref } from 'vue'

const MAX_MESSAGES = 80
const MESSAGE_TIMEOUT = 10_000
let nextMessageId = 0
const dismissalTimers = new Map()

// The history is session-only on purpose: it survives toast dismissal and route
// changes, but a page close/reload starts a clean run log.
export const uiMessageHistory = ref([])
const transientUiMessages = ref([])
export const activeUiMessages = computed(() => transientUiMessages.value)

function clearDismissalTimer(id) {
  const timer = dismissalTimers.get(id)
  if (timer) globalThis.clearTimeout(timer)
  dismissalTimers.delete(id)
}

function removeTransientMessage(id) {
  clearDismissalTimer(id)
  transientUiMessages.value = transientUiMessages.value.filter((item) => item.id !== id)
}

export function publishUiMessage(key, type, text) {
  const normalized = String(text || '').trim()
  const source = String(key || normalized || Date.now())
  if (!normalized) return null

  const message = {
    id: `${Date.now()}-${nextMessageId += 1}`,
    source,
    type: ['error', 'warning', 'success', 'info'].includes(type) ? type : 'info',
    text: normalized,
    timestamp: Date.now(),
  }
  transientUiMessages.value.unshift(message)
  uiMessageHistory.value.unshift(message)
  uiMessageHistory.value = uiMessageHistory.value.slice(0, MAX_MESSAGES)
  dismissalTimers.set(message.id, globalThis.setTimeout(() => {
    removeTransientMessage(message.id)
  }, MESSAGE_TIMEOUT))
  return message.id
}

export function dismissUiMessage(id) {
  removeTransientMessage(id)
}

export function clearUiMessages() {
  dismissalTimers.forEach((timer) => globalThis.clearTimeout(timer))
  dismissalTimers.clear()
  transientUiMessages.value = []
  uiMessageHistory.value = []
}
