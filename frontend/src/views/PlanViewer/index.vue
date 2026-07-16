<script setup>
import * as VTable from '@visactor/vtable'
import { InputEditor } from '@visactor/vtable-editors'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import {
  deletePlan,
  exportPlanPatchRows,
  fetchPlanFileRows,
  fetchPlanRows,
  importPlanPatchRows,
  movePlanDate,
  savePlanFileRows,
} from '../../api/plans'
import PlanViewerHeader from './PlanViewerHeader.vue'
import UnsavedChangesDialog from '../../components/UnsavedChangesDialog.vue'
import { formatSize, formatTime, t } from '../../services/pipecloudState'
import { selectedProjectId, selectedProjectParams } from '../../services/projectState'
import { getBasicVTableTheme, vTableThemeKey } from '../../services/vtableTheme'
import { attachVTableColumnSelectionCount, createVTableSelectionLayout } from '../../services/vtableSelectionCount'

const route = useRoute()
const router = useRouter()

const planTabs = [
  { key: 'anti-corrosion', titleKey: 'antiCorrosion', descriptionKey: 'antiCorrosionPlanDescription' },
  { key: 'cutting', titleKey: 'cutting', descriptionKey: 'cuttingPlanDescription' },
  { key: 'welding', titleKey: 'welding', descriptionKey: 'weldingPlanDescription' },
  { key: 'gantt', titleKey: 'planTable', descriptionKey: 'ganttPlanDescription' },
]

const WELDING_PRIMARY_FILE_NAME = '管段焊口表.xlsx'
const CUTTING_PRIMARY_FILE_NAME = '下料排产单.xlsx'
const CUTTING_DETAIL_FILE_NAME = '切管明细表.xlsx'
const CUTTING_SUMMARY_FILE_NAME = '切管汇总表.xlsx'
const ANTI_CORROSION_MATERIAL_FILE_NAME = '防腐材料单.xlsx'
const ANTI_CORROSION_WELD_FILE_NAME = '防腐焊口单.xlsx'

const loading = ref(false)
const fileLoading = ref(false)
const saving = ref(false)
const errorMessage = ref('')
const fileError = ref('')
const saveMessage = ref('')
const selectedDate = ref('')
const calendarMonth = ref('')
const ganttDate = ref('')
const ganttMonthMenu = ref(false)
const ganttDateMenu = ref(false)
const selectedPlan = ref(null)
const selectedFile = ref(null)
const selectedSheet = ref('')
const planImportInput = ref(null)
const planTableContainer = ref(null)
const movingPlanId = ref(null)
const deletingPlanId = ref(null)
const draggingPlan = ref(null)
const planTableViewTab = ref('calendar')
const pendingPlanDateMoves = ref([])
const planDateDialog = ref({
  show: false,
  plan: null,
  date: '',
})
const planDeleteDialog = ref({
  show: false,
  plan: null,
})
const planData = ref({
  key: '',
  name: '',
  selectedDate: '',
  dates: [],
  sources: [],
  timeline: [],
})
const fileData = ref({
  name: '',
  path: '',
  sheet: '',
  sheets: [],
  total: 0,
  columns: [],
  rows: [],
})
const editableRows = ref([])
const isDirty = ref(false)
const planSectionOpen = ref({
  today: true,
  future: true,
  history: true,
})
const unsavedChangesDialog = ref(null)
let planLoadRequestId = 0
let fileLoadRequestId = 0
let planVTable = null
let planTableResizeObserver = null
let releasePlanSelectionCount = null
const planTextEditor = new InputEditor()

const activePlanKey = computed(() => route.params.planKey || 'anti-corrosion')
const isGanttView = computed(() => activePlanKey.value === 'gantt')
const activePlan = computed(() => planTabs.find((item) => item.key === activePlanKey.value) || planTabs[0])
const activePlanTitle = computed(() => t(activePlan.value.titleKey))
const activePlanDescription = computed(() => t(activePlan.value.descriptionKey))
const activeSource = computed(() => planData.value.sources[0] || null)
const todayPlans = computed(() => activeSource.value?.todayPlans || [])
const futurePlans = computed(() => activeSource.value?.futurePlans || [])
const historyPlans = computed(() => activeSource.value?.historyPlans || [])
const isWeldingPlan = computed(() => activePlanKey.value === 'welding')
const isAntiCorrosionPlan = computed(() => activePlanKey.value === 'anti-corrosion')
const selectedPlanFiles = computed(() => sortedPlanFiles(selectedPlan.value?.files || []))
const usesGroupedPlanFiles = computed(() => ['anti-corrosion', 'welding', 'cutting'].includes(activePlanKey.value))
const primaryPlanFile = computed(() => selectedPlanFiles.value.find((file) => isPrimaryPlanFile(file)) || null)
const auxiliaryPlanFiles = computed(() => selectedPlanFiles.value.filter((file) => !isPrimaryPlanFile(file)))
const editableColumns = computed(() => fileData.value.columns || [])
const isSelectedTodayPlan = computed(() => {
  return Boolean(selectedPlan.value && todayPlans.value.some((plan) => plan.id === selectedPlan.value.id))
})
const isSelectedPrimaryEditableFile = computed(() => !usesGroupedPlanFiles.value || isPrimaryPlanFile(selectedFile.value))
const canEditSelectedFile = computed(() => {
  return Boolean(fileData.value.name && isSelectedTodayPlan.value && isSelectedPrimaryEditableFile.value && !fileLoading.value)
})
const calendarPlanMap = computed(() => applyPendingPlanMoves(buildCalendarPlanMap(planData.value.timeline || []), pendingPlanDateMoves.value))
const calendarModelValue = computed(() => {
  return calendarMonth.value || compactDateToIso(selectedDate.value) || formatCalendarMonth(new Date())
})
const calendarMonthTitle = computed(() => {
  const date = parseIsoDate(calendarModelValue.value)
  if (!date) return t('planTable')
  return `${date.getFullYear()}年${String(date.getMonth() + 1).padStart(2, '0')}月`
})
const currentMonthDays = computed(() => buildCurrentMonthDays(calendarModelValue.value))
const currentMonthRealDays = computed(() => currentMonthDays.value.filter((day) => !day.blank))
const ganttModelValue = computed(() => ganttDate.value || todayIso())
const ganttDay = computed(() => buildGanttDay(ganttModelValue.value))
const ganttHourColumns = computed(() => buildGanttHourColumns())
const ganttRows = computed(() => buildGanttRows(ganttDay.value, calendarPlanMap.value))
const planTablePeriodTitle = computed(() => {
  if (planTableViewTab.value === 'gantt') {
    return ganttModelValue.value
  }
  return calendarMonthTitle.value
})

function releasePlanVTable() {
  if (planVTable) {
    planVTable.release()
    planVTable = null
  }
  releasePlanSelectionCount?.()
  releasePlanSelectionCount = null
  if (planTableResizeObserver) {
    planTableResizeObserver.disconnect()
    planTableResizeObserver = null
  }
}

function planVTableOptions() {
  return {
    records: editableRows.value.map((row, index) => ({
      __index: index + 1,
      ...row,
    })),
    columns: [
      {
        field: '__index',
        title: '#',
        width: 64,
        fixed: 'left',
        headerStyle: { textAlign: 'center', fontWeight: 700 },
        style: { textAlign: 'center', color: '#64748b', fontWeight: 600 },
      },
      ...editableColumns.value.map((column) => ({
        field: column,
        title: column,
        width: 150,
        minWidth: 120,
        sort: true,
        editor: canEditSelectedFile.value ? planTextEditor : undefined,
        headerStyle: { fontWeight: 700 },
      })),
    ],
    editCellTrigger: ['doubleclick', 'keydown'],
    widthMode: 'standard',
    heightMode: 'standard',
    defaultRowHeight: 36,
    defaultHeaderRowHeight: 40,
    frozenColCount: 1,
    autoWrapText: false,
    keyboardOptions: {
      copySelected: true,
    },
    tooltip: {
      isShowOverflowTextTooltip: true,
    },
    theme: getBasicVTableTheme({ rowHeader: true }),
  }
}

