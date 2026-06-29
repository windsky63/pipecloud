<script setup>
import * as VTable from '@visactor/vtable'
import { FilterPlugin } from '@visactor/vtable-plugins'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  fetchArrivalFileRows,
  fetchArrivalFiles,
  fetchCuttingPreSchedule,
  fetchCuttingVisualization,
  fetchInitializationStats,
  syncInitializationData,
  updateInitializationProjectMetrics,
  commitStagedPlan,
  fetchStagedPlanFileRows,
  generateFutureSchedule,
  fetchTodayArrival,
  fetchWeldingDashboard,
  uploadArrivalFileRequest,
} from '../../api/workflow'
import ArrivalModule from './ArrivalModule.vue'
import CuttingModule from './CuttingModule.vue'
import FutureScheduleModule from './FutureScheduleModule.vue'
import GenericModule from './GenericModule.vue'
import InitializationModule from './InitializationModule.vue'
import PrefabWorkspaceHeader from './PrefabWorkspaceHeader.vue'
import WeldingModule from './WeldingModule.vue'
import { selectedProjectId, selectedProjectParams } from '../../services/projectState'
import { localizedModuleTitle } from '../../services/navigationLabels'
import { getBasicVTableTheme, getVTablePalette, vTableThemeKey } from '../../services/vtableTheme'
import {
  errorMessage,
  formatSize,
  formatTime,
  lastRun,
  loadSummary,
  loading,
  runAction,
  runningKey,
  summary,
  t,
} from '../../services/pipecloudState'

const route = useRoute()
const router = useRouter()
const initializationLoading = ref(false)
const initializationError = ref('')
const initializationStats = ref({
  totalWeldCount: 0,
  prefabWeldCount: 0,
  autoWeldCount: 0,
  prefabRate: 0,
  autoRate: 0,
  unitCount: 0,
  units: [],
  sources: {},
})
const initializationSyncLoading = ref(false)
const initializationSyncMessage = ref('')
const initializationSyncError = ref('')
const projectMetricsLoading = ref(false)
const projectMetricsMessage = ref('')
const projectMetricsError = ref('')
const weldingDashboardLoading = ref(false)
const weldingDashboardError = ref('')
const weldingDashboard = ref({
  planCount: 0,
  historyPlanCount: 0,
  todayPlanCount: 0,
  totalRows: 0,
  completedRows: 0,
  completionRate: 0,
  historyTotalRows: 0,
  historyCompletedRows: 0,
  historyCompletionRate: 0,
  todayTotalRows: 0,
  todayCompletedRows: 0,
  todayCompletionRate: 0,
  recentPlans: [],
  cachePath: '',
  fromCache: false,
})
const weldingScheduleConfig = ref({
  weldDate: '',
  targetDiameter: '',
  ordersPerDay: '',
})
const weldingScheduleMessage = ref('')
const weldingScheduleError = ref('')
const weldingPendingStage = ref(null)
const weldingStageSaving = ref(false)
const futureScheduleLoading = ref(false)
const futureScheduleError = ref('')
const futureScheduleMessage = ref('')
const futurePendingStage = ref(null)
const futureStageSaving = ref(false)
const futurePendingPreviewLoading = ref(false)
const futurePendingPreviewError = ref('')
const futurePendingPreview = ref({
  file: null,
  sheet: '',
  sheets: [],
  total: 0,
  columns: [],
  rows: [],
})
const selectedFuturePendingFilePath = ref('')
const holidayConflictDialog = ref({
  show: false,
  dates: [],
  resolve: null,
})
const futureScheduleConfig = ref({
  dateMode: 'auto',
  weldStartDate: '',
  manualWeldDates: '',
  maxDays: '',
  targetDiameter: '',
  ordersPerDay: '',
  skipHolidays: true,
  holidayDates: '',
  canceledWeekendDates: '',
  cuttingLeadDays: '',
})
const arrivalActiveTab = ref('overview')
const arrivalLoading = ref(false)
const arrivalError = ref('')
const arrivalFiles = ref({
  path: '',
  total: 0,
  files: [],
})
const todayArrival = ref({
  date: '',
  file: null,
  sheet: '',
  sheets: [],
  total: 0,
  columns: [],
  rows: [],
  summary: {},
})
const arrivalFileDetail = ref({
  file: null,
  sheet: '',
  sheets: [],
  total: 0,
  columns: [],
  rows: [],
  summary: {},
})
const selectedArrivalFile = ref('')
const selectedArrivalSheet = ref('')
const arrivalImportCompleteKey = ref(0)
const cuttingLoading = ref(false)
const cuttingError = ref('')
const preScheduleLoading = ref(false)
const preScheduleError = ref('')
const preScheduleActiveSheet = ref('')
const preScheduleData = ref({
  path: '',
  sheet: '',
  sheets: [],
  total: 0,
  columns: [],
  rows: [],
})
const preScheduleOptions = ref({
  onlyAutoWeld: true,
})
const cuttingTableContainer = ref(null)
const cuttingTooltip = ref({
  visible: false,
  x: 0,
  y: 0,
  title: '',
  lines: [],
})
const cuttingData = ref({
  rows: [],
  total: 0,
  totalOriginalLength: 0,
  totalUsedLength: 0,
  totalRemainingLength: 0,
  averageUtilization: 0,
})
let cuttingVTable = null
const cuttingSegmentHitBoxes = new Map()
const cuttingSegmentMinWidth = 40
const cuttingMergeThreshold = 8
let resizeObserver = null

const activeModule = computed(() => {
  return summary.value.modules.find((item) => item.key === route.params.moduleKey) || summary.value.modules[0]
})

const activeModuleTitle = computed(() => {
  return localizedModuleTitle(activeModule.value)
})

