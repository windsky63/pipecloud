<script setup>
import * as VTable from '@visactor/vtable'
import { InputEditor } from '@visactor/vtable-editors'
import { FilterPlugin } from '@visactor/vtable-plugins'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { fetchLibraryRows, saveLibraryRows } from '../../api/libraries'
import WeldLibraryHeader from './WeldLibraryHeader.vue'
import UnsavedChangesDialog from '../../components/UnsavedChangesDialog.vue'
import { clearLibraryError, libraries, libraryError, libraryLoading, loadLibraries } from '../../services/weldLibraryState'
import { formatTime, t } from '../../services/pipecloudState'
import { selectedProjectId, selectedProjectParams } from '../../services/projectState'
import { getBasicVTableTheme, vTableThemeKey } from '../../services/vtableTheme'
import { attachVTableColumnSelectionCount, createVTableSelectionLayout } from '../../services/vtableSelectionCount'

const ROW_KEY_FIELD = '__libraryRowKey'
const SELECT_FIELD = '__libraryRowSelected'
const DELETE_FIELD = '__libraryRowDeleted'
const COMMON_FIELD_COLUMNS = new Set([
  '壁厚',
  '壁厚号',
  '寸径',
  '外径',
  '材质',
  '材质代号',
  '材料代号1',
  '材料代号2',
  '材料唯一码1',
  '材料唯一码2',
  '材料代码1',
  '材料代码2',
  '材料油漆1',
  '材料油漆2',
  '数量1',
  '数量2',
  '单位1',
  '单位2',
  '描述1',
  '描述2',
])
const SOURCE_STYLES = {
  primary: {
    key: 'primary',
    labelKey: 'primaryKey',
    order: 0,
    chipColor: 'warning',
    chipVariant: 'flat',
    headerBg: '#fef3c7',
    headerColor: '#92400e',
  },
  common: {
    key: 'common',
    labelKey: 'commonTable',
    order: 1,
    chipColor: 'teal',
    chipVariant: 'flat',
    headerBg: '#ccfbf1',
    headerColor: '#0f766e',
  },
  status: {
    key: 'status',
    labelKey: 'statusTable',
    order: 2,
    chipColor: 'info',
    chipVariant: 'flat',
    headerBg: '#eff6ff',
    headerColor: '#1d4ed8',
  },
  antiCorrosionStage: {
    key: 'antiCorrosionStage',
    labelKey: 'antiCorrosionStage',
    order: 3,
    chipColor: 'success',
    chipVariant: 'flat',
    headerBg: '#ecfdf5',
    headerColor: '#047857',
  },
  cuttingStage: {
    key: 'cuttingStage',
    labelKey: 'cuttingStage',
    order: 4,
    chipColor: 'deep-orange',
    chipVariant: 'flat',
    headerBg: '#fff7ed',
    headerColor: '#c2410c',
  },
  weldingStage: {
    key: 'weldingStage',
    labelKey: 'weldingStage',
    order: 5,
    chipColor: 'deep-purple',
    chipVariant: 'flat',
    headerBg: '#f5f3ff',
    headerColor: '#6d28d9',
  },
  table: {
    key: 'table',
    labelKey: 'currentTable',
    order: 10,
    chipColor: 'secondary',
    chipVariant: 'tonal',
    headerBg: '#f8fafc',
    headerColor: '#334155',
  },
}

const route = useRoute()
const router = useRouter()

const tableLoading = ref(false)
const tableError = ref('')
const tableRows = ref([])
const columns = ref([])
const primaryKeyColumns = ref([])
const readonlyColumns = ref([])
const stageColumns = ref([])
const statusColumns = ref([])
const visibleColumnKeys = ref([])
const columnSelectMenuOpen = ref(false)
const total = ref(0)
const dirty = ref(false)
const saving = ref(false)
const batchColumn = ref('')
const batchValue = ref('')
const undoStack = ref([])
const selectedRowKeys = ref(new Set())
const deletedRowKeys = ref(new Set())
const tableContainer = ref(null)
const snackbar = ref({
  show: false,
  text: '',
  color: 'success',
})
const confirmDialog = ref({
  show: false,
  title: '',
  text: '',
  confirmText: t('confirm'),
  color: 'primary',
  resolve: null,
})
const unsavedChangesDialog = ref(null)
let vtableInstance = null
let releaseSelectionCount = null
let applyingHistory = false
let loadRowsRequestId = 0
let loadRowsController = null
let loadRowsTimer = null
let columnVisibilityFrame = null

const activeLibrary = computed(() => {
  return libraries.value.find((item) => item.key === route.params.libraryKey) || libraries.value[0]
})

const isPlanLibrary = computed(() => {
  return activeLibrary.value?.key === 'master-schedule-library'
})

