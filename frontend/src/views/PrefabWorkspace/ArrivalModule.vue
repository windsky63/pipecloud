<script setup>
import { computed, ref, watch } from 'vue'
import ArrivalDashboardPanel from '../../components/ArrivalDashboardPanel.vue'
import DataVTable from '../../components/DataVTable.vue'
import FileUploadDropzone from '../../components/FileUploadDropzone.vue'
import InfoTooltip from '../../components/InfoTooltip.vue'
import { localizedModuleDescription } from '../../services/navigationLabels'
import { dashboardVisibility, displayDataPath, formatTime, setDashboardVisibility, t } from '../../services/pipecloudState'

const props = defineProps({
  activeModule: { type: Object, required: true },
  activeModuleTitle: { type: String, required: true },
  arrivalActiveTab: { type: String, required: true },
  arrivalLoading: { type: Boolean, default: false },
  arrivalError: { type: String, default: '' },
  arrivalDashboard: { type: Object, required: true },
  arrivalDashboardLoading: { type: Boolean, default: false },
  arrivalDashboardError: { type: String, default: '' },
  todayArrival: { type: Object, required: true },
  todayArrivalSummaryRows: { type: Array, default: () => [] },
  arrivalSummaryTableColumns: { type: Array, default: () => [] },
  todayArrivalColumns: { type: Array, default: () => [] },
  arrivalFileOptions: { type: Array, default: () => [] },
  selectedArrivalFile: { type: String, default: '' },
  selectedArrivalSheet: { type: String, default: '' },
  arrivalFileDetail: { type: Object, required: true },
  arrivalFileDetailSummaryRows: { type: Array, default: () => [] },
  arrivalFileDetailColumns: { type: Array, default: () => [] },
  arrivalFiles: { type: Object, required: true },
  arrivalFileRows: { type: Array, default: () => [] },
  arrivalFileTableColumns: { type: Array, default: () => [] },
  arrivalImportCompleteKey: { type: Number, default: 0 },
})

const emit = defineEmits([
  'change-tab',
  'refresh-today-arrival',
  'refresh-arrival-dashboard',
  'refresh-arrival-files',
  'confirm-arrival-import',
  'change-arrival-file',
  'change-arrival-sheet',
])

const selectedArrivalUploadFiles = ref([])
const dashboardCollapsed = ref(false)
const arrivalImportResults = ref([])
const arrivalImportActiveIndex = ref(0)
const arrivalImportError = ref('')
const previewLoading = ref(false)
const activeArrivalImportResult = computed(() => arrivalImportResults.value[arrivalImportActiveIndex.value] || null)
const arrivalImportPreview = computed(() => {
  const item = activeArrivalImportResult.value
  if (!item) return {}
  const sheet = item.activeSheet || item.preview?.sheet || item.sheets?.[0] || ''
  return item.previews?.[sheet] || item.preview || {}
})
const arrivalImportPreviewColumns = computed(() => arrivalImportPreview.value.columns || [])
const arrivalImportPreviewRows = computed(() => arrivalImportPreview.value.rows || [])
const hasPendingArrivalImport = computed(() => selectedArrivalUploadFiles.value.length > 0 && arrivalImportResults.value.length > 0)
const arrivalDateChartRows = computed(() => {
  const grouped = new Map()
  for (const row of props.arrivalDashboard.dateStats || []) {
    const date = String(row.date || '-')
    const item = grouped.get(date) || {
      date,
      pipeQty: 0,
      otherQty: 0,
      pipeRows: 0,
      otherRows: 0,
      pipeCount: 0,
    }
    const quantity = Number(row.quantity) || 0
    if (row.materialType === 'pipe') {
      item.pipeQty += quantity
      item.pipeRows += Number(row.rowCount) || 0
      item.pipeCount += Number(row.pipeCount) || 0
    } else {
      item.otherQty += quantity
      item.otherRows += Number(row.rowCount) || 0
    }
    grouped.set(date, item)
  }
  return Array.from(grouped.values()).sort((left, right) => left.date.localeCompare(right.date))
})
const arrivalDateChartMax = computed(() => {
  return Math.max(1, ...arrivalDateChartRows.value.map((row) => Math.max(row.pipeQty, row.otherQty)))
})