const showCuttingVisualization = computed(() => activeModule.value?.key === 'cutting')
const showInitializationStats = computed(() => activeModule.value?.key === 'initialization')
const showWeldingDashboard = computed(() => activeModule.value?.key === 'welding')
const showFutureSchedule = computed(() => activeModule.value?.key === 'schedule')
const showCuttingChart = computed(() => showCuttingVisualization.value)
const showArrivalTabs = computed(() => activeModule.value?.key === 'arrival')
const cuttingOverviewActions = computed(() => {
  return activeModule.value?.actions?.filter((action) => !['weld-pre-schedule', 'confirm-cutting-pre-schedule'].includes(action.key)) || []
})
const cuttingPreScheduleAction = computed(() => {
  return activeModule.value?.actions?.find((action) => action.key === 'weld-pre-schedule') || null
})
const cuttingConfirmAction = computed(() => {
  return activeModule.value?.actions?.find((action) => action.key === 'confirm-cutting-pre-schedule') || null
})
const futureScheduleAction = computed(() => {
  return activeModule.value?.actions?.find((action) => action.key === 'future-schedule') || null
})
const weldingScheduleAction = computed(() => {
  return activeModule.value?.actions?.find((action) => action.key === 'auto-weld-schedule') || null
})
const weldingScheduleDefaults = computed(() => weldingScheduleAction.value?.defaults || {})
const futureScheduleDefaults = computed(() => futureScheduleAction.value?.defaults || {})
const futureScheduleDateModeOptions = computed(() => [
  { title: t('autoGenerateDates'), value: 'auto' },
  { title: t('manualSelectDates'), value: 'manual' },
])
const scheduleCalendarStart = computed(() => `${new Date().getFullYear()}-01-01`)
const scheduleCalendarEnd = computed(() => `${new Date().getFullYear() + 3}-12-31`)
const manualWeldDateList = computed(() => parseDateList(futureScheduleConfig.value.manualWeldDates))
const holidayDateList = computed(() => parseDateList(futureScheduleConfig.value.holidayDates))
const canceledWeekendDateList = computed(() => parseDateList(futureScheduleConfig.value.canceledWeekendDates))
const calendarWeekendDates = computed(() => weekendDatesBetween(scheduleCalendarStart.value, scheduleCalendarEnd.value))
const holidayCalendarDateList = computed(() => {
  if (!futureScheduleConfig.value.skipHolidays) return []
  const canceled = new Set(canceledWeekendDateList.value)
  return Array.from(new Set([
    ...calendarWeekendDates.value.filter((date) => !canceled.has(date)),
    ...holidayDateList.value,
  ])).sort()
})
const arrivalFileTableColumns = computed(() => [
  { field: 'name', title: t('fileName'), width: 300 },
  { field: 'path', title: t('backendPath'), width: 460 },
  { field: 'sizeText', title: t('size'), width: 120 },
  { field: 'updatedText', title: t('updatedAt'), width: 190 },
])
const arrivalSummaryTableColumns = computed(() => [
  { field: 'label', title: t('metric'), width: 150 },
  { field: 'value', title: t('quantity'), width: 130 },
])
const arrivalFileRows = computed(() => {
  return arrivalFiles.value.files.map((row) => ({
    ...row,
    sizeText: formatSize(row.size),
    updatedText: formatTime(row.updatedAt),
  }))
})
const arrivalFileOptions = computed(() => arrivalFiles.value.files.map((file) => ({
  title: file.name,
  value: file.name,
})))
const todayArrivalColumns = computed(() => buildDynamicColumns(todayArrival.value.columns))
const arrivalFileDetailColumns = computed(() => buildDynamicColumns(arrivalFileDetail.value.columns))
const futurePendingPreviewColumns = computed(() => buildDynamicColumns(futurePendingPreview.value.columns))
const todayArrivalSummaryRows = computed(() => buildArrivalSummaryRows(todayArrival.value.summary))
const arrivalFileDetailSummaryRows = computed(() => buildArrivalSummaryRows(arrivalFileDetail.value.summary))
const preScheduleTableColumns = computed(() => {
  return preScheduleData.value.columns.map((column) => ({
    field: column,
    title: column,
    width: 150,
  }))
})

function buildDynamicColumns(columns) {
  return (columns || []).map((column) => ({
    field: column,
    title: column || '-',
    width: Math.max(140, Math.min(String(column || '').length * 16 + 56, 280)),
  }))
}

function buildArrivalSummaryRows(summary = {}) {
  return [
    { label: t('arrivalMaterialRows'), value: summary.materialRows || 0 },
    { label: t('arrivalPipeRows'), value: summary.pipeRows || 0 },
    { label: t('arrivalFittingRows'), value: summary.fittingRows || 0 },
    { label: t('arrivalPipeCount'), value: summary.pipeCount || 0 },
    { label: t('arrivalTotalQuantity'), value: summary.totalQuantity || 0 },
  ]
}

function formatDateForInput(value) {
  if (!value) return ''
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    const year = value.getFullYear()
    const month = String(value.getMonth() + 1).padStart(2, '0')
    const day = String(value.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
  }
  const text = String(value).trim()
  const match = text.match(/^(\d{4})-?(\d{2})-?(\d{2})/)
  if (match) {
    return `${match[1]}-${match[2]}-${match[3]}`
  }
  const parsed = new Date(text)
  if (!Number.isNaN(parsed.getTime())) {
    return formatDateForInput(parsed)
  }
  return ''
}

function dateFromInput(value) {
  const text = formatDateForInput(value)
  if (!text) return null
  const [year, month, day] = text.split('-').map(Number)
  const date = new Date(year, month - 1, day)
  return Number.isNaN(date.getTime()) ? null : date
}

function isWeekendDate(value) {
  const date = dateFromInput(value)
  if (!date) return false
  return date.getDay() === 0 || date.getDay() === 6
}

function weekendDatesBetween(startValue, endValue) {
  const startDate = dateFromInput(startValue)
  const endDate = dateFromInput(endValue)
  if (!startDate || !endDate) return []

  const dates = []
  const cursor = new Date(startDate)
  while (cursor <= endDate) {
    const text = formatDateForInput(cursor)
    if (isWeekendDate(text)) {
      dates.push(text)
    }
    cursor.setDate(cursor.getDate() + 1)
  }
  return dates
}

function parseDateList(value) {
  const seen = new Set()
  return String(value || '')
    .replace(/，|；|;/g, ',')
    .split(',')
    .map(formatDateForInput)
    .filter((date) => {
      if (!date || seen.has(date)) return false
      seen.add(date)
      return true
    })
}

function setDateList(key, dates) {
  futureScheduleConfig.value[key] = dates.join(', ')
}

function updateDateList(key, value) {
  const dates = Array.isArray(value) ? value.map(formatDateForInput).filter(Boolean) : parseDateList(value)
  setDateList(key, Array.from(new Set(dates)).sort())
}

function isHolidaySelectedDate(value) {
  const date = formatDateForInput(value)
  return Boolean(date && futureScheduleConfig.value.skipHolidays && holidayCalendarDateList.value.includes(date))
}

function resolveHolidayConflict(confirmed) {
  const resolver = holidayConflictDialog.value.resolve
  holidayConflictDialog.value.show = false
  holidayConflictDialog.value.resolve = null
  if (resolver) resolver(confirmed)
}

function askHolidayConflict(dates) {
  holidayConflictDialog.value.dates = dates
  holidayConflictDialog.value.show = true
  return new Promise((resolve) => {
    holidayConflictDialog.value.resolve = resolve
  })
}

function markDateAsWorkday(value) {
  const date = formatDateForInput(value)
  if (!date) return
  if (isWeekendDate(date)) {
    setDateList('canceledWeekendDates', Array.from(new Set([...canceledWeekendDateList.value, date])).sort())
    return
  }
  setDateList('holidayDates', holidayDateList.value.filter((item) => item !== date).sort())
}