const hiddenColumnCount = computed(() => columns.value.length - visibleColumnKeys.value.length)
const allColumnsVisible = computed(() => columns.value.length > 0 && hiddenColumnCount.value === 0)
const undoCount = computed(() => undoStack.value.length)
const editableColumns = computed(() => columns.value.filter((column) => !isReadonlyColumn(column)))
const selectedRowsCount = computed(() => selectedRowIndexes().length)
const deletedRowsCount = computed(() => deletedRowKeys.value.size)
const columnSourceLegend = computed(() => {
  const counts = columns.value.reduce((result, column) => {
    const source = columnSourceFor(column)
    result[source.key] = (result[source.key] || 0) + 1
    return result
  }, {})
  return Object.values(SOURCE_STYLES)
    .filter((source) => counts[source.key])
    .sort((left, right) => left.order - right.order)
    .map((source) => ({
      ...source,
      label: t(source.labelKey),
      count: counts[source.key],
      visibleCount: columns.value.filter((column) => (
        columnSourceFor(column).key === source.key && visibleColumnKeys.value.includes(column)
      )).length,
    }))
})

function releaseVTable() {
  if (vtableInstance) {
    vtableInstance.release()
    vtableInstance = null
  }
  releaseSelectionCount?.()
  releaseSelectionCount = null
}

function buildVTableRecords() {
  return tableRows.value.map((row, index) => ({
    [ROW_KEY_FIELD]: getRowStableKey(row, index),
    [SELECT_FIELD]: selectedRowKeys.value.has(getRowStableKey(row, index)),
    [DELETE_FIELD]: deletedRowKeys.value.has(getRowStableKey(row, index)),
    __index: index + 1,
    ...row,
  }))
}

function buildVTableColumns() {
  const textEditor = isPlanLibrary.value ? null : new InputEditor()
  return [
    {
      field: SELECT_FIELD,
      title: '',
      width: 46,
      minWidth: 46,
      maxWidth: 46,
      fixed: 'left',
      cellType: 'checkbox',
      headerType: 'checkbox',
      checked: (args = {}) => {
        const headerRows = Math.max(Number(args.table?.columnHeaderLevelCount) || 1, 1)
        if (args.row < headerRows) return areAllVisibleRowsSelected()
        const record = getRecordFromCell(1, args.row, args.table) || getRecordFromCell(args.col, args.row, args.table)
        return selectedRowKeys.value.has(getRecordKey(record))
      },
      disable: false,
      filter: false,
      style: {
        textAlign: 'center',
        bgColor: rowCellBackground,
      },
      headerStyle: {
        textAlign: 'center',
      },
    },
    {
      field: '__index',
      title: '#',
      width: 64,
      fixed: 'left',
      headerStyle: { textAlign: 'center', fontWeight: 700 },
      style: { textAlign: 'center', color: '#64748b', fontWeight: 600, bgColor: rowCellBackground },
    },
    ...columns.value.map((column) => {
      const source = columnSourceFor(column)
      return {
        field: column,
        title: column,
        width: 150,
        minWidth: 120,
        hide: !visibleColumnKeys.value.includes(column),
        filter: true,
        sort: true,
        editor: textEditor && !isReadonlyColumn(column) ? textEditor : undefined,
        style: {
          bgColor: rowCellBackground,
        },
        headerStyle: {
          fontWeight: 700,
          bgColor: source.headerBg,
          color: source.headerColor,
        },
      }
    }),
  ]
}

function getRowStableKey(row, index) {
  const primaryColumn = primaryKeyColumns.value[0]
  const primaryValue = primaryColumn ? row?.[primaryColumn] : ''
  if (primaryValue !== undefined && primaryValue !== null && String(primaryValue).trim()) {
    return String(primaryValue)
  }
  return `row-${index}`
}

function getRecordKey(record) {
  if (!record) return ''
  return String(record[ROW_KEY_FIELD] ?? '')
}

function isDeletedRecord(record) {
  return deletedRowKeys.value.has(getRecordKey(record))
}

function isDeletedRowIndex(rowIndex) {
  if (!Number.isInteger(rowIndex) || rowIndex < 0 || rowIndex >= tableRows.value.length) return false
  return deletedRowKeys.value.has(getRowStableKey(tableRows.value[rowIndex], rowIndex))
}

function isPrimaryKeyColumn(column) {
  return primaryKeyColumns.value.includes(column)
}

function isReadonlyColumn(column) {
  return readonlyColumns.value.includes(column) || isPrimaryKeyColumn(column)
}

function isStageColumn(column) {
  return stageColumns.value.includes(column)
}

function isStatusColumn(column) {
  return statusColumns.value.includes(column)
}

function isCommonColumn(column) {
  return COMMON_FIELD_COLUMNS.has(column)
}

function stageSourceFor(column) {
  const text = String(column || '')
  if (!isStageColumn(column)) return null
  if (text.startsWith('防腐/')) return SOURCE_STYLES.antiCorrosionStage
  if (text.startsWith('下料/')) return SOURCE_STYLES.cuttingStage
  if (text.startsWith('焊接/')) return SOURCE_STYLES.weldingStage
  return SOURCE_STYLES.antiCorrosionStage
}

function columnSourceFor(column) {
  if (isPrimaryKeyColumn(column)) return SOURCE_STYLES.primary
  if (isCommonColumn(column)) return SOURCE_STYLES.common
  if (isStatusColumn(column)) return SOURCE_STYLES.status
  return stageSourceFor(column) || SOURCE_STYLES.table
}