function barHeight(value) {
  return `${Math.max(6, Math.round((Number(value) || 0) / arrivalDateChartMax.value * 120))}px`
}

function formatNumber(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '0'
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 }).format(number)
}

async function setArrivalUploadFiles(files) {
  selectedArrivalUploadFiles.value = Array.from(files || [])
  await previewArrivalFiles(selectedArrivalUploadFiles.value)
}

async function previewArrivalFiles(files) {
  arrivalImportError.value = ''
  arrivalImportResults.value = []
  arrivalImportActiveIndex.value = 0
  if (!files.length) return
  previewLoading.value = true
  try {
    const ExcelJS = await import('exceljs')
    const Workbook = ExcelJS.default?.Workbook || ExcelJS.Workbook
    const results = []
    for (const [index, file] of files.entries()) {
      if (!file.name.toLowerCase().endsWith('.xlsx')) {
        throw new Error(t('onlySupportFiles', { types: '.xlsx', files: file.name }))
      }
      const workbook = new Workbook()
      await workbook.xlsx.load(await file.arrayBuffer())
      const sheets = workbook.worksheets.map((item) => item.name)
      if (!sheets.length) {
        results.push(buildEmptyArrivalPreview(file, index))
        continue
      }
      const previews = workbook.worksheets.reduce((items, sheet) => {
        items[sheet.name] = buildArrivalSheetPreview(sheet)
        return items
      }, {})
      const activeSheet = sheets[0]
      results.push({
        id: `${file.name}-${file.size}-${file.lastModified}-${index}`,
        filename: file.name,
        sourceName: file.name,
        confirmed: false,
        activeSheet,
        sheets,
        previews,
        preview: previews[activeSheet],
      })
    }
    arrivalImportResults.value = results
  } catch (error) {
    arrivalImportError.value = t('arrivalPreviewFailed', { message: error.message })
  } finally {
    previewLoading.value = false
  }
}

function buildArrivalSheetPreview(sheet) {
  const headerRow = sheet.getRow(1)
  const columnCount = Math.max(sheet.columnCount || 0, headerRow.cellCount || 0)
  const columns = Array.from({ length: columnCount }, (_, columnIndex) => {
    return stringifyExcelValue(headerRow.getCell(columnIndex + 1).value) || `${t('columnCount')} ${columnIndex + 1}`
  })
  const previewLimit = 20
  const rowCount = Math.max((sheet.rowCount || 1) - 1, 0)
  const rows = []
  for (let rowNumber = 2; rowNumber <= Math.min(sheet.rowCount, previewLimit + 1); rowNumber += 1) {
    const row = sheet.getRow(rowNumber)
    const record = {}
    columns.forEach((column, columnIndex) => {
      record[column] = stringifyExcelValue(row.getCell(columnIndex + 1).value)
    })
    rows.push(record)
  }
  return {
    sheet: sheet.name,
    sheets: [],
    total: rowCount,
    columns,
    rows,
    previewLimit,
  }
}

function buildEmptyArrivalPreview(file, index) {
  return {
    id: `${file.name}-${file.size}-${file.lastModified}-${index}`,
    filename: file.name,
    sourceName: file.name,
    confirmed: false,
    activeSheet: '',
    sheets: [],
    previews: {},
    preview: {
      sheet: '',
      sheets: [],
      total: 0,
      columns: [],
      rows: [],
      previewLimit: 20,
    },
  }
}

function stringifyExcelValue(value) {
  if (value === null || value === undefined) return ''
  if (value instanceof Date) return value.toLocaleString()
  if (typeof value !== 'object') return String(value)
  if (Array.isArray(value.richText)) return value.richText.map((item) => item.text || '').join('')
  if (value.text !== undefined) return String(value.text)
  if (value.result !== undefined) return stringifyExcelValue(value.result)
  if (value.hyperlink !== undefined) return String(value.hyperlink)
  return String(value)
}

function setArrivalImportActiveIndex(index) {
  arrivalImportActiveIndex.value = index
}