async function updateManualWeldDateList(value) {
  const nextDates = Array.isArray(value) ? Array.from(new Set(value.map(formatDateForInput).filter(Boolean))).sort() : parseDateList(value)
  const current = new Set(manualWeldDateList.value)
  const addedHolidayDates = nextDates.filter((date) => !current.has(date) && isHolidaySelectedDate(date))

  if (!addedHolidayDates.length) {
    setDateList('manualWeldDates', nextDates)
    return
  }

  const confirmed = await askHolidayConflict(addedHolidayDates)
  if (confirmed) {
    addedHolidayDates.forEach(markDateAsWorkday)
    setDateList('manualWeldDates', nextDates)
    return
  }

  const rejected = new Set(addedHolidayDates)
  setDateList('manualWeldDates', nextDates.filter((date) => !rejected.has(date)))
}

function updateHolidayDateList(value) {
  const selectedDates = Array.isArray(value) ? value.map(formatDateForInput).filter(Boolean) : parseDateList(value)
  const selectedSet = new Set(selectedDates)
  const allWeekendSet = new Set(calendarWeekendDates.value)
  const weekdayHolidays = selectedDates.filter((date) => !isWeekendDate(date))
  const canceledWeekends = calendarWeekendDates.value.filter((date) => !selectedSet.has(date))

  setDateList('holidayDates', Array.from(new Set(weekdayHolidays)).sort())
  setDateList('canceledWeekendDates', Array.from(new Set(canceledWeekends)).filter((date) => allWeekendSet.has(date)).sort())
}

function updateWeldStartDate(value) {
  futureScheduleConfig.value.weldStartDate = formatDateForInput(value)
}

function updateWeldingDate(value) {
  weldingScheduleConfig.value.weldDate = formatDateForInput(value)
}

function syncWeekendHolidayDates() {
  if (!futureScheduleConfig.value.skipHolidays) {
    setDateList('holidayDates', [])
    setDateList('canceledWeekendDates', [])
    return
  }
  setDateList('holidayDates', holidayDateList.value.filter((date) => !isWeekendDate(date)).sort())
  setDateList('canceledWeekendDates', canceledWeekendDateList.value.filter((date) => isWeekendDate(date)).sort())
}

function ensureModuleRoute() {
  if (!summary.value.modules.length) return
  const hasModule = summary.value.modules.some((item) => item.key === route.params.moduleKey)
  if (!hasModule) {
    router.replace(`/prefab/${summary.value.modules[0].key}`)
  }
}

function formatLength(length) {
  const number = Number(length)
  if (!Number.isFinite(number)) return '-'
  return `${number.toFixed(number % 1 === 0 ? 0 : 3)} m`
}

function formatCutLength(length) {
  const number = Number(length)
  if (!Number.isFinite(number)) return '-'
  return number.toFixed(number % 1 === 0 ? 0 : 3)
}

function formatCutLengthWithUnit(length) {
  return `${formatCutLength(length)} m`
}

function formatCutLengthInMillimeters(length) {
  const number = Number(length)
  if (!Number.isFinite(number)) return '-'
  return String(Math.round(number * 1000))
}

function hideCuttingTooltip() {
  cuttingTooltip.value = {
    visible: false,
    x: 0,
    y: 0,
    title: '',
    lines: [],
  }
}

function showCuttingTooltip(event, segment, pipe) {
  const nativeEvent = event?.event || event?.nativeEvent || event
  const clientX = nativeEvent?.clientX ?? 0
  const clientY = nativeEvent?.clientY ?? 0
  const isRemaining = segment.type === 'remaining'
  const tooltipWidth = 220
  const tooltipHeight = isRemaining ? 132 : 124
  const margin = 12
  const preferredX = clientX + 14
  const preferredY = clientY + 14
  const maxX = window.innerWidth - tooltipWidth - margin
  const maxY = window.innerHeight - tooltipHeight - margin
  cuttingTooltip.value = {
    visible: true,
    x: Math.max(margin, Math.min(preferredX, maxX)),
    y: Math.max(margin, Math.min(preferredY, maxY)),
    title: isRemaining ? t('remainingMaterial') : t('cutSegmentTitle', { index: segment.index }),
    lines: isRemaining
      ? [
          t('remainingLengthLine', { value: formatCutLengthWithUnit(segment.length) }),
          t('pipeNoLine', { value: pipe.pipeNo || '-' }),
          t('originalLengthLine', { value: formatCutLengthWithUnit(pipe.originalLength) }),
          t('utilizationLine', { value: pipe.utilization }),
        ]
      : segment.count > 1
        ? [
            t('singleDesignLengthLine', { value: formatCutLengthWithUnit(segment.length) }),
            t('mergedSegmentCountLine', { count: segment.count }),
            t('totalDesignLengthLine', { value: formatCutLengthWithUnit(segment.totalLength) }),
            t('totalConsumedLengthLine', { value: formatCutLengthWithUnit(segment.consumedLength) }),
            t('totalCuttingAllowanceLine', { value: formatCutLengthWithUnit(segment.lossLength) }),
            t('pipeNoLine', { value: pipe.pipeNo || '-' }),
          ]
      : [
          t('designLengthLine', { value: formatCutLengthWithUnit(segment.length) }),
          t('consumedLengthLine', { value: formatCutLengthWithUnit(segment.consumedLength) }),
          t('cuttingAllowanceLine', { value: formatCutLengthWithUnit(segment.lossLength) }),
          t('pipeNoLine', { value: pipe.pipeNo || '-' }),
        ],
  }
}

function releaseCuttingVTable() {
  if (cuttingVTable) {
    cuttingVTable.release()
    cuttingVTable = null
  }
  cuttingSegmentHitBoxes.clear()
  hideCuttingTooltip()
}

function cuttingVTableRecords() {
  return cuttingData.value.rows.map((pipe) => ({
    materialCode: pipe.materialCode,
    pipeNo: pipe.pipeNo || '-',
    originalLength: formatLength(pipe.originalLength),
    remainingLength: formatLength(pipe.remainingLength),
    cutSegments: pipe,
  }))
}