function orderColumnsBySource(sourceColumns, sourcePrimaryKeys = [], sourceStageColumns = [], sourceStatusColumns = []) {
  const originalIndexes = new Map(sourceColumns.map((column, index) => [column, index]))
  const previousPrimaryKeys = primaryKeyColumns.value
  const previousStageColumns = stageColumns.value
  const previousStatusColumns = statusColumns.value
  primaryKeyColumns.value = sourcePrimaryKeys
  stageColumns.value = sourceStageColumns
  statusColumns.value = sourceStatusColumns
  const ordered = [...sourceColumns].sort((left, right) => {
    const leftSource = columnSourceFor(left)
    const rightSource = columnSourceFor(right)
    if (leftSource.order !== rightSource.order) return leftSource.order - rightSource.order
    return (originalIndexes.get(left) || 0) - (originalIndexes.get(right) || 0)
  })
  primaryKeyColumns.value = previousPrimaryKeys
  stageColumns.value = previousStageColumns
  statusColumns.value = previousStatusColumns
  return ordered
}

function columnSelectItems() {
  return columns.value.map((column) => ({
    title: column,
    value: column,
    primaryKey: isPrimaryKeyColumn(column),
    commonColumn: isCommonColumn(column),
    stageColumn: isStageColumn(column),
    statusColumn: isStatusColumn(column),
    source: columnSourceFor(column),
    sourceLabel: t(columnSourceFor(column).labelKey),
  }))
}

function columnChipColor(item) {
  return (item.raw?.source || item.source)?.chipColor || 'secondary'
}

function columnChipVariant(item) {
  return (item.raw?.source || item.source)?.chipVariant || 'tonal'
}

function sourceVisibilityIcon(source) {
  if (!source.visibleCount) return 'mdi-eye-off-outline'
  if (source.visibleCount < source.count) return 'mdi-eye-minus-outline'
  return 'mdi-eye-outline'
}

function sourceVisibilityLabel(source) {
  const label = source.label || t(source.labelKey)
  return source.visibleCount ? t('hideSourceFields', { source: label }) : t('showSourceFields', { source: label })
}

function toggleSourceColumns(source) {
  const sourceColumnKeys = columns.value
    .filter((column) => columnSourceFor(column).key === source.key)

  if (source.visibleCount) {
    const sourceColumnSet = new Set(sourceColumnKeys)
    visibleColumnKeys.value = visibleColumnKeys.value.filter((column) => !sourceColumnSet.has(column))
  } else {
    const visibleColumnSet = new Set(visibleColumnKeys.value)
    sourceColumnKeys.forEach((column) => visibleColumnSet.add(column))
    visibleColumnKeys.value = columns.value.filter((column) => visibleColumnSet.has(column))
  }
  applyColumnVisibility()
}

function rowCellBackground(args = {}) {
  const row = Number(args.row ?? 0)
  if (row <= 0) return undefined
  const rowIndex = row - 1
  if (isDeletedRowIndex(rowIndex)) return '#fff1f2'
  return row % 2 === 0 ? '#ffffff' : '#f8fafc'
}

function buildVTableOptions() {
  const filterPlugin = new FilterPlugin({
    filterModes: ['byValue'],
  })

  return {
    records: buildVTableRecords(),
    columns: buildVTableColumns(),
    plugins: [filterPlugin],
    editCellTrigger: ['doubleclick', 'keydown'],
    widthMode: 'standard',
    heightMode: 'standard',
    autoWrapText: false,
    defaultRowHeight: 34,
    defaultHeaderRowHeight: 38,
    frozenColCount: 2,
    enableHeaderCheckboxCascade: false,
    enableCheckboxCascade: false,
    tooltip: {
      isShowOverflowTextTooltip: true,
    },
    keyboardOptions: {
      copySelected: true,
    },
    theme: {
      ...getBasicVTableTheme({ rowHeader: true }),
      frozenColumnLine: {
        shadow: {
          width: 0,
          startColor: 'rgba(255, 255, 255, 0)',
          endColor: 'rgba(255, 255, 255, 0)',
          visible: 'always',
        },
        border: {
          lineColor: 'rgba(255, 255, 255, 0)',
          lineWidth: 0,
        },
      },
    },
  }
}

function createVTable() {
  if (!tableContainer.value) return

  releaseVTable()
  const selectionLayout = createVTableSelectionLayout(tableContainer.value)
  vtableInstance = new VTable.ListTable(selectionLayout.viewport, buildVTableOptions())
  bindTableEvents()
  releaseSelectionCount = attachVTableColumnSelectionCount(vtableInstance, selectionLayout)
  vtableInstance.on(VTable.ListTable.EVENT_TYPE.CHANGE_CELL_VALUE, (event) => {
    if (applyingHistory) return
    const recordIndex = Array.isArray(event.recordIndex) ? event.recordIndex[0] : event.recordIndex
    const rowKey = getRowStableKey(tableRows.value[recordIndex], recordIndex)
    if (
      typeof recordIndex === 'number'
      && event.field
      && event.field !== '__index'
      && event.field !== SELECT_FIELD
      && !isReadonlyColumn(event.field)
      && !deletedRowKeys.value.has(rowKey)
    ) {
      const oldValue = tableRows.value[recordIndex]?.[event.field] ?? ''
      const newValue = event.changedValue ?? ''
      if (oldValue === newValue) return
      tableRows.value[recordIndex] = {
        ...tableRows.value[recordIndex],
        [event.field]: newValue,
      }
      recordChanges([{
        rowIndex: recordIndex,
        column: event.field,
        oldValue,
        newValue,
      }], t('cellEdit'))
    }
  })
}