function changeArrivalImportSheet(sheet) {
  const index = arrivalImportActiveIndex.value
  const item = arrivalImportResults.value[index]
  if (!item?.previews?.[sheet]) return
  arrivalImportResults.value[index] = {
    ...item,
    activeSheet: sheet,
    preview: item.previews[sheet],
  }
}

function confirmArrivalImport() {
  emit('confirm-arrival-import', selectedArrivalUploadFiles.value)
}

function clearArrivalImport() {
  selectedArrivalUploadFiles.value = []
  arrivalImportResults.value = []
  arrivalImportActiveIndex.value = 0
  arrivalImportError.value = ''
}

watch(() => props.arrivalImportCompleteKey, () => {
  clearArrivalImport()
})
</script>

<template>
  <ArrivalDashboardPanel
    v-if="dashboardVisibility.arrival"
    :title="t('arrivalDashboardTitle')"
    :description="t('arrivalDashboardDescription')"
    :dashboard="arrivalDashboard"
    :loading="arrivalDashboardLoading"
    :error="arrivalDashboardError"
    show-refresh
    collapsible
    :collapsed="dashboardCollapsed"
    @refresh="$emit('refresh-arrival-dashboard')"
    @hide="setDashboardVisibility('arrival', false)"
    @toggle="dashboardCollapsed = !dashboardCollapsed"
  />

  <v-card class="module-panel" :loading="arrivalLoading">
    <div class="section-head">
      <div>
        <div class="section-title-with-tip">
          <h2>{{ activeModuleTitle }}</h2>
          <InfoTooltip :text="localizedModuleDescription(activeModule)" />
        </div>
      </div>
      <v-btn
        :loading="arrivalLoading"
        icon="mdi-refresh"
        variant="text"
        :aria-label="t('refreshTodayArrival')"
        :title="t('refreshTodayArrival')"
        @click="$emit('refresh-today-arrival')"
      />
    </div>

    <v-alert v-if="arrivalError" :text="arrivalError" type="error" density="compact" class="status-alert" />

    <v-tabs :model-value="arrivalActiveTab" color="primary" class="arrival-tabs" @update:model-value="$emit('change-tab', $event)">
      <v-tab value="overview">{{ t('arrivalManagement') }}</v-tab>
      <v-tab value="arrivalFiles">{{ t('arrivalOrder') }}</v-tab>
      <v-tab value="arrivalImport">{{ t('importArrivalOrder') }}</v-tab>
    </v-tabs>
    <v-window :model-value="arrivalActiveTab" @update:model-value="$emit('change-tab', $event)">
      <v-window-item value="overview">
        <div class="arrival-tab-content">
          <section class="arrival-date-chart-panel">
            <div class="section-head arrival-date-chart-head">
              <div>
                <h2>{{ t('arrivalOrderDateChart') }}</h2>
                <span>{{ t('arrivalOrderDateChartDescription') }}</span>
              </div>
              <div class="arrival-date-chart-legend">
                <span><i class="is-pipe" />{{ t('pipeMaterial') }}</span>
                <span><i class="is-other" />{{ t('otherMaterial') }}</span>
              </div>
            </div>
            <div v-if="arrivalDateChartRows.length" class="arrival-date-chart">
              <div
                v-for="row in arrivalDateChartRows"
                :key="row.date"
                class="arrival-date-chart-day"
              >
                <div class="arrival-date-bars">
                  <div class="arrival-date-bar-wrap">
                    <span>{{ formatNumber(row.pipeQty) }}</span>
                    <div class="arrival-date-bar is-pipe" :style="{ height: barHeight(row.pipeQty) }" />
                  </div>
                  <div class="arrival-date-bar-wrap">
                    <span>{{ formatNumber(row.otherQty) }}</span>
                    <div class="arrival-date-bar is-other" :style="{ height: barHeight(row.otherQty) }" />
                  </div>
                </div>
                <div class="arrival-date-label">
                  <strong>{{ row.date }}</strong>
                  <small>{{ t('arrivalDateRowsHint', { pipe: row.pipeRows, other: row.otherRows }) }}</small>
                  <small v-if="row.pipeCount">{{ t('arrivalPipeCountWithValue', { value: formatNumber(row.pipeCount) }) }}</small>
                </div>
              </div>
            </div>
            <v-alert v-else :text="t('noArrivalOrderDateStats')" type="info" variant="tonal" density="compact" />
          </section>

          <v-sheet class="arrival-today-layout" color="transparent">
            <div class="arrival-today-summary">
              <div class="section-head arrival-detail-head">
                <div>
                  <h2>{{ t('todayArrivalDetail') }}</h2>
                  <span>{{ displayDataPath(todayArrival.file?.path, todayArrival.file?.name || t('noArrivalOrderForDate', { date: todayArrival.date || t('today') })) }}</span>
                </div>
                <v-chip color="secondary" variant="tonal">{{ t('rowCount', { count: todayArrival.total }) }}</v-chip>
              </div>
              <DataVTable
                :records="todayArrivalSummaryRows"
                :columns="arrivalSummaryTableColumns"
                :height="234"
                :empty-text="t('noTodayArrivalStats')"
              />
            </div>
            <div class="arrival-today-table">
              <DataVTable
                :records="todayArrival.rows"
                :columns="todayArrivalColumns"
                :height="320"
                :empty-text="t('noTodayArrivalRows')"
              />
            </div>
          </v-sheet>

        </div>
      </v-window-item>

      <v-window-item value="arrivalFiles">
        <div class="arrival-tab-content">
          <div class="arrival-file-controls">
            <v-select
              :model-value="selectedArrivalFile"
              :items="arrivalFileOptions"
              density="compact"
              hide-details
              class="arrival-file-select"
              :placeholder="t('selectArrivalOrder')"
              :disabled="arrivalLoading || !arrivalFileOptions.length"
              @update:model-value="$emit('change-arrival-file', $event)"
            />
            <v-select
              :model-value="selectedArrivalSheet"
              :items="arrivalFileDetail.sheets"
              density="compact"
              hide-details
              :placeholder="t('selectSheet')"
              class="arrival-sheet-select"
              :disabled="arrivalLoading || !arrivalFileDetail.sheets.length"
              @update:model-value="$emit('change-arrival-sheet', $event)"
            />
            <div class="arrival-file-meta">
              <span v-if="displayDataPath(arrivalFileDetail.file?.path)">{{ t('fileMetaPath', { value: displayDataPath(arrivalFileDetail.file?.path) }) }}</span>
              <span>{{ t('fileMetaRows', { value: arrivalFileDetail.total }) }}</span>
              <span>{{ t('fileMetaUpdatedAt', { value: formatTime(arrivalFileDetail.file?.updatedAt) }) }}</span>
            </div>
          </div>

          <v-sheet class="arrival-file-detail" color="transparent">
            <DataVTable
              :records="arrivalFileDetailSummaryRows"
              :columns="arrivalSummaryTableColumns"
              :height="234"
              :empty-text="t('noArrivalOrderStats')"
            />
            <DataVTable
              :records="arrivalFileDetail.rows"
              :columns="arrivalFileDetailColumns"
              :height="420"
              :empty-text="t('selectArrivalOrderForDetail')"
            />
          </v-sheet>

          <div class="section-head arrival-file-head">
            <div>
              <div class="section-title-with-tip">
                <h2>{{ t('arrivalOrderList') }}</h2>
                <InfoTooltip :text="t('arrivalOrderListTip')" />
              </div>
            </div>
          </div>
          <DataVTable
            :records="arrivalFileRows"
            :columns="arrivalFileTableColumns"
            :height="300"
            :empty-text="t('noArrivalOrderFiles')"
          />
        </div>
      </v-window-item>

      <v-window-item value="arrivalImport">
        <div class="arrival-tab-content">
          <v-sheet class="arrival-import-panel" color="transparent">
            <div class="arrival-import-actions">
              <FileUploadDropzone
                class="arrival-import-dropzone"
                :files="selectedArrivalUploadFiles"
                accept=".xlsx"
                multiple
                :disabled="arrivalLoading || previewLoading"
                :title="t('selectArrivalOrderFiles')"
                :hint="t('arrivalMultiImportHint')"
                @files-selected="setArrivalUploadFiles"
              />
              <div class="arrival-import-button-row">
                <v-btn
                  color="success"
                  prepend-icon="mdi-file-sync-outline"
                  :loading="arrivalLoading"
                  :disabled="!hasPendingArrivalImport || previewLoading || Boolean(arrivalImportError)"
                  @click="confirmArrivalImport"
                >
                  {{ t('confirmImportAndUpdateStock') }}
                </v-btn>
                <v-btn
                  :loading="previewLoading"
                  :disabled="!selectedArrivalUploadFiles.length || arrivalLoading"
                  prepend-icon="mdi-refresh"
                  @click="previewArrivalFiles(selectedArrivalUploadFiles)"
                >
                  {{ t('refresh') }}
                </v-btn>
                <v-btn :disabled="arrivalLoading || previewLoading || !selectedArrivalUploadFiles.length" @click="clearArrivalImport">{{ t('clear') }}</v-btn>
              </div>
            </div>
            <v-alert v-if="arrivalImportError" :text="arrivalImportError" type="error" density="compact" class="arrival-import-alert" />
            <div v-if="arrivalImportResults.length" class="arrival-import-preview">
              <div class="arrival-import-preview-layout">
                <aside class="arrival-import-file-list">
                  <div class="arrival-import-file-list-head">
                    <strong>{{ t('arrivalOrderList') }}</strong>
                    <span>{{ t('fileCount', { count: arrivalImportResults.length }) }}</span>
                  </div>
                  <button
                    v-for="(item, index) in arrivalImportResults"
                    :key="item.id || index"
                    type="button"
                    class="arrival-import-file-item"
                    :class="{ 'is-active': index === arrivalImportActiveIndex }"
                    @click="setArrivalImportActiveIndex(index)"
                  >
                    <strong>{{ item.sourceName || item.filename || `${t('arrivalOrder')} ${index + 1}` }}</strong>
                    <span>{{ t('sheetCount', { value: item.sheets?.length || 0 }) }}</span>
                  </button>
                </aside>

                <div class="arrival-import-preview-main">
                  <div v-if="activeArrivalImportResult?.sheets?.length" class="library-toolbar">
                    <v-tabs
                      :model-value="arrivalImportPreview.sheet"
                      color="primary"
                      @update:model-value="changeArrivalImportSheet"
                    >
                      <v-tab
                        v-for="sheet in activeArrivalImportResult.sheets"
                        :key="sheet"
                        :value="sheet"
                      >
                        {{ sheet }}
                      </v-tab>
                    </v-tabs>
                  </div>

                  <v-alert
                    v-if="activeArrivalImportResult"
                    :type="activeArrivalImportResult.confirmed ? 'success' : 'warning'"
                    variant="tonal"
                    density="compact"
                    class="arrival-import-alert"
                  >
                    {{ activeArrivalImportResult.confirmed ? t('confirmedImported') : t('waitingConfirm') }}：{{ activeArrivalImportResult.filename }}
                    <span v-if="arrivalImportPreview.total">（{{ t('previewRowsSummary', { shown: arrivalImportPreviewRows.length, total: arrivalImportPreview.total }) }}）</span>
                  </v-alert>
                  <DataVTable
                    :records="arrivalImportPreviewRows"
                    :columns="arrivalImportPreviewColumns.map((column) => ({ field: column, title: column, width: 150 }))"
                    :height="360"
                    :empty-text="t('noPreviewData')"
                  />
                </div>
              </div>
            </div>
          </v-sheet>
        </div>
      </v-window-item>
    </v-window>
  </v-card>
