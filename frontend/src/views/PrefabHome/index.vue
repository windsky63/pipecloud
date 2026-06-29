<script setup>
import * as VTable from '@visactor/vtable'
import { InputEditor } from '@visactor/vtable-editors'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRouter } from 'vue-router'
import {
  fetchInitializationStats,
  fetchWeldingDashboard,
} from '../../api/workflow'
import {
  createProject,
  deleteProjectById,
  fetchProjects,
  fetchProjectWelds,
  importProjectsFile,
  projectExportUrl,
  updateProject,
} from '../../api/projects'
import PageHeader from '../../components/PageHeader.vue'
import InitializationDashboardPanel from '../../components/InitializationDashboardPanel.vue'
import UnsavedChangesDialog from '../../components/UnsavedChangesDialog.vue'
import WeldingDashboardPanel from '../../components/WeldingDashboardPanel.vue'
import {
  errorMessage as workflowErrorMessage,
  homeComponentVisibility,
  loadSummary,
  loading as workflowLoading,
  runAction,
  runningKey,
  summary,
  t,
  workflowActions,
} from '../../services/pipecloudState'
import { selectedProjectId, selectedProjectParams, setSelectedProjectId } from '../../services/projectState'
import { getBasicVTableTheme, getVTablePalette, isDarkVTableTheme, vTableThemeKey } from '../../services/vtableTheme'
import { localizedActionName } from '../../services/navigationLabels'

const projectRows = ref([])
const projectColumns = ref([])
const weldRows = ref([])
const weldColumns = ref([])
const weldMeta = ref({
  dataPath: '',
  file: null,
  total: 0,
  page: 1,
  pageSize: 100,
  totalPages: 0,
})
const loading = ref(false)
const weldLoading = ref(false)
const initializationDashboardLoading = ref(false)
const weldingDashboardLoading = ref(false)
const saving = ref(false)
const errorMessage = ref('')
const weldErrorMessage = ref('')
const initializationDashboardError = ref('')
const weldingDashboardError = ref('')
const searchText = ref('')
const dirtyRowIds = ref(new Set())
const projectImportInput = ref(null)
const projectTableContainer = ref(null)
const weldTableContainer = ref(null)
const projectTableWidth = ref(0)
const weldPage = ref(1)
const weldPageSize = ref(100)
const projectDialog = ref(false)
const projectForm = ref({})
const projectFormError = ref('')
const unsavedChangesDialog = ref(null)
const initializationDashboardCollapsed = ref(false)
const weldingDashboardCollapsed = ref(false)
const initializationDashboard = ref(emptyInitializationDashboard())
const weldingDashboard = ref(emptyWeldingDashboard())
let projectTableInstance = null
let weldTableInstance = null
let projectResizeObserver = null
const weldPageSizeOptions = [50, 100, 200, 500]
const router = useRouter()

const displayedProjectRows = computed(() => {
  const keyword = searchText.value.trim().toLowerCase()
  if (!keyword) return projectRows.value
  return projectRows.value.filter((row) => {
    return projectColumns.value.some((column) => String(row[column.field] || '').toLowerCase().includes(keyword))
  })
})

const selectedProject = computed(() => projectRows.value.find((row) => row.id === selectedProjectId.value) || null)
const dirtyCount = computed(() => dirtyRowIds.value.size)
const projectOptions = computed(() => projectRows.value.map((project) => ({
  title: project.project_name || t('projectWithId', { id: project.id }),
  value: project.id,
})))
const requiredProjectColumns = computed(() => projectColumns.value.filter((column) => column.field === 'project_name'))
const optionalProjectColumns = computed(() => projectColumns.value.filter((column) => column.field !== 'project_name'))
const weldTotalPages = computed(() => Math.max(Number(weldMeta.value.totalPages) || 0, weldMeta.value.total ? 1 : 0))
const selectedProjectNeedsInitialization = computed(() => Boolean(selectedProject.value?.needsInitializationData))
const selectedProjectInitializationHint = computed(() => (
  selectedProject.value?.initializationHint || t('noInitializationDataHint')
))
const showInitializationDashboard = computed(() => homeComponentVisibility.value.initializationDashboard)
const showWeldingDashboard = computed(() => homeComponentVisibility.value.weldingDashboard)
const showHomeWorkflow = computed(() => homeComponentVisibility.value.workflow)
const showProjectData = computed(() => homeComponentVisibility.value.projectData)
const showProjectWeldInfo = computed(() => homeComponentVisibility.value.projectWeldInfo)
const showHomeProjectLayout = computed(() => showProjectData.value || showProjectWeldInfo.value)