async function renderPlanVTable() {
  await nextTick()
  if (!planTableContainer.value || !editableColumns.value.length) {
    releasePlanVTable()
    return
  }
  if (planVTable) {
    await planVTable.updateOption(planVTableOptions(), {
      clearColWidthCache: false,
      clearRowHeightCache: false,
    })
    return
  }

  const selectionLayout = createVTableSelectionLayout(planTableContainer.value)
  planVTable = new VTable.ListTable(selectionLayout.viewport, planVTableOptions())
  releasePlanSelectionCount = attachVTableColumnSelectionCount(planVTable, selectionLayout)
  planVTable.on(VTable.ListTable.EVENT_TYPE.CHANGE_CELL_VALUE, (event) => {
    const recordIndex = Array.isArray(event.recordIndex) ? event.recordIndex[0] : event.recordIndex
    if (!canEditSelectedFile.value || !Number.isInteger(recordIndex) || event.field === '__index') return
    const oldValue = editableRows.value[recordIndex]?.[event.field] ?? ''
    const newValue = event.changedValue ?? ''
    if (oldValue === newValue) return
    editableRows.value[recordIndex] = {
      ...editableRows.value[recordIndex],
      [event.field]: newValue,
    }
    isDirty.value = true
    saveMessage.value = ''
  })
  planTableResizeObserver = new ResizeObserver(() => {
    planVTable?.updateOption(planVTableOptions(), {
      clearColWidthCache: true,
      clearRowHeightCache: false,
    })
  })
  planTableResizeObserver.observe(planTableContainer.value)
}

function ensurePlanRoute() {
  if (!planTabs.some((item) => item.key === activePlanKey.value)) {
    router.replace('/plans/anti-corrosion')
  }
}

function parseCompactDate(date) {
  if (!/^\d{8}$/.test(String(date))) return null
  const year = Number(date.slice(0, 4))
  const month = Number(date.slice(4, 6)) - 1
  const day = Number(date.slice(6, 8))
  return new Date(year, month, day)
}

function formatCompactDate(date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}${month}${day}`
}

function formatDateIso(date) {
  return compactDateToIso(formatCompactDate(date))
}

function todayIso() {
  return formatDateIso(new Date())
}

function todayCompact() {
  return formatCompactDate(new Date())
}

function compactDateToIso(date) {
  if (!/^\d{8}$/.test(String(date))) return ''
  return `${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)}`
}

function isoDateToCompact(date) {
  return /^\d{4}-\d{2}-\d{2}$/.test(String(date)) ? String(date).replaceAll('-', '') : ''
}

function routePlanDate() {
  const date = route.query.date
  return /^\d{8}$/.test(String(date || '')) ? String(date) : ''
}

function parseIsoDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value))) return null
  const [year, month, day] = value.split('-').map(Number)
  return new Date(year, month - 1, day)
}

function formatCalendarMonth(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-01`
}

function normalizePlanName(plan) {
  const raw = plan?.planName || plan?.name || ''
  if (raw.includes('防腐')) return '防腐'
  if (raw.includes('下料')) return '下料'
  if (raw.includes('焊')) return '焊接'
  return raw
}

function calendarPlanClass(name) {
  if (name === '防腐') return 'is-anti'
  if (name === '下料') return 'is-cutting'
  return 'is-welding'
}

function calendarPlanColor(name) {
  if (name === '防腐') return 'success'
  if (name === '下料') return 'primary'
  return 'warning'
}


function planTooltipRows(plan) {
  const summary = plan?.summary || {}
  const rows = [
    { label: t('planDate'), value: compactDateToIso(plan?.planDate) || plan?.planDate || '-' },
  ]
  const orderNumbers = summary.orderNumbers || []
  if (orderNumbers.length) {
    rows.push({
      label: plan?.planKey === 'cutting' ? t('cuttingOrderNumbers') : t('weldingOrderNumbers'),
      value: orderNumbers.join('、'),
    })
  }
  const relatedOrderNumbers = summary.relatedOrderNumbers || []
  if (plan?.planKey === 'cutting' && relatedOrderNumbers.length) {
    rows.push({ label: t('relatedWeldingOrderNumbers'), value: relatedOrderNumbers.join('、') })
  }
  if (summary.weldCount !== undefined) {
    rows.push({ label: t('weldCount'), value: summary.weldCount })
  }
  if (plan?.planKey === 'anti-corrosion' && summary.commissionArea !== undefined) {
    rows.push({ label: t('commissionCoatingArea'), value: `${summary.commissionArea} ${t('squareMeterUnit')}` })
  }
  if (summary.diameterTotal !== undefined) {
    rows.push({ label: t('planDiameterTotal'), value: summary.diameterTotal })
  }
  return rows
}

