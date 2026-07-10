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

const route = useRoute()
const router = useRouter()

const tableLoading = ref(false)
const tableError = ref('')
const tableRows = ref([])
const columns = ref([])
const primaryKeyColumns = ref([])
const readonlyColumns = ref([])
const stageColumns = ref([])
const visibleColumnKeys = ref([])
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

const activeLibrary = computed(() => {
  return libraries.value.find((item) => item.key === route.params.libraryKey) || libraries.value[0]
})

const isPlanLibrary = computed(() => {
  return activeLibrary.value?.key === 'master-schedule-library'
})

const hiddenColumnCount = computed(() => columns.value.length - visibleColumnKeys.value.length)
const undoCount = computed(() => undoStack.value.length)
const editableColumns = computed(() => columns.value.filter((column) => !isReadonlyColumn(column)))
const selectedRowsCount = computed(() => selectedRowIndexes().length)
const deletedRowsCount = computed(() => deletedRowKeys.value.size)
const pageTitle = computed(() => activeLibrary.value?.name || t('weldLibraries'))

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
    ...columns.value.map((column) => ({
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
        bgColor: isStageColumn(column) ? '#ecfdf5' : undefined,
        color: isStageColumn(column) ? '#047857' : undefined,
      },
    })),
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

function columnSelectItems() {
  return columns.value.map((column) => ({
    title: column,
    value: column,
    primaryKey: isPrimaryKeyColumn(column),
    stageColumn: isStageColumn(column),
  }))
}

function columnChipColor(item) {
  if (item.raw.primaryKey) return 'warning'
  if (item.raw.stageColumn) return 'success'
  return 'secondary'
}

function columnChipVariant(item) {
  if (item.raw.primaryKey) return 'flat'
  return 'tonal'
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

async function applyColumnVisibility() {
  await nextTick()
  if (!vtableInstance) {
    createVTable()
    return
  }
  await vtableInstance.updateOption(buildVTableOptions(), {
    clearColWidthCache: true,
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
    columns.value = payload.columns || []
    primaryKeyColumns.value = payload.primaryKeyColumns || []
    readonlyColumns.value = payload.readonlyColumns || []
    stageColumns.value = payload.stageColumns || []
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
    tableError.value = t('libraryFileSyncFailed', { message: '计划库来自管段焊口表，暂不支持在库页面直接保存，请在计划页面编辑具体计划文件。' })
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
  <WeldLibraryHeader :title="pageTitle" :description="t('weldLibraryDescription')">
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

    <div class="library-meta">
      <span>{{ t('updatedAt') }}：{{ formatTime(activeLibrary.updatedAt) }}</span>
      <span>{{ t('totalRows') }}：{{ total }}</span>
      <span>{{ t('hiddenColumns') }}：{{ hiddenColumnCount }}</span>
      <span>{{ t('selectedRows') }}：{{ selectedRowsCount }}</span>
      <span>{{ t('pendingDeleteRows') }}：{{ deletedRowsCount }}</span>
      <span>{{ t('undoable') }}：{{ undoCount }}</span>
      <span>{{ t('editStatus') }}：{{ dirty ? t('unsyncedChanges') : t('synced') }}</span>
      <span v-if="isPlanLibrary">当前为管段焊口表计划库，只读</span>
    </div>

    <div class="column-toolbar">
      <v-select
        v-model="visibleColumnKeys"
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
        <template #chip="{ props, item }">
          <v-chip
            v-bind="props"
            :color="columnChipColor(item)"
            :variant="columnChipVariant(item)"
          >
            {{ item.title }}
          </v-chip>
        </template>
      </v-select>
      <v-btn @click="showAllColumns">{{ t('showAll') }}</v-btn>
      <v-btn @click="hideAllColumns">{{ t('hideAll') }}</v-btn>
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