function emptyInitializationDashboard() {
  return {
    totalWeldCount: 0,
    prefabWeldCount: 0,
    autoWeldCount: 0,
    prefabRate: 0,
    autoRate: 0,
    unitCount: 0,
    units: [],
    sources: {},
  }
}

function emptyWeldingDashboard() {
  return {
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

function releaseProjectTable() {
  if (projectTableInstance) {
    projectTableInstance.release()
    projectTableInstance = null
  }
}

function releaseWeldTable() {
  if (weldTableInstance) {
    weldTableInstance.release()
    weldTableInstance = null
  }
}

function buildProjectRecords() {
  return displayedProjectRows.value.map((row, index) => ({
    __index: index + 1,
    ...row,
  }))
}

function getProjectColumnBaseWidth(column) {
  if (column.field === '__index') return 54
  if (column.field === 'project_name') return 220
  if (column.field === 'pipe_segment') return 150
  if (column.field === 'prefab_weld_count') return 150
  if (column.field === 'completion_rate') return 170
  if (column.field === 'start_date') return 150
  return 132
}

function normalizeCompletionRate(value) {
  const number = Number.parseFloat(String(value ?? '').replace('%', ''))
  if (!Number.isFinite(number)) return 0
  const percent = number > 0 && number <= 1 ? number * 100 : number
  return Math.max(0, Math.min(percent, 100))
}

function renderCompletionRate(args) {
  const palette = getVTablePalette()
  const rawValue = args.dataValue ?? args.value ?? args.originData?.completion_rate ?? args.record?.completion_rate
  const rate = normalizeCompletionRate(rawValue)
  const cellWidth = args.table.getColWidth(args.col)
  const barWidth = Math.max(cellWidth - 38, 64)
  const barHeight = 13
  const barX = 18
  const barY = 12
  const fillWidth = Math.max(Math.round((barWidth * rate) / 100), rate > 0 ? 10 : 0)
  const trackColor = isDarkVTableTheme.value ? '#293548' : '#e1ece9'
  const startColor = isDarkVTableTheme.value ? '#60a5fa' : '#93c5fd'
  const endColor = isDarkVTableTheme.value ? '#14b8a6' : '#0f8f82'

  return {
    elements: [
      {
        type: 'rect',
        x: barX,
        y: barY,
        width: barWidth,
        height: barHeight,
        fill: trackColor,
        radius: 7,
      },
      {
        type: 'rect',
        x: barX,
        y: barY,
        width: fillWidth,
        height: barHeight,
        fill: {
          gradient: 'linear',
          x0: 0,
          y0: 0,
          x1: 1,
          y1: 0,
          stops: [
            { offset: 0, color: startColor },
            { offset: 1, color: endColor },
          ],
        },
        radius: 7,
      },
      {
        type: 'text',
        x: barX,
        y: barY + barHeight + 13,
        text: `${Math.round(rate)}%`,
        fill: palette.bodyText,
        fontSize: 12,
        fontWeight: 600,
        textAlign: 'left',
        textBaseline: 'middle',
      },
    ],
    expectedHeight: 48,
    expectedWidth: cellWidth,
    renderDefault: false,
  }
}

function stretchProjectColumns(columns) {
  const availableWidth = Math.floor(projectTableWidth.value)
  const totalWidth = columns.reduce((total, column) => total + getProjectColumnBaseWidth(column), 0)

  if (!columns.length || !availableWidth || totalWidth >= availableWidth) return columns

  let usedWidth = 0
  return columns.map((column, index) => {
    const baseWidth = getProjectColumnBaseWidth(column)
    const isLast = index === columns.length - 1
    const width = isLast ? availableWidth - usedWidth : Math.floor((baseWidth / totalWidth) * availableWidth)
    usedWidth += width
    return {
      ...column,
      width: Math.max(width, baseWidth),
    }
  })
}

function buildProjectColumns() {
  const textEditor = new InputEditor()
  const columns = [
    {
      field: '__index',
      title: '#',
      width: getProjectColumnBaseWidth({ field: '__index' }),
      fixed: 'left',
      style: { textAlign: 'center', color: '#64748b', fontWeight: 600 },
      headerStyle: { textAlign: 'center', fontWeight: 700 },
    },
    ...projectColumns.value.map((column) => ({
      field: column.field,
      title: column.title,
      width: getProjectColumnBaseWidth(column),
      minWidth: 110,
      sort: true,
      editor: textEditor,
      customRender: column.field === 'completion_rate' ? renderCompletionRate : undefined,
      headerStyle: { fontWeight: 700 },
    })),
  ]
  return stretchProjectColumns(columns)
}

function buildWeldRecords() {
  return weldRows.value.map((row, index) => ({
    __index: (weldPage.value - 1) * weldPageSize.value + index + 1,
    ...row,
  }))
}

function buildWeldColumns() {
  return [
    {
      field: '__index',
      title: '#',
      width: 58,
      fixed: 'left',
      style: { textAlign: 'center', color: '#64748b', fontWeight: 600 },
      headerStyle: { textAlign: 'center', fontWeight: 700 },
    },
    ...weldColumns.value.map((column) => ({
      field: column,
      title: column,
      width: 150,
      minWidth: 120,
      sort: true,
      headerStyle: { fontWeight: 700 },
    })),
  ]
}

function tableTheme() {
  return getBasicVTableTheme()
}

function buildProjectOptions() {
  return {
    records: buildProjectRecords(),
    columns: buildProjectColumns(),
    editCellTrigger: ['doubleclick', 'keydown'],
    widthMode: 'standard',
    heightMode: 'standard',
    defaultRowHeight: 52,
    defaultHeaderRowHeight: 40,
    frozenColCount: 1,
    autoWrapText: false,
    keyboardOptions: { copySelected: true },
    tooltip: { isShowOverflowTextTooltip: true },
    theme: tableTheme(),
  }
}

function buildWeldOptions() {
  return {
    records: buildWeldRecords(),
    columns: buildWeldColumns(),
    widthMode: 'standard',
    heightMode: 'standard',
    defaultRowHeight: 36,
    defaultHeaderRowHeight: 40,
    frozenColCount: 1,
    autoWrapText: false,
    keyboardOptions: { copySelected: true },
    tooltip: { isShowOverflowTextTooltip: true },
    theme: tableTheme(),
  }
}

async function renderProjectTable() {
  await nextTick()
  if (!projectTableContainer.value || !projectColumns.value.length) {
    releaseProjectTable()
    return
  }
  projectTableWidth.value = projectTableContainer.value.clientWidth || 0

  releaseProjectTable()
  projectTableInstance = new VTable.ListTable(projectTableContainer.value, buildProjectOptions())
  projectTableInstance.on(VTable.ListTable.EVENT_TYPE.CHANGE_CELL_VALUE, (event) => {
    const recordIndex = Array.isArray(event.recordIndex) ? event.recordIndex[0] : event.recordIndex
    const row = displayedProjectRows.value[recordIndex]
    if (!row || event.field === '__index') return
    const newValue = event.changedValue ?? ''
    const oldValue = row[event.field] ?? ''
    if (newValue === oldValue) return
    row[event.field] = newValue
    dirtyRowIds.value = new Set([...dirtyRowIds.value, row.id])
    if (event.field === 'completion_rate' && projectTableInstance) {
      projectTableInstance.updateOption(buildProjectOptions(), {
        clearColWidthCache: false,
        clearRowHeightCache: false,
      })
    }
  })
  projectTableInstance.on(VTable.ListTable.EVENT_TYPE.CLICK_CELL, (event) => {
    const record = event?.originData || event?.dataValue
    if (record?.id) setSelectedProjectId(record.id)
  })
}

function setupProjectResizeObserver() {
  if (projectResizeObserver || !projectTableContainer.value) return
  projectResizeObserver = new ResizeObserver(() => {
    projectTableWidth.value = projectTableContainer.value?.clientWidth || 0
    if (projectTableInstance) {
      projectTableInstance.updateOption(buildProjectOptions(), {
        clearColWidthCache: true,
        clearRowHeightCache: true,
      })
    }
  })
  projectResizeObserver.observe(projectTableContainer.value)
}

async function renderWeldTable() {
  await nextTick()
  if (!weldTableContainer.value || !weldColumns.value.length) {
    releaseWeldTable()
    return
  }
  releaseWeldTable()
  weldTableInstance = new VTable.ListTable(weldTableContainer.value, buildWeldOptions())
}

async function loadProjects() {
  loading.value = true
  errorMessage.value = ''
  try {
    const payload = await fetchProjects()
    projectColumns.value = payload.columns || []
    projectRows.value = payload.rows || []
    dirtyRowIds.value = new Set()
    if (!selectedProjectId.value || !projectRows.value.some((project) => project.id === selectedProjectId.value)) {
      setSelectedProjectId(projectRows.value[0]?.id || null)
    }
    await renderProjectTable()
  } catch (error) {
    errorMessage.value = t('projectDataReadFailed', { message: error.message })
  } finally {
    loading.value = false
  }
}

async function loadProjectWelds(page = weldPage.value) {
  if (!selectedProjectId.value) {
    weldRows.value = []
    weldColumns.value = []
    weldMeta.value = { dataPath: '', file: null, total: 0, page: 1, pageSize: weldPageSize.value, totalPages: 0 }
    releaseWeldTable()
    return
  }

  weldLoading.value = true
  weldErrorMessage.value = ''
  try {
    const params = new URLSearchParams({
      page: String(page || 1),
      page_size: String(weldPageSize.value),
    })
    const payload = await fetchProjectWelds(selectedProjectId.value, params.toString())
    weldRows.value = payload.rows || []
    weldColumns.value = payload.columns || []
    weldPage.value = Number(payload.page) || 1
    weldPageSize.value = Number(payload.pageSize) || weldPageSize.value
    weldMeta.value = {
      dataPath: payload.dataPath || '',
      file: payload.file || null,
      total: payload.total || 0,
      page: Number(payload.page) || 1,
      pageSize: Number(payload.pageSize) || weldPageSize.value,
      totalPages: Number(payload.totalPages) || 0,
    }
    await renderWeldTable()
  } catch (error) {
    weldRows.value = []
    weldColumns.value = []
    releaseWeldTable()
    weldErrorMessage.value = t('projectWeldReadFailed', { message: error.message })
  } finally {
    weldLoading.value = false
  }
}

async function loadInitializationDashboard() {
  if (!selectedProjectId.value) {
    initializationDashboard.value = emptyInitializationDashboard()
    return
  }

  initializationDashboardLoading.value = true
  initializationDashboardError.value = ''
  try {
    initializationDashboard.value = await fetchInitializationStats(selectedProjectParams())
  } catch (error) {
    initializationDashboard.value = emptyInitializationDashboard()
    initializationDashboardError.value = t('initializationStatsReadFailed', { message: error.message })
  } finally {
    initializationDashboardLoading.value = false
  }
}

async function loadWeldingDashboard() {
  if (!selectedProjectId.value) {
    weldingDashboard.value = emptyWeldingDashboard()
    return
  }

  weldingDashboardLoading.value = true
  weldingDashboardError.value = ''
  try {
    weldingDashboard.value = await fetchWeldingDashboard(selectedProjectParams())
  } catch (error) {
    weldingDashboard.value = emptyWeldingDashboard()
    weldingDashboardError.value = t('weldingDashboardReadFailed', { message: error.message })
  } finally {
    weldingDashboardLoading.value = false
  }
}

async function changeWeldPage(page) {
  const nextPage = Math.max(1, Math.min(Number(page) || 1, weldTotalPages.value || 1))
  await loadProjectWelds(nextPage)
}

async function changeWeldPageSize(size) {
  weldPageSize.value = Number(size) || 100
  weldPage.value = 1
  await loadProjectWelds(1)
}

function openProjectDialog() {
  projectForm.value = projectColumns.value.reduce((form, column) => {
    form[column.field] = ''
    return form
  }, {})
  projectFormError.value = ''
  projectDialog.value = true
}

function projectInputType(field) {
  if (field === 'prefab_weld_count') return 'number'
  if (field === 'completion_rate') return 'number'
  if (field === 'start_date') return 'date'
  return 'text'
}

async function addProject() {
  if (!String(projectForm.value.project_name || '').trim()) {
    projectFormError.value = t('projectNameRequired')
    return
  }

  saving.value = true
  errorMessage.value = ''
  projectFormError.value = ''
  try {
    const payload = await createProject(projectForm.value)
    projectRows.value = [payload, ...projectRows.value]
    setSelectedProjectId(payload.id)
    projectDialog.value = false
    await renderProjectTable()
  } catch (error) {
    projectFormError.value = t('projectCreateFailed', { message: error.message })
  } finally {
    saving.value = false
  }
}

async function saveProjects() {
  if (!dirtyRowIds.value.size) return
  saving.value = true
  errorMessage.value = ''
  try {
    const dirtyIds = Array.from(dirtyRowIds.value)
    for (const id of dirtyIds) {
      const row = projectRows.value.find((item) => item.id === id)
      if (!row) continue
      const payload = await updateProject(id, row)
      projectRows.value = projectRows.value.map((item) => (item.id === id ? payload : item))
    }
    dirtyRowIds.value = new Set()
    await renderProjectTable()
    await loadProjectWelds(weldPage.value)
  } catch (error) {
    errorMessage.value = t('projectSaveFailed', { message: error.message })
  } finally {
    saving.value = false
  }
}

async function deleteProject() {
  if (!selectedProject.value) return
  const projectId = selectedProject.value.id
  saving.value = true
  errorMessage.value = ''
  try {
    await deleteProjectById(projectId)
    projectRows.value = projectRows.value.filter((row) => row.id !== projectId)
    dirtyRowIds.value.delete(projectId)
    dirtyRowIds.value = new Set(dirtyRowIds.value)
    setSelectedProjectId(projectRows.value[0]?.id || null)
    await renderProjectTable()
  } catch (error) {
    errorMessage.value = t('projectDeleteFailed', { message: error.message })
  } finally {
    saving.value = false
  }
}

function triggerProjectImport() {
  projectImportInput.value?.click()
}

function openFileParser() {
  router.push({ name: 'parser' })
}

async function importProjects(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return

  saving.value = true
  errorMessage.value = ''
  try {
    await importProjectsFile(file)
    await loadProjects()
  } catch (error) {
    errorMessage.value = t('projectImportFailed', { message: error.message })
  } finally {
    saving.value = false
  }
}

function exportProjects() {
  window.location.href = projectExportUrl()
}

async function confirmLeaveWithUnsyncedChanges() {
  if (!dirtyCount.value) return true
  return unsavedChangesDialog.value?.open() ?? true
}

function handleBeforeUnload(event) {
  if (!dirtyCount.value) return
  event.preventDefault()
  event.returnValue = t('unsavedLeaveConfirm')
}

async function executeWorkflowAction(actionKey) {
  await runAction(actionKey)
  await loadProjects()
  await loadInitializationDashboard()
  await loadProjectWelds(weldPage.value)
  await loadWeldingDashboard()
}

onMounted(async () => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  if (!summary.value.modules.length) {
    await loadSummary()
  }
  await loadProjects()
  await loadInitializationDashboard()
  await loadWeldingDashboard()
  setupProjectResizeObserver()
  await loadProjectWelds(1)
})

onBeforeRouteLeave(async () => confirmLeaveWithUnsyncedChanges())
onBeforeRouteUpdate(async () => confirmLeaveWithUnsyncedChanges())

watch(searchText, renderProjectTable)
watch(selectedProjectId, async () => {
  weldPage.value = 1
  await loadInitializationDashboard()
  await loadWeldingDashboard()
  await loadProjectWelds(1)
})
watch(vTableThemeKey, async () => {
  if (projectTableInstance) {
    await projectTableInstance.updateOption(buildProjectOptions(), {
      clearColWidthCache: true,
      clearRowHeightCache: true,
    })
  }
  if (weldTableInstance) {
    await weldTableInstance.updateOption(buildWeldOptions(), {
      clearColWidthCache: true,
      clearRowHeightCache: true,
    })
  }
})
watch([showProjectData, showProjectWeldInfo], async () => {
  if (showProjectData.value) {
    await renderProjectTable()
    setupProjectResizeObserver()
  }
  if (showProjectWeldInfo.value) {
    await renderWeldTable()
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
  releaseProjectTable()
  releaseWeldTable()
  if (projectResizeObserver) {
    projectResizeObserver.disconnect()
    projectResizeObserver = null
  }
})
</script>

<template>
  <PageHeader
    :title="t('prefabHome')"
    :description="t('prefabHomeDescription')"
  >
    <template #actions>
      <label class="project-switcher-wrap">
        <div class="project-switcher-label">
          <v-icon icon="mdi-swap-horizontal-bold" size="18" />
          <span>{{ t('currentProject') }}</span>
        </div>

        <div class="project-switcher-control">
          <v-select
            :model-value="selectedProjectId"
            :items="projectOptions"
            density="compact"
            hide-details
            class="project-switcher"
            prepend-inner-icon="mdi-briefcase-outline"
            :placeholder="t('selectProjectPlaceholder')"
            @update:model-value="setSelectedProjectId"
          />
        </div>
      </label>
    </template>
  </PageHeader>

  <v-alert v-if="errorMessage" :text="errorMessage" type="error" density="compact" class="status-alert" />
  <v-alert v-if="workflowErrorMessage" :text="workflowErrorMessage" type="error" density="compact" class="status-alert" />

  <InitializationDashboardPanel
    v-if="showInitializationDashboard"
    :title="t('initializationDashboardTitle')"
    :description="t('initializationDashboardDescription')"
    :dashboard="initializationDashboard"
    :loading="initializationDashboardLoading"
    :error="initializationDashboardError"
    :collapsed="initializationDashboardCollapsed"
    show-refresh
    collapsible
    @refresh="loadInitializationDashboard"
    @toggle="initializationDashboardCollapsed = !initializationDashboardCollapsed"
  />

  <WeldingDashboardPanel
    v-if="showWeldingDashboard"
    :title="t('weldingDashboardTitle')"
    :description="t('weldingDashboardDescription')"
    :dashboard="weldingDashboard"
    :loading="weldingDashboardLoading"
    :error="weldingDashboardError"
    :collapsed="weldingDashboardCollapsed"
    show-refresh
    collapsible
    @refresh="loadWeldingDashboard"
    @toggle="weldingDashboardCollapsed = !weldingDashboardCollapsed"
  />

  <v-card v-if="showHomeWorkflow" class="workflow" variant="flat">
    <div class="section-head">
      <div class="section-title-with-tip">
        <h2>{{ t('workflow') }}</h2>
        <InfoTooltip :text="t('workflowTip')" />
      </div>
    </div>
    <div class="workflow-steps">
      <v-btn
        v-for="(action, index) in workflowActions"
        :key="action.key"
        :loading="runningKey === action.key"
        :disabled="workflowLoading || !selectedProject"
        prepend-icon="mdi-check-circle-outline"
        @click="executeWorkflowAction(action.key)"
      >
        {{ index + 1 }}. {{ localizedActionName(action) }}
      </v-btn>
    </div>
  </v-card>

  <v-sheet v-if="showHomeProjectLayout" class="home-project-layout" :class="{ 'is-single': !showProjectData || !showProjectWeldInfo }" color="transparent">
    <v-card v-if="showProjectData" class="module-panel project-panel" variant="flat">
      <div class="section-head">
        <div>
          <div class="section-title-with-tip">
            <h2>{{ t('projectData') }}</h2>
            <InfoTooltip :text="t('projectDataTip')" />
          </div>
          <span>{{ t('projectRowsSummary', { total: projectRows.length, dirty: dirtyCount }) }}</span>
        </div>
      </div>

      <div class="project-file-actions">
        <v-text-field
          v-model="searchText"
          density="compact"
          hide-details
          clearable
          prepend-inner-icon="mdi-magnify"
          :placeholder="t('searchProject')"
          class="project-search"
        />
        <v-btn prepend-icon="mdi-plus" color="primary" variant="tonal" :loading="saving" @click="openProjectDialog">{{ t('add') }}</v-btn>
        <v-btn prepend-icon="mdi-content-save" color="secondary" variant="tonal" :disabled="!dirtyCount" :loading="saving" @click="saveProjects">{{ t('save') }}</v-btn>
        <v-btn prepend-icon="mdi-delete-outline" color="error" variant="tonal" :disabled="!selectedProject" :loading="saving" @click="deleteProject">{{ t('delete') }}</v-btn>
        <v-btn prepend-icon="mdi-refresh" :loading="loading" @click="loadProjects">{{ t('refreshProjects') }}</v-btn>
        <input ref="projectImportInput" type="file" accept=".xlsx,.xlsm" hidden @change="importProjects" />
        <v-btn prepend-icon="mdi-upload" :loading="saving" @click="triggerProjectImport">{{ t('importProjects') }}</v-btn>
        <v-btn prepend-icon="mdi-download" @click="exportProjects">{{ t('exportProjects') }}</v-btn>
      </div>

      <div ref="projectTableContainer" class="project-vtable-host" @wheel.stop @touchmove.stop />
    </v-card>

    <v-card
      v-if="showProjectWeldInfo"
      class="module-panel project-panel weld-panel"
      :class="{
        'is-loading': weldLoading,
        'is-empty': !weldColumns.length && !weldLoading && !weldErrorMessage,
      }"
      variant="flat"
    >
      <div class="section-head">
        <div>
          <h2>{{ t('projectWeldInfo') }}</h2>
        </div>
        <div class="project-file-actions">
          <v-btn prepend-icon="mdi-file-search-outline" :disabled="!selectedProject" @click="openFileParser">{{ t('fileParser') }}</v-btn>
          <v-btn prepend-icon="mdi-refresh" :disabled="!selectedProject" :loading="weldLoading" @click="loadProjectWelds(weldPage)">{{ t('refreshWelds') }}</v-btn>
        </div>
      </div>

      <v-alert v-if="weldErrorMessage" type="error" density="comfortable" class="status-alert weld-error-alert">
        {{ weldErrorMessage }}
      </v-alert>
      <v-alert
        v-else-if="selectedProjectNeedsInitialization"
        type="warning"
        variant="tonal"
        density="comfortable"
        class="status-alert project-init-alert"
      >
        <div class="project-init-alert-body">
          <div>
            <strong>{{ t('currentProjectNoInitializationData') }}</strong>
            <span>{{ selectedProjectInitializationHint }}</span>
          </div>
        </div>
      </v-alert>

      <div class="library-meta project-meta">
        <span>{{ t('project') }}：{{ selectedProject?.project_name || t('unselected') }}</span>
        <span>{{ t('weldRows') }}：{{ weldMeta.total }}</span>
        <span>{{ t('dataPath') }}：{{ weldMeta.dataPath || '-' }}</span>
      </div>

      <div class="project-file-actions weld-pagination">
        <v-select
          :model-value="weldPageSize"
          :items="weldPageSizeOptions"
          density="compact"
          hide-details
          class="weld-page-size"
          :placeholder="t('perPage')"
          :disabled="weldLoading || !selectedProject"
          @update:model-value="changeWeldPageSize"
        />
        <v-btn icon="mdi-chevron-left" variant="text" :disabled="weldLoading || weldPage <= 1" @click="changeWeldPage(weldPage - 1)" />
        <span class="page-indicator">{{ t('pageIndicator', { page: weldPage, total: weldTotalPages || 0 }) }}</span>
        <v-btn icon="mdi-chevron-right" variant="text" :disabled="weldLoading || !weldTotalPages || weldPage >= weldTotalPages" @click="changeWeldPage(weldPage + 1)" />
      </div>

      <div v-if="!weldColumns.length && !weldLoading" class="project-empty-note">
        {{ t('noProjectWeldInitializationData') }}
      </div>
      <div v-if="weldColumns.length" ref="weldTableContainer" class="project-vtable-host weld-vtable-host" @wheel.stop @touchmove.stop />
    </v-card>
  </v-sheet>

  <v-dialog v-model="projectDialog" max-width="860">
    <v-card class="project-create-dialog">
      <v-card-title class="project-create-head">
        <div>
          <strong>{{ t('addProject') }}</strong>
          <span>{{ t('addProjectDescription') }}</span>
        </div>
      </v-card-title>
      <v-card-text class="project-create-body">
        <v-alert v-if="projectFormError" :text="projectFormError" type="error" density="compact" class="status-alert" />
        <div class="project-dialog-grid">
          <label
            v-for="column in requiredProjectColumns"
            :key="column.field"
            class="project-form-field is-required"
          >
            <span>{{ column.title }} *</span>
            <v-text-field
              v-model="projectForm[column.field]"
              :type="projectInputType(column.field)"
              :placeholder="t('inputColumn', { column: column.title })"
              density="compact"
              hide-details
            />
          </label>
          <label
            v-for="column in optionalProjectColumns"
            :key="column.field"
            class="project-form-field"
          >
            <span>{{ column.title }}</span>
            <v-text-field
              v-model="projectForm[column.field]"
              :type="projectInputType(column.field)"
              :placeholder="t('inputColumn', { column: column.title })"
              density="compact"
              hide-details
            />
          </label>
        </div>
      </v-card-text>
      <v-card-actions class="project-create-actions">
        <v-spacer />
        <v-btn variant="text" @click="projectDialog = false">{{ t('cancel') }}</v-btn>
        <v-btn color="primary" variant="tonal" :loading="saving" @click="addProject">{{ t('confirmAdd') }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <UnsavedChangesDialog ref="unsavedChangesDialog" />
</template>