function resetEditHistory() {
  undoStack.value = []
  dirty.value = false
}

function resetRowState() {
  selectedRowKeys.value = new Set()
  deletedRowKeys.value = new Set()
}

function recordChanges(changes, label, type = 'cell') {
  const effectiveChanges = changes.filter((change) => change.oldValue !== change.newValue)
  if (!effectiveChanges.length) return false
  undoStack.value.push({
    label,
    type,
    changes: effectiveChanges,
  })
  dirty.value = true
  return true
}

function notify(color, text) {
  snackbar.value = {
    show: true,
    color,
    text,
  }
}

function askConfirm({ title, text, confirmText = t('confirm'), color = 'primary' }) {
  return new Promise((resolve) => {
    confirmDialog.value = {
      show: true,
      title,
      text,
      confirmText,
      color,
      resolve,
    }
  })
}

function closeConfirm(result) {
  const resolve = confirmDialog.value.resolve
  confirmDialog.value.show = false
  confirmDialog.value.resolve = null
  resolve?.(result)
}

function applyChanges(changes, valueKey) {
  applyingHistory = true
  changes.forEach((change) => {
    if (change.column === DELETE_FIELD) {
      const nextDeletedKeys = new Set(deletedRowKeys.value)
      if (change[valueKey]) nextDeletedKeys.add(change.rowKey)
      else nextDeletedKeys.delete(change.rowKey)
      deletedRowKeys.value = nextDeletedKeys
      return
    }
    if (!tableRows.value[change.rowIndex]) return
    tableRows.value[change.rowIndex] = {
      ...tableRows.value[change.rowIndex],
      [change.column]: change[valueKey] ?? '',
    }
  })
  applyingHistory = false
}

function getRecordFromCell(col, row, table = vtableInstance) {
  if (!table || row < (table.columnHeaderLevelCount || 1)) return null
  const record = table.getCellOriginRecord?.(col, row) || table.getCellRawRecord?.(col, row)
  if (Array.isArray(record)) return record[0] || null
  return record || null
}

function getVisibleRecords() {
  if (!vtableInstance) return buildVTableRecords()
  const headerRows = Math.max(Number(vtableInstance.columnHeaderLevelCount) || 1, 1)
  const records = []
  const usedKeys = new Set()

  for (let row = headerRows; row < vtableInstance.rowCount; row += 1) {
    const record = getRecordFromCell(1, row) || getRecordFromCell(0, row)
    const key = getRecordKey(record)
    if (!key || usedKeys.has(key)) continue
    usedKeys.add(key)
    records.push(record)
  }

  return records.length ? records : buildVTableRecords()
}

function areAllVisibleRowsSelected() {
  const records = getVisibleRecords().filter((record) => !isDeletedRecord(record))
  return records.length > 0 && records.every((record) => selectedRowKeys.value.has(getRecordKey(record)))
}

function setTableRowCheckedState(row, checked) {
  vtableInstance?.stateManager?.setCheckedState?.(0, row, SELECT_FIELD, checked)
}

function setTableHeaderCheckedState(checked) {
  vtableInstance?.stateManager?.setHeaderCheckedState?.(SELECT_FIELD, checked)
}

function updateCheckboxCellGraphic(row, checked) {
  const cell = vtableInstance?.scenegraph?.getCell?.(0, row)
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
  if (!vtableInstance) return
  const headerRows = Math.max(Number(vtableInstance.columnHeaderLevelCount) || 1, 1)
  const allVisibleSelected = areAllVisibleRowsSelected()
  setTableHeaderCheckedState(allVisibleSelected)
  updateCheckboxCellGraphic(0, allVisibleSelected)
  for (let row = headerRows; row < vtableInstance.rowCount; row += 1) {
    const record = getRecordFromCell(1, row) || getRecordFromCell(0, row)
    const checked = selectedRowKeys.value.has(getRecordKey(record))
    setTableRowCheckedState(row, checked)
    updateCheckboxCellGraphic(row, checked)
  }
  vtableInstance.scenegraph?.updateNextFrame?.()
  vtableInstance.scenegraph?.renderSceneGraph?.()
}

function toggleVisibleRows(checked) {
  const nextKeys = new Set(selectedRowKeys.value)
  getVisibleRecords().forEach((record) => {
    const key = getRecordKey(record)
    if (!key || isDeletedRecord(record)) return
    if (checked) nextKeys.add(key)
    else nextKeys.delete(key)
    record[SELECT_FIELD] = checked
  })
  selectedRowKeys.value = nextKeys
  refreshSelectionCells()
}