function normalizeCalendarDate(value) {
  if (!value) return ''
  if (typeof value === 'string') return value
  if (value.date) return value.date
  if (value instanceof Date) {
    const year = value.getFullYear()
    const month = String(value.getMonth() + 1).padStart(2, '0')
    const day = String(value.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
  }
  return ''
}

function buildCalendarPlanMap(timeline) {
  return (timeline || []).reduce((map, day) => {
    const isoDate = compactDateToIso(day.date)
    if (!isoDate) return map
    map[isoDate] = (day.plans || []).flatMap((plan) => {
      const name = normalizePlanName(plan)
      const records = plan.records || []
      if (records.length) {
        return records.map((record) => ({
          id: record.id,
          planKey: record.planKey || plan.planKey,
          name,
          planFolder: record.planFolder,
          planDate: record.planDate || day.date,
          originalPlanDate: record.planDate || day.date,
          fileCount: record.fileCount || plan.fileCount || 0,
          summary: record.summary || plan.summary || {},
          available: true,
        }))
      }
      return [{
        id: `${plan.planKey}-${day.date}`,
        planKey: plan.planKey,
        name,
        planFolder: day.date,
        planDate: day.date,
        originalPlanDate: day.date,
        fileCount: plan.fileCount || 0,
        summary: plan.summary || {},
        available: Boolean(plan.available),
      }]
    })
      .filter((plan) => ['防腐', '下料', '焊接'].includes(plan.name))
      .filter((plan) => plan.available || plan.fileCount > 0)
    return map
  }, {})
}

function applyPendingPlanMoves(planMap, moves) {
  if (!moves.length) return planMap
  const nextMap = Object.fromEntries(Object.entries(planMap).map(([date, plans]) => [date, [...plans]]))
  moves.forEach((move) => {
    const sourceIso = compactDateToIso(move.originalDate)
    const targetIso = compactDateToIso(move.targetDate)
    if (!sourceIso || !targetIso) return
    const sourcePlans = nextMap[sourceIso] || []
    const sourceIndex = sourcePlans.findIndex((plan) => plan.id === move.plan.id)
    const sourcePlan = sourceIndex >= 0 ? sourcePlans[sourceIndex] : move.plan
    if (sourceIndex >= 0) {
      sourcePlans.splice(sourceIndex, 1)
      nextMap[sourceIso] = sourcePlans
    }
    nextMap[targetIso] = [
      ...(nextMap[targetIso] || []).filter((plan) => plan.id !== move.plan.id),
      {
        ...sourcePlan,
        planDate: move.targetDate,
        originalPlanDate: move.originalDate,
        pending: true,
      },
    ]
  })
  return nextMap
}

function dayPlans(date) {
  return calendarPlanMap.value[normalizeCalendarDate(date)] || []
}

function openCalendarPlan(date, plan) {
  const compactDate = isoDateToCompact(normalizeCalendarDate(date))
  if (!compactDate || !plan?.planKey) return
  router.push({
    name: 'plan-viewer',
    params: { planKey: plan.planKey },
    query: { date: compactDate },
  })
}

function setCalendarMonthFromTimeline(timeline, fallbackDate = selectedDate.value) {
  const firstTimelineDate = (timeline || []).find((day) => parseCompactDate(day.date))?.date
  calendarMonth.value = compactDateToIso(firstTimelineDate || fallbackDate) || formatCalendarMonth(new Date())
}

function moveCalendarMonth(offset) {
  const current = parseIsoDate(calendarModelValue.value) || new Date()
  current.setMonth(current.getMonth() + offset)
  calendarMonth.value = formatCalendarMonth(current)
}

function moveGanttDate(offset) {
  const current = parseIsoDate(ganttModelValue.value) || new Date()
  current.setDate(current.getDate() + offset)
  ganttDate.value = formatDateIso(current)
}

function normalizePickerDate(value) {
  const candidate = Array.isArray(value) ? value[0] : value
  if (candidate instanceof Date) return formatDateIso(candidate)
  const text = String(candidate || '').slice(0, 10)
  return parseIsoDate(text) ? text : ''
}

function selectGanttMonth(value) {
  const month = String(value || '').slice(0, 7)
  if (!/^\d{4}-\d{2}$/.test(month)) return
  const current = parseIsoDate(ganttModelValue.value) || new Date()
  const target = parseIsoDate(`${month}-01`)
  if (!target) return
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate()
  target.setDate(Math.min(current.getDate(), lastDay))
  ganttDate.value = formatDateIso(target)
  ganttMonthMenu.value = false
}

function selectGanttDate(value) {
  const selected = normalizePickerDate(value)
  if (!selected) return
  ganttDate.value = selected
  ganttDateMenu.value = false
}

function movePlanTablePeriod(offset) {
  if (planTableViewTab.value === 'gantt') {
    moveGanttDate(offset)
    return
  }
  moveCalendarMonth(offset)
}

function buildCurrentMonthDays(value) {
  const monthStart = parseIsoDate(value) || new Date()
  const year = monthStart.getFullYear()
  const month = monthStart.getMonth()
  const firstDay = new Date(year, month, 1)
  const leadingBlankCount = (firstDay.getDay() + 6) % 7
  const dayCount = new Date(year, month + 1, 0).getDate()
  const today = formatCompactDate(new Date())
  const days = Array.from({ length: leadingBlankCount }, (_, index) => ({
    key: `blank-start-${index}`,
    blank: true,
  }))
  for (let day = 1; day <= dayCount; day += 1) {
    const date = new Date(year, month, day)
    const compact = formatCompactDate(date)
    const iso = compactDateToIso(compact)
    days.push({
      key: iso,
      blank: false,
      day,
      compact,
      iso,
      weekday: date.getDay(),
      isToday: compact === today,
    })
  }
  const trailingBlankCount = (7 - (days.length % 7)) % 7
  for (let index = 0; index < trailingBlankCount; index += 1) {
    days.push({
      key: `blank-end-${index}`,
      blank: true,
    })
  }
  return days
}

function buildGanttDay(value) {
  const date = parseIsoDate(value) || new Date()
  const compact = formatCompactDate(date)
  return {
    key: compactDateToIso(compact),
    blank: false,
    day: date.getDate(),
    compact,
    iso: compactDateToIso(compact),
    isToday: compact === formatCompactDate(new Date()),
  }
}

function buildGanttHourColumns() {
  return Array.from({ length: 24 }, (_, hour) => ({
    key: String(hour),
    hour,
    label: `${String(hour).padStart(2, '0')}:00`,
    isMajor: hour % 6 === 0,
  }))
}

function buildGanttRows(day, planMap) {
  return ['防腐', '下料', '焊接'].map((name) => ({
    name,
    className: calendarPlanClass(name),
    items: (planMap[day.iso] || [])
      .filter((plan) => plan.name === name)
      .map((plan, planIndex) => {
        const range = planHourRange(plan)
        return {
          ...plan,
          key: `${day.iso}-${plan.id}`,
          day,
          row: planIndex,
          startColumn: range.startHour + 1,
          span: Math.max(range.endHour - range.startHour, 1),
          timeText: `${String(range.startHour).padStart(2, '0')}:00-${String(range.endHour).padStart(2, '0')}:00`,
        }
      }),
  }))
}

function planHourRange(plan) {
  const startHour = Number(plan.startHour ?? plan.start_hour ?? 0)
  const endHour = Number(plan.endHour ?? plan.end_hour ?? 24)
  return {
    startHour: Number.isInteger(startHour) && startHour >= 0 && startHour < 24 ? startHour : 0,
    endHour: Number.isInteger(endHour) && endHour > 0 && endHour <= 24 ? endHour : 24,
  }
}

function openPlanDateDialog(plan) {
  if (!plan?.id || movingPlanId.value === plan.id) return
  planDateDialog.value = {
    show: true,
    plan,
    date: todayIso(),
  }
}

function closePlanDateDialog() {
  planDateDialog.value = {
    show: false,
    plan: null,
    date: '',
  }
}

async function applyPlanDateDialog() {
  if (!planDateDialog.value.plan || !planDateDialog.value.date) return
  await updatePlanDate(planDateDialog.value.plan, planDateDialog.value.date)
  closePlanDateDialog()
}

function openPlanDeleteDialog(plan) {
  if (!plan?.id || deletingPlanId.value === plan.id) return
  planDeleteDialog.value = {
    show: true,
    plan,
  }
}

function closePlanDeleteDialog() {
  planDeleteDialog.value = {
    show: false,
    plan: null,
  }
}

async function confirmDeletePlan() {
  const plan = planDeleteDialog.value.plan
  if (!plan?.id || deletingPlanId.value) return
  deletingPlanId.value = plan.id
  errorMessage.value = ''
  fileError.value = ''
  try {
    await deletePlan(plan.planKey || activePlanKey.value, selectedProjectParams(), {
      recordId: plan.id,
    })
    if (selectedPlan.value?.id === plan.id) {
      selectedPlan.value = null
      selectedFile.value = null
      selectedSheet.value = ''
      fileData.value = {
        name: '',
        path: '',
        sheet: '',
        sheets: [],
        total: 0,
        columns: [],
        rows: [],
      }
      editableRows.value = []
      isDirty.value = false
      saveMessage.value = ''
      releasePlanVTable()
    }
    closePlanDeleteDialog()
    await loadPlan(selectedDate.value)
  } catch (error) {
    errorMessage.value = t('planDeleteFailed', { message: error.message })
  } finally {
    deletingPlanId.value = null
  }
}

function startDragPlan(plan) {
  draggingPlan.value = plan
}

function endDragPlan() {
  draggingPlan.value = null
}

async function dropPlanOnDate(day) {
  if (!draggingPlan.value || day.blank || !day.iso) return
  const plan = draggingPlan.value
  draggingPlan.value = null
  queuePlanDateMove(plan, day.iso)
}

function queuePlanDateMove(plan, targetIsoDate) {
  const targetDate = isoDateToCompact(targetIsoDate)
  const originalDate = plan.originalPlanDate || plan.planDate
  if (!plan?.id || !plan?.planKey || !targetDate || targetDate === originalDate) {
    pendingPlanDateMoves.value = pendingPlanDateMoves.value.filter((move) => move.plan.id !== plan?.id)
    return
  }
  pendingPlanDateMoves.value = [
    ...pendingPlanDateMoves.value.filter((move) => move.plan.id !== plan.id),
    {
      plan: {
        ...plan,
        originalPlanDate: originalDate,
      },
      originalDate,
      targetDate,
    },
  ]
}

function cancelPendingPlanMoves() {
  pendingPlanDateMoves.value = []
}

async function confirmPendingPlanMoves() {
  if (!pendingPlanDateMoves.value.length) return
  const moves = [...pendingPlanDateMoves.value]
  movingPlanId.value = 'pending'
  errorMessage.value = ''
  try {
    const params = selectedProjectParams()
    for (const move of moves) {
      await movePlanDate(move.plan.planKey, params, {
        recordId: move.plan.id,
        targetDate: move.targetDate,
      })
    }
    pendingPlanDateMoves.value = []
    await loadPlan(selectedDate.value)
  } catch (error) {
    errorMessage.value = t('planDateUpdateFailed', { message: error.message })
  } finally {
    movingPlanId.value = null
  }
}

async function updatePlanDate(plan, targetIsoDate) {
  const targetDate = isoDateToCompact(targetIsoDate)
  if (!plan?.id || !plan?.planKey || !targetDate || targetDate === plan.planDate) return
  movingPlanId.value = plan.id
  errorMessage.value = ''
  try {
    const params = selectedProjectParams()
    await movePlanDate(plan.planKey, params, {
      recordId: plan.id,
      targetDate,
    })
    const reloadDate = isGanttView.value ? selectedDate.value : targetDate
    await loadPlan(reloadDate)
    calendarMonth.value = formatCalendarMonth(parseIsoDate(targetIsoDate) || new Date())
  } catch (error) {
    errorMessage.value = t('planDateUpdateFailed', { message: error.message })
  } finally {
    movingPlanId.value = null
  }
}

function resetFileData() {
  fileLoadRequestId += 1
  selectedFile.value = null
  selectedSheet.value = ''
  fileError.value = ''
  saveMessage.value = ''
  editableRows.value = []
  isDirty.value = false
  fileData.value = {
    name: '',
    path: '',
    sheet: '',
    sheets: [],
    total: 0,
    columns: [],
    rows: [],
  }
}

function resetPlanSelection() {
  selectedPlan.value = null
  resetFileData()
}

function isWeldingPrimaryFile(file) {
  return file?.name === WELDING_PRIMARY_FILE_NAME || String(file?.name || '').startsWith('管段焊口表')
}

function planFileDisplayName(file) {
  const name = String(file?.name || '')
  return name
}

function isCuttingPrimaryFile(file) {
  const name = String(file?.name || '')
  return name === CUTTING_PRIMARY_FILE_NAME || name.includes('下料排产单')
}

function isCuttingDetailFile(file) {
  const name = String(file?.name || '')
  return name === CUTTING_DETAIL_FILE_NAME || name.includes('切管明细表')
}

function isCuttingSummaryFile(file) {
  const name = String(file?.name || '')
  return name === CUTTING_SUMMARY_FILE_NAME || name.includes('切管汇总表')
}

function isAntiCorrosionMaterialFile(file) {
  const name = String(file?.name || '')
  return name === ANTI_CORROSION_MATERIAL_FILE_NAME || name.includes('防腐材料单')
}

function isAntiCorrosionWeldFile(file) {
  const name = String(file?.name || '')
  return name === ANTI_CORROSION_WELD_FILE_NAME || name.includes('防腐焊口单')
}

function isPrimaryPlanFile(file) {
  if (isWeldingPlan.value) return isWeldingPrimaryFile(file)
  if (activePlanKey.value === 'cutting') return isCuttingPrimaryFile(file)
  if (isAntiCorrosionPlan.value) return isAntiCorrosionMaterialFile(file)
  return false
}

function sortedPlanFiles(files) {
  const list = [...files]
  if (!usesGroupedPlanFiles.value) return list
  return list.sort((left, right) => {
    const leftPrimary = isPrimaryPlanFile(left) ? 0 : isCuttingDetailFile(left) || isCuttingSummaryFile(left) || isAntiCorrosionWeldFile(left) ? 1 : 2
    const rightPrimary = isPrimaryPlanFile(right) ? 0 : isCuttingDetailFile(right) || isCuttingSummaryFile(right) || isAntiCorrosionWeldFile(right) ? 1 : 2
    if (leftPrimary !== rightPrimary) return leftPrimary - rightPrimary
    return String(left.name || '').localeCompare(String(right.name || ''), 'zh-Hans-CN')
  })
}

function defaultPlanFile(plan) {
  const files = sortedPlanFiles(plan?.files || [])
  if (!usesGroupedPlanFiles.value) return files[0] || null
  return files.find((file) => isPrimaryPlanFile(file)) || files[0] || null
}

function defaultPlanForDate(source, date) {
  const compactDate = String(date || '').replaceAll('-', '')
  const plans = [
    ...(source?.todayPlans || []),
    ...(source?.futurePlans || []),
    ...(source?.historyPlans || []),
  ]
  if (!compactDate) return plans[0] || null
  return plans.find((plan) => String(plan.planDate || plan.planFolder || '').replaceAll('-', '') === compactDate) || plans[0] || null
}

function togglePlanSection(sectionKey) {
  planSectionOpen.value = {
    ...planSectionOpen.value,
    [sectionKey]: !planSectionOpen.value[sectionKey],
  }
}

async function loadPlan(date = selectedDate.value) {
  ensurePlanRoute()
  const requestId = ++planLoadRequestId
  const requestKey = isGanttView.value ? 'all' : activePlanKey.value
  const requestedDate = date || todayCompact()
  loading.value = true
  errorMessage.value = ''
  try {
    const params = selectedProjectParams()
    if (requestedDate) params.set('date', requestedDate)
    const payload = await fetchPlanRows(requestKey, params)
    if (requestId !== planLoadRequestId) return
    planData.value = payload
    selectedDate.value = payload.selectedDate || ''
    if (isGanttView.value && !calendarMonth.value) {
      setCalendarMonthFromTimeline(payload.timeline || [], payload.selectedDate)
    }
    resetPlanSelection()
    if (!isGanttView.value) {
      const source = payload.sources?.[0]
      const initialPlan = defaultPlanForDate(source, requestedDate)
      if (initialPlan) {
        await selectPlan(initialPlan)
      }
    }
  } catch (error) {
    if (requestId !== planLoadRequestId) return
    planData.value = {
      key: '',
      name: '',
      selectedDate: '',
      dates: [],
      sources: [],
      timeline: [],
    }
    resetPlanSelection()
    errorMessage.value = t('planFileReadFailed', { message: error.message })
  } finally {
    if (requestId === planLoadRequestId) {
      loading.value = false
    }
  }
}

async function selectPlan(plan, options = {}) {
  selectedPlan.value = plan
  selectedDate.value = plan.planDate || selectedDate.value
  resetFileData()
  if (options.openDefaultFile !== false) {
    const file = defaultPlanFile(plan)
    if (file) {
      await loadFile(file)
    }
  }
}

async function loadFile(file, sheet = '') {
  if (!file || !selectedPlan.value || isGanttView.value) return
  const requestId = ++fileLoadRequestId
  const requestedSheet = typeof sheet === 'string' ? sheet : ''
  const isSameFile = selectedFile.value?.path === file.path
  selectedFile.value = file
  selectedSheet.value = requestedSheet
  if (!isSameFile) {
    fileData.value = {
      name: file.name,
      path: file.path,
      sheet: requestedSheet,
      sheets: [],
      total: 0,
      columns: [],
      rows: [],
    }
    editableRows.value = []
  }
  isDirty.value = false
  saveMessage.value = ''
  fileLoading.value = true
  fileError.value = ''
  try {
    const params = selectedProjectParams({
      date: selectedPlan.value.planDate || selectedDate.value,
      planFolder: selectedPlan.value.planFolder || selectedPlan.value.name,
      file: file.name,
    })
    if (requestedSheet) params.set('sheet', requestedSheet)
    const payload = await fetchPlanFileRows(activePlanKey.value, params)
    if (requestId !== fileLoadRequestId) return
    fileData.value = payload
    editableRows.value = cloneRows(payload.rows || [])
    isDirty.value = false
    saveMessage.value = ''
    selectedSheet.value = payload.sheet || ''
  } catch (error) {
    if (requestId !== fileLoadRequestId) return
    fileData.value = {
      name: file.name,
      path: file.path,
      sheet: '',
      sheets: [],
      total: 0,
      columns: [],
      rows: [],
    }
    editableRows.value = []
    isDirty.value = false
    selectedSheet.value = ''
    fileError.value = t('planFileContentReadFailed', { message: error.message })
  } finally {
    if (requestId === fileLoadRequestId) {
      fileLoading.value = false
    }
  }
}

async function changeSheet(sheet) {
  if (typeof sheet !== 'string' || !sheet || sheet === selectedSheet.value || !fileData.value.sheets.includes(sheet)) {
    return
  }
  if (isDirty.value && !(await confirmDiscardUnsaved(t('unsavedSheetSwitchConfirm')))) {
    return
  }
  selectedSheet.value = sheet
  await loadFile(selectedFile.value, sheet)
}

async function confirmDiscardUnsaved(text = t('unsavedLeaveConfirm')) {
  if (!isDirty.value) return true
  return unsavedChangesDialog.value?.open({ text }) ?? true
}

async function confirmLeaveWithUnsyncedChanges() {
  return confirmDiscardUnsaved()
}

function handleBeforeUnload(event) {
  if (!isDirty.value) return
  event.preventDefault()
  event.returnValue = t('unsavedLeaveConfirm')
}

function cloneRows(rows) {
  return rows.map((row) => ({ ...row }))
}

function ensureEditableColumn(candidates, fallback) {
  const existingColumn = candidates.find((column) => editableColumns.value.includes(column))
  if (existingColumn) return existingColumn
  fileData.value = {
    ...fileData.value,
    columns: [...fileData.value.columns, fallback],
  }
  return fallback
}

function ensureCompletionColumn() {
  if (activePlanKey.value === 'anti-corrosion' && !isAntiCorrosionMaterialFile(selectedFile.value || fileData.value)) {
    const antiCandidates = ['材料防腐状态', '防腐状态', '是否防腐完成', '防腐完成状态']
    return ensureEditableColumn(antiCandidates, '材料防腐状态')
  }
  if (activePlanKey.value === 'cutting') {
    const cuttingCandidates = ['材料下料状态', '下料状态', '是否下料完成', '下料完成状态', '是否完成']
    return ensureEditableColumn(cuttingCandidates, '材料下料状态')
  }
  const candidates = ['材料焊接状态', '是否完成', '完成状态', '完工状态', '状态']
  return ensureEditableColumn(candidates, '材料焊接状态')
}

function markAntiCorrosionMaterialCompleted() {
  const commissionAreaColumn = '委托面积'
  const completedAreaColumn = ensureEditableColumn(['已完成面积'], '已完成面积')
  editableRows.value = editableRows.value.map((row) => ({
    ...row,
    [completedAreaColumn]: row[commissionAreaColumn] ?? row[completedAreaColumn] ?? '',
  }))
}

function completedRowsPayload(columns, rows, candidates, fallback, value) {
  const completionColumn = candidates.find((column) => columns.includes(column)) || fallback
  const nextColumns = columns.includes(completionColumn) ? [...columns] : [...columns, completionColumn]
  return {
    columns: nextColumns,
    rows: rows.map((row) => ({
      ...row,
      [completionColumn]: value,
    })),
  }
}

async function completeAllCuttingSheets() {
  if (!selectedFile.value || !selectedPlan.value || !fileData.value.sheets.length) return
  const file = selectedFile.value
  const currentSheet = selectedSheet.value
  const sheets = [...fileData.value.sheets]
  const candidates = ['材料下料状态', '下料状态', '是否下料完成', '下料完成状态', '是否完成']
  saving.value = true
  fileError.value = ''
  saveMessage.value = ''
  try {
    for (const sheet of sheets) {
      let columns
      let rows
      if (sheet === currentSheet) {
        columns = [...editableColumns.value]
        rows = cloneRows(editableRows.value)
      } else {
        const fetchParams = selectedProjectParams({
          date: selectedPlan.value.planDate || selectedDate.value,
          planFolder: selectedPlan.value.planFolder || selectedPlan.value.name,
          file: file.name,
          sheet,
        })
        const sheetPayload = await fetchPlanFileRows(activePlanKey.value, fetchParams)
        columns = sheetPayload.columns || []
        rows = sheetPayload.rows || []
      }
      const completed = completedRowsPayload(columns, rows, candidates, '材料下料状态', true)
      const saveParams = selectedProjectParams({
        date: selectedPlan.value.planDate || selectedDate.value,
        planFolder: selectedPlan.value.planFolder || selectedPlan.value.name,
        file: file.name,
      })
      await savePlanFileRows(activePlanKey.value, saveParams, {
        sheet,
        columns: completed.columns,
        rows: completed.rows,
      })
    }
    await loadFile(file, currentSheet)
    saveMessage.value = t('cuttingAllSheetsCompleted', { count: sheets.length })
  } catch (error) {
    fileError.value = t('planFileSaveFailed', { message: error.message })
  } finally {
    saving.value = false
  }
}

async function markTodayPlanCompleted() {
  if (!canEditSelectedFile.value) return
  if (activePlanKey.value === 'cutting' && isCuttingPrimaryFile(selectedFile.value || fileData.value)) {
    await completeAllCuttingSheets()
    return
  }
  if (activePlanKey.value === 'anti-corrosion' && isAntiCorrosionMaterialFile(selectedFile.value || fileData.value)) {
    markAntiCorrosionMaterialCompleted()
    isDirty.value = true
    saveMessage.value = t('todayPlanMarkedComplete')
    return
  }
  const completionColumn = ensureCompletionColumn()
  const completionValue = ['anti-corrosion', 'cutting'].includes(activePlanKey.value) ? true : '已完成'
  editableRows.value = editableRows.value.map((row) => ({
    ...row,
    [completionColumn]: completionValue,
  }))
  isDirty.value = true
  saveMessage.value = t('todayPlanMarkedComplete')
}

async function exportCurrentPlanFile() {
  if (!editableRows.value.length || !editableColumns.value.length) {
    fileError.value = t('planExportEmpty')
    return
  }
  fileError.value = ''
  try {
    const params = selectedProjectParams()
    const blob = await exportPlanPatchRows(activePlanKey.value, params, {
      sheet: selectedSheet.value,
      columns: editableColumns.value,
      rows: editableRows.value,
    })
    const link = document.createElement('a')
    const baseName = String(planFileDisplayName(selectedFile.value || fileData.value) || 'plan').replace(/\.[^.]+$/, '')
    const sheetName = selectedSheet.value ? `-${selectedSheet.value}` : ''
    link.href = URL.createObjectURL(blob)
    link.download = `${baseName}${sheetName}.xlsx`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(link.href)
  } catch (error) {
    fileError.value = t('planExportFailed', { message: error.message })
  }
}

function triggerPlanImport() {
  planImportInput.value?.click()
}

async function importPlanPatch(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  fileError.value = ''
  saveMessage.value = ''
  try {
    const formData = new FormData()
    formData.append('file', file)
    if (selectedSheet.value) formData.append('sheet', selectedSheet.value)
    const params = selectedProjectParams()
    const payload = await importPlanPatchRows(activePlanKey.value, formData, params)
    const headers = payload.columns?.map((header) => String(header || '').trim()) || []
    const libraryIndexColumn = '库序号'
    const libraryIndexPosition = headers.indexOf(libraryIndexColumn)
    if (libraryIndexPosition < 0) {
      fileError.value = t('planImportRequiresLibraryIndex')
      return
    }
    const editableColumnSet = new Set(editableColumns.value)
    const updateHeaders = headers.filter((header) => header && header !== libraryIndexColumn && editableColumnSet.has(header))
    if (!updateHeaders.length) {
      fileError.value = t('planImportNoUpdatableColumns')
      return
    }
    const incomingRows = payload.rows || []
    const incomingByIndex = new Map(
      incomingRows
        .map((row) => [String(row[libraryIndexColumn] ?? '').trim(), row])
        .filter(([key]) => key),
    )
    let mergedCount = 0
    editableRows.value = editableRows.value.map((row) => {
      const key = String(row[libraryIndexColumn] ?? '').trim()
      const incoming = incomingByIndex.get(key)
      if (!incoming) return row
      mergedCount += 1
      return updateHeaders.reduce((nextRow, column) => {
        nextRow[column] = incoming[column]
        return nextRow
      }, { ...row })
    })
    if (!mergedCount) {
      fileError.value = t('planImportNoMatchedRows')
      return
    }
    isDirty.value = true
    saveMessage.value = t('planImportMerged', { count: mergedCount })
  } catch (error) {
    fileError.value = t('planImportReadFailed', { message: error.message })
  }
}

async function saveCurrentFile() {
  if (!canEditSelectedFile.value || !selectedFile.value || !selectedPlan.value) return
  saving.value = true
  fileError.value = ''
  saveMessage.value = ''
  try {
    const params = selectedProjectParams({
      date: selectedPlan.value.planDate || selectedDate.value,
      planFolder: selectedPlan.value.planFolder || selectedPlan.value.name,
      file: selectedFile.value.name,
    })
    const payload = await savePlanFileRows(activePlanKey.value, params, {
      sheet: selectedSheet.value,
      columns: editableColumns.value,
      rows: editableRows.value,
    })
    fileData.value = {
      ...fileData.value,
      total: payload.total,
      sheet: payload.sheet,
    }
    isDirty.value = false
    saveMessage.value = t('savedToPlanFile')
  } catch (error) {
    fileError.value = t('planFileSaveFailed', { message: error.message })
  } finally {
    saving.value = false
  }
}

watch([() => route.params.planKey, () => route.query.date], () => {
  selectedDate.value = ''
  calendarMonth.value = ''
  pendingPlanDateMoves.value = []
  loadPlan(routePlanDate())
})
watch(selectedProjectId, () => {
  selectedDate.value = ''
  calendarMonth.value = ''
  pendingPlanDateMoves.value = []
  loadPlan(routePlanDate())
})
watch(
  [editableRows, editableColumns, canEditSelectedFile, () => vTableThemeKey.value],
  renderPlanVTable,
  { deep: true },
)

onBeforeRouteLeave(async () => confirmLeaveWithUnsyncedChanges())
onBeforeRouteUpdate(async () => confirmLeaveWithUnsyncedChanges())

onMounted(() => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  loadPlan(routePlanDate())
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
  releasePlanVTable()
})
</script>

