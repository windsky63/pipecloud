<script setup>
import * as VTable from '@visactor/vtable'
import { InputEditor } from '@visactor/vtable-editors'
import { FilterPlugin } from '@visactor/vtable-plugins'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { fetchLibraryRows, saveLibraryRows } from '../../api/libraries'
import WeldLibraryHeader from './WeldLibraryHeader.vue'
import UnsavedChangesDialog from '../../components/UnsavedChangesDialog.vue'
import { libraries, libraryError, libraryLoading, loadLibraries } from '../../services/weldLibraryState'
import { formatSize, formatTime, t } from '../../services/pipecloudState'
import { selectedProjectId, selectedProjectParams } from '../../services/projectState'
import { getBasicVTableTheme, vTableThemeKey } from '../../services/vtableTheme'

const route = useRoute()
const router = useRouter()

const tableLoading = ref(false)
const tableError = ref('')
const tableRows = ref([])
const columns = ref([])
const visibleColumnKeys = ref([])
const sheets = ref([])
const activeSheet = ref('')
const total = ref(0)
const dirty = ref(false)
const saving = ref(false)
const batchColumn = ref('')
const batchValue = ref('')
const batchScope = ref('selected')
const undoStack = ref([])
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
let applyingHistory = false

const activeLibrary = computed(() => {
  return libraries.value.find((item) => item.key === route.params.libraryKey) || libraries.value[0]
})

const isPlanLibrary = computed(() => {
  return activeLibrary.value?.key === 'master-schedule-library'
})

const hiddenColumnCount = computed(() => columns.value.length - visibleColumnKeys.value.length)
const undoCount = computed(() => undoStack.value.length)

function releaseVTable() {
  if (vtableInstance) {
    vtableInstance.release()
    vtableInstance = null
  }
}

function buildVTableRecords() {
  return tableRows.value.map((row, index) => ({
    __index: index + 1,
    ...row,
  }))
}

function buildVTableColumns() {
  const textEditor = isPlanLibrary.value ? null : new InputEditor()
  return [
    {
      field: '__index',
      title: '#',
      width: 64,
      fixed: 'left',
      headerStyle: { textAlign: 'center', fontWeight: 700 },
      style: { textAlign: 'center', color: '#64748b', fontWeight: 600 },
    },
    ...columns.value.map((column) => ({
      field: column,
      title: column,
      width: 150,
      minWidth: 120,
      hide: !visibleColumnKeys.value.includes(column),
      filter: true,
      sort: true,
      editor: textEditor || undefined,
      headerStyle: { fontWeight: 700 },
    })),
  ]
}