function cuttingSegmentElements(args) {
  const palette = getVTablePalette()
  const pipe = args.dataValue
  const cellWidth = args.table.getColWidth(args.col)
  const cellHeight = args.table.getRowHeight(args.row)
  const barX = 10
  const barY = Math.max((cellHeight - 28) / 2, 5)
  const barHeight = 28
  const barWidth = Math.max(cellWidth - 20, 80)
  const hitKey = `${args.col}:${args.row}`
  const hitBoxes = []
  const elements = [{
    type: 'rect',
    x: barX,
    y: barY,
    width: barWidth,
    height: barHeight,
    fill: palette.underlay,
    stroke: palette.frameLine,
    radius: 4,
  }]

  if (!pipe?.segments?.length || !pipe.originalLength) {
    cuttingSegmentHitBoxes.set(hitKey, { pipe, boxes: hitBoxes })
    return { elements, expectedHeight: 44, expectedWidth: cellWidth, renderDefault: false }
  }

  const displaySegments = buildDisplaySegments(pipe.segments)
  const displayWidths = calculateSegmentDisplayWidths(displaySegments, pipe.originalLength, barWidth)
  let x = barX
  displaySegments.forEach((segment, index) => {
    const isLast = index === displaySegments.length - 1
    const segmentWidth = isLast ? Math.max(barX + barWidth - x, 0) : Math.min(displayWidths[index], barX + barWidth - x)
    if (segmentWidth <= 0) return

    hitBoxes.push({
      segment,
      x1: x,
      x2: x + segmentWidth,
    })

    elements.push({
      type: 'rect',
      x,
      y: barY,
      width: segmentWidth,
      height: barHeight,
      fill: segment.type === 'cut' ? palette.cutFill : palette.remainingFill,
      stroke: palette.segmentStroke,
      lineWidth: 3,
      radius: 2,
    })

    if (segmentWidth >= 24) {
      elements.push({
        type: 'text',
        x: x + segmentWidth / 2,
        y: barY + barHeight / 2,
        text: formatSegmentLabel(segment),
        fill: palette.segmentText,
        fontSize: 12,
        fontWeight: segment.type === 'cut' ? 700 : 500,
        textAlign: 'center',
        textBaseline: 'middle',
        maxLineWidth: Math.max(segmentWidth - 6, 0),
        ellipsis: true,
      })
    }

    x += segmentWidth
  })

  cuttingSegmentHitBoxes.set(hitKey, { pipe, boxes: hitBoxes })
  return { elements, expectedHeight: 44, expectedWidth: cellWidth, renderDefault: false }
}

function buildDisplaySegments(segments) {
  const cutSegments = segments.filter((segment) => segment.type === 'cut')
  if (cutSegments.length <= cuttingMergeThreshold) return segments

  const mergedCuts = []
  const mergedByLength = new Map()

  cutSegments.forEach((segment) => {
    const lengthKey = String(Math.round(Number(segment.length) * 1000))
    const existing = mergedByLength.get(lengthKey)
    if (existing) {
      existing.count += 1
      existing.totalLength += Number(segment.length) || 0
      existing.consumedLength += Number(segment.consumedLength) || 0
      existing.lossLength += Number(segment.lossLength) || 0
      return
    }

    const merged = {
      ...segment,
      count: 1,
      totalLength: Number(segment.length) || 0,
      consumedLength: Number(segment.consumedLength) || 0,
      lossLength: Number(segment.lossLength) || 0,
      label: Number(segment.length) || 0,
    }
    mergedByLength.set(lengthKey, merged)
    mergedCuts.push(merged)
  })

  const remainingSegments = segments.filter((segment) => segment.type === 'remaining')
  return [...mergedCuts, ...remainingSegments]
}

function formatSegmentLabel(segment) {
  const label = formatCutLengthInMillimeters(segment.label)
  return segment.count > 1 ? `${label}x${segment.count}` : label
}

function calculateSegmentDisplayWidths(segments, originalLength, barWidth) {
  if (!segments.length || originalLength <= 0) return []

  const rawWidths = segments.map((segment) => {
    return (Number(segment.consumedLength || segment.length) / originalLength) * barWidth
  })

  if (segments.length * cuttingSegmentMinWidth > barWidth) {
    return segments.map(() => barWidth / segments.length)
  }

  const widths = rawWidths.slice()
  const fixed = new Set()

  while (true) {
    let changed = false
    widths.forEach((width, index) => {
      if (!fixed.has(index) && width < cuttingSegmentMinWidth) {
        widths[index] = cuttingSegmentMinWidth
        fixed.add(index)
        changed = true
      }
    })

    const fixedTotal = Array.from(fixed).reduce((total, index) => total + widths[index], 0)
    const flexibleIndexes = widths.map((_, index) => index).filter((index) => !fixed.has(index))
    const flexibleRawTotal = flexibleIndexes.reduce((total, index) => total + rawWidths[index], 0)
    const flexibleWidth = Math.max(barWidth - fixedTotal, 0)

    flexibleIndexes.forEach((index) => {
      widths[index] = flexibleRawTotal > 0 ? (rawWidths[index] / flexibleRawTotal) * flexibleWidth : 0
    })

    if (!changed || !flexibleIndexes.length) break
  }

  const total = widths.reduce((sum, width) => sum + width, 0)
  const diff = barWidth - total
  if (Math.abs(diff) > 0.01 && widths.length) {
    widths[widths.length - 1] += diff
  }
  return widths
}

function cuttingChartColumnWidth() {
  const containerWidth = cuttingTableContainer.value?.clientWidth || 1240
  return Math.max(containerWidth - 170 - 120 - 130 - 130 - 6, 620)
}

function cuttingVTableOptions() {
  const filterPlugin = new FilterPlugin({
    filterModes: ['byValue'],
  })
  const theme = getBasicVTableTheme()

  return {
    records: cuttingVTableRecords(),
    columns: [
      { field: 'materialCode', title: t('materialCode'), width: 170, sort: true, filter: true },
      { field: 'pipeNo', title: t('pipeNo'), width: 120, sort: true, filter: true },
      { field: 'originalLength', title: t('originalLength'), width: 130, sort: true, filter: true },
      { field: 'remainingLength', title: t('remainingMeters'), width: 130, sort: true, filter: true },
      {
        field: 'cutSegments',
        title: t('cuttingLength'),
        width: cuttingChartColumnWidth(),
        minWidth: 620,
        customRender: cuttingSegmentElements,
      },
    ],
    plugins: [filterPlugin],
    widthMode: 'standard',
    heightMode: 'standard',
    defaultRowHeight: 46,
    defaultHeaderRowHeight: 38,
    autoWrapText: false,
    tooltip: {
      isShowOverflowTextTooltip: true,
    },
    theme: {
      ...theme,
      frameStyle: {
        ...theme.frameStyle,
        borderLineWidth: [1, 0, 1, 0],
        cornerRadius: 6,
      },
      columnResize: {
        visibleOnHover: false,
      },
    },
  }
}

function handleCuttingCellMouseMove(event) {
  const col = event?.col
  const row = event?.row
  if (col !== 4 || typeof row !== 'number' || row < 1) {
    hideCuttingTooltip()
    return
  }

  const hitData = cuttingSegmentHitBoxes.get(`${col}:${row}`)
  const nativeEvent = event?.event || event?.nativeEvent || event
  const rect = cuttingTableContainer.value?.getBoundingClientRect()
  if (!hitData || !nativeEvent || !rect) {
    hideCuttingTooltip()
    return
  }

  const localX = nativeEvent.clientX - rect.left
  const cellLeft = 170 + 120 + 130 + 130
  const cellX = localX - cellLeft
  const hit = hitData.boxes.find((box) => cellX >= box.x1 && cellX <= box.x2)
  if (!hit) {
    hideCuttingTooltip()
    return
  }

  showCuttingTooltip(nativeEvent, hit.segment, hitData.pipe)
}

