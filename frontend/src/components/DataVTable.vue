<script setup>
import * as VTable from '@visactor/vtable'
import { FilterPlugin } from '@visactor/vtable-plugins'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { t } from '../services/pipecloudState'
import { getBasicVTableTheme, vTableThemeKey } from '../services/vtableTheme'
import { attachVTableColumnSelectionCount, createVTableSelectionLayout } from '../services/vtableSelectionCount'

const ROW_KEY_FIELD = '__dataVTableRowKey'
const SELECT_FIELD = '__dataVTableSelected'

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
  filterable: {
    type: Boolean,
    default: false,
  },
  selectable: {
    type: Boolean,
    default: false,
  },
  rowKey: {
    type: String,
    default: '',
  },
})
const emit = defineEmits(['selection-change'])

const tableHost = ref(null)
const tableWidth = ref(0)
const selectedKeys = ref(new Set())
const resolvedEmptyText = computed(() => props.emptyText || t('noData'))
const preparedRecords = computed(() => props.records.map((record, index) => ({
  ...record,
  [ROW_KEY_FIELD]: getRecordStableKey(record, index),
  [SELECT_FIELD]: selectedKeys.value.has(getRecordStableKey(record, index)),
})))
let tableInstance = null
let resizeObserver = null
let releaseSelectionCount = null

function releaseTable() {
  if (tableInstance) {
    tableInstance.release()
    tableInstance = null
  }
  releaseSelectionCount?.()
  releaseSelectionCount = null
}

function getColumnBaseWidth(column) {
  return Number(column.width || column.minWidth || 160)
}

function getRecordStableKey(record, index) {
  if (props.rowKey && record?.[props.rowKey] !== undefined && record?.[props.rowKey] !== null) {
    return String(record[props.rowKey])
  }
  return String(index)
}

function getRecordKey(record) {
  if (!record) return ''
  return String(record[ROW_KEY_FIELD] ?? '')
}

function selectedPayload() {
  const rows = preparedRecords.value.filter((record) => selectedKeys.value.has(getRecordKey(record)))
  return {
    keys: rows.map((record) => getRecordKey(record)),
    rows: rows.map(({ [ROW_KEY_FIELD]: _rowKey, [SELECT_FIELD]: _selected, ...record }) => record),
  }
}

function createFilterPlugin() {
  return new FilterPlugin({
    filterModes: ['byValue'],
    defaultEnabled: true,
  })
}

function getRecordFromCell(col, row, table = tableInstance) {
  if (!table || row < (table.columnHeaderLevelCount || 1)) return null
  const record = table.getCellOriginRecord?.(col, row) || table.getCellRawRecord?.(col, row)
  if (Array.isArray(record)) return record[0] || null
  return record || null
}

function getVisibleRecords() {
  if (!tableInstance) return preparedRecords.value
  const headerRows = Math.max(Number(tableInstance.columnHeaderLevelCount) || 1, 1)
  const bodyCol = props.selectable && tableInstance.colCount > 1 ? 1 : 0
  const records = []
  const usedKeys = new Set()

  for (let row = headerRows; row < tableInstance.rowCount; row += 1) {
    const record = getRecordFromCell(bodyCol, row) || getRecordFromCell(0, row)
    const key = getRecordKey(record)
    if (!key || usedKeys.has(key)) continue
    usedKeys.add(key)
    records.push(record)
  }

  return records.length ? records : preparedRecords.value
}

function areAllVisibleRowsSelected() {
  const records = getVisibleRecords()
  return records.length > 0 && records.every((record) => selectedKeys.value.has(getRecordKey(record)))
}

function setTableRowCheckedState(row, checked) {
  tableInstance?.stateManager?.setCheckedState?.(0, row, SELECT_FIELD, checked)
}

function setTableHeaderCheckedState(checked) {
  tableInstance?.stateManager?.setHeaderCheckedState?.(SELECT_FIELD, checked)
}

function updateCheckboxCellGraphic(row, checked) {
  const cell = tableInstance?.scenegraph?.getCell?.(0, row)
  if (!cell?.forEachChildren) return false
  let updated = false
  cell.forEachChildren((child) => {
    if (child?.name !== 'checkbox') return
    child.setAttributes({
      checked,
      indeterminate: false,
    })
    updated = true
  })
  return updated
}

function refreshSelectionCells() {
  if (!tableInstance) return
  const headerRows = Math.max(Number(tableInstance.columnHeaderLevelCount) || 1, 1)
  const allVisibleSelected = areAllVisibleRowsSelected()
  setTableHeaderCheckedState(allVisibleSelected)
  updateCheckboxCellGraphic(0, allVisibleSelected)
  for (let row = headerRows; row < tableInstance.rowCount; row += 1) {
    const record = getRecordFromCell(tableInstance.colCount > 1 ? 1 : 0, row) || getRecordFromCell(0, row)
    const checked = selectedKeys.value.has(getRecordKey(record))
    setTableRowCheckedState(row, checked)
    updateCheckboxCellGraphic(row, checked)
  }
  tableInstance.scenegraph?.updateNextFrame?.()
  tableInstance.scenegraph?.renderSceneGraph?.()
}

