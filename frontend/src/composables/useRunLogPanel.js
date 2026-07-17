import { computed, onBeforeUnmount, ref, watch } from 'vue'

const COLLAPSED_STORAGE_KEY = 'pipecloud.runLogCollapsed'
const POSITION_STORAGE_KEY = 'pipecloud.runLogTogglePosition'
const TOGGLE_SIZE = 42
const VIEWPORT_MARGIN = 8

function readStoredPosition() {
  if (typeof window === 'undefined') return null
  try {
    const value = JSON.parse(window.localStorage.getItem(POSITION_STORAGE_KEY) || 'null')
    if (Number.isFinite(value?.x) && Number.isFinite(value?.y)) return value
  } catch {
    // 损坏的浏览器缓存不应阻止应用启动，回退到右下角默认位置。
  }
  return null
}

function clampToViewport(x, y) {
  if (typeof window === 'undefined') return { x, y }
  return {
    x: Math.max(VIEWPORT_MARGIN, Math.min(x, window.innerWidth - TOGGLE_SIZE - VIEWPORT_MARGIN)),
    y: Math.max(VIEWPORT_MARGIN, Math.min(y, window.innerHeight - TOGGLE_SIZE - VIEWPORT_MARGIN)),
  }
}

/**
 * 管理运行日志抽屉的折叠状态和悬浮按钮拖拽行为。
 * 拖拽状态使用普通变量保存，避免高频 pointermove 产生不必要的深层响应式开销。
 */
export function useRunLogPanel() {
  const runLogCollapsed = ref(
    typeof window !== 'undefined'
      && window.localStorage.getItem(COLLAPSED_STORAGE_KEY) === 'true',
  )
  const togglePosition = ref(readStoredPosition())
  let dragState = null
  let suppressNextClick = false

  const runLogToggleStyle = computed(() => (
    togglePosition.value
      ? { left: `${togglePosition.value.x}px`, top: `${togglePosition.value.y}px` }
      : { right: '24px', bottom: '24px' }
  ))

  function startRunLogToggleDrag(event) {
    if (event.button !== undefined && event.button !== 0) return
    const rect = event.currentTarget.getBoundingClientRect()
    dragState = {
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
    if (!dragState) return
    togglePosition.value = clampToViewport(
      event.clientX - dragState.offsetX,
      event.clientY - dragState.offsetY,
    )
    if (Math.hypot(event.clientX - dragState.startX, event.clientY - dragState.startY) > 4) {
      dragState.moved = true
    }
  }

  function stopRunLogToggleDrag() {
    if (!dragState) return
    suppressNextClick = dragState.moved
    if (dragState.moved) {
      window.localStorage.setItem(POSITION_STORAGE_KEY, JSON.stringify(togglePosition.value))
    }
    dragState = null
    window.removeEventListener('pointermove', moveRunLogToggle)
  }

  function openRunLogFromToggle() {
    // pointerup 后浏览器仍会触发 click；拖拽结束时必须吞掉这一次点击。
    if (suppressNextClick) {
      suppressNextClick = false
      return
    }
    runLogCollapsed.value = false
  }

  watch(runLogCollapsed, (value) => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(COLLAPSED_STORAGE_KEY, String(value))
    }
  })

  onBeforeUnmount(() => {
    window.removeEventListener('pointermove', moveRunLogToggle)
  })

  return {
    runLogCollapsed,
    runLogToggleStyle,
    startRunLogToggleDrag,
    openRunLogFromToggle,
  }
}