</template>

<style scoped>
.arrival-today-layout {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.arrival-tabs {
  margin-bottom: 18px;
}

.arrival-tab-content {
  display: grid;
  gap: 16px;
}

.arrival-overview-actions {
  margin-top: 18px;
  margin-bottom: 18px;
}

.arrival-date-chart-panel {
  display: grid;
  gap: 12px;
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel-soft);
}

.arrival-date-chart-head {
  margin: 0;
}

.arrival-date-chart-head h2 {
  margin: 0;
}

.arrival-date-chart-head span {
  color: var(--muted);
  font-size: 12px;
}

.arrival-date-chart-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  color: var(--muted);
  font-size: 12px;
}

.arrival-date-chart-legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.arrival-date-chart-legend i {
  width: 10px;
  height: 10px;
  border-radius: 2px;
}

.arrival-date-chart-legend .is-pipe,
.arrival-date-bar.is-pipe {
  background: #2563eb;
}

.arrival-date-chart-legend .is-other,
.arrival-date-bar.is-other {
  background: #0f9f6e;
}

.arrival-date-chart {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(116px, 1fr);
  gap: 10px;
  min-height: 210px;
  overflow-x: auto;
  padding-bottom: 4px;
}

.arrival-date-chart-day {
  display: grid;
  align-content: end;
  gap: 8px;
  min-width: 0;
}