function handleCheckboxStateChange(event = {}) {
  if (event.col !== 0) return
  const headerRows = Math.max(Number(vtableInstance?.columnHeaderLevelCount) || 1, 1)
  if (event.row < headerRows) {
    toggleVisibleRows(Boolean(event.checked))
    return
  }

  const record = getRecordFromCell(1, event.row) || getRecordFromCell(event.col, event.row)
  if (isDeletedRecord(record)) {
    setTableRowCheckedState(event.row, false)
    updateCheckboxCellGraphic(event.row, false)
    return
  }
  const key = getRecordKey(record)
  if (!key) return

  const nextKeys = new Set(selectedRowKeys.value)
  const nextChecked = Boolean(event.checked)
  if (nextChecked) nextKeys.add(key)
  else nextKeys.delete(key)
  record[SELECT_FIELD] = nextChecked
  selectedRowKeys.value = nextKeys
  setTableRowCheckedState(event.row, nextChecked)
  setTableHeaderCheckedState(areAllVisibleRowsSelected())
  updateCheckboxCellGraphic(event.row, nextChecked)
  updateCheckboxCellGraphic(0, areAllVisibleRowsSelected())
  vtableInstance?.scenegraph?.updateNextFrame?.()
}

function bindTableEvents() {
  if (!vtableInstance) return
  vtableInstance.on(vtableInstance.constructor.EVENT_TYPE.CHECKBOX_STATE_CHANGE, handleCheckboxStateChange)
}

async function refreshVTableData() {
  await nextTick()
  if (!vtableInstance) {
    createVTable()
    return
  }
  await vtableInstance.updateOption(buildVTableOptions(), {
    clearColWidthCache: false,
  })
}

function selectedRowIndexes() {
  return tableRows.value
    .map((row, index) => ({ index, key: getRowStableKey(row, index) }))
    .filter((item) => selectedRowKeys.value.has(item.key) && !deletedRowKeys.value.has(item.key))
    .map((item) => item.index)
}

async function applyBatchEdit() {
  if (!batchColumn.value) {
    notify('warning', t('selectBatchColumnFirst'))
    return
  }

  const rowIndexes = selectedRowIndexes()
  if (!rowIndexes.length) {
    notify('warning', t('selectRowsForBatchFirst'))
    return
  }

  const changes = rowIndexes.map((rowIndex) => ({
    rowIndex,
    column: batchColumn.value,
    oldValue: tableRows.value[rowIndex]?.[batchColumn.value] ?? '',
    newValue: batchValue.value ?? '',
  }))

  const changed = recordChanges(changes, `${t('batchEdit')} ${batchColumn.value}`)
  if (!changed) {
    notify('info', t('batchEditNoChange'))
    return
  }

  applyChanges(changes, 'newValue')
  await refreshVTableData()
  notify('success', t('batchEditSuccess', { count: changes.filter((change) => change.oldValue !== change.newValue).length }))
}

async function markSelectedRowsDeleted() {
  const rowIndexes = selectedRowIndexes()
  if (!rowIndexes.length) {
    notify('warning', t('selectRowsForDeleteFirst'))
    return
  }
  const confirmed = await askConfirm({
    title: t('deleteRows'),
    text: t('deleteRowsConfirmText', { count: rowIndexes.length }),
    confirmText: t('markRowsDeleted'),
    color: 'warning',
  })
  if (!confirmed) return

  const changes = rowIndexes.map((rowIndex) => {
    const rowKey = getRowStableKey(tableRows.value[rowIndex], rowIndex)
    return {
      rowIndex,
      rowKey,
      column: DELETE_FIELD,
      oldValue: deletedRowKeys.value.has(rowKey),
      newValue: true,
    }
  })
  const changed = recordChanges(changes, t('deleteRows'), 'delete')
  if (!changed) {
    notify('info', t('deleteRowsNoChange'))
    return
  }
  applyChanges(changes, 'newValue')
  selectedRowKeys.value = new Set(Array.from(selectedRowKeys.value).filter((key) => !deletedRowKeys.value.has(key)))
  await refreshVTableData()
  notify('success', t('rowsMarkedDeleted', { count: changes.length }))
}

async function undoLastChange() {
  const historyItem = undoStack.value.pop()
  if (!historyItem) return
  applyChanges(historyItem.changes, 'oldValue')
  dirty.value = undoStack.value.length > 0
  await refreshVTableData()
  notify('success', t('undoSuccess', { label: historyItem.label }))
}

function applyColumnVisibility() {
  if (columnVisibilityFrame !== null) {
    window.cancelAnimationFrame(columnVisibilityFrame)
  }
  columnVisibilityFrame = window.requestAnimationFrame(async () => {
    columnVisibilityFrame = null
    await nextTick()
    if (!vtableInstance) {
      createVTable()
      return
    }
    vtableInstance.updateColumns(buildVTableColumns(), {
      clearColWidthCache: false,
      clearRowHeightCache: false,
    })
  })
}

async function renderVTable() {
  await nextTick()
  createVTable()
}

function ensureLibraryRoute() {
  if (!libraries.value.length) return
  const hasLibrary = libraries.value.some((item) => item.key === route.params.libraryKey)
  if (!hasLibrary) {
    router.replace(`/libraries/${libraries.value[0].key}`)
  }
}