function tableRowBackground(args) {
  const row = Number(args?.row ?? 0)
  if (row <= 0) return '#ffffff'
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
    frozenColCount: 1,
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
  vtableInstance = new VTable.ListTable(tableContainer.value, buildVTableOptions())
  vtableInstance.on(VTable.ListTable.EVENT_TYPE.CHANGE_CELL_VALUE, (event) => {
    if (applyingHistory) return
    const recordIndex = Array.isArray(event.recordIndex) ? event.recordIndex[0] : event.recordIndex
    if (typeof recordIndex === 'number' && event.field && event.field !== '__index') {
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

function recordChanges(changes, label) {
  const effectiveChanges = changes.filter((change) => change.oldValue !== change.newValue)
  if (!effectiveChanges.length) return false
  undoStack.value.push({
    label,
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
    if (!tableRows.value[change.rowIndex]) return
    tableRows.value[change.rowIndex] = {
      ...tableRows.value[change.rowIndex],
      [change.column]: change[valueKey] ?? '',
    }
  })
  applyingHistory = false
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
  const selectedInfos = vtableInstance?.getSelectedCellInfos?.() || []
  const indexesFromCellInfos = new Set()
  selectedInfos.flat().forEach((cellInfo) => {
    const recordIndex = Number(cellInfo?.originData?.__index) - 1
    if (recordIndex >= 0 && recordIndex < tableRows.value.length) {
      indexesFromCellInfos.add(recordIndex)
    }
  })
  if (indexesFromCellInfos.size) {
    return Array.from(indexesFromCellInfos).sort((a, b) => a - b)
  }

  const ranges = vtableInstance?.getSelectedCellRanges?.() || []
  const rowIndexes = new Set()
  ranges.forEach((range) => {
    const startRow = Math.min(range.start.row, range.end.row)
    const endRow = Math.max(range.start.row, range.end.row)
    for (let tableRow = startRow; tableRow <= endRow; tableRow += 1) {
      const rowIndex = tableRow - 1
      if (rowIndex >= 0 && rowIndex < tableRows.value.length) {
        rowIndexes.add(rowIndex)
      }
    }
  })
  return Array.from(rowIndexes).sort((a, b) => a - b)
}

function batchTargetRowIndexes() {
  if (batchScope.value === 'all') {
    return tableRows.value.map((_, index) => index)
  }
  return selectedRowIndexes()
}

async function applyBatchEdit() {
  if (!batchColumn.value) {
    notify('warning', t('selectBatchColumnFirst'))
    return
  }

  const rowIndexes = batchTargetRowIndexes()
  if (!rowIndexes.length) {
    notify('warning', t('selectRowsForBatchFirst'))
    return
  }

  if (batchScope.value === 'all') {
    const confirmed = await askConfirm({
      title: t('batchEdit'),
      text: t('batchConfirmText', { column: batchColumn.value, count: rowIndexes.length }),
      confirmText: t('confirmBatchEdit'),
      color: 'warning',
    })
    if (!confirmed) {
      return
    }
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
    router.replace(`/weld-libraries/${libraries.value[0].key}`)
  }
}

async function loadRows() {
  if (!activeLibrary.value) return

  tableLoading.value = true
  tableError.value = ''
  try {
    const params = selectedProjectParams()
    if (activeSheet.value) params.set('sheet', activeSheet.value)
    const payload = await fetchLibraryRows(activeLibrary.value.key, params)
    tableRows.value = payload.rows || []
    columns.value = payload.columns || []
    visibleColumnKeys.value = columns.value.slice()
    sheets.value = payload.sheets || []
    activeSheet.value = payload.sheet || ''
    total.value = payload.total || 0
    batchColumn.value = columns.value[0] || ''
    resetEditHistory()
    await renderVTable()
  } catch (error) {
    tableRows.value = []
    columns.value = []
    visibleColumnKeys.value = []
    releaseVTable()
    tableError.value = t('libraryFileReadFailed', { message: error.message })
  } finally {
    tableLoading.value = false
  }
}

function currentEditableRows() {
  return tableRows.value.map((record) => {
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
      sheet: activeSheet.value,
      columns: columns.value,
      rows: currentEditableRows(),
    })
    resetEditHistory()
    total.value = payload.total || total.value
    notify('success', t('syncedToBackend'))
    await loadLibraries()
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

async function changeSheet(sheet) {
  if (!(await confirmDiscardUnsaved())) return
  activeSheet.value = sheet
  loadRows()
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
  activeSheet.value = ''
  await loadRows()
})
watch(selectedProjectId, async () => {
  if (!(await confirmDiscardUnsaved())) return
  activeSheet.value = ''
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
  window.removeEventListener('beforeunload', handleBeforeUnload)
  releaseVTable()
})
</script>

<template>
  <WeldLibraryHeader :title="t('weldLibraryFile')" :description="t('weldLibraryDescription')">
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
      <v-chip :color="activeLibrary.exists ? 'success' : 'secondary'" variant="flat">{{ activeLibrary.exists ? t('ready') : t('missing') }}</v-chip>
    </div>

    <div class="library-meta">
      <span>{{ t('size') }}：{{ formatSize(activeLibrary.size) }}</span>
      <span>{{ t('updatedAt') }}：{{ formatTime(activeLibrary.updatedAt) }}</span>
      <span>{{ t('currentSheet') }}：{{ activeSheet || t('unselected') }}</span>
      <span>{{ t('totalRows') }}：{{ total }}</span>
      <span>{{ t('hiddenColumns') }}：{{ hiddenColumnCount }}</span>
      <span>{{ t('undoable') }}：{{ undoCount }}</span>
      <span>{{ t('editStatus') }}：{{ dirty ? t('unsyncedChanges') : t('synced') }}</span>
      <span v-if="isPlanLibrary">当前为管段焊口表计划库，只读</span>
    </div>

    <div class="library-toolbar">
      <v-tabs :model-value="activeSheet" color="primary" @update:model-value="changeSheet">
        <v-tab v-for="sheet in sheets" :key="sheet" :value="sheet">{{ sheet }}</v-tab>
      </v-tabs>
    </div>

    <div class="column-toolbar">
      <v-select
        v-model="visibleColumnKeys"
        :items="columns"
        multiple
        chips
        closable-chips
        density="compact"
        hide-details
        :placeholder="t('chooseVisibleColumns')"
        class="column-select"
        @update:model-value="applyColumnVisibility"
      />
      <v-btn @click="showAllColumns">{{ t('showAll') }}</v-btn>
      <v-btn @click="hideAllColumns">{{ t('hideAll') }}</v-btn>
    </div>

    <div v-if="!isPlanLibrary" class="batch-toolbar">
      <v-select
        v-model="batchColumn"
        :items="columns"
        density="compact"
        hide-details
        :placeholder="t('chooseBatchColumn')"
        class="batch-column-select"
      />
      <v-text-field v-model="batchValue" clearable density="compact" hide-details :placeholder="t('inputNewValue')" class="batch-value-input" />
      <v-btn-toggle
        v-model="batchScope"
        mandatory
        density="compact"
      >
        <v-btn value="selected">{{ t('selectedRows') }}</v-btn>
        <v-btn value="all">{{ t('allRows') }}</v-btn>
      </v-btn-toggle>
      <v-btn
        color="primary"
        prepend-icon="mdi-pencil"
        :disabled="!columns.length || tableLoading"
        @click="applyBatchEdit"
      >
        {{ t('batchEdit') }}
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