.arrival-date-bars {
  display: flex;
  align-items: end;
  justify-content: center;
  gap: 8px;
  height: 148px;
  padding: 8px 6px 0;
  border-bottom: 1px solid var(--line);
}

.arrival-date-bar-wrap {
  display: grid;
  justify-items: center;
  align-items: end;
  gap: 4px;
  width: 40px;
  color: var(--muted);
  font-size: 11px;
}

.arrival-date-bar {
  width: 22px;
  min-height: 6px;
  border-radius: 5px 5px 0 0;
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 24%);
}

.arrival-date-label {
  display: grid;
  justify-items: center;
  gap: 2px;
  min-height: 58px;
  text-align: center;
}

.arrival-date-label strong {
  color: var(--strong);
  font-size: 12px;
}

.arrival-date-label small {
  color: var(--muted);
  font-size: 11px;
}

.arrival-today-summary,
.arrival-today-table,
.arrival-file-detail {
  min-width: 0;
}

.arrival-detail-head,
.arrival-file-head {
  margin-top: 14px;
}

.arrival-file-controls {
  display: grid;
  grid-template-columns: 260px 180px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  margin-bottom: 14px;
}

.arrival-file-select,
.arrival-sheet-select {
  min-width: 0;
}

.arrival-file-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
  color: var(--muted);
  font-size: 12px;
}