async function renderCuttingVTable() {
  await nextTick()
  if (!showCuttingChart.value || !cuttingTableContainer.value || !cuttingData.value.rows.length) {
    releaseCuttingVTable()
    return
  }

  if (cuttingVTable) {
    await cuttingVTable.updateOption(cuttingVTableOptions(), {
      clearColWidthCache: true,
      clearRowHeightCache: true,
    })
    return
  }
  cuttingVTable = new VTable.ListTable(cuttingTableContainer.value, cuttingVTableOptions())
  cuttingVTable.on(VTable.ListTable.EVENT_TYPE.MOUSEMOVE_CELL, handleCuttingCellMouseMove)
  cuttingVTable.on(VTable.ListTable.EVENT_TYPE.MOUSELEAVE_CELL, hideCuttingTooltip)
  cuttingVTable.on(VTable.ListTable.EVENT_TYPE.MOUSELEAVE_TABLE, hideCuttingTooltip)
}

async function setCuttingTableContainer(element) {
  cuttingTableContainer.value = element
  if (!element) {
    releaseCuttingVTable()
    if (resizeObserver) {
      resizeObserver.disconnect()
      resizeObserver = null
    }
    return
  }
  if (element) {
    await renderCuttingVTable()
    setupCuttingResizeObserver()
  }
}

function setupCuttingResizeObserver() {
  if (!showCuttingChart.value || resizeObserver || !cuttingTableContainer.value) return
  resizeObserver = new ResizeObserver(() => {
    if (cuttingVTable) {
      cuttingVTable.updateOption(cuttingVTableOptions(), {
        clearColWidthCache: true,
        clearRowHeightCache: true,
      })
    }
  })
  resizeObserver.observe(cuttingTableContainer.value)
}

async function loadInitializationStats() {
  if (!showInitializationStats.value) return
  initializationLoading.value = true
  initializationError.value = ''
  try {
    initializationStats.value = await fetchInitializationStats(selectedProjectParams())
  } catch (error) {
    initializationStats.value = {
      totalWeldCount: 0,
      prefabWeldCount: 0,
      autoWeldCount: 0,
      prefabRate: 0,
      autoRate: 0,
      unitCount: 0,
      units: [],
      sources: {},
    }
    initializationError.value = t('initializationStatsReadFailed', { message: error.message })
  } finally {
    initializationLoading.value = false
  }
}

async function syncCurrentInitializationData() {
  if (!showInitializationStats.value) return
  initializationSyncLoading.value = true
  initializationSyncMessage.value = ''
  initializationSyncError.value = ''
  try {
    const payload = await syncInitializationData(selectedProjectParams())
    if (payload.stats) {
      initializationStats.value = payload.stats
    }
    summary.value.modules = payload.summary || summary.value.modules
    initializationSyncMessage.value = t('initializationSyncedToMysql', { count: payload.total || 0 })
  } catch (error) {
    initializationSyncError.value = t('initializationSyncToMysqlFailed', { message: error.message })
  } finally {
    initializationSyncLoading.value = false
  }
}

async function updateCurrentProjectMetrics() {
  if (!showInitializationStats.value) return
  projectMetricsLoading.value = true
  projectMetricsMessage.value = ''
  projectMetricsError.value = ''
  try {
    const payload = await updateInitializationProjectMetrics(selectedProjectParams())
    summary.value.modules = payload.summary || summary.value.modules
    await loadSummary()
    await loadInitializationStats()
    const project = payload.project || {}
    projectMetricsMessage.value = t('projectMetricsUpdated', {
      segments: project.pipe_segment || 0,
      welds: project.prefab_weld_count || 0,
    })
  } catch (error) {
    projectMetricsError.value = t('projectMetricsUpdateFailed', { message: error.message })
  } finally {
    projectMetricsLoading.value = false
  }
}

function resetWeldingDashboard() {
  weldingDashboard.value = {
    planCount: 0,
    historyPlanCount: 0,
    todayPlanCount: 0,
    totalRows: 0,
    completedRows: 0,
    completionRate: 0,
    historyTotalRows: 0,
    historyCompletedRows: 0,
    historyCompletionRate: 0,
    todayTotalRows: 0,
    todayCompletedRows: 0,
    todayCompletionRate: 0,
    recentPlans: [],
    cachePath: '',
    fromCache: false,
  }
}

async function loadWeldingDashboard() {
  if (!showWeldingDashboard.value) return
  weldingDashboardLoading.value = true
  weldingDashboardError.value = ''
  try {
    weldingDashboard.value = await fetchWeldingDashboard(selectedProjectParams())
  } catch (error) {
    resetWeldingDashboard()
    weldingDashboardError.value = t('weldingDashboardReadFailed', { message: error.message })
  } finally {
    weldingDashboardLoading.value = false
  }
}

async function loadArrivalFiles() {
  if (!showArrivalTabs.value) return
  arrivalLoading.value = true
  arrivalError.value = ''
  try {
    const payload = await fetchArrivalFiles(selectedProjectParams())
    arrivalFiles.value = payload
    const hasSelectedFile = payload.files?.some((file) => file.name === selectedArrivalFile.value)
    if ((!selectedArrivalFile.value || !hasSelectedFile) && payload.files?.length) {
      selectedArrivalFile.value = payload.files[0].name
    }
    if (selectedArrivalFile.value) {
      await loadArrivalFileDetail(selectedArrivalFile.value)
    }
  } catch (error) {
    arrivalFiles.value = {
      path: '',
      total: 0,
      files: [],
    }
    arrivalFileDetail.value = {
      file: null,
      sheet: '',
      sheets: [],
      total: 0,
      columns: [],
      rows: [],
      summary: {},
    }
    arrivalError.value = t('arrivalFilesReadFailed', { message: error.message })
  } finally {
    arrivalLoading.value = false
  }
}

async function loadTodayArrival() {
  if (!showArrivalTabs.value) return
  arrivalLoading.value = true
  arrivalError.value = ''
  try {
    todayArrival.value = await fetchTodayArrival(selectedProjectParams())
  } catch (error) {
    todayArrival.value = {
      date: '',
      file: null,
      sheet: '',
      sheets: [],
      total: 0,
      columns: [],
      rows: [],
      summary: {},
    }
    arrivalError.value = t('todayArrivalReadFailed', { message: error.message })
  } finally {
    arrivalLoading.value = false
  }
}

