<script setup>
import * as VTable from '@visactor/vtable'
import { FilterPlugin } from '@visactor/vtable-plugins'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  fetchArrivalFileRows,
  fetchArrivalFiles,
  fetchArrivalDashboard,
  fetchAntiCorrosionDashboard,
  fetchAntiCorrosionPreSchedule,
  fetchCuttingDashboard,
  fetchCuttingPreSchedule,
  fetchCuttingVisualization,
  fetchMaterialLockingRows,
  fetchInitializationStats,
  commitStagedPlan,
  fetchStagedPlanFileRows,
  generateFutureSchedule,
  fetchTodayArrival,
  fetchWeldingDashboard,
  fetchWeldingPreSchedule,
  uploadArrivalFileRequest,
} from '../../api/workflow'
import ArrivalModule from './ArrivalModule.vue'
import AntiCorrosionModule from './AntiCorrosionModule.vue'
import CuttingModule from './CuttingModule.vue'
import FutureScheduleModule from './FutureScheduleModule.vue'
import GenericModule from './GenericModule.vue'
import InitializationModule from './InitializationModule.vue'
import PrefabWorkspaceHeader from './PrefabWorkspaceHeader.vue'
import WeldingModule from './WeldingModule.vue'
import { selectedProjectId, selectedProjectParams } from '../../services/projectState'
import { localizedModuleTitle } from '../../services/navigationLabels'
import { getBasicVTableTheme, getVTablePalette, vTableThemeKey } from '../../services/vtableTheme'
import { attachVTableColumnSelectionCount, createVTableSelectionLayout } from '../../services/vtableSelectionCount'
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
let workspaceLoadController = null
let workspaceLoadTimer = null
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
const weldingPreScheduleLoading = ref(false)
const weldingPreScheduleError = ref('')
const weldingPreScheduleActiveSheet = ref('')
const weldingPreScheduleData = ref({
  path: '',
  sheet: '',
  sheets: [],
  total: 0,
  columns: [],
  rows: [],
})
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
const materialLibraryConfirmDialog = ref({
  show: false,
  files: [],
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
const arrivalDashboardLoading = ref(false)
const arrivalDashboardError = ref('')
const arrivalDashboard = ref(emptyArrivalDashboard())
const antiCorrosionDashboardLoading = ref(false)
const antiCorrosionDashboardError = ref('')
const antiCorrosionDashboard = ref(emptyAntiCorrosionDashboard())
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
const cuttingDashboardLoading = ref(false)
const cuttingDashboardError = ref('')
const cuttingDashboard = ref(emptyCuttingDashboard())
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
  onlyAutoWeld: false,
  ignoreAntiCorrosionStatus: false,
  concentrationDimension: 'segment',
  concentrationThresholdPercent: 50,
})
const antiCorrosionPreScheduleOptions = ref({
  onlyAutoWeld: false,
  concentrationDimension: 'segment',
  concentrationThresholdPercent: 50,
})
const antiCorrosionCommissionOptions = ref({
  commissionArea: 400,
  dateMode: 'auto',
  weldStartDate: '',
  manualWeldDates: '',
  maxDays: '',
  skipHolidays: true,
  holidayDates: '',
  canceledWeekendDates: '',
})
const antiCorrosionCommissionMessage = ref('')
const antiCorrosionCommissionError = ref('')
const antiCorrosionPendingStage = ref(null)
const antiCorrosionStageSaving = ref(false)
const antiCorrosionPendingPreviewLoading = ref(false)
const antiCorrosionPendingPreviewError = ref('')
const antiCorrosionPendingPreview = ref({
  file: null,
  sheet: '',
  sheets: [],
  total: 0,
  columns: [],
  rows: [],
})
const antiCorrosionSelectedRows = ref([])
const antiCorrosionPreScheduleLoading = ref(false)
const antiCorrosionPreScheduleError = ref('')
const antiCorrosionPreScheduleActiveSheet = ref('')
const antiCorrosionPreScheduleData = ref({
  path: '',
  sheet: '',
  sheets: [],
  total: 0,
  columns: [],
  rows: [],
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
let releaseCuttingSelectionCount = null
const cuttingSegmentHitBoxes = new Map()
const cuttingSegmentMinWidth = 40
const cuttingMergeThreshold = 8
let resizeObserver = null

function emptyArrivalDashboard() {
  return {
    summaries: {
      pipe: { expectedQty: 0, actualQty: 0, requiredActualQty: 0, extraQty: 0, differenceQty: 0, arrivalRate: 0, materialCount: 0 },
      other: { expectedQty: 0, actualQty: 0, requiredActualQty: 0, extraQty: 0, differenceQty: 0, arrivalRate: 0, materialCount: 0 },
    },
    rows: [],
  }
}

function emptyAntiCorrosionDashboard() {
  return {
    planCount: 0,
    todayPlanCount: 0,
    commissionCount: 0,
    segmentCount: 0,
    totalArea: 0,
    preSchedule: {
      path: '',
      totalRows: 0,
      schedulableRows: 0,
      rejectedRows: 0,
      statusRows: [],
    },
    rows: [],
    recentPlans: [],
  }
}

function emptyCuttingDashboard() {
  return {
    planCount: 0,
    todayPlanCount: 0,
    orderCount: 0,
    todayOrderCount: 0,
    weldCount: 0,
    todayWeldCount: 0,
    diameterTotal: 0,
    preSchedule: {
      path: '',
      totalRows: 0,
      schedulableRows: 0,
      rejectedRows: 0,
      statusRows: [],
    },
    rows: [],
  }
}

const activeModule = computed(() => {
  return summary.value.modules.find((item) => item.key === route.params.moduleKey) || summary.value.modules[0]
})

const activeModuleTitle = computed(() => {
  return localizedModuleTitle(activeModule.value)
})

const showMaterialLocking = computed(() => activeModule.value?.key === 'materialLocking')
const showCuttingVisualization = computed(() => activeModule.value?.key === 'cutting')
const showInitializationStats = computed(() => activeModule.value?.key === 'initialization')
const showWeldingDashboard = computed(() => activeModule.value?.key === 'welding')
const showFutureSchedule = computed(() => activeModule.value?.key === 'schedule')
const showCuttingChart = computed(() => showMaterialLocking.value)
const showArrivalTabs = computed(() => activeModule.value?.key === 'arrival')
const showAntiCorrosionPreSchedule = computed(() => activeModule.value?.key === 'antiCorrosion')
const antiCorrosionPreScheduleAction = computed(() => {
  return activeModule.value?.actions?.find((action) => action.key === 'anti-corrosion-pre-schedule') || null
})
const antiCorrosionOverviewActions = computed(() => {
  return activeModule.value?.actions?.filter((action) => action.key !== 'anti-corrosion-pre-schedule') || []
})
const cuttingOverviewActions = computed(() => {
  return activeModule.value?.actions?.filter((action) => action.key !== 'weld-pre-schedule') || []
})
const cuttingPreScheduleAction = computed(() => {
  return activeModule.value?.actions?.find((action) => action.key === 'weld-pre-schedule') || null
})
const materialLockingAction = computed(() => {
  return activeModule.value?.actions?.find((action) => action.key === 'material-locking') || null
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
const pipelineConcentrationDimensionOptions = computed(() => [
  { title: t('segmentConcentration'), value: 'segment' },
  { title: t('weldConcentration'), value: 'weld' },
])
const scheduleCalendarStart = computed(() => `${new Date().getFullYear()}-01-01`)
const scheduleCalendarEnd = computed(() => `${new Date().getFullYear() + 3}-12-31`)
const manualWeldDateList = computed(() => parseDateList(futureScheduleConfig.value.manualWeldDates))
const holidayDateList = computed(() => parseDateList(futureScheduleConfig.value.holidayDates))
const canceledWeekendDateList = computed(() => parseDateList(futureScheduleConfig.value.canceledWeekendDates))
const antiCorrosionManualDateList = computed(() => parseDateList(antiCorrosionCommissionOptions.value.manualWeldDates))
const antiCorrosionHolidayDateList = computed(() => parseDateList(antiCorrosionCommissionOptions.value.holidayDates))
const antiCorrosionCanceledWeekendDateList = computed(() => parseDateList(antiCorrosionCommissionOptions.value.canceledWeekendDates))
const calendarWeekendDates = computed(() => weekendDatesBetween(scheduleCalendarStart.value, scheduleCalendarEnd.value))
const holidayCalendarDateList = computed(() => {
  if (!futureScheduleConfig.value.skipHolidays) return []
  const canceled = new Set(canceledWeekendDateList.value)
  return Array.from(new Set([
    ...calendarWeekendDates.value.filter((date) => !canceled.has(date)),
    ...holidayDateList.value,
  ])).sort()
})
const antiCorrosionHolidayCalendarDateList = computed(() => {
  if (!antiCorrosionCommissionOptions.value.skipHolidays) return []
  const canceled = new Set(antiCorrosionCanceledWeekendDateList.value)
  return Array.from(new Set([
    ...calendarWeekendDates.value.filter((date) => !canceled.has(date)),
    ...antiCorrosionHolidayDateList.value,
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

function setAntiCorrosionDateList(key, dates) {
  antiCorrosionCommissionOptions.value[key] = dates.join(', ')
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

function updateAntiCorrosionStartDate(value) {
  antiCorrosionCommissionOptions.value.weldStartDate = formatDateForInput(value)
}

function updateAntiCorrosionManualDateList(value) {
  const dates = Array.isArray(value) ? Array.from(new Set(value.map(formatDateForInput).filter(Boolean))).sort() : parseDateList(value)
  setAntiCorrosionDateList('manualWeldDates', dates)
}

function updateAntiCorrosionHolidayDateList(value) {
  const selectedDates = Array.isArray(value) ? value.map(formatDateForInput).filter(Boolean) : parseDateList(value)
  const selectedSet = new Set(selectedDates)
  const allWeekendSet = new Set(calendarWeekendDates.value)
  const weekdayHolidays = selectedDates.filter((date) => !isWeekendDate(date))
  const canceledWeekends = calendarWeekendDates.value.filter((date) => !selectedSet.has(date))

  setAntiCorrosionDateList('holidayDates', Array.from(new Set(weekdayHolidays)).sort())
  setAntiCorrosionDateList('canceledWeekendDates', Array.from(new Set(canceledWeekends)).filter((date) => allWeekendSet.has(date)).sort())
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
  releaseCuttingSelectionCount?.()
  releaseCuttingSelectionCount = null
  cuttingSegmentHitBoxes.clear()
  hideCuttingTooltip()
}

function cuttingVTableRecords() {
  return cuttingData.value.rows.map((pipe) => ({
    inventoryType: pipe.inventoryType || '-',
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
  return Math.max(containerWidth - 100 - 170 - 120 - 130 - 130 - 6, 620)
}

function cuttingVTableOptions() {
  const filterPlugin = new FilterPlugin({
    filterModes: ['byValue'],
  })
  const theme = getBasicVTableTheme()

  return {
    records: cuttingVTableRecords(),
    columns: [
      { field: 'inventoryType', title: t('inventoryType'), width: 100, sort: true, filter: true },
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
  const cuttingColumn = 5
  if (col !== cuttingColumn || typeof row !== 'number' || row < 1) {
    hideCuttingTooltip()
    return
  }

  const hitData = cuttingSegmentHitBoxes.get(`${col}:${row}`)
  const nativeEvent = event?.event || event?.nativeEvent || event
  const tableRect = cuttingVTable?.getElement?.()?.getBoundingClientRect?.()
  const rect = tableRect || cuttingTableContainer.value?.getBoundingClientRect()
  if (!hitData || !nativeEvent || !rect) {
    hideCuttingTooltip()
    return
  }

  const localX = nativeEvent.clientX - rect.left
  let cellLeft = 0
  for (let index = 0; index < cuttingColumn; index += 1) {
    cellLeft += Number(cuttingVTable?.getColWidth?.(index)) || 0
  }
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
  const selectionLayout = createVTableSelectionLayout(cuttingTableContainer.value)
  cuttingVTable = new VTable.ListTable(selectionLayout.viewport, cuttingVTableOptions())
  releaseCuttingSelectionCount = attachVTableColumnSelectionCount(cuttingVTable, selectionLayout)
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

async function loadInitializationStats(options = {}) {
  if (!showInitializationStats.value) return
  initializationLoading.value = true
  initializationError.value = ''
  try {
    const payload = await fetchInitializationStats(selectedProjectParams(), options)
    if (options.signal?.aborted) return
    initializationStats.value = payload
  } catch (error) {
    if (error?.name === 'AbortError') return
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
    if (!options.signal?.aborted) initializationLoading.value = false
  }
}

function syncAntiCorrosionWeekendHolidayDates() {
  if (!antiCorrosionCommissionOptions.value.skipHolidays) {
    setAntiCorrosionDateList('holidayDates', [])
    setAntiCorrosionDateList('canceledWeekendDates', [])
    return
  }
  setAntiCorrosionDateList('holidayDates', antiCorrosionHolidayDateList.value.filter((date) => !isWeekendDate(date)).sort())
  setAntiCorrosionDateList('canceledWeekendDates', antiCorrosionCanceledWeekendDateList.value.filter((date) => isWeekendDate(date)).sort())
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

async function loadWeldingDashboard(options = {}) {
  if (!showWeldingDashboard.value) return
  weldingDashboardLoading.value = true
  weldingDashboardError.value = ''
  try {
    const payload = await fetchWeldingDashboard(selectedProjectParams(), options)
    if (options.signal?.aborted) return
    weldingDashboard.value = payload
  } catch (error) {
    if (error?.name === 'AbortError') return
    resetWeldingDashboard()
    weldingDashboardError.value = t('weldingDashboardReadFailed', { message: error.message })
  } finally {
    if (!options.signal?.aborted) weldingDashboardLoading.value = false
  }
}

async function loadArrivalFiles(options = {}) {
  if (!showArrivalTabs.value) return
  arrivalLoading.value = true
  arrivalError.value = ''
  try {
    const payload = await fetchArrivalFiles(selectedProjectParams(), options)
    if (options.signal?.aborted) return
    arrivalFiles.value = payload
    const hasSelectedFile = payload.files?.some((file) => file.name === selectedArrivalFile.value)
    if ((!selectedArrivalFile.value || !hasSelectedFile) && payload.files?.length) {
      selectedArrivalFile.value = payload.files[0].name
    }
    if (selectedArrivalFile.value) {
      await loadArrivalFileDetail(selectedArrivalFile.value, '', options)
    }
  } catch (error) {
    if (error?.name === 'AbortError') return
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

async function loadTodayArrival(options = {}) {
  if (!showArrivalTabs.value) return
  arrivalLoading.value = true
  arrivalError.value = ''
  try {
    const payload = await fetchTodayArrival(selectedProjectParams(), options)
    if (options.signal?.aborted) return
    todayArrival.value = payload
  } catch (error) {
    if (error?.name === 'AbortError') return
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
    if (!options.signal?.aborted) arrivalLoading.value = false
  }
}

async function loadArrivalDashboard(options = {}) {
  if (!showArrivalTabs.value) return
  arrivalDashboardLoading.value = true
  arrivalDashboardError.value = ''
  try {
    const payload = await fetchArrivalDashboard(selectedProjectParams(), options)
    if (options.signal?.aborted) return
    arrivalDashboard.value = payload
  } catch (error) {
    if (error?.name === 'AbortError') return
    arrivalDashboard.value = emptyArrivalDashboard()
    arrivalDashboardError.value = t('arrivalDashboardReadFailed', { message: error.message })
  } finally {
    if (!options.signal?.aborted) arrivalDashboardLoading.value = false
  }
}

async function loadAntiCorrosionDashboard(options = {}) {
  if (!showAntiCorrosionPreSchedule.value) return
  antiCorrosionDashboardLoading.value = true
  antiCorrosionDashboardError.value = ''
  try {
    const payload = await fetchAntiCorrosionDashboard(selectedProjectParams(), options)
    if (options.signal?.aborted) return
    antiCorrosionDashboard.value = payload
  } catch (error) {
    if (error?.name === 'AbortError') return
    antiCorrosionDashboard.value = emptyAntiCorrosionDashboard()
    antiCorrosionDashboardError.value = t('antiCorrosionDashboardReadFailed', { message: error.message })
  } finally {
    if (!options.signal?.aborted) antiCorrosionDashboardLoading.value = false
  }
}

async function loadCuttingDashboard(options = {}) {
  if (!showCuttingVisualization.value) return
  cuttingDashboardLoading.value = true
  cuttingDashboardError.value = ''
  try {
    const payload = await fetchCuttingDashboard(selectedProjectParams(), options)
    if (options.signal?.aborted) return
    cuttingDashboard.value = payload
  } catch (error) {
    if (error?.name === 'AbortError') return
    cuttingDashboard.value = emptyCuttingDashboard()
    cuttingDashboardError.value = t('cuttingDashboardReadFailed', { message: error.message })
  } finally {
    if (!options.signal?.aborted) cuttingDashboardLoading.value = false
  }
}

async function loadArrivalFileDetail(fileName = selectedArrivalFile.value, sheet = selectedArrivalSheet.value, options = {}) {
  if (!showArrivalTabs.value || !fileName) return
  arrivalLoading.value = true
  arrivalError.value = ''
  try {
    const payload = await fetchArrivalFileRows(selectedProjectParams(), fileName, sheet, options)
    if (options.signal?.aborted) return
    arrivalFileDetail.value = payload
    selectedArrivalFile.value = payload.file?.name || fileName
    selectedArrivalSheet.value = payload.sheet || ''
  } catch (error) {
    if (error?.name === 'AbortError') return
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
    if (!options.signal?.aborted) arrivalLoading.value = false
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
    await loadArrivalDashboard()
    await loadSummary()
    arrivalImportCompleteKey.value += 1
  } catch (error) {
    arrivalError.value = t('arrivalFileUploadFailed', { message: error.message })
  } finally {
    arrivalLoading.value = false
  }
}

async function loadPreScheduleRows(sheet = preScheduleActiveSheet.value, options = {}) {
  if (!showCuttingVisualization.value && !showMaterialLocking.value) return
  preScheduleLoading.value = true
  preScheduleError.value = ''
  try {
    const params = selectedProjectParams()
    if (sheet) params.set('sheet', sheet)
    const payload = showMaterialLocking.value
      ? await fetchMaterialLockingRows(params, options)
      : await fetchCuttingPreSchedule(params, options)
    if (options.signal?.aborted) return
    preScheduleData.value = payload
    preScheduleActiveSheet.value = payload.sheet || ''
  } catch (error) {
    if (error?.name === 'AbortError') return
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
    if (!options.signal?.aborted) preScheduleLoading.value = false
  }
}

async function changePreScheduleSheet(sheet) {
  preScheduleActiveSheet.value = sheet
  await loadPreScheduleRows(sheet)
}

async function loadAntiCorrosionPreScheduleRows(
  sheet = antiCorrosionPreScheduleActiveSheet.value,
  options = {},
) {
  if (!showAntiCorrosionPreSchedule.value) return
  antiCorrosionPreScheduleLoading.value = true
  antiCorrosionPreScheduleError.value = ''
  try {
    const params = selectedProjectParams()
    if (sheet) params.set('sheet', sheet)
    const payload = await fetchAntiCorrosionPreSchedule(params, options)
    if (options.signal?.aborted) return
    antiCorrosionPreScheduleData.value = payload
    antiCorrosionPreScheduleActiveSheet.value = payload.sheet || ''
  } catch (error) {
    if (error?.name === 'AbortError') return
    antiCorrosionPreScheduleData.value = {
      path: '',
      sheet: '',
      sheets: [],
      total: 0,
      columns: [],
      rows: [],
    }
    antiCorrosionPreScheduleError.value = t('antiCorrosionPreScheduleReadFailed', { message: error.message })
  } finally {
    if (!options.signal?.aborted) antiCorrosionPreScheduleLoading.value = false
  }
}

async function changeAntiCorrosionPreScheduleSheet(sheet) {
  antiCorrosionPreScheduleActiveSheet.value = sheet
  await loadAntiCorrosionPreScheduleRows(sheet)
}

async function loadWeldingPreScheduleRows(
  sheet = weldingPreScheduleActiveSheet.value,
  options = {},
) {
  if (!showWeldingDashboard.value) return
  weldingPreScheduleLoading.value = true
  weldingPreScheduleError.value = ''
  try {
    const params = selectedProjectParams()
    if (sheet) params.set('sheet', sheet)
    const payload = await fetchWeldingPreSchedule(params, options)
    if (options.signal?.aborted) return
    weldingPreScheduleData.value = payload
    weldingPreScheduleActiveSheet.value = payload.sheet || ''
  } catch (error) {
    if (error?.name === 'AbortError') return
    weldingPreScheduleData.value = {
      path: '',
      sheet: '',
      sheets: [],
      total: 0,
      columns: [],
      rows: [],
    }
    weldingPreScheduleError.value = t('weldingPreScheduleReadFailed', { message: error.message })
  } finally {
    if (!options.signal?.aborted) weldingPreScheduleLoading.value = false
  }
}

async function changeWeldingPreScheduleSheet(sheet) {
  weldingPreScheduleActiveSheet.value = sheet
  await loadWeldingPreScheduleRows(sheet)
}

function resetAntiCorrosionPendingPreview() {
  antiCorrosionPendingPreviewLoading.value = false
  antiCorrosionPendingPreviewError.value = ''
  antiCorrosionPendingPreview.value = {
    file: null,
    sheet: '',
    sheets: [],
    total: 0,
    columns: [],
    rows: [],
  }
}

async function loadAntiCorrosionPendingFile(file, sheet = '') {
  if (!file || !antiCorrosionPendingStage.value?.token) return
  antiCorrosionPendingPreviewLoading.value = true
  antiCorrosionPendingPreviewError.value = ''
  try {
    const payload = await fetchStagedPlanFileRows(
      selectedProjectParams(),
      antiCorrosionPendingStage.value.token,
      file.path,
      file.sourceKey,
      sheet,
    )
    antiCorrosionPendingPreview.value = {
      file,
      sheet: payload.sheet || '',
      sheets: payload.sheets || [],
      total: payload.total || 0,
      columns: payload.columns || [],
      rows: payload.rows || [],
    }
  } catch (error) {
    if (error?.name === 'AbortError') return
    resetAntiCorrosionPendingPreview()
    antiCorrosionPendingPreviewError.value = t('stagedPlanFileReadFailed', { message: error.message })
  } finally {
    antiCorrosionPendingPreviewLoading.value = false
  }
}

function changeAntiCorrosionCommissionPreviewSheet(sheet) {
  const file = antiCorrosionPendingPreview.value.file || antiCorrosionPendingStage.value?.files?.[0]
  if (!file) return
  return loadAntiCorrosionPendingFile(file, sheet)
}

async function saveAntiCorrosionPendingStage() {
  if (!antiCorrosionPendingStage.value?.token) return
  antiCorrosionCommissionError.value = ''
  antiCorrosionStageSaving.value = true
  try {
    const payload = await commitStagedPlan(selectedProjectParams(), antiCorrosionPendingStage.value.token)
    summary.value.modules = payload.summary || summary.value.modules
    antiCorrosionPendingStage.value = null
    resetAntiCorrosionPendingPreview()
    antiCorrosionCommissionMessage.value = t('commissionSavedToLibrary', { count: payload.savedFiles?.length || 0 })
    await loadAntiCorrosionDashboard()
    await loadAntiCorrosionPreScheduleRows()
    await loadSummary()
  } catch (error) {
    antiCorrosionCommissionError.value = t('stagedPlansSaveFailed', { message: error.message })
  } finally {
    antiCorrosionStageSaving.value = false
  }
}

async function loadCuttingVisualization(options = {}) {
  if (!showMaterialLocking.value) return
  cuttingLoading.value = true
  cuttingError.value = ''
  try {
    const payload = await fetchCuttingVisualization(selectedProjectParams(), options)
    if (options.signal?.aborted) return
    cuttingData.value = payload
    if (showCuttingChart.value) {
      await renderCuttingVTable()
      setupCuttingResizeObserver()
    }
  } catch (error) {
    if (error?.name === 'AbortError') return
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
    if (!options.signal?.aborted) cuttingLoading.value = false
  }
}

async function loadActiveModuleData(options = {}) {
  await loadInitializationStats(options)
  await loadTodayArrival(options)
  await loadArrivalFiles(options)
  await loadArrivalDashboard(options)
  await loadWeldingDashboard(options)
  await loadWeldingPreScheduleRows(weldingPreScheduleActiveSheet.value, options)
  await loadAntiCorrosionDashboard(options)
  await loadAntiCorrosionPreScheduleRows(antiCorrosionPreScheduleActiveSheet.value, options)
  await loadCuttingVisualization(options)
  await loadCuttingDashboard(options)
  await loadPreScheduleRows(preScheduleActiveSheet.value, options)
}

function cancelWorkspaceLoad() {
  if (workspaceLoadTimer) {
    window.clearTimeout(workspaceLoadTimer)
    workspaceLoadTimer = null
  }
  workspaceLoadController?.abort()
  workspaceLoadController = null
  initializationLoading.value = false
  weldingDashboardLoading.value = false
  weldingPreScheduleLoading.value = false
  arrivalDashboardLoading.value = false
  antiCorrosionDashboardLoading.value = false
  cuttingDashboardLoading.value = false
  antiCorrosionPreScheduleLoading.value = false
  preScheduleLoading.value = false
  cuttingLoading.value = false
}

async function runWorkspaceLoad({ includeSummary = false } = {}) {
  cancelWorkspaceLoad()
  const controller = new AbortController()
  workspaceLoadController = controller
  const options = { signal: controller.signal }
  if (includeSummary) {
    await loadSummary(options)
  }
  ensureModuleRoute()
  if (!controller.signal.aborted) {
    await loadActiveModuleData(options)
  }
  if (workspaceLoadController === controller) {
    workspaceLoadController = null
  }
}

function scheduleWorkspaceLoad(options = {}) {
  cancelWorkspaceLoad()
  workspaceLoadTimer = window.setTimeout(() => {
    workspaceLoadTimer = null
    runWorkspaceLoad(options)
  }, 150)
}

async function refreshWorkspace() {
  await runWorkspaceLoad({ includeSummary: true })
}

async function executeAction(actionKey) {
  if (actionKey === 'arrival-library') {
    const shouldContinue = await confirmExistingMaterialLibraries()
    if (!shouldContinue) return
  }
  const options = actionOptionsPayload(actionKey)
  if (actionKey === 'auto-weld-schedule') {
    weldingScheduleError.value = ''
    weldingScheduleMessage.value = ''
  }
  if (actionKey === 'anti-corrosion-schedule') {
    antiCorrosionCommissionError.value = ''
    antiCorrosionCommissionMessage.value = ''
    antiCorrosionPendingStage.value = null
    resetAntiCorrosionPendingPreview()
  }
  const started = await runAction(actionKey, options)
  if (!started) return
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
  if (actionKey === 'anti-corrosion-schedule') {
    const payload = lastRun.value || {}
    if (payload.ok && payload.stageToken) {
      const files = buildStagedFileRows(payload.stagedFiles || [])
      antiCorrosionPendingStage.value = {
        token: payload.stageToken,
        files,
      }
      antiCorrosionCommissionMessage.value = t('commissionStagedForSave', { count: files.length })
      if (files[0]) {
        await loadAntiCorrosionPendingFile(files[0])
      }
    }
  }
  if (showInitializationStats.value) {
    await loadSummary()
    await loadInitializationStats()
  }
  if (showCuttingVisualization.value && actionKey === 'weld-pre-schedule') {
    await loadSummary()
    await loadCuttingDashboard()
    await loadPreScheduleRows()
  }
  if (showMaterialLocking.value && actionKey === 'material-locking') {
    await loadSummary()
    await loadPreScheduleRows()
    await loadCuttingVisualization()
  }
  if (showWeldingDashboard.value && ['welding-pre-schedule', 'auto-weld-schedule'].includes(actionKey)) {
    await loadSummary()
    await loadWeldingDashboard()
    await loadWeldingPreScheduleRows()
  }
  if (showAntiCorrosionPreSchedule.value && ['anti-corrosion-pre-schedule', 'anti-corrosion-schedule'].includes(actionKey)) {
    await loadSummary()
    await loadAntiCorrosionDashboard()
    await loadAntiCorrosionPreScheduleRows()
  }
  if (showArrivalTabs.value) {
    await loadArrivalDashboard()
  }
}

function existingMaterialLibraryFiles() {
  const libraryNames = new Set([
    '库管理/管子材料库.xlsx',
    '库管理/管件法兰材料库.xlsx',
    '库管理/防腐管子材料库.xlsx',
    '库管理/防腐管件法兰材料库.xlsx',
  ])
  return (summary.value.modules || [])
    .flatMap((module) => module.files || [])
    .filter((file) => libraryNames.has(file.name) && Number(file.count || 0) > 0)
    .map((file) => file.name.replace('库管理/', '').replace('.xlsx', ''))
}

function confirmExistingMaterialLibraries() {
  const files = existingMaterialLibraryFiles()
  if (!files.length) return Promise.resolve(true)
  return new Promise((resolve) => {
    materialLibraryConfirmDialog.value = {
      show: true,
      files,
      resolve,
    }
  })
}

function resolveMaterialLibraryConfirmation(confirmed) {
  const resolve = materialLibraryConfirmDialog.value.resolve
  materialLibraryConfirmDialog.value = {
    show: false,
    files: [],
    resolve: null,
  }
  resolve?.(confirmed)
}

function actionOptionsPayload(actionKey) {
  if (actionKey === 'weld-pre-schedule') {
    return {}
  }
  if (actionKey === 'anti-corrosion-pre-schedule') {
    return { ...antiCorrosionPreScheduleOptions.value }
  }
  if (actionKey === 'anti-corrosion-schedule') {
    return {
      ...antiCorrosionCommissionOptions.value,
      stageOnly: true,
      selectedLibrarySeqs: antiCorrosionSelectedRows.value
        .map((row) => row?.['库序号'])
        .filter((value) => value !== undefined && value !== null && String(value).trim() !== ''),
    }
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
    const name = typeof file === 'string' ? parts.at(-1) : file.name
    const planKey = typeof file === 'string' ? parts[0] : file.planKey
    const planDate = typeof file === 'string' ? parts[1] || '' : file.planDate
    const normalizedDate = String(planDate || '').replaceAll('-', '')
    const displayDate = normalizedDate.length === 8
      ? `${normalizedDate.slice(0, 4)}-${normalizedDate.slice(4, 6)}-${normalizedDate.slice(6)}`
      : String(planDate || '')
    const extensionIndex = String(name || '').lastIndexOf('.')
    const displayName = ['welding', 'cutting'].includes(planKey) && displayDate
      ? (
          extensionIndex > 0
            ? `${name.slice(0, extensionIndex)}-${displayDate}${name.slice(extensionIndex)}`
            : `${name}-${displayDate}`
        )
      : name
    return {
      path,
      sourceKey: typeof file === 'string' ? '' : file.sourceKey,
      name,
      displayName,
      planType: typeof file === 'string' ? parts[0] : (file.planName || file.planKey),
      planDate,
      weldDate: typeof file === 'string' ? parts[1] || '' : file.weldDate,
      cutDate: typeof file === 'string' ? '' : file.cutDate,
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
    if (error?.name === 'AbortError') return
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
watch(
  [
    () => antiCorrosionCommissionOptions.value.skipHolidays,
    () => antiCorrosionCommissionOptions.value.dateMode,
    () => antiCorrosionCommissionOptions.value.weldStartDate,
    () => antiCorrosionCommissionOptions.value.maxDays,
    () => antiCorrosionCommissionOptions.value.manualWeldDates,
  ],
  syncAntiCorrosionWeekendHolidayDates,
  { immediate: true },
)
watch(() => route.params.moduleKey, () => {
  ensureModuleRoute()
  if (!showMaterialLocking.value) {
    releaseCuttingVTable()
  }
  scheduleWorkspaceLoad()
})
const antiCorrosionPreScheduleTableColumns = computed(() => {
  return buildDynamicColumns(antiCorrosionPreScheduleData.value.columns)
})
const weldingPreScheduleTableColumns = computed(() => {
  return buildDynamicColumns(weldingPreScheduleData.value.columns)
})
const antiCorrosionCommissionPreviewColumns = computed(() => {
  return buildDynamicColumns(antiCorrosionPendingPreview.value.columns)
})
watch(selectedProjectId, () => scheduleWorkspaceLoad({ includeSummary: true }))
watch(vTableThemeKey, async () => {
  if (cuttingVTable) {
    await cuttingVTable.updateOption(cuttingVTableOptions(), {
      clearColWidthCache: true,
      clearRowHeightCache: true,
    })
  }
})

onMounted(async () => {
  await runWorkspaceLoad({ includeSummary: !summary.value.modules.length })
})

onBeforeUnmount(() => {
  cancelWorkspaceLoad()
  releaseCuttingVTable()
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
    :running-key="runningKey"
    @execute-action="executeAction"
    @refresh-stats="loadInitializationStats"
  />

  <ArrivalModule
    v-else-if="activeModule && showArrivalTabs"
    :active-module="activeModule"
    :active-module-title="activeModuleTitle"
    :arrival-active-tab="arrivalActiveTab"
    :arrival-loading="arrivalLoading"
    :arrival-error="arrivalError"
    :arrival-dashboard="arrivalDashboard"
    :arrival-dashboard-loading="arrivalDashboardLoading"
    :arrival-dashboard-error="arrivalDashboardError"
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
    @refresh-arrival-dashboard="loadArrivalDashboard"
    @refresh-arrival-files="loadArrivalFiles"
    @confirm-arrival-import="confirmArrivalImport"
    @change-arrival-file="changeArrivalFile"
    @change-arrival-sheet="changeArrivalSheet"
  />

  <CuttingModule
    v-else-if="activeModule && showMaterialLocking"
    :active-module="activeModule"
    :active-module-title="activeModuleTitle"
    :show-dashboard="false"
    :show-visualization="true"
    pre-schedule-title-key="materialMatchingLocking"
    pre-schedule-path-fallback-key="materialLockingResultDefaultPath"
    result-title-key="materialMatchingLockingResult"
    result-tip-key="materialMatchingLockingResultTip"
    :dashboard="cuttingDashboard"
    :dashboard-loading="cuttingDashboardLoading"
    :dashboard-error="cuttingDashboardError"
    :pre-schedule-loading="preScheduleLoading"
    :pre-schedule-data="preScheduleData"
    :pre-schedule-active-sheet="preScheduleActiveSheet"
    :pre-schedule-error="preScheduleError"
    :pre-schedule-table-columns="preScheduleTableColumns"
    :cutting-loading="cuttingLoading"
    :cutting-data="cuttingData"
    :cutting-error="cuttingError"
    :cutting-tooltip="cuttingTooltip"
    :cutting-pre-schedule-action="materialLockingAction"
    :cutting-overview-actions="[]"
    :running-key="runningKey"
    :format-length="formatLength"
    @execute-action="executeAction"
    @refresh-match-result="loadPreScheduleRows"
    @refresh-visualization="loadCuttingVisualization"
    @change-pre-schedule-sheet="changePreScheduleSheet"
    @table-container-ready="setCuttingTableContainer"
  />

  <AntiCorrosionModule
    v-else-if="activeModule && showAntiCorrosionPreSchedule"
    :active-module="activeModule"
    :active-module-title="activeModuleTitle"
    :dashboard="antiCorrosionDashboard"
    :dashboard-loading="antiCorrosionDashboardLoading"
    :dashboard-error="antiCorrosionDashboardError"
    :pre-schedule-action="antiCorrosionPreScheduleAction"
    :pre-schedule-options="antiCorrosionPreScheduleOptions"
    :commission-options="antiCorrosionCommissionOptions"
    :date-mode-options="futureScheduleDateModeOptions"
    :schedule-calendar-start="scheduleCalendarStart"
    :schedule-calendar-end="scheduleCalendarEnd"
    :manual-date-list="antiCorrosionManualDateList"
    :holiday-calendar-date-list="antiCorrosionHolidayCalendarDateList"
    :commission-message="antiCorrosionCommissionMessage"
    :commission-error="antiCorrosionCommissionError"
    :commission-pending-stage="antiCorrosionPendingStage"
    :commission-stage-saving="antiCorrosionStageSaving"
    :commission-preview-loading="antiCorrosionPendingPreviewLoading"
    :commission-preview-error="antiCorrosionPendingPreviewError"
    :commission-preview-data="antiCorrosionPendingPreview"
    :commission-preview-columns="antiCorrosionCommissionPreviewColumns"
    :concentration-dimension-options="pipelineConcentrationDimensionOptions"
    :overview-actions="antiCorrosionOverviewActions"
    :pre-schedule-loading="antiCorrosionPreScheduleLoading"
    :pre-schedule-error="antiCorrosionPreScheduleError"
    :pre-schedule-data="antiCorrosionPreScheduleData"
    :pre-schedule-active-sheet="antiCorrosionPreScheduleActiveSheet"
    :pre-schedule-table-columns="antiCorrosionPreScheduleTableColumns"
    :running-key="runningKey"
    @execute-action="executeAction"
    @change-pre-schedule-sheet="changeAntiCorrosionPreScheduleSheet"
    @change-commission-preview-sheet="changeAntiCorrosionCommissionPreviewSheet"
    @selection-change="antiCorrosionSelectedRows = $event.rows || []"
    @save-commission-stage="saveAntiCorrosionPendingStage"
    @preview-commission-file="loadAntiCorrosionPendingFile"
    @update-start-date="updateAntiCorrosionStartDate"
    @update-manual-date-list="updateAntiCorrosionManualDateList"
    @update-holiday-date-list="updateAntiCorrosionHolidayDateList"
  />

  <CuttingModule
    v-else-if="activeModule && showCuttingVisualization"
    :active-module="activeModule"
    :active-module-title="activeModuleTitle"
    :dashboard="cuttingDashboard"
    :dashboard-loading="cuttingDashboardLoading"
    :dashboard-error="cuttingDashboardError"
    :pre-schedule-loading="preScheduleLoading"
    :pre-schedule-data="preScheduleData"
    :pre-schedule-active-sheet="preScheduleActiveSheet"
    :pre-schedule-error="preScheduleError"
    :pre-schedule-table-columns="preScheduleTableColumns"
    :cutting-loading="cuttingLoading"
    :cutting-data="cuttingData"
    :cutting-error="cuttingError"
    :cutting-tooltip="cuttingTooltip"
    :cutting-pre-schedule-action="cuttingPreScheduleAction"
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
    :welding-pre-schedule-loading="weldingPreScheduleLoading"
    :welding-pre-schedule-error="weldingPreScheduleError"
    :welding-pre-schedule-data="weldingPreScheduleData"
    :welding-pre-schedule-active-sheet="weldingPreScheduleActiveSheet"
    :welding-pre-schedule-table-columns="weldingPreScheduleTableColumns"
    :running-key="runningKey"
    @execute-action="executeAction"
    @refresh-dashboard="loadWeldingDashboard"
    @update-welding-date="updateWeldingDate"
    @save-pending-stage="saveWeldingPendingStage"
    @change-welding-pre-schedule-sheet="changeWeldingPreScheduleSheet"
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

  <v-dialog v-model="materialLibraryConfirmDialog.show" max-width="520" persistent>
    <v-card class="schedule-confirm-dialog" variant="flat">
      <v-card-title>{{ t('materialLibraryExistsTitle') }}</v-card-title>
      <v-card-text>
        {{ t('materialLibraryExistsText', { files: materialLibraryConfirmDialog.files.join('、') }) }}
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="resolveMaterialLibraryConfirmation(false)">
          {{ t('cancel') }}
        </v-btn>
        <v-btn color="warning" variant="tonal" @click="resolveMaterialLibraryConfirmation(true)">
          {{ t('continueGenerateMaterialLibrary') }}
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