.arrival-file-meta span {
  max-width: 100%;
  padding: 6px 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--panel-soft);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.arrival-file-detail {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.arrival-import-panel {
  display: grid;
  gap: 14px;
  justify-items: center;
  padding-top: 10px;
}

.arrival-import-actions {
  display: grid;
  width: min(760px, 100%);
  gap: 12px;
  align-items: center;
  justify-items: center;
}

.arrival-import-dropzone {
  width: 100%;
}

.arrival-import-preview {
  display: grid;
  width: 100%;
  gap: 12px;
}

.arrival-import-preview-layout {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 12px;
  align-items: stretch;
  max-height: min(62vh, 560px);
  overflow: hidden;
}

.arrival-import-file-list {
  display: grid;
  align-content: start;
  gap: 8px;
  min-height: 0;
  max-height: 100%;
  overflow: auto;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel-soft);
}

.arrival-import-file-list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 2px 2px 6px;
  color: var(--muted);
  font-size: 12px;
}

.arrival-import-file-list-head strong {
  color: var(--strong);
  font-size: 14px;
}

.arrival-import-file-item {
  display: grid;
  gap: 4px;
  width: 100%;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
  text-align: left;
  cursor: pointer;
}

.arrival-import-file-item:hover,
.arrival-import-file-item.is-active {
  border-color: color-mix(in srgb, var(--primary) 58%, var(--line));
  background: color-mix(in srgb, var(--primary) 9%, var(--panel));
}

.arrival-import-file-item strong {
  min-width: 0;
  color: var(--strong);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.arrival-import-file-item span {
  color: var(--muted);
  font-size: 12px;
}

.arrival-import-preview-main {
  display: grid;
  min-width: 0;
  min-height: 0;
  max-height: 100%;
  overflow: auto;
  gap: 12px;
}

.arrival-import-alert {
  margin: 0;
}

.arrival-import-button-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
}

@media (max-width: 1100px) {
  .arrival-today-layout,
  .arrival-file-detail,
  .arrival-file-controls,
  .arrival-import-preview-layout {
    grid-template-columns: 1fr;
  }
}
</style>
