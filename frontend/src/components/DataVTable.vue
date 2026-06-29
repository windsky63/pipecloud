<script setup>
import * as VTable from '@visactor/vtable'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { t } from '../services/pipecloudState'
import { getBasicVTableTheme, vTableThemeKey } from '../services/vtableTheme'

const props = defineProps({
  records: {
    type: Array,
    default: () => [],
  },
  columns: {
    type: Array,
    default: () => [],
  },
  height: {
    type: [Number, String],
    default: 360,
  },
  emptyText: {
    type: String,
    default: '',
  },
})

const tableHost = ref(null)
const tableWidth = ref(0)
const resolvedEmptyText = computed(() => props.emptyText || t('noData'))
let tableInstance = null
let resizeObserver = null

function releaseTable() {
  if (tableInstance) {
    tableInstance.release()
    tableInstance = null
  }
}

function getColumnBaseWidth(column) {
  return Number(column.width || column.minWidth || 160)
}

function getResolvedColumns() {
  const columns = props.columns.map((column) => ({
    ...column,
    width: getColumnBaseWidth(column),
  }))
  const availableWidth = Math.floor(tableWidth.value)
  const totalWidth = columns.reduce((total, column) => total + getColumnBaseWidth(column), 0)

  if (!columns.length || !availableWidth || totalWidth >= availableWidth) return columns

  let usedWidth = 0
  return columns.map((column, index) => {
    const isLast = index === columns.length - 1
    const baseWidth = getColumnBaseWidth(column)
    const width = isLast ? availableWidth - usedWidth : Math.floor((baseWidth / totalWidth) * availableWidth)
    usedWidth += width
    return {
      ...column,
      width: Math.max(width, baseWidth),
    }
  })
}

function tableOptions() {
  return {
    records: props.records,
    columns: getResolvedColumns(),
    widthMode: 'standard',
    heightMode: 'standard',
    defaultRowHeight: 38,
    defaultHeaderRowHeight: 40,
    autoWrapText: false,
    tooltip: {
      isShowOverflowTextTooltip: true,
    },
    theme: getBasicVTableTheme(),
  }
}

async function renderTable() {
  await nextTick()
  if (!tableHost.value || !props.columns.length) {
    releaseTable()
    return
  }
  tableWidth.value = tableHost.value.clientWidth

  if (tableInstance) {
    await tableInstance.updateOption(tableOptions(), {
      clearColWidthCache: true,
      clearRowHeightCache: true,
    })
    return
  }

  tableInstance = new VTable.ListTable(tableHost.value, tableOptions())
}

function setupResizeObserver() {
  if (resizeObserver || !tableHost.value) return
  resizeObserver = new ResizeObserver(() => {
    tableWidth.value = tableHost.value?.clientWidth || 0
    if (tableInstance) {
      tableInstance.updateOption(tableOptions(), {
        clearColWidthCache: true,
        clearRowHeightCache: true,
      })
    } else {
      renderTable()
    }
  })
  resizeObserver.observe(tableHost.value)
}

onMounted(async () => {
  await renderTable()
  setupResizeObserver()
})

watch(
  () => [props.records, props.columns, vTableThemeKey.value],
  () => {
    renderTable()
  },
  { deep: true },
)

onBeforeUnmount(() => {
  releaseTable()
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
})
</script>

<template>
  <div
    class="data-vtable-wrap"
    :style="{ height: typeof height === 'number' ? `${height}px` : height }"
    @wheel.stop
    @touchmove.stop
  >
    <div ref="tableHost" class="data-vtable-host" />
    <div v-if="!records.length" class="data-vtable-empty">{{ resolvedEmptyText }}</div>
  </div>
</template>

<style scoped>
.data-vtable-wrap {
  position: relative;
  width: 100%;
  min-height: 180px;
  overflow: hidden;
  overscroll-behavior: contain;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .7);
}

html[data-theme="dark"] .data-vtable-wrap {
  border-color: #374151;
  background: #111827;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .04);
}

.data-vtable-host {
  width: 100%;
  height: 100%;
  scrollbar-color: var(--scrollbar-thumb) var(--scrollbar-track);
  scrollbar-width: thin;
}

.data-vtable-host :deep(*) {
  scrollbar-color: var(--scrollbar-thumb) var(--scrollbar-track);
  scrollbar-width: thin;
}

.data-vtable-host :deep(*::-webkit-scrollbar) {
  width: 10px;
  height: 10px;
}

.data-vtable-host :deep(*::-webkit-scrollbar-thumb) {
  border: 2px solid transparent;
  border-radius: 999px;
  background: var(--scrollbar-thumb);
  background-clip: padding-box;
}

.data-vtable-host :deep(*::-webkit-scrollbar-thumb:hover) {
  background: var(--scrollbar-thumb-hover);
  background-clip: padding-box;
}

.data-vtable-host :deep(*::-webkit-scrollbar-track),
.data-vtable-host :deep(*::-webkit-scrollbar-corner) {
  background: var(--scrollbar-track);
}

.data-vtable-empty {
  position: absolute;
  top: 50%;
  left: 50%;
  padding: 10px 14px;
  border: 1px dashed var(--line);
  border-radius: 6px;
  background: var(--panel-soft);
  color: var(--muted);
  font-size: 13px;
  pointer-events: none;
  transform: translate(-50%, -50%);
}

html[data-theme="dark"] .data-vtable-empty {
  border-color: #374151;
  background: #1f2937;
  color: #9ca3af;
}
</style>