function toggleVisibleRows(checked) {
  const nextKeys = new Set(selectedKeys.value)
  getVisibleRecords().forEach((record) => {
    const key = getRecordKey(record)
    if (!key) return
    if (checked) nextKeys.add(key)
    else nextKeys.delete(key)
    record[SELECT_FIELD] = checked
  })
  selectedKeys.value = nextKeys
  refreshSelectionCells()
}

function handleCheckboxStateChange(event = {}) {
  if (!props.selectable || event.col !== 0) return
  const headerRows = Math.max(Number(tableInstance?.columnHeaderLevelCount) || 1, 1)
  if (event.row < headerRows) {
    toggleVisibleRows(Boolean(event.checked))
    return
  }

  const fallbackCol = Math.min(1, Math.max((tableInstance?.colCount || 1) - 1, 0))
  const record = getRecordFromCell(event.col, event.row) || getRecordFromCell(fallbackCol, event.row)
  const key = getRecordKey(record)
  if (!key) return

  const nextKeys = new Set(selectedKeys.value)
  const nextChecked = Boolean(event.checked)
  if (nextChecked) nextKeys.add(key)
  else nextKeys.delete(key)
  record[SELECT_FIELD] = nextChecked
  selectedKeys.value = nextKeys
  setTableRowCheckedState(event.row, nextChecked)
  setTableHeaderCheckedState(areAllVisibleRowsSelected())
  updateCheckboxCellGraphic(event.row, nextChecked)
  updateCheckboxCellGraphic(0, areAllVisibleRowsSelected())
  tableInstance?.scenegraph?.updateNextFrame?.()
}

function bindTableEvents() {
  if (!tableInstance || !props.selectable) return
  tableInstance.on(tableInstance.constructor.EVENT_TYPE.CHECKBOX_STATE_CHANGE, handleCheckboxStateChange)
}

function getResolvedColumns() {
  const columns = props.columns.map((column) => ({
    ...column,
    width: getColumnBaseWidth(column),
    filter: props.filterable ? column.filter !== false : column.filter,
  }))
  const availableWidth = Math.floor(tableWidth.value)
  const totalWidth = columns.reduce((total, column) => total + getColumnBaseWidth(column), 0)

  const sizedColumns = (() => {
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
  })()

  if (!props.selectable) return sizedColumns

  return [
    {
      field: SELECT_FIELD,
      title: '',
      width: 46,
      minWidth: 46,
      maxWidth: 46,
      cellType: 'checkbox',
      headerType: 'checkbox',
      checked: (args = {}) => {
        const headerRows = Math.max(Number(args.table?.columnHeaderLevelCount) || 1, 1)
        if (args.row < headerRows) return areAllVisibleRowsSelected()
        const dataCol = args.table?.colCount > 1 ? 1 : 0
        const record = getRecordFromCell(dataCol, args.row, args.table) || getRecordFromCell(args.col, args.row, args.table)
        return selectedKeys.value.has(getRecordKey(record))
      },
      disable: false,
      filter: false,
      style: {
        textAlign: 'center',
      },
      headerStyle: {
        textAlign: 'center',
      },
    },
    ...sizedColumns,
  ]
}

function tableOptions() {
  return {
    records: props.selectable ? preparedRecords.value : props.records,
    columns: getResolvedColumns(),
    plugins: props.filterable ? [createFilterPlugin()] : [],
    widthMode: 'standard',
    heightMode: 'standard',
    defaultRowHeight: 38,
    defaultHeaderRowHeight: 40,
    enableHeaderCheckboxCascade: false,
    enableCheckboxCascade: false,
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

  const selectionLayout = createVTableSelectionLayout(tableHost.value)
  tableInstance = new VTable.ListTable(selectionLayout.viewport, tableOptions())
  bindTableEvents()
  releaseSelectionCount = attachVTableColumnSelectionCount(tableInstance, selectionLayout)
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
  () => [props.records, props.columns, props.filterable, props.selectable, props.rowKey, vTableThemeKey.value],
  () => {
    renderTable()
  },
  { deep: true },
)

watch(
  preparedRecords,
  (records) => {
    const availableKeys = new Set(records.map((record) => getRecordKey(record)))
    const nextKeys = new Set(Array.from(selectedKeys.value).filter((key) => availableKeys.has(key)))
    if (nextKeys.size !== selectedKeys.value.size) selectedKeys.value = nextKeys
  },
  { deep: true },
)

watch(
  selectedKeys,
  () => {
    emit('selection-change', selectedPayload())
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