async function loadRows() {
  const library = activeLibrary.value
  if (!library) return

  if (loadRowsTimer) {
    window.clearTimeout(loadRowsTimer)
    loadRowsTimer = null
  }
  loadRowsController?.abort()
  const controller = new AbortController()
  loadRowsController = controller
  const requestId = ++loadRowsRequestId

  tableLoading.value = true
  tableError.value = ''
  try {
    const params = selectedProjectParams()
    const payload = await fetchLibraryRows(library.key, params, {
      signal: controller.signal,
    })
    if (requestId !== loadRowsRequestId) return
    clearLibraryError()
    tableRows.value = payload.rows || []
    const nextPrimaryKeyColumns = payload.primaryKeyColumns || []
    const nextStageColumns = payload.stageColumns || []
    const nextStatusColumns = payload.statusColumns || []
    columns.value = orderColumnsBySource(payload.columns || [], nextPrimaryKeyColumns, nextStageColumns, nextStatusColumns)
    primaryKeyColumns.value = nextPrimaryKeyColumns
    readonlyColumns.value = payload.readonlyColumns || []
    stageColumns.value = nextStageColumns
    statusColumns.value = nextStatusColumns
    visibleColumnKeys.value = columns.value.slice()
    total.value = payload.total || 0
    batchColumn.value = editableColumns.value[0] || ''
    resetRowState()
    resetEditHistory()
    await renderVTable()
  } catch (error) {
    if (error?.name === 'AbortError') return
    if (requestId !== loadRowsRequestId) return
    tableRows.value = []
    columns.value = []
    primaryKeyColumns.value = []
    readonlyColumns.value = []
    stageColumns.value = []
    statusColumns.value = []
    visibleColumnKeys.value = []
    releaseVTable()
    tableError.value = t('libraryFileReadFailed', { message: error.message })
  } finally {
    if (requestId === loadRowsRequestId) {
      loadRowsController = null
      tableLoading.value = false
    }
  }
}

function scheduleLoadRows() {
  if (loadRowsTimer) {
    window.clearTimeout(loadRowsTimer)
  }
  loadRowsController?.abort()
  loadRowsRequestId += 1
  tableLoading.value = true
  loadRowsTimer = window.setTimeout(() => {
    loadRowsTimer = null
    loadRows()
  }, 150)
}

function currentEditableRows() {
  return tableRows.value.filter((record, index) => !deletedRowKeys.value.has(getRowStableKey(record, index))).map((record) => {
    return columns.value.reduce((row, column) => {
      row[column] = record[column] ?? ''
      return row
    }, {})
  })
}

async function confirmDiscardUnsaved() {
  if (!dirty.value) return true
  return unsavedChangesDialog.value?.open({
    text: t('unsyncedEditDiscardText'),
  }) ?? true
}

function handleBeforeUnload(event) {
  if (!dirty.value) return
  event.preventDefault()
  event.returnValue = t('unsavedLeaveConfirm')
}

async function saveRows() {
  if (isPlanLibrary.value) {
    tableError.value = t('libraryFileSyncFailed', { message: t('planLibraryReadonlyHint') })
    return
  }
  if (!activeLibrary.value || !dirty.value) return
  const confirmed = await askConfirm({
    title: t('syncToBackend'),
    text: t('syncToBackendConfirm'),
    confirmText: t('syncToBackend'),
    color: 'warning',
  })
  if (!confirmed) {
    return
  }

  saving.value = true
  tableError.value = ''
  try {
    const payload = await saveLibraryRows(activeLibrary.value.key, selectedProjectParams(), {
      columns: columns.value,
      rows: currentEditableRows(),
    })
    resetEditHistory()
    total.value = payload.total || total.value
    notify('success', t('syncedToBackend'))
    await loadLibraries()
    await loadRows()
  } catch (error) {
    tableError.value = t('libraryFileSyncFailed', { message: error.message })
  } finally {
    saving.value = false
  }
}

function showAllColumns() {
  visibleColumnKeys.value = columns.value.slice()
  applyColumnVisibility()
}

function hideAllColumns() {
  visibleColumnKeys.value = []
  applyColumnVisibility()
}

function toggleAllColumns() {
  if (allColumnsVisible.value) hideAllColumns()
  else showAllColumns()
}

function hideColumn(column) {
  columnSelectMenuOpen.value = false
  visibleColumnKeys.value = visibleColumnKeys.value.filter((item) => item !== column)
  applyColumnVisibility()
}

async function focusTableColumn(column) {
  columnSelectMenuOpen.value = false
  await nextTick()
  const columnIndex = vtableInstance?.getTableIndexByField?.(column)
  if (!Number.isInteger(columnIndex) || columnIndex < 0) return
  vtableInstance.scrollToCol(columnIndex, { duration: 260 })
}

async function refreshAll() {
  if (!(await confirmDiscardUnsaved())) return
  await loadLibraries()
  ensureLibraryRoute()
  await loadRows()
}

watch(() => libraries.value, ensureLibraryRoute)
watch(() => route.params.libraryKey, async () => {
  if (!(await confirmDiscardUnsaved())) return
  ensureLibraryRoute()
  scheduleLoadRows()
})
watch(selectedProjectId, async () => {
  if (!(await confirmDiscardUnsaved())) return
  await refreshAll()
})
watch(vTableThemeKey, refreshVTableData)