async function loadArrivalFileDetail(fileName = selectedArrivalFile.value, sheet = selectedArrivalSheet.value) {
  if (!showArrivalTabs.value || !fileName) return
  arrivalLoading.value = true
  arrivalError.value = ''
  try {
    const payload = await fetchArrivalFileRows(selectedProjectParams(), fileName, sheet)
    arrivalFileDetail.value = payload
    selectedArrivalFile.value = payload.file?.name || fileName
    selectedArrivalSheet.value = payload.sheet || ''
  } catch (error) {
    arrivalFileDetail.value = {
      file: null,
      sheet: '',
      sheets: [],
      total: 0,
      columns: [],
      rows: [],
      summary: {},
    }
    arrivalError.value = t('arrivalFileReadFailed', { message: error.message })
  } finally {
    arrivalLoading.value = false
  }
}

async function changeArrivalFile(fileName) {
  selectedArrivalSheet.value = ''
  await loadArrivalFileDetail(fileName, '')
}

async function changeArrivalSheet(sheet) {
  await loadArrivalFileDetail(selectedArrivalFile.value, sheet)
}

async function confirmArrivalImport(payload) {
  const files = Array.isArray(payload) ? payload : Array.from(payload?.target?.files || [])
  if (payload?.target) payload.target.value = ''
  if (files.length) {
    await uploadArrivalFile(files)
  }
}

async function uploadArrivalFile(files) {
  arrivalLoading.value = true
  arrivalError.value = ''
  try {
    const payload = await uploadArrivalFileRequest(selectedProjectParams(), files)
    selectedArrivalFile.value = payload.file?.name || selectedArrivalFile.value
    selectedArrivalSheet.value = ''
    await loadArrivalFiles()
    await loadTodayArrival()
    await loadSummary()
    arrivalImportCompleteKey.value += 1
  } catch (error) {
    arrivalError.value = t('arrivalFileUploadFailed', { message: error.message })
  } finally {
    arrivalLoading.value = false
  }
}

async function loadPreScheduleRows(sheet = preScheduleActiveSheet.value) {
  if (!showCuttingVisualization.value) return
  preScheduleLoading.value = true
  preScheduleError.value = ''
  try {
    const params = selectedProjectParams()
    if (sheet) params.set('sheet', sheet)
    const payload = await fetchCuttingPreSchedule(params)
    preScheduleData.value = payload
    preScheduleActiveSheet.value = payload.sheet || ''
  } catch (error) {
    preScheduleData.value = {
      path: '',
      sheet: '',
      sheets: [],
      total: 0,
      columns: [],
      rows: [],
    }
    preScheduleError.value = t('preScheduleReadFailed', { message: error.message })
  } finally {
    preScheduleLoading.value = false
  }
}

async function changePreScheduleSheet(sheet) {
  preScheduleActiveSheet.value = sheet
  await loadPreScheduleRows(sheet)
}

async function loadCuttingVisualization() {
  if (!showCuttingVisualization.value) return
  cuttingLoading.value = true
  cuttingError.value = ''
  try {
    const payload = await fetchCuttingVisualization(selectedProjectParams())
    cuttingData.value = payload
    if (showCuttingChart.value) {
      await renderCuttingVTable()
      setupCuttingResizeObserver()
    }
  } catch (error) {
    cuttingData.value = {
      rows: [],
      total: 0,
      totalOriginalLength: 0,
      totalUsedLength: 0,
      totalRemainingLength: 0,
      averageUtilization: 0,
    }
    cuttingError.value = t('cuttingVisualizationReadFailed', { message: error.message })
    releaseCuttingVTable()
  } finally {
    cuttingLoading.value = false
  }
}

async function refreshWorkspace() {
  await loadSummary()
  ensureModuleRoute()
  await loadInitializationStats()
  await loadTodayArrival()
  await loadArrivalFiles()
  await loadWeldingDashboard()
  await loadPreScheduleRows()
  await loadCuttingVisualization()
}

async function executeAction(actionKey) {
  const options = actionOptionsPayload(actionKey)
  if (actionKey === 'auto-weld-schedule') {
    weldingScheduleError.value = ''
    weldingScheduleMessage.value = ''
  }
  await runAction(actionKey, options)
  if (actionKey === 'auto-weld-schedule') {
    const payload = lastRun.value || {}
    if (payload.ok && payload.stageToken) {
      weldingPendingStage.value = {
        token: payload.stageToken,
        files: buildStagedFileRows(payload.stagedFiles || []),
      }
      weldingScheduleMessage.value = t('plansStagedForSave', { count: payload.stagedFiles?.length || 0 })
    } else if (payload.ok) {
      weldingPendingStage.value = null
      weldingScheduleMessage.value = t('allPlansGenerated')
    }
  }
  if (showInitializationStats.value) {
    await loadSummary()
    await loadInitializationStats()
  }
  if (showCuttingVisualization.value && ['weld-pre-schedule', 'confirm-cutting-pre-schedule'].includes(actionKey)) {
    await loadSummary()
    await loadPreScheduleRows()
    await loadCuttingVisualization()
  }
  if (showWeldingDashboard.value && actionKey === 'auto-weld-schedule') {
    await loadSummary()
    await loadWeldingDashboard()
  }
}

function actionOptionsPayload(actionKey) {
  if (actionKey === 'weld-pre-schedule') {
    return { ...preScheduleOptions.value }
  }
  if (actionKey === 'auto-weld-schedule') {
    return { ...generationOptionsPayload(weldingScheduleConfig.value), stageOnly: true }
  }
  return {}
}

function generationOptionsPayload(config) {
  return Object.entries(config).reduce((payload, [key, value]) => {
    if (value !== '' && value !== null && value !== undefined) {
      payload[key] = value
    }
    return payload
  }, {})
}

function futureScheduleOptionsPayload() {
  return { ...generationOptionsPayload(futureScheduleConfig.value), stageOnly: true }
}

function buildStagedFileRows(files) {
  return (files || []).map((file) => {
    const path = typeof file === 'string' ? file : file.path
    const parts = String(path || '').includes(':')
      ? String(path || '').split(':')
      : String(path || '').split(/[\\/]/)
    return {
      path,
      sourceKey: typeof file === 'string' ? '' : file.sourceKey,
      name: typeof file === 'string' ? parts.at(-1) : file.name,
      planType: typeof file === 'string' ? parts[0] : file.planType,
      planDate: typeof file === 'string' ? parts[1] || '' : file.planDate,
      sizeText: typeof file === 'string' ? '-' : formatSize(file.size),
      updatedText: typeof file === 'string' ? '-' : formatTime(file.updatedAt),
    }
  })
}

function resetFuturePendingPreview() {
  futurePendingPreviewLoading.value = false
  futurePendingPreviewError.value = ''
  selectedFuturePendingFilePath.value = ''
  futurePendingPreview.value = {
    file: null,
    sheet: '',
    sheets: [],
    total: 0,
    columns: [],
    rows: [],
  }
}