<template>
  <PlanViewerHeader :title="t('plans')" :description="activePlanDescription">
    <template #actions>
      <v-btn color="primary" :loading="loading" prepend-icon="mdi-refresh" @click="loadPlan()">{{ t('refreshPlan') }}</v-btn>
    </template>
  </PlanViewerHeader>

  <v-alert v-if="errorMessage" :text="errorMessage" type="error" density="compact" class="status-alert" />

  <v-card class="module-panel" :loading="loading">
    <div class="section-head">
      <div>
        <h2>{{ activePlanTitle }}</h2>
      </div>
    </div>

    <div v-if="!isGanttView" class="plan-workbench">
      <aside class="plan-browser">
        <div class="plan-browser-section">
          <button
            class="plan-section-toggle"
            type="button"
            :aria-expanded="planSectionOpen.today"
            @click="togglePlanSection('today')"
          >
            <v-icon :icon="planSectionOpen.today ? 'mdi-chevron-down' : 'mdi-chevron-right'" size="18" />
            <strong>{{ t('todayPlan') }}</strong>
            <span>{{ todayPlans.length }}</span>
          </button>
          <div v-show="planSectionOpen.today" class="plan-tree">
            <div
              v-for="plan in todayPlans"
              :key="plan.id"
              :class="['plan-tree-file', { 'is-active': selectedPlan?.id === plan.id }]"
              role="button"
              tabindex="0"
              @click="selectPlan(plan)"
              @keydown.enter="selectPlan(plan)"
            >
              <v-icon icon="mdi-calendar-today-outline" size="18" />
              <span>{{ plan.name }}</span>
              <small>{{ t('fileCount', { count: plan.fileCount }) }} · {{ formatTime(plan.updatedAt) }}</small>
              <div class="plan-tree-actions">
                <v-icon-btn
                  icon="mdi-pencil-outline"
                  variant="plain"
                  icon-color="warning"
                  size="small"
                  density="comfortable"
                  :loading="movingPlanId === plan.id"
                  :aria-label="t('changePlanDate')"
                  @click.stop="openPlanDateDialog(plan)"
                />
                <v-icon-btn
                  icon="mdi-delete-outline"
                  variant="plain"
                  icon-color="error"
                  size="small"
                  density="comfortable"
                  :loading="deletingPlanId === plan.id"
                  :aria-label="t('deletePlan')"
                  @click.stop="openPlanDeleteDialog(plan)"
                />
              </div>
            </div>
            <span v-if="!todayPlans.length" class="plan-empty-note">{{ t('noTodayPlan') }}</span>
          </div>
        </div>

        <div class="plan-browser-section">
          <button
            class="plan-section-toggle"
            type="button"
            :aria-expanded="planSectionOpen.future"
            @click="togglePlanSection('future')"
          >
            <v-icon :icon="planSectionOpen.future ? 'mdi-chevron-down' : 'mdi-chevron-right'" size="18" />
            <strong>{{ t('futurePlan') }}</strong>
            <span>{{ futurePlans.length }}</span>
          </button>
          <div v-show="planSectionOpen.future" class="plan-tree">
            <div
              v-for="plan in futurePlans"
              :key="plan.id"
              :class="['plan-tree-file', { 'is-active': selectedPlan?.id === plan.id }]"
              role="button"
              tabindex="0"
              @click="selectPlan(plan)"
              @keydown.enter="selectPlan(plan)"
            >
              <v-icon icon="mdi-calendar-month-outline" size="18" />
              <span>{{ plan.name }}</span>
              <small>{{ plan.planDate }} · {{ t('fileCount', { count: plan.fileCount }) }}</small>
              <div class="plan-tree-actions">
                <v-icon-btn
                  icon="mdi-pencil-outline"
                  variant="plain"
                  icon-color="warning"
                  size="small"
                  density="comfortable"
                  :loading="movingPlanId === plan.id"
                  :aria-label="t('changePlanDate')"
                  @click.stop="openPlanDateDialog(plan)"
                />
                <v-icon-btn
                  icon="mdi-delete-outline"
                  variant="plain"
                  icon-color="error"
                  size="small"
                  density="comfortable"
                  :loading="deletingPlanId === plan.id"
                  :aria-label="t('deletePlan')"
                  @click.stop="openPlanDeleteDialog(plan)"
                />
              </div>
            </div>
            <span v-if="!futurePlans.length" class="plan-empty-note">{{ t('noFuturePlan') }}</span>
          </div>
        </div>

        <div class="plan-browser-section">
          <button
            class="plan-section-toggle"
            type="button"
            :aria-expanded="planSectionOpen.history"
            @click="togglePlanSection('history')"
          >
            <v-icon :icon="planSectionOpen.history ? 'mdi-chevron-down' : 'mdi-chevron-right'" size="18" />
            <strong>{{ t('historyPlan') }}</strong>
            <span>{{ historyPlans.length }}</span>
          </button>
          <div v-show="planSectionOpen.history" class="plan-tree">
            <div
              v-for="plan in historyPlans"
              :key="plan.id"
              :class="['plan-tree-file', { 'is-active': selectedPlan?.id === plan.id }]"
              role="button"
              tabindex="0"
              @click="selectPlan(plan)"
              @keydown.enter="selectPlan(plan)"
            >
              <v-icon icon="mdi-history" size="18" />
              <span>{{ plan.name }}</span>
              <small>{{ plan.planDate }} · {{ t('fileCount', { count: plan.fileCount }) }}</small>
              <div class="plan-tree-actions">
                <v-icon-btn
                  icon="mdi-pencil-outline"
                  variant="plain"
                  icon-color="warning"
                  size="small"
                  density="comfortable"
                  :loading="movingPlanId === plan.id"
                  :aria-label="t('changePlanDate')"
                  @click.stop="openPlanDateDialog(plan)"
                />
                <v-icon-btn
                  icon="mdi-delete-outline"
                  variant="plain"
                  icon-color="error"
                  size="small"
                  density="comfortable"
                  :loading="deletingPlanId === plan.id"
                  :aria-label="t('deletePlan')"
                  @click.stop="openPlanDeleteDialog(plan)"
                />
              </div>
            </div>
            <span v-if="!historyPlans.length" class="plan-empty-note">{{ t('noHistoryPlan') }}</span>
          </div>
        </div>
      </aside>

      <v-card class="plan-preview" variant="flat" :loading="fileLoading">
        <div class="plan-preview-head">
          <div>
            <h3>{{ selectedPlan?.name || t('selectPlan') }}</h3>
            <span v-if="fileData.name">{{ t('currentFile') }}：{{ planFileDisplayName(selectedFile || fileData) }}</span>
          </div>
          <span v-if="selectedPlan">{{ formatTime(selectedPlan.updatedAt) }}</span>
        </div>

        <v-alert v-if="fileError" :text="fileError" type="error" density="compact" class="status-alert" />

        <div v-if="selectedPlan && !usesGroupedPlanFiles" class="plan-file-list">
          <button
            v-for="file in selectedPlanFiles"
            :key="file.path"
            :class="['plan-file-item', { 'is-active': selectedFile?.path === file.path }]"
            type="button"
            @click="loadFile(file)"
          >
            <div class="plan-file-main">
              <strong>{{ planFileDisplayName(file) }}</strong>
              <span>{{ formatSize(file.size) }} · {{ formatTime(file.updatedAt) }}</span>
            </div>
            <div class="plan-file-meta">
              <span>{{ t('sheetCount', { value: file.sheets?.length || 0 }) }}</span>
            </div>
          </button>
        </div>

        <div v-else-if="selectedPlan" class="plan-file-groups">
          <v-sheet class="plan-file-group" color="transparent">
            <strong>{{ t('primaryScheduleFile') }}</strong>
            <button
              v-if="primaryPlanFile"
              :class="['plan-file-item', 'is-primary', { 'is-active': selectedFile?.path === primaryPlanFile.path }]"
              type="button"
              @click="loadFile(primaryPlanFile)"
            >
              <div class="plan-file-main">
                <strong>{{ planFileDisplayName(primaryPlanFile) }}</strong>
                <span>{{ formatSize(primaryPlanFile.size) }} · {{ formatTime(primaryPlanFile.updatedAt) }}</span>
              </div>
              <div class="plan-file-meta">
                <span>{{ t('sheetCount', { value: primaryPlanFile.sheets?.length || 0 }) }}</span>
              </div>
            </button>
            <span v-else class="plan-empty-note">{{ t('primaryScheduleFileMissing') }}</span>
          </v-sheet>

          <v-sheet class="plan-file-group" color="transparent">
            <strong>{{ t('auxiliaryFiles') }}</strong>
            <button
              v-for="file in auxiliaryPlanFiles"
              :key="file.path"
              :class="['plan-file-item', { 'is-active': selectedFile?.path === file.path }]"
              type="button"
              @click="loadFile(file)"
            >
              <div class="plan-file-main">
                <strong>{{ planFileDisplayName(file) }}</strong>
                <span>{{ formatSize(file.size) }} · {{ formatTime(file.updatedAt) }}</span>
              </div>
              <div class="plan-file-meta">
                <span>{{ t('sheetCount', { value: file.sheets?.length || 0 }) }}</span>
              </div>
            </button>
            <span v-if="!auxiliaryPlanFiles.length" class="plan-empty-note">{{ t('noAuxiliaryFiles') }}</span>
          </v-sheet>
        </div>

        <div v-if="fileData.sheets.length" class="library-toolbar">
          <v-tabs :model-value="selectedSheet" color="primary" @update:model-value="changeSheet">
            <v-tab v-for="sheet in fileData.sheets" :key="sheet" :value="sheet">{{ sheet }}</v-tab>
          </v-tabs>
        </div>

        <div v-if="fileData.name" class="library-meta">
          <span>{{ t('currentSheet') }}：{{ selectedSheet || t('unselected') }}</span>
          <span>{{ t('totalRows') }}：{{ fileData.total }}</span>
          <span>{{ t('columnCount') }}：{{ fileData.columns.length }}</span>
          <span v-if="isDirty">{{ t('unsyncedChanges') }}</span>
          <span v-else-if="canEditSelectedFile">{{ t('synced') }}</span>
        </div>

        <div v-if="fileData.name" class="plan-edit-toolbar">
          <input ref="planImportInput" type="file" accept=".xlsx,.xlsm" hidden @change="importPlanPatch" />
          <v-btn
            prepend-icon="mdi-upload"
            :disabled="!canEditSelectedFile || !editableRows.length || saving"
            @click="triggerPlanImport"
          >
            {{ t('import') }}
          </v-btn>
          <v-btn
            prepend-icon="mdi-download"
            :disabled="!fileData.name || !editableRows.length"
            @click="exportCurrentPlanFile"
          >
            {{ t('export') }}
          </v-btn>
          <v-btn
            v-if="canEditSelectedFile"
            color="primary"
            prepend-icon="mdi-content-save-outline"
            :loading="saving"
            :disabled="!isDirty"
            @click="saveCurrentFile"
          >
            {{ t('saveToPlanFile') }}
          </v-btn>
          <v-btn
            v-if="canEditSelectedFile"
            color="success"
            prepend-icon="mdi-check-all"
            :loading="saving"
            :disabled="!editableRows.length || saving"
            @click="markTodayPlanCompleted"
          >
            {{ t('completeTodayPlan') }}
          </v-btn>
          <span v-if="!isSelectedTodayPlan" class="plan-edit-note">{{ t('nonTodayReadonly') }}</span>
          <span v-else-if="usesGroupedPlanFiles && !isSelectedPrimaryEditableFile" class="plan-edit-note">{{ t('auxiliaryReadonly') }}</span>
        </div>

        <v-alert v-if="saveMessage" :text="saveMessage" type="success" density="compact" class="status-alert" />

        <div v-if="fileData.name" class="plan-edit-table-wrap">
          <div ref="planTableContainer" class="plan-edit-vtable" />
          <div v-if="!editableRows.length" class="plan-table-empty">{{ t('currentSheetNoData') }}</div>
        </div>
        <div v-else class="plan-edit-empty">{{ t('selectPlanFileOrNoData') }}</div>
      </v-card>
    </div>

    <div v-else class="calendar-plan">
      <div class="calendar-plan-head">
        <div class="calendar-plan-nav">
          <v-btn icon="mdi-chevron-left" variant="text" size="small" @click="movePlanTablePeriod(-1)" />
          <strong>{{ planTablePeriodTitle }}</strong>
          <v-btn icon="mdi-chevron-right" variant="text" size="small" @click="movePlanTablePeriod(1)" />
        </div>
        <v-tabs v-model="planTableViewTab" class="plan-table-tabs" color="primary" density="compact">
          <v-tab value="calendar">{{ t('dateTable') }}</v-tab>
          <v-tab value="gantt">{{ t('ganttChart') }}</v-tab>
        </v-tabs>
        <div v-if="planTableViewTab === 'gantt'" class="gantt-period-controls">
          <v-menu v-model="ganttMonthMenu" :close-on-content-click="false">
            <template #activator="{ props }">
              <v-btn v-bind="props" prepend-icon="mdi-calendar-month-outline" size="small" variant="outlined">
                {{ t('ganttMonth') }}：{{ ganttModelValue.slice(0, 7) }}
              </v-btn>
            </template>
            <v-card class="pa-3" min-width="280">
              <v-text-field
                :model-value="ganttModelValue.slice(0, 7)"
                :label="t('ganttMonth')"
                type="month"
                density="compact"
                hide-details
                @update:model-value="selectGanttMonth"
              />
            </v-card>
          </v-menu>
          <v-menu v-model="ganttDateMenu" :close-on-content-click="false">
            <template #activator="{ props }">
              <v-btn v-bind="props" prepend-icon="mdi-calendar-today-outline" size="small" variant="outlined">
                {{ t('ganttDate') }}：{{ ganttModelValue }}
              </v-btn>
            </template>
            <v-date-picker :model-value="ganttModelValue" @update:model-value="selectGanttDate" />
          </v-menu>
        </div>
        <div class="calendar-plan-legend">
          <v-chip color="success" variant="flat" size="small">防腐</v-chip>
          <v-chip color="primary" variant="flat" size="small">下料</v-chip>
          <v-chip color="warning" variant="flat" size="small">焊接</v-chip>
        </div>
      </div>

      <div v-if="pendingPlanDateMoves.length" class="plan-pending-moves">
        <span>{{ t('pendingPlanDateMoves', { count: pendingPlanDateMoves.length }) }}</span>
        <div>
          <v-btn variant="text" size="small" @click="cancelPendingPlanMoves">{{ t('cancel') }}</v-btn>
          <v-btn
            color="primary"
            size="small"
            :loading="movingPlanId === 'pending'"
            @click="confirmPendingPlanMoves"
          >
            {{ t('confirmSync') }}
          </v-btn>
        </div>
      </div>

      <div v-if="calendarModelValue && planTableViewTab === 'calendar'" class="calendar-grid plan-month-grid">
        <div v-for="weekday in ['一', '二', '三', '四', '五', '六', '日']" :key="weekday" class="calendar-weekday">
          周{{ weekday }}
        </div>
        <div
          v-for="day in currentMonthDays"
          :key="day.key"
          :class="['calendar-day', { 'is-blank': day.blank, 'is-today': day.isToday, 'has-work': !day.blank && dayPlans(day.iso).length }]"
          @dragover.prevent="!day.blank"
          @drop.prevent="dropPlanOnDate(day)"
        >
          <template v-if="!day.blank">
            <div class="calendar-day-top">
              <strong>{{ day.day }}</strong>
            </div>
            <div v-if="dayPlans(day.iso).length" class="calendar-day-plans">
              <v-tooltip
                v-for="plan in dayPlans(day.iso)"
                :key="`${day.iso}-${plan.id}`"
                location="top"
                open-delay="120"
                max-width="420"
              >
                <template #activator="{ props }">
                  <v-chip
                    v-bind="props"
                    :color="calendarPlanColor(plan.name)"
                    :class="['calendar-day-plan-chip', calendarPlanClass(plan.name), { 'is-pending': plan.pending }]"
                    variant="flat"
                    size="x-small"
                    role="button"
                    tabindex="0"
                    draggable="true"
                    @dragstart="startDragPlan(plan)"
                    @dragend="endDragPlan"
                    @click.stop="openCalendarPlan(day.iso, plan)"
                    @keydown.enter.stop="openCalendarPlan(day.iso, plan)"
                  >
                    {{ plan.name }}
                  </v-chip>
                </template>
                <div class="plan-chip-tooltip">
                  <strong>{{ plan.name }}</strong>
                  <div v-for="row in planTooltipRows(plan)" :key="row.label">
                    <span>{{ row.label }}</span>
                    <b>{{ row.value }}</b>
                  </div>
                </div>
              </v-tooltip>
            </div>
          </template>
        </div>
      </div>

      <div v-else-if="calendarModelValue && planTableViewTab === 'gantt'" class="plan-gantt">
        <div class="plan-gantt-scroll">
          <div
            class="plan-gantt-hour-grid"
            :style="{ '--gantt-hour-count': ganttHourColumns.length }"
          >
            <div class="plan-gantt-corner">{{ t('module') }}</div>
            <div class="plan-gantt-hour-head">
              <div
                v-for="column in ganttHourColumns"
                :key="column.key"
                :class="['plan-gantt-hour-tick', { 'is-major': column.isMajor }]"
              >
                <span>{{ column.label }}</span>
              </div>
            </div>

            <template v-for="row in ganttRows" :key="row.name">
              <div :class="['plan-gantt-label', row.className]">{{ row.name }}</div>
              <div
                class="plan-gantt-track"
                :style="{ '--gantt-hour-count': ganttHourColumns.length }"
              >
                <div
                  v-for="column in ganttHourColumns"
                  :key="`${row.name}-${column.key}`"
                  :class="['plan-gantt-hour-cell', { 'is-major': column.isMajor }]"
                />
                <v-tooltip
                  v-for="plan in row.items"
                  :key="plan.key"
                  location="top"
                  open-delay="120"
                  max-width="420"
                >
                  <template #activator="{ props }">
                    <button
                      v-bind="props"
                      :class="['plan-gantt-bar', row.className]"
                      type="button"
                      :style="{ gridColumn: `${plan.startColumn} / span ${plan.span}`, gridRow: plan.row + 1 }"
                      @click="openCalendarPlan(plan.day.iso, plan)"
                    >
                      {{ plan.name }} {{ plan.timeText }}
                    </button>
                  </template>
                  <div class="plan-chip-tooltip">
                    <strong>{{ plan.name }} {{ plan.timeText }}</strong>
                    <div v-for="detail in planTooltipRows(plan)" :key="detail.label">
                      <span>{{ detail.label }}</span>
                      <b>{{ detail.value }}</b>
                    </div>
                  </div>
                </v-tooltip>
              </div>
            </template>
          </div>
        </div>
      </div>
      <div v-else class="empty-cutting">{{ t('noPlan') }}</div>
    </div>
  </v-card>

  <v-dialog v-model="planDateDialog.show" max-width="420">
    <v-card class="plan-date-dialog" variant="flat">
      <v-card-title>{{ t('changePlanDate') }}</v-card-title>
      <v-card-text>
        <v-text-field
          v-model="planDateDialog.date"
          type="date"
          :label="t('planDate')"
          density="comfortable"
          variant="outlined"
          hide-details
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="closePlanDateDialog">{{ t('cancel') }}</v-btn>
        <v-btn color="primary" :loading="movingPlanId === planDateDialog.plan?.id" @click="applyPlanDateDialog">{{ t('confirm') }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <v-dialog v-model="planDeleteDialog.show" max-width="460">
    <v-card class="plan-date-dialog" variant="flat">
      <v-card-title>{{ t('deletePlan') }}</v-card-title>
      <v-card-text>
        {{ t('deletePlanConfirmText', {
          name: planDeleteDialog.plan?.name || '-',
          date: planDeleteDialog.plan?.planDate || '-',
        }) }}
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="closePlanDeleteDialog">{{ t('cancel') }}</v-btn>
        <v-btn
          color="error"
          :loading="deletingPlanId === planDeleteDialog.plan?.id"
          @click="confirmDeletePlan"
        >
          {{ t('deletePlan') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <UnsavedChangesDialog ref="unsavedChangesDialog" />
</template>

<style scoped>
.plan-edit-table-wrap {
  position: relative;
  width: 100%;
  height: 520px;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
}

.plan-edit-vtable {
  width: 100%;
  height: 100%;
}

.plan-table-empty {
  position: absolute;
  top: 50%;
  left: 50%;
  display: inline-flex;
  padding: 10px 14px;
  border: 1px dashed var(--line);
  border-radius: 6px;
  background: var(--panel-soft);
  color: var(--muted);
  font-size: 13px;
  pointer-events: none;
  transform: translate(-50%, -50%);
}
</style>