onMounted(async () => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  if (!libraries.value.length) {
    await loadLibraries()
  }
  ensureLibraryRoute()
  await loadRows()
})

onBeforeRouteLeave(async () => confirmDiscardUnsaved())
onBeforeRouteUpdate(async () => confirmDiscardUnsaved())

onBeforeUnmount(() => {
  if (columnVisibilityFrame !== null) {
    window.cancelAnimationFrame(columnVisibilityFrame)
    columnVisibilityFrame = null
  }
  if (loadRowsTimer) {
    window.clearTimeout(loadRowsTimer)
    loadRowsTimer = null
  }
  loadRowsController?.abort()
  loadRowsController = null
  loadRowsRequestId += 1
  window.removeEventListener('beforeunload', handleBeforeUnload)
  releaseVTable()
})
</script>

<template>
  <WeldLibraryHeader :title="t('weldLibraries')" :description="t('weldLibraryDescription')">
    <template #actions>
      <v-btn
        prepend-icon="mdi-undo"
        :disabled="!undoCount || tableLoading || saving"
        @click="undoLastChange"
      >
        {{ t('undo') }}
      </v-btn>
      <v-btn
        prepend-icon="mdi-upload"
        :loading="saving"
        :disabled="!dirty || tableLoading || isPlanLibrary"
        color="secondary"
        variant="tonal"
        @click="saveRows"
      >
        {{ t('syncToBackend') }}
      </v-btn>
      <v-btn color="secondary" variant="tonal" :loading="libraryLoading || tableLoading" prepend-icon="mdi-refresh" @click="refreshAll">{{ t('refresh') }}</v-btn>
    </template>
  </WeldLibraryHeader>

  <v-alert v-if="libraryError || tableError" :text="libraryError || tableError" type="error" density="compact" class="status-alert" />

  <v-card v-if="activeLibrary" class="module-panel" :loading="tableLoading">
    <div class="section-head">
      <div>
        <div class="section-title-with-tip">
          <h2>{{ activeLibrary.name }}</h2>
          <InfoTooltip :text="t('libraryMaintenance')" />
        </div>
      </div>
    </div>

    <div class="library-meta" :aria-label="t('tableSummary')">
      <div class="library-meta-item is-wide">
        <span>{{ t('updatedAt') }}</span>
        <strong>{{ formatTime(activeLibrary.updatedAt) }}</strong>
      </div>
      <div class="library-meta-item">
        <span>{{ t('totalRows') }}</span>
        <strong>{{ total }}</strong>
      </div>
      <div class="library-meta-item">
        <span>{{ t('hiddenColumns') }}</span>
        <strong>{{ hiddenColumnCount }}</strong>
      </div>
      <div class="library-meta-item">
        <span>{{ t('selectedRows') }}</span>
        <strong>{{ selectedRowsCount }}</strong>
      </div>
      <div class="library-meta-item">
        <span>{{ t('pendingDeleteRows') }}</span>
        <strong>{{ deletedRowsCount }}</strong>
      </div>
      <div class="library-meta-item">
        <span>{{ t('undoable') }}</span>
        <strong>{{ undoCount }}</strong>
      </div>
      <div :class="['library-meta-item', 'is-status', { 'has-changes': dirty }]">
        <span>{{ t('editStatus') }}</span>
        <strong>{{ dirty ? t('unsyncedChanges') : t('synced') }}</strong>
      </div>
      <div v-if="isPlanLibrary" class="library-readonly-note">
        <v-icon icon="mdi-lock-outline" size="16" />
        <span>{{ t('planLibraryReadonly') }}</span>
      </div>
    </div>

    <div v-if="columnSourceLegend.length" class="column-source-legend">
      <div
        v-for="source in columnSourceLegend"
        :key="source.key"
        class="column-source-item"
        :class="{ 'is-hidden': !source.visibleCount }"
        :style="{ '--source-color': source.headerColor, '--source-bg': source.headerBg }"
      >
        <span class="column-source-marker" />
        <span class="column-source-name">{{ source.label }}</span>
        <span class="column-source-count">{{ source.visibleCount }}/{{ source.count }}</span>
        <v-tooltip :text="sourceVisibilityLabel(source)" location="top">
          <template #activator="{ props }">
            <v-btn
              v-bind="props"
              :icon="sourceVisibilityIcon(source)"
              :aria-label="sourceVisibilityLabel(source)"
              size="x-small"
              variant="text"
              class="column-source-toggle"
              @click="toggleSourceColumns(source)"
            />
          </template>
        </v-tooltip>
      </div>
    </div>

    <div class="column-toolbar">
      <v-select
        v-model="visibleColumnKeys"
        v-model:menu="columnSelectMenuOpen"
        :items="columnSelectItems()"
        item-title="title"
        item-value="value"
        multiple
        chips
        closable-chips
        density="compact"
        hide-details
        :placeholder="t('chooseVisibleColumns')"
        class="column-select"
        @update:model-value="applyColumnVisibility"
      >
        <template #chip="{ item }">
          <v-chip
            closable
            :color="columnChipColor(item)"
            :variant="columnChipVariant(item)"
            class="column-select-chip"
            @pointerdown.stop
            @mousedown.stop
            @click.stop="focusTableColumn(item.value)"
            @click:close.stop="hideColumn(item.value)"
          >
            <span class="column-chip-label">{{ item.title }}</span>
            <small class="column-chip-source">{{ item.raw.sourceLabel }}</small>
          </v-chip>
        </template>
      </v-select>
      <v-tooltip :text="allColumnsVisible ? t('hideAll') : t('showAll')" location="top">
        <template #activator="{ props }">
          <v-btn
            v-bind="props"
            :icon="allColumnsVisible ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
            :aria-label="allColumnsVisible ? t('hideAll') : t('showAll')"
            variant="text"
            @click="toggleAllColumns"
          />
        </template>
      </v-tooltip>
    </div>

    <div v-if="!isPlanLibrary" class="batch-toolbar">
      <v-select
        v-model="batchColumn"
        :items="editableColumns"
        density="compact"
        hide-details
        :placeholder="t('chooseBatchColumn')"
        class="batch-column-select"
      />
      <v-text-field v-model="batchValue" clearable density="compact" hide-details :placeholder="t('inputNewValue')" class="batch-value-input" />
      <v-btn
        color="primary"
        prepend-icon="mdi-pencil"
        :disabled="!editableColumns.length || !selectedRowsCount || tableLoading"
        @click="applyBatchEdit"
      >
        {{ t('batchEdit') }}
      </v-btn>
      <v-btn
        color="warning"
        variant="tonal"
        prepend-icon="mdi-delete-outline"
        :disabled="!selectedRowsCount || tableLoading"
        @click="markSelectedRowsDeleted"
      >
        {{ t('deleteRows') }}
      </v-btn>
    </div>

    <div ref="tableContainer" class="vtable-host" @wheel.stop @touchmove.stop />
  </v-card>

  <v-snackbar v-model="snackbar.show" :color="snackbar.color" timeout="2600">
    {{ snackbar.text }}
  </v-snackbar>

  <v-dialog v-model="confirmDialog.show" max-width="420">
    <v-card>
      <v-card-title>{{ confirmDialog.title }}</v-card-title>
      <v-card-text>{{ confirmDialog.text }}</v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="closeConfirm(false)">{{ t('cancel') }}</v-btn>
        <v-btn :color="confirmDialog.color" variant="flat" @click="closeConfirm(true)">
          {{ confirmDialog.confirmText }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <UnsavedChangesDialog ref="unsavedChangesDialog" />
</template>

<style scoped>
.column-source-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 2px 0 16px;
}