async function loadFuturePendingFile(file, sheet = '') {
  if (!file || !futurePendingStage.value?.token) return
  selectedFuturePendingFilePath.value = file.path
  futurePendingPreviewLoading.value = true
  futurePendingPreviewError.value = ''
  try {
    const payload = await fetchStagedPlanFileRows(
      selectedProjectParams(),
      futurePendingStage.value.token,
      file.path,
      file.sourceKey,
      sheet,
    )
    if (selectedFuturePendingFilePath.value !== file.path) return
    futurePendingPreview.value = {
      file,
      sheet: payload.sheet || '',
      sheets: payload.sheets || [],
      total: payload.total || 0,
      columns: payload.columns || [],
      rows: payload.rows || [],
    }
  } catch (error) {
    if (selectedFuturePendingFilePath.value !== file.path) return
    futurePendingPreview.value = {
      file,
      sheet: '',
      sheets: [],
      total: 0,
      columns: [],
      rows: [],
    }
    futurePendingPreviewError.value = t('stagedPlanFileReadFailed', { message: error.message })
  } finally {
    if (selectedFuturePendingFilePath.value === file.path) {
      futurePendingPreviewLoading.value = false
    }
  }
}

function changeFuturePendingSheet(sheet) {
  const file = futurePendingPreview.value.file
  if (!file) return
  return loadFuturePendingFile(file, sheet)
}

async function executeFutureSchedule() {
  if (!futureScheduleAction.value) return
  futureScheduleLoading.value = true
  futureScheduleError.value = ''
  futureScheduleMessage.value = ''
  resetFuturePendingPreview()
  try {
    const payload = await generateFutureSchedule(selectedProjectParams(), futureScheduleOptionsPayload())
    lastRun.value = payload
    if (!payload.ok) {
      const detail = payload.stderr || payload.stdout || t('scriptReturnedCode', { code: payload.returnCode })
      throw new Error(detail)
    }
    summary.value.modules = payload.summary || summary.value.modules
    if (payload.stageToken) {
      futurePendingStage.value = {
        token: payload.stageToken,
        files: buildStagedFileRows(payload.stagedFiles || []),
      }
      futureScheduleMessage.value = t('plansStagedForSave', { count: payload.stagedFiles?.length || 0 })
    } else {
      futureScheduleMessage.value = t('allPlansGenerated')
      await loadSummary()
      await loadWeldingDashboard()
    }
  } catch (error) {
    futureScheduleError.value = t('futureScheduleGenerateFailed', { message: error.message })
  } finally {
    futureScheduleLoading.value = false
  }
}

async function commitPendingStage(stageRef, setMessage, setError, savingRef) {
  if (!stageRef.value?.token) return
  setError('')
  savingRef.value = true
  try {
    const payload = await commitStagedPlan(selectedProjectParams(), stageRef.value.token)
    summary.value.modules = payload.summary || summary.value.modules
    stageRef.value = null
    const warnings = Array.isArray(payload.syncWarnings) ? payload.syncWarnings.filter(Boolean) : []
    const warningText = warnings.length
      ? t('stagedPlansSavedWithWarnings', {
        count: payload.savedFiles?.length || 0,
        warnings: warnings.slice(0, 3).join('；'),
      })
      : t('stagedPlansSaved', { count: payload.savedFiles?.length || 0 })
    setMessage(warningText)
    await loadSummary()
    await loadWeldingDashboard()
  } catch (error) {
    setError(t('stagedPlansSaveFailed', { message: error.message }))
  } finally {
    savingRef.value = false
  }
}

function saveWeldingPendingStage() {
  return commitPendingStage(
    weldingPendingStage,
    (message) => { weldingScheduleMessage.value = message },
    (message) => { weldingScheduleError.value = message },
    weldingStageSaving,
  )
}

async function saveFuturePendingStage() {
  await commitPendingStage(
    futurePendingStage,
    (message) => { futureScheduleMessage.value = message },
    (message) => { futureScheduleError.value = message },
    futureStageSaving,
  )
  if (!futurePendingStage.value) resetFuturePendingPreview()
}

watch(() => summary.value.modules, ensureModuleRoute)
watch(
  [
    () => futureScheduleConfig.value.skipHolidays,
    () => futureScheduleConfig.value.dateMode,
    () => futureScheduleConfig.value.weldStartDate,
    () => futureScheduleConfig.value.maxDays,
    () => futureScheduleConfig.value.manualWeldDates,
    () => futureScheduleConfig.value.cuttingLeadDays,
    () => futureScheduleDefaults.value.weldStartDate,
    () => futureScheduleDefaults.value.cuttingLeadDays,
  ],
  syncWeekendHolidayDates,
  { immediate: true },
)
watch(() => route.params.moduleKey, async () => {
  ensureModuleRoute()
  if (showInitializationStats.value) {
    await loadInitializationStats()
  }
  if (showArrivalTabs.value) {
    await loadTodayArrival()
    await loadArrivalFiles()
  }
  if (showWeldingDashboard.value) {
    await loadWeldingDashboard()
  }
  if (showCuttingVisualization.value) {
    await loadPreScheduleRows()
    await loadCuttingVisualization()
  } else {
    releaseCuttingVTable()
  }
})
watch(selectedProjectId, refreshWorkspace)
watch(vTableThemeKey, async () => {
  if (cuttingVTable) {
    await cuttingVTable.updateOption(cuttingVTableOptions(), {
      clearColWidthCache: true,
      clearRowHeightCache: true,
    })
  }
})

onMounted(async () => {
  if (!summary.value.modules.length) {
  await loadSummary()
  }
  ensureModuleRoute()
  await loadInitializationStats()
  await loadTodayArrival()
  await loadArrivalFiles()
  await loadWeldingDashboard()
  await loadPreScheduleRows()
  await loadCuttingVisualization()
})

onBeforeUnmount(releaseCuttingVTable)
onBeforeUnmount(() => {
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
})
</script>