.column-source-item {
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 3px 4px 3px 10px;
  border: 1px solid color-mix(in srgb, var(--source-color) 22%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--source-bg) 62%, transparent);
  color: var(--source-color);
  transition: opacity 160ms ease, background-color 160ms ease;
}

.column-source-item.is-hidden {
  opacity: 0.58;
  background: transparent;
}

.column-source-marker {
  width: 3px;
  height: 16px;
  margin-right: 8px;
  border-radius: 2px;
  background: var(--source-color);
}

.column-source-name {
  font-size: 13px;
  font-weight: 700;
}

.column-source-count {
  min-width: 34px;
  margin-left: 7px;
  color: color-mix(in srgb, var(--source-color) 70%, #64748b);
  font-size: 12px;
  text-align: center;
}

.column-source-toggle {
  margin-left: 2px;
  color: currentColor;
}

.library-meta {
  display: flex;
  align-items: stretch;
  flex-wrap: wrap;
  gap: 0;
  margin-bottom: 14px;
  padding: 10px 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}

.library-meta span {
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.library-meta-item {
  display: grid;
  align-content: center;
  min-width: 90px;
  padding: 2px 18px;
  border-right: 1px solid var(--line);
}

.library-meta-item:first-child {
  padding-left: 0;
}

.library-meta-item.is-wide {
  min-width: 184px;
}

.library-meta-item > span {
  color: #64748b;
  font-size: 11px;
  line-height: 1.3;
}

.library-meta-item > strong {
  margin-top: 3px;
  color: #1e293b;
  font-size: 14px;
  line-height: 1.35;
}

.library-meta-item.is-status > strong {
  color: #047857;
}

.library-meta-item.is-status.has-changes > strong {
  color: #c2410c;
}

.library-readonly-note {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 16px;
  color: #64748b;
  font-size: 12px;
}

.column-chip-source {
  margin-left: 6px;
  margin-right: 2px;
  flex: 0 0 auto;
  opacity: 0.78;
  font-size: 11px;
  font-weight: 600;
}

.column-select-chip {
  max-width: 260px;
  cursor: pointer;
}

.column-select-chip :deep(.v-chip__content) {
  min-width: 0;
}

.column-chip-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.column-select :deep(.v-field__input) {
  align-items: center;
  gap: 6px;
  min-height: 46px;
  padding-block: 6px;
}

@media (max-width: 720px) {
  .library-meta-item,
  .library-meta-item:first-child {
    flex: 1 1 33.333%;
    min-width: 110px;
    padding: 7px 12px;
  }

  .library-meta-item.is-wide {
    flex-basis: 100%;
  }
}
</style>