<template>
  <PrefabWorkspaceHeader :title="t('workspaceTitle')" :description="t('workspaceDescription')">
    <template #actions>
      <v-btn color="secondary" variant="tonal" :loading="loading || cuttingLoading || weldingDashboardLoading" prepend-icon="mdi-refresh" @click="refreshWorkspace">{{ t('refreshStatus') }}</v-btn>
    </template>
  </PrefabWorkspaceHeader>

  <v-alert v-if="errorMessage" :text="errorMessage" type="error" density="compact" class="status-alert" />

  <InitializationModule
    v-if="activeModule && showInitializationStats"
    :active-module="activeModule"
    :active-module-title="activeModuleTitle"
    :initialization-loading="initializationLoading"
    :initialization-stats="initializationStats"
    :initialization-error="initializationError"
    :initialization-sync-loading="initializationSyncLoading"
    :initialization-sync-message="initializationSyncMessage"
    :initialization-sync-error="initializationSyncError"
    :project-metrics-loading="projectMetricsLoading"
    :project-metrics-message="projectMetricsMessage"
    :project-metrics-error="projectMetricsError"
    :running-key="runningKey"
    @execute-action="executeAction"
    @refresh-stats="loadInitializationStats"
    @sync-initialization="syncCurrentInitializationData"
    @update-project-metrics="updateCurrentProjectMetrics"
  />

  <ArrivalModule
    v-else-if="activeModule && showArrivalTabs"
    :active-module="activeModule"
    :active-module-title="activeModuleTitle"
    :arrival-active-tab="arrivalActiveTab"
    :arrival-loading="arrivalLoading"
    :arrival-error="arrivalError"
    :today-arrival="todayArrival"
    :today-arrival-summary-rows="todayArrivalSummaryRows"
    :arrival-summary-table-columns="arrivalSummaryTableColumns"
    :today-arrival-columns="todayArrivalColumns"
    :arrival-file-options="arrivalFileOptions"
    :selected-arrival-file="selectedArrivalFile"
    :selected-arrival-sheet="selectedArrivalSheet"
    :arrival-file-detail="arrivalFileDetail"
    :arrival-file-detail-summary-rows="arrivalFileDetailSummaryRows"
    :arrival-file-detail-columns="arrivalFileDetailColumns"
    :arrival-files="arrivalFiles"
    :arrival-file-rows="arrivalFileRows"
    :arrival-file-table-columns="arrivalFileTableColumns"
    :arrival-import-complete-key="arrivalImportCompleteKey"
    :running-key="runningKey"
    @change-tab="arrivalActiveTab = $event"
    @execute-action="executeAction"
    @refresh-today-arrival="loadTodayArrival"
    @refresh-arrival-files="loadArrivalFiles"
    @confirm-arrival-import="confirmArrivalImport"
    @change-arrival-file="changeArrivalFile"
    @change-arrival-sheet="changeArrivalSheet"
  />

  <CuttingModule
    v-else-if="activeModule && showCuttingVisualization"
    :active-module="activeModule"
    :active-module-title="activeModuleTitle"
    :pre-schedule-loading="preScheduleLoading"
    :cutting-loading="cuttingLoading"
    :pre-schedule-data="preScheduleData"
    :pre-schedule-options="preScheduleOptions"
    :pre-schedule-active-sheet="preScheduleActiveSheet"
    :pre-schedule-error="preScheduleError"
    :pre-schedule-table-columns="preScheduleTableColumns"
    :cutting-data="cuttingData"
    :cutting-error="cuttingError"
    :cutting-tooltip="cuttingTooltip"
    :cutting-pre-schedule-action="cuttingPreScheduleAction"
    :cutting-confirm-action="cuttingConfirmAction"
    :cutting-overview-actions="cuttingOverviewActions"
    :running-key="runningKey"
    :format-length="formatLength"
    @execute-action="executeAction"
    @refresh-match-result="loadPreScheduleRows"
    @refresh-visualization="loadCuttingVisualization"
    @change-pre-schedule-sheet="changePreScheduleSheet"
    @table-container-ready="setCuttingTableContainer"
  />

  <FutureScheduleModule
    v-else-if="activeModule && showFutureSchedule"
    :active-module="activeModule"
    :active-module-title="activeModuleTitle"
    :future-schedule-loading="futureScheduleLoading"
    :future-schedule-error="futureScheduleError"
    :future-schedule-message="futureScheduleMessage"
    :future-pending-stage="futurePendingStage"
    :future-stage-saving="futureStageSaving"
    :future-pending-preview-loading="futurePendingPreviewLoading"
    :future-pending-preview-error="futurePendingPreviewError"
    :future-pending-preview="futurePendingPreview"
    :future-pending-preview-columns="futurePendingPreviewColumns"
    :selected-future-pending-file-path="selectedFuturePendingFilePath"
    :future-schedule-action="futureScheduleAction"
    :future-schedule-config="futureScheduleConfig"
    :future-schedule-defaults="futureScheduleDefaults"
    :future-schedule-date-mode-options="futureScheduleDateModeOptions"
    :schedule-calendar-start="scheduleCalendarStart"
    :schedule-calendar-end="scheduleCalendarEnd"
    :manual-weld-date-list="manualWeldDateList"
    :holiday-calendar-date-list="holidayCalendarDateList"
    :loading="loading"
    @execute-future-schedule="executeFutureSchedule"
    @refresh-status="loadSummary"
    @update-weld-start-date="updateWeldStartDate"
    @update-manual-weld-date-list="updateManualWeldDateList"
    @update-holiday-date-list="updateHolidayDateList"
    @preview-pending-file="loadFuturePendingFile"
    @change-pending-preview-sheet="changeFuturePendingSheet"
    @save-pending-stage="saveFuturePendingStage"
  />

  <WeldingModule
    v-else-if="activeModule && showWeldingDashboard"
    :active-module="activeModule"
    :active-module-title="activeModuleTitle"
    :welding-dashboard-loading="weldingDashboardLoading"
    :welding-dashboard="weldingDashboard"
    :welding-dashboard-error="weldingDashboardError"
    :welding-schedule-message="weldingScheduleMessage"
    :welding-schedule-error="weldingScheduleError"
    :welding-pending-stage="weldingPendingStage"
    :welding-stage-saving="weldingStageSaving"
    :welding-schedule-config="weldingScheduleConfig"
    :welding-schedule-defaults="weldingScheduleDefaults"
    :running-key="runningKey"
    @execute-action="executeAction"
    @refresh-dashboard="loadWeldingDashboard"
    @update-welding-date="updateWeldingDate"
    @save-pending-stage="saveWeldingPendingStage"
  />

  <GenericModule
    v-else-if="activeModule"
    :active-module="activeModule"
    :active-module-title="activeModuleTitle"
    :running-key="runningKey"
    @execute-action="executeAction"
  />
  <v-dialog v-model="holidayConflictDialog.show" max-width="460" persistent>
    <v-card class="schedule-confirm-dialog" variant="flat">
      <v-card-title>{{ t('holidayConflictTitle') }}</v-card-title>
      <v-card-text>
        {{ t('holidayConflictText', { dates: holidayConflictDialog.dates.join('、') }) }}
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="resolveHolidayConflict(false)">
          {{ t('cancel') }}
        </v-btn>
        <v-btn color="primary" variant="tonal" @click="resolveHolidayConflict(true)">
          {{ t('confirmUseWorkday') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

</template>

<style scoped>
.schedule-confirm-dialog {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
}

.schedule-confirm-dialog :deep(.v-card-title) {
  color: var(--strong);
  font-size: 16px;
  font-weight: 800;
}

.schedule-confirm-dialog :deep(.v-card-text) {
  color: var(--muted);
  line-height: 1.6;
}
</style>
