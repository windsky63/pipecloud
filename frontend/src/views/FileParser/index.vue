<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute } from 'vue-router'
import {
  cancelParserJob,
  confirmIdfModel,
  confirmInitializationFile,
  downloadAllParserFiles,
  downloadCurrentParserFile,
  fetchLatestParserResult,
  fetchParserJobStatus,
  fetchParserPreview,
  fetchParserProjectList,
  mergeParserResults,
  parseUploadedFiles,
  uploadInitializationFile,
} from '../../api/fileParser'
import FileParserHeader from './FileParserHeader.vue'
import DataVTable from '../../components/DataVTable.vue'
import FileUploadDropzone from '../../components/FileUploadDropzone.vue'
import UnsavedChangesDialog from '../../components/UnsavedChangesDialog.vue'
import { t } from '../../services/pipecloudState'
import { selectedProjectId, selectedProjectParams, setSelectedProjectId } from '../../services/projectState'

const route = useRoute()
const parsing = ref(false)
const restoringResult = ref(false)
const cancelingJob = ref(false)
const confirming = ref(false)
const savingModel = ref(false)
const loadingProject = ref(false)
const selectedFiles = ref([])
const parseError = ref('')
const results = ref([])
const activeResultIndex = ref(0)
const activePreviewSheet = ref('')
const previewLoading = ref(false)
const downloadingPreview = ref(false)
const currentProject = ref(null)
const mode = ref(route.query.tab === 'parse' ? 'parse' : 'upload')
const unsavedChangesDialog = ref(null)
const uploadDropzone = ref(null)
const parserJob = ref(null)
const uploadProgress = ref(null)
let parserJobTimer = null

const snackbar = ref({
  show: false,
  text: '',
  color: 'success',
})

function notify(color, text) {
  snackbar.value = { show: true, color, text }
}

function clearResult() {
  stopParserJobPolling()
  parseError.value = ''
  results.value = []
  activeResultIndex.value = 0
  activePreviewSheet.value = ''
  parserJob.value = null
  uploadProgress.value = null
}

async function confirmDiscardParserResult(text = t('parserUnsavedLeaveText')) {
  if (!hasUnconfirmedResult.value) return true
  return unsavedChangesDialog.value?.open({
    title: t('parserUnsavedTitle'),
    text,
    confirmText: t('continueDiscard'),
    color: 'warning',
  }) ?? true
}

function fileExtension(name = '') {
  return name.split('.').pop()?.toLowerCase() || ''
}

function parserResultName(item, index) {
  return item.source === 'merge'
    ? t('mergedResult')
    : item.sourceName || item.filename || `${t('dataPreview')} ${index + 1}`
}

const acceptedFileTypes = computed(() => (mode.value === 'parse' ? '.idf,.pcf' : '.xlsx,.xlsm'))
const modeTitle = computed(() => (mode.value === 'parse' ? t('parseIdfPcf') : t('uploadInitializationData')))
const modeDescription = computed(() => (
  mode.value === 'parse'
    ? t('parseModeDescription')
    : t('uploadModeDescription')
))
const uploadProgressText = computed(() => {
  if (mode.value === 'upload') {
    return uploadProgress.value?.phase === 'preparing'
      ? t('initializationUploadPreparing')
      : t('initializationUploadProgress')
  }
  return uploadProgress.value?.phase === 'preparing'
    ? t('parserUploadPreparing')
    : t('parserUploadProgress')
})
const result = computed(() => results.value[activeResultIndex.value] || null)
const isParserJobActive = computed(() => (
  parserJob.value?.status === 'queued' || parserJob.value?.status === 'running'
))
const parserActionsLocked = computed(() => parsing.value || isParserJobActive.value)
const pendingResults = computed(() => results.value.filter((item) => (
  item?.stagedPath
  && !item?.confirmed
  && (
    item.source === 'upload'
    || (item.fileType === 'idf' && !item.modelSaved && !parserJob.value?.modelSaved)
  )
)))
const mergeableResults = computed(() => results.value.filter((item) => (
  item?.stagedPath && !item?.confirmed && item.source !== 'merge' && item.fileType !== 'idf'
)))
const previewRows = computed(() => result.value?.preview?.rows || [])
const previewColumns = computed(() => result.value?.preview?.columns || [])
function tableColumns(columns) {
  return columns.map((column) => ({
    field: column,
    title: column || '-',
    width: Math.max(140, Math.min(String(column || '').length * 16 + 56, 280)),
  }))
}
const previewTableColumns = computed(() => tableColumns(previewColumns.value))
const fixedPreviewColumns = computed(() => result.value?.preview?.fixedColumns || [])
const fixedPreviewRows = computed(() => result.value?.preview?.fixedRows || [])
const fixedPreviewTableColumns = computed(() => tableColumns(fixedPreviewColumns.value))
const extraPreviewColumns = computed(() => result.value?.preview?.extraColumns || [])
const extraPreviewRows = computed(() => result.value?.preview?.extraRows || [])
const extraPreviewTableColumns = computed(() => tableColumns(extraPreviewColumns.value))
const hasSplitInitializationPreview = computed(() => (
  result.value?.source === 'upload' && fixedPreviewColumns.value.length > 0
))
const previewSheets = computed(() => result.value?.preview?.sheets || [])
const normalization = computed(() => result.value?.normalization || result.value?.preview?.normalization || null)
const normalizationSheets = computed(() => normalization.value?.sheets || [])
const activeNormalizationSheet = computed(() => (
  normalizationSheets.value.find((item) => item.sheet === result.value?.preview?.sheet)
  || normalizationSheets.value[0]
  || null
))
const canImportResult = computed(() => !normalization.value || normalization.value.canImport !== false)
const aliasMappingText = computed(() => {
  const mappings = activeNormalizationSheet.value?.aliasMappings || []
  if (!mappings.length) return t('normalizationNoAliases')
  return mappings.slice(0, 8).map((item) => `${item.source} → ${item.target}`).join('，')
})
const missingRequiredText = computed(() => {
  const fields = activeNormalizationSheet.value?.missingRequiredFields || []
  return fields.map((item) => item.column).join('，')
})
const invalidRowsText = computed(() => {
  const rows = activeNormalizationSheet.value?.invalidRows || []
  return rows.slice(0, 5).map((item) => `${t('rowIndex', { index: item.rowIndex + 1 })}：${item.missingColumns.join(' / ')}`).join('；')
})
const hasPreview = computed(() => previewColumns.value.length > 0)
const hasUnconfirmedResult = computed(() => pendingResults.value.length > 0)
const isIdfResult = computed(() => (
  result.value?.fileType === 'idf' && Number(result.value?.modelPartIndex) > 0
))
const canImportSpreadsheet = computed(() => result.value?.source === 'upload')
const downloadableResults = computed(() => results.value.filter((item) => item?.artifactId || item?.stagedPath))

const projectStatusColor = computed(() => (currentProject.value ? 'primary' : 'warning'))
const idfModelStatus = computed(() => currentProject.value?.parserModels?.idf || null)
const projectStatusItems = computed(() => {
  const project = currentProject.value
  if (!project) return []
  const idf = idfModelStatus.value
  return [
    {
      key: 'initialization',
      icon: 'mdi-database-check-outline',
      title: '焊口初始化数据',
      color: project.hasInitializationData ? 'success' : 'warning',
      status: project.hasInitializationData ? t('ready') : t('notFound'),
      detail: project.weldFile?.name || project.initializationHint || t('notFound'),
    },
    {
      key: 'prefab',
      icon: 'mdi-source-branch-check',
      title: '预制焊口库',
      color: project.prefabWeldFile ? 'success' : 'warning',
      status: project.prefabWeldFile ? t('ready') : t('notFound'),
      detail: project.prefabWeldFile?.name || '生成预制焊口库后可用于管道校验',
    },
    {
      key: 'idf-model',
      icon: 'mdi-cube-scan',
      title: 'IDF模型文件',
      color: idf?.exists ? 'success' : (idf?.status && idf.status !== 'missing' ? 'info' : 'warning'),
      status: idf?.exists ? t('ready') : parserStatusText(idf?.status),
      detail: idf?.modelFile?.name || idf?.message || '解析并预览 IDF 后，由用户确认是否保存',
      meta: idf ? `${idf.inputFileCount || 0} IDF / ${idf.resultCount || 0} 结果${idf.percent ? ` / ${idf.percent}%` : ''}` : '',
    },
  ]
})

function validateFiles(files) {
  const allowed = mode.value === 'parse' ? ['idf', 'pcf'] : ['xlsx', 'xlsm']
  const invalid = files.filter((file) => !allowed.includes(fileExtension(file.name)))

  if (invalid.length) {
    throw new Error(t('onlySupportFiles', {
      types: allowed.join(' / '),
      files: invalid.map((file) => file.name).join(' / '),
    }))
  }

  const fileTypes = new Set(files.map((file) => fileExtension(file.name)))
  if (mode.value === 'parse' && fileTypes.size > 1) {
    throw new Error(t('uploadSameFormat'))
  }
}

function normalizeParserResults(payload) {
  const list = Array.isArray(payload?.results) ? payload.results : (payload?.stagedPath ? [payload] : [])
  return list.map((item, index) => ({
    ...item,
    id: item.stagedPath || `${Date.now()}-${index}`,
    confirmed: Boolean(item.confirmed),
  }))
}

function syncActivePreviewSheet() {
  activePreviewSheet.value = result.value?.preview?.sheet || previewSheets.value[0] || ''
}

async function changePreviewSheet(sheet) {
  if (!result.value?.stagedPath || !sheet || sheet === result.value?.preview?.sheet) {
    activePreviewSheet.value = sheet || ''
    return
  }
  const targetIndex = activeResultIndex.value
  previewLoading.value = true
  parseError.value = ''
  try {
    const payload = await fetchParserPreview({
      artifactId: result.value.artifactId,
      stagedPath: result.value.stagedPath,
      sheet,
      previewMode: result.value.source === 'upload' ? 'initialization' : 'raw',
    })
    results.value[targetIndex] = {
      ...results.value[targetIndex],
      preview: payload.preview,
      normalization: payload.normalization,
      totalRows: payload.totalRows,
    }
    activePreviewSheet.value = payload.preview?.sheet || sheet
  } catch (error) {
    activePreviewSheet.value = result.value?.preview?.sheet || ''
    parseError.value = t('parseFailed', { message: error.message })
  } finally {
    previewLoading.value = false
  }
}

function parserStatusText(status) {
  if (!status || status === 'missing') return t('notFound')
  return t(`parserJobStatus_${status}`)
}

function stopParserJobPolling() {
  if (parserJobTimer) {
    window.clearTimeout(parserJobTimer)
    parserJobTimer = null
  }
}

async function pollParserJob(jobId) {
  stopParserJobPolling()
  try {
    const payload = await fetchParserJobStatus(jobId)
    parserJob.value = payload
    if (['completed', 'failed', 'canceled'].includes(payload.status)) {
      results.value = normalizeParserResults(payload)
      activeResultIndex.value = 0
      syncActivePreviewSheet()
      parsing.value = false
      if (payload.status === 'completed' && results.value.length) {
        loadCurrentProject()
        notify('success', payload.reused ? t('parserJobReused') : t('parseCompletedConfirmImport'))
      } else if (payload.errors?.length) {
        parseError.value = t('parserJobFailed', { message: payload.message || payload.errors[0]?.error || '-' })
      } else if (payload.status === 'canceled') {
        notify('warning', t('parserJobCanceled'))
      }
      return
    }
    parserJobTimer = window.setTimeout(() => pollParserJob(jobId), 1500)
  } catch (error) {
    parsing.value = false
    parseError.value = t('parseFailed', { message: error.message })
  }
}

async function loadCurrentProject() {
  loadingProject.value = true
  try {
    const payload = await fetchParserProjectList()
    const projects = payload.rows || []
    let nextProject = projects.find((project) => project.id === selectedProjectId.value) || null
    if (!nextProject) {
      nextProject = projects[0] || null
      setSelectedProjectId(nextProject?.id || null)
    }
    currentProject.value = nextProject
  } catch {
    currentProject.value = null
  } finally {
    loadingProject.value = false
  }
}

async function submitFiles() {
  if (parserActionsLocked.value) return
  if (!(await confirmDiscardParserResult(t('parserUnsavedReparseText')))) return
  clearResult()

  const files = Array.from(selectedFiles.value || [])
  if (!files.length) {
    notify('warning', t('selectFileFirst'))
    return
  }

  try {
    validateFiles(files)

    parsing.value = true

    const payload = mode.value === 'parse'
      ? await parseUploadedFiles(selectedProjectParams(), files, (progress) => {
        uploadProgress.value = progress
      })
      : await uploadInitializationFile(selectedProjectParams(), files, ({ loaded, total }) => {
        const ratio = total > 0 ? Math.min(loaded / total, 1) : 0
        uploadProgress.value = {
          phase: ratio >= 1 ? 'preparing' : 'uploading',
          percent: Math.round(ratio * 100),
          uploadedFiles: ratio >= 1 ? files.length : Math.floor(files.length * ratio),
          totalFiles: files.length,
        }
      })

    uploadProgress.value = null
    if (payload?.jobId && payload?.status !== 'completed' && payload?.status !== 'failed') {
      parserJob.value = payload
      notify('success', t('parserJobSubmitted'))
      pollParserJob(payload.jobId)
      return
    }

    if (payload?.jobId) {
      parserJob.value = payload
      if (payload.status === 'completed') await loadCurrentProject()
    }

    results.value = normalizeParserResults(payload)
    activeResultIndex.value = 0
    syncActivePreviewSheet()
    notify('success', payload?.reused ? t('parserJobReused') : (mode.value === 'parse' ? t('parseCompletedConfirmImport') : t('uploadCompletedConfirmImport')))
  } catch (error) {
    parseError.value = mode.value === 'parse'
      ? t('parseFailed', { message: error.message })
      : t('uploadFailed', { message: error.message })
  } finally {
    uploadProgress.value = null
    parsing.value = false
  }
}

async function restoreLastParseResult() {
  if (parserActionsLocked.value) return
  if (!(await confirmDiscardParserResult(t('parserUnsavedReparseText')))) return

  restoringResult.value = true
  parseError.value = ''
  try {
    const payload = await fetchLatestParserResult(selectedProjectParams())
    stopParserJobPolling()
    selectedFiles.value = []
    uploadProgress.value = null
    parserJob.value = payload
    results.value = normalizeParserResults(payload)
    activeResultIndex.value = 0
    syncActivePreviewSheet()
    notify('success', t('parserLastResultRestored'))
  } catch (error) {
    if (error.status === 404) {
      notify('warning', t('parserNoLastResult'))
    } else {
      parseError.value = t('parserRestoreFailed', { message: error.message })
    }
  } finally {
    restoringResult.value = false
  }
}

async function cancelCurrentParserJob() {
  if (!isParserJobActive.value || !parserJob.value?.jobId || cancelingJob.value) return
  const confirmed = await unsavedChangesDialog.value?.open({
    title: t('parserCancelTitle'),
    text: t('parserCancelConfirmText'),
    confirmText: t('interruptParsing'),
    color: 'error',
  })
  if (!confirmed) return

  cancelingJob.value = true
  parseError.value = ''
  try {
    const payload = await cancelParserJob(parserJob.value.jobId)
    stopParserJobPolling()
    parserJob.value = payload
    parsing.value = false
    notify('warning', t('parserJobCanceled'))
  } catch (error) {
    parseError.value = t('parserCancelFailed', { message: error.message })
  } finally {
    cancelingJob.value = false
  }
}

async function confirmImport(importMode) {
  if (!canImportSpreadsheet.value) {
    notify('warning', '解析生成的表格仅供下载，不允许导入数据库。')
    return
  }
  if (!result.value?.artifactId && !result.value?.stagedPath) {
    notify('warning', t('noConfirmableFile'))
    return
  }
  if (!canImportResult.value) {
    notify('error', t('normalizationCannotImport'))
    return
  }
  const confirmed = await unsavedChangesDialog.value?.open({
    title: t('parserImportConfirmTitle'),
    text: t('parserImportConfirmText', {
      file: result.value.filename || result.value.sourceName || '-',
      mode: importMode === 'append' ? t('appendImport') : t('replaceImport'),
    }),
    confirmText: t('confirmImport'),
    color: importMode === 'append' ? 'primary' : 'warning',
  })
  if (!confirmed) return

  confirming.value = true
  parseError.value = ''
  try {
    const targetIndex = activeResultIndex.value
    const payload = await confirmInitializationFile(selectedProjectParams(), {
      artifactId: result.value.artifactId,
      stagedPath: result.value.stagedPath,
      filename: result.value.filename,
      importMode,
    })
    results.value[targetIndex] = {
      ...results.value[targetIndex],
      confirmed: true,
      importMode: payload.importMode,
      projectFile: payload.file,
      confirmMessage: payload.message,
    }
    if (results.value[targetIndex]?.source === 'merge') {
      const mergedPathSet = new Set(results.value[targetIndex].mergedFromPaths || [])
      results.value = results.value.map((item, index) => {
        if (index === targetIndex || !mergedPathSet.has(item.stagedPath)) return item
        return {
          ...item,
          confirmed: true,
          importMode: payload.importMode,
          projectFile: payload.file,
          confirmMessage: t('importedByMergedResult'),
        }
      })
    }
    await loadCurrentProject()
    notify('success', payload.importMode === 'append' ? t('importedAppend') : t('importedReplace'))
  } catch (error) {
    parseError.value = t('confirmImportFailed', { message: error.message })
  } finally {
    confirming.value = false
  }
}

async function saveIdfModel() {
  if (!parserJob.value?.jobId || !isIdfResult.value) {
    notify('warning', '没有可保存的 IDF 模型。')
    return
  }
  const confirmed = await unsavedChangesDialog.value?.open({
    title: '保存 IDF 模型',
    text: '确认将当前已预览的 IDF 模型保存到项目数据库吗？',
    confirmText: '确认保存',
    color: 'primary',
  })
  if (!confirmed) return

  savingModel.value = true
  parseError.value = ''
  try {
    const payload = await confirmIdfModel(selectedProjectParams(), parserJob.value.jobId)
    parserJob.value = { ...parserJob.value, modelSaved: true }
    results.value = results.value.map((item) => (
      item.fileType === 'idf' ? { ...item, modelSaved: true } : item
    ))
    await loadCurrentProject()
    notify('success', payload.message)
  } catch (error) {
    parseError.value = `保存 IDF 模型失败：${error.message}`
  } finally {
    savingModel.value = false
  }
}

async function mergeResults() {
  const mergeSources = mergeableResults.value
  if (mergeSources.length < 2) {
    notify('warning', t('parserMergeNeedTwo'))
    return
  }

  parsing.value = true
  parseError.value = ''
  try {
    const payload = await mergeParserResults(selectedProjectParams(), {
      sources: mergeSources.map((item) => ({
        artifactId: item.artifactId,
        stagedPath: item.stagedPath,
      })),
      stagedPaths: mergeSources.map((item) => item.stagedPath),
    })
    results.value = [{
      ...payload,
      id: payload.stagedPath || `${Date.now()}-merge`,
      confirmed: false,
    }]
    activeResultIndex.value = 0
    syncActivePreviewSheet()
    notify('success', t('parserMergeCompleted'))
  } catch (error) {
    parseError.value = t('parserMergeFailed', { message: error.message })
  } finally {
    parsing.value = false
  }
}

function saveDownloadedBlob(blob, filename) {
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
}

async function downloadCurrentPreview() {
  if (!result.value?.artifactId && !result.value?.stagedPath) {
    notify('warning', t('noDownloadableExcel'))
    return
  }
  downloadingPreview.value = true
  try {
    const blob = await downloadCurrentParserFile(result.value)
    saveDownloadedBlob(blob, result.value.filename || 'parsed.xlsx')
  } catch (error) {
    notify('error', t('downloadPreviewFailed', { message: error.message }))
  } finally {
    downloadingPreview.value = false
  }
}

async function downloadAllPreviews() {
  if (!downloadableResults.value.length) {
    notify('warning', t('noDownloadableExcel'))
    return
  }
  downloadingPreview.value = true
  try {
    const blob = await downloadAllParserFiles(downloadableResults.value)
    saveDownloadedBlob(blob, t('allPreviewFilesArchive'))
  } catch (error) {
    notify('error', t('downloadPreviewFailed', { message: error.message }))
  } finally {
    downloadingPreview.value = false
  }
}

function resetFilesNow() {
  selectedFiles.value = []
  clearResult()
}

async function resetFiles() {
  if (parserActionsLocked.value) return
  if (!(await confirmDiscardParserResult(t('parserUnsavedClearText')))) return
  resetFilesNow()
}

async function changeMode(nextMode) {
  if (parserActionsLocked.value) return
  if (nextMode === mode.value) return
  if (!(await confirmDiscardParserResult(t('parserUnsavedModeText')))) return
  mode.value = nextMode
  resetFilesNow()
}

async function setFiles(files) {
  if (parserActionsLocked.value) return
  if (!(await confirmDiscardParserResult(t('parserUnsavedReplaceFileText')))) return
  selectedFiles.value = Array.from(files || [])
  clearResult()
}

function selectFolder() {
  uploadDropzone.value?.openFolderPicker()
}

function handleBeforeUnload(event) {
  if (!hasUnconfirmedResult.value) return
  event.preventDefault()
  event.returnValue = t('parserUnsavedLeaveText')
}

onMounted(() => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  loadCurrentProject()
})

onBeforeRouteLeave(async () => confirmDiscardParserResult())
onBeforeRouteUpdate(async () => confirmDiscardParserResult())

onBeforeUnmount(() => {
  stopParserJobPolling()
  window.removeEventListener('beforeunload', handleBeforeUnload)
})

watch(activeResultIndex, () => {
  syncActivePreviewSheet()
})
watch(() => route.query.tab, (tab) => {
  const nextMode = tab === 'parse' ? 'parse' : 'upload'
  if (nextMode !== mode.value && !hasUnconfirmedResult.value) {
    mode.value = nextMode
    resetFilesNow()
  }
})
</script>

<template>
  <FileParserHeader :title="t('fileParser')" :description="t('fileParserDescription')" />

  <v-alert
    v-if="parseError"
    :text="parseError"
    type="error"
    density="compact"
    class="status-alert"
  />

  <v-sheet class="parser-layout" color="transparent">
    <v-card class="module-panel parser-status-panel" :loading="loadingProject">
      <div class="parser-project-head">
        <v-avatar :color="projectStatusColor" variant="tonal" rounded="lg">
          <v-icon icon="mdi-folder-information-outline" />
        </v-avatar>
        <div>
          <span>{{ t('currentProject') }}</span>
          <strong>{{ currentProject?.project_name || t('noProjectSelected') }}</strong>
        </div>
      </div>
      <div v-if="projectStatusItems.length" class="parser-project-status-list">
        <div
          v-for="item in projectStatusItems"
          :key="item.key"
          class="parser-project-status-item"
        >
          <v-icon :icon="item.icon" :color="item.color" size="22" />
          <div>
            <div class="parser-project-status-title">
              <strong>{{ item.title }}</strong>
              <v-chip :color="item.color" variant="tonal" size="x-small">{{ item.status }}</v-chip>
            </div>
            <span>{{ item.detail }}</span>
            <small v-if="item.meta">{{ item.meta }}</small>
          </div>
        </div>
      </div>
      <InfoTooltip
        :text="currentProject?.initializationHint || (currentProject?.weldFile ? t('importHintWithExistingFile') : t('importHintNoFile'))"
        location="bottom"
      />
    </v-card>

    <v-card class="module-panel parser-upload-panel" :loading="parsing && !isParserJobActive">
      <div class="section-head">
        <div>
          <h2>
            {{ modeTitle }}
            <InfoTooltip :text="modeDescription" location="bottom" />
          </h2>
        </div>
      </div>

      <v-btn-toggle
        :model-value="mode"
        color="primary"
        density="compact"
        mandatory
        class="parser-mode-toggle"
        :disabled="parserActionsLocked"
        @update:model-value="changeMode"
      >
        <v-btn value="upload" prepend-icon="mdi-upload">{{ t('initializationUpload') }}</v-btn>
        <v-btn value="parse" prepend-icon="mdi-file-search-outline">{{ t('fileParse') }}</v-btn>
      </v-btn-toggle>

      <FileUploadDropzone
        ref="uploadDropzone"
        :files="selectedFiles"
        :accept="acceptedFileTypes"
        multiple
        :disabled="parserActionsLocked"
        @files-selected="setFiles"
      />

      <v-alert
        v-if="uploadProgress && !parserJob"
        type="info"
        variant="tonal"
        density="compact"
        class="parser-job-alert"
      >
        <div class="parser-job-head">
          <strong>{{ uploadProgressText }}</strong>
          <span>{{ uploadProgress.percent || 0 }}%</span>
        </div>
        <v-progress-linear
          :model-value="uploadProgress.percent || 0"
          height="8"
          rounded
          color="primary"
          class="parser-job-progress"
        />
        <div class="parser-job-message">
          {{ t('parserUploadFileCount', {
            uploaded: uploadProgress.uploadedFiles || 0,
            total: uploadProgress.totalFiles || 0,
          }) }}
        </div>
      </v-alert>

      <v-alert
        v-if="parserJob"
        :type="parserJob.status === 'failed' ? 'error' : (parserJob.status === 'completed' ? 'success' : (parserJob.status === 'canceled' ? 'warning' : 'info'))"
        variant="tonal"
        density="compact"
        class="parser-job-alert"
      >
        <div class="parser-job-head">
          <strong>{{ t('parserJobStatus') }}：{{ t(`parserJobStatus_${parserJob.status || 'queued'}`) }}</strong>
          <span>{{ parserJob.completed || 0 }}/{{ parserJob.total || 0 }} · {{ t('parserJobFailedCount', { count: parserJob.failed || 0 }) }}</span>
        </div>
        <v-progress-linear
          :model-value="parserJob.percent || 0"
          height="8"
          rounded
          color="primary"
          class="parser-job-progress"
        />
        <div class="parser-job-message">
          {{ parserJob.current || parserJob.message || t('parserJobSubmitted') }}
        </div>
      </v-alert>

      <div class="parser-actions">
        <v-btn
          prepend-icon="mdi-folder-upload-outline"
          color="secondary"
          variant="tonal"
          :disabled="parserActionsLocked"
          @click="selectFolder"
        >
          {{ t('selectFolder') }}
        </v-btn>

        <v-btn
          color="primary"
          prepend-icon="mdi-cog-play"
          :loading="parsing && !isParserJobActive"
          :disabled="parserActionsLocked || !selectedFiles?.length"
          @click="submitFiles"
        >
          {{ mode === 'parse' ? t('parseToExcel') : t('uploadAndPreview') }}
        </v-btn>

        <v-btn
          v-if="mode === 'parse'"
          prepend-icon="mdi-history"
          color="primary"
          variant="tonal"
          :loading="restoringResult"
          :disabled="parserActionsLocked"
          @click="restoreLastParseResult"
        >
          {{ t('restoreLastParseResult') }}
        </v-btn>

        <v-btn
          prepend-icon="mdi-refresh"
          :disabled="parserActionsLocked"
          @click="resetFiles"
        >
          {{ t('clear') }}
        </v-btn>

        <v-btn
          prepend-icon="mdi-call-merge"
          color="secondary"
          variant="tonal"
          :loading="parsing && !isParserJobActive"
          :disabled="parserActionsLocked || mergeableResults.length < 2"
          @click="mergeResults"
        >
          {{ t('mergeResults') }}
        </v-btn>

        <v-btn
          v-if="canImportSpreadsheet"
          color="success"
          prepend-icon="mdi-file-sync-outline"
          :loading="confirming"
          :disabled="parserActionsLocked || (!result?.artifactId && !result?.stagedPath) || result?.confirmed || !canImportResult"
          @click="confirmImport('replace')"
        >
          {{ t('replaceImport') }}
        </v-btn>

        <v-btn
          v-if="canImportSpreadsheet"
          color="primary"
          variant="tonal"
          prepend-icon="mdi-table-row-plus-after"
          :loading="confirming"
          :disabled="parserActionsLocked || (!result?.artifactId && !result?.stagedPath) || result?.confirmed || !canImportResult"
          @click="confirmImport('append')"
        >
          {{ t('appendImport') }}
        </v-btn>

        <v-btn
          v-if="isIdfResult"
          color="primary"
          prepend-icon="mdi-database-plus-outline"
          :loading="savingModel"
          :disabled="parserActionsLocked || parserJob?.modelSaved || result?.modelSaved || !parserJob?.modelAvailable"
          @click="saveIdfModel"
        >
          {{ parserJob?.modelSaved || result?.modelSaved ? '模型已保存' : '保存 IDF 模型' }}
        </v-btn>

        <v-btn
          v-if="mode === 'parse'"
          prepend-icon="mdi-download"
          :loading="downloadingPreview"
          :disabled="parserActionsLocked || (!result?.artifactId && !result?.stagedPath)"
          @click="downloadCurrentPreview"
        >
          {{ t('downloadCurrentPreviewFile') }}
        </v-btn>

        <v-btn
          v-if="mode === 'parse'"
          prepend-icon="mdi-folder-download-outline"
          variant="tonal"
          :disabled="parserActionsLocked || downloadingPreview || !downloadableResults.length"
          @click="downloadAllPreviews"
        >
          {{ t('downloadAllPreviewFiles') }}
        </v-btn>

        <v-btn
          v-if="isParserJobActive"
          prepend-icon="mdi-stop-circle-outline"
          color="error"
          variant="tonal"
          :loading="cancelingJob"
          @click="cancelCurrentParserJob"
        >
          {{ t('interruptParsing') }}
        </v-btn>
      </div>

      <div class="parser-preview-panel">
        <div class="section-head">
          <div>
            <h2>
              {{ t('dataPreview') }}
              <InfoTooltip
                :text="result
                  ? `${result.preview?.sheet || t('defaultSheet')}，${t('previewRowsSummary', { shown: result.preview?.rows?.length || 0, total: result.preview?.total || 0 })}`
                  : t('waitForPreview')"
                location="bottom"
              />
            </h2>
          </div>
          <v-select
            v-if="previewSheets.length > 1"
            :model-value="activePreviewSheet"
            :items="previewSheets"
            :loading="previewLoading"
            density="compact"
            hide-details
            prepend-inner-icon="mdi-table"
            class="parser-sheet-select"
            @update:model-value="changePreviewSheet"
          />
        </div>

        <div v-if="results.length" class="parser-result-tabs">
          <div class="parser-result-tabs-scroll">
            <v-tabs v-model="activeResultIndex" color="primary" show-arrows>
              <v-tab
                v-for="(item, index) in results"
                :key="item.id || item.stagedPath || index"
                :value="index"
              >
                <v-tooltip location="top" open-delay="150">
                  <template #activator="{ props }">
                    <span v-bind="props" class="parser-result-tab-label">
                      {{ parserResultName(item, index) }}
                    </span>
                  </template>
                  <span>{{ parserResultName(item, index) }}</span>
                </v-tooltip>
              </v-tab>
            </v-tabs>
          </div>
          <div class="parser-result-summary">
            <span>{{ t('resultCount', { count: results.length }) }}</span>
            <span>{{ t('waitingForConfirm') }}：{{ pendingResults.length }}</span>
            <span v-if="result?.preview?.sheet">{{ result.preview.sheet }}</span>
          </div>
        </div>

        <v-alert
          v-if="result || normalization"
          :type="normalization ? (canImportResult ? 'success' : 'error') : 'success'"
          variant="tonal"
          density="compact"
          class="parser-preview-alert"
        >
          <div v-if="result">{{ result.confirmed ? t('imported') : t('waitingConfirm') }}：{{ result.filename || 'parsed.xlsx' }}</div>
          <div v-if="result?.totalRows !== undefined">{{ t('totalRows') }}：{{ result.totalRows }}</div>
          <div v-if="result?.projectFile?.name">{{ t('projectFile') }}：{{ result.projectFile.name }}</div>
          <div v-if="result?.confirmMessage">{{ result.confirmMessage }}</div>
          <div v-else-if="result?.message">{{ result.message }}</div>
          <div v-if="normalization">
            {{ canImportResult ? t('normalizationCanImport') : t('normalizationCannotImport') }}
          </div>
          <div v-if="normalization">{{ t('normalizationAliasMappings') }}：{{ aliasMappingText }}</div>
          <div v-if="missingRequiredText">{{ t('normalizationMissingRequired') }}：{{ missingRequiredText }}</div>
          <div v-if="invalidRowsText">{{ t('normalizationInvalidRows') }}：{{ invalidRowsText }}</div>
        </v-alert>

        <template v-if="hasSplitInitializationPreview">
          <div class="parser-preview-subsection">
            <div class="parser-preview-subsection-title">
              <strong>固定字段</strong>
              <span>{{ fixedPreviewColumns.length }} 列</span>
            </div>
            <DataVTable
              :records="fixedPreviewRows"
              :columns="fixedPreviewTableColumns"
              :height="360"
            />
          </div>
          <div class="parser-preview-subsection">
            <div class="parser-preview-subsection-title">
              <strong>额外字段</strong>
              <span>{{ extraPreviewColumns.length }} 列</span>
            </div>
            <DataVTable
              v-if="extraPreviewColumns.length"
              :records="extraPreviewRows"
              :columns="extraPreviewTableColumns"
              :height="300"
            />
            <v-alert
              v-else
              type="info"
              variant="tonal"
              density="compact"
              text="当前文件没有固定模型之外的额外字段。"
            />
          </div>
        </template>
        <DataVTable
          v-else-if="hasPreview"
          :records="previewRows"
          :columns="previewTableColumns"
          :height="360"
        />
        <div v-else class="parser-preview-empty">
          <v-icon icon="mdi-table-eye-off" size="34" />
          <strong>{{ t('noPreviewData') }}</strong>
          <InfoTooltip :text="t('previewEmptyHint')" location="bottom" />
        </div>
      </div>

    </v-card>
  </v-sheet>

  <v-snackbar v-model="snackbar.show" :color="snackbar.color" timeout="2600">
    {{ snackbar.text }}
  </v-snackbar>

  <UnsavedChangesDialog ref="unsavedChangesDialog" />
</template>

<style scoped>
.parser-layout {
  display: grid;
  grid-template-columns: minmax(260px, 340px) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.parser-status-panel,
.parser-upload-panel {
  min-height: 100%;
}

.parser-project-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.parser-project-head span {
  display: block;
  color: var(--muted);
  font-size: 12px;
}

.parser-project-head strong {
  display: block;
  color: var(--strong);
  font-size: 17px;
  overflow-wrap: anywhere;
}

.parser-project-status-list {
  display: grid;
  gap: 10px;
  margin: 12px 0;
}

.parser-project-status-item {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel-soft);
}

.parser-project-status-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
  margin-bottom: 4px;
}

.parser-project-status-title strong {
  min-width: 0;
  color: var(--strong);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.parser-project-status-item span,
.parser-project-status-item small {
  display: block;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.parser-project-status-item small {
  margin-top: 2px;
}

.parser-status-panel p {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.parser-mode-toggle {
  margin-bottom: 14px;
}

.parser-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
  flex-wrap: wrap;
}

.parser-job-alert {
  margin-top: 14px;
}

.parser-job-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  color: var(--strong);
}

.parser-job-progress {
  margin: 8px 0;
}

.parser-job-message {
  color: var(--muted);
  font-size: 13px;
}

.parser-result-tabs {
  min-width: 0;
  margin-top: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
}

.parser-result-tabs-scroll {
  max-width: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-gutter: stable;
  padding-bottom: 8px;
}

.parser-result-tabs-scroll :deep(.v-tabs) {
  min-width: max-content;
}

.parser-result-tabs-scroll :deep(.v-slide-group__container) {
  overflow: visible;
}

.parser-result-tabs :deep(.v-tab) {
  max-width: 220px;
  min-width: 0;
  overflow: hidden;
  justify-content: flex-start;
}

.parser-result-tabs :deep(.v-tab .v-btn__content) {
  display: block;
  width: 100%;
  min-width: 0;
  overflow: hidden;
}

.parser-result-tab-label {
  display: inline-block;
  width: 100%;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
  vertical-align: top;
}

.parser-result-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 12px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 12px;
}

.parser-preview-panel {
  margin-top: 16px;
}

.parser-preview-subsection + .parser-preview-subsection {
  margin-top: 18px;
}

.parser-preview-subsection-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  color: var(--muted);
  font-size: 13px;
}

.parser-preview-subsection-title strong {
  color: var(--strong);
  font-size: 14px;
}

.parser-sheet-select {
  width: min(280px, 100%);
  flex: 0 1 280px;
}

.parser-preview-alert {
  margin-top: 12px;
  margin-bottom: 12px;
}

.parser-preview-empty {
  display: grid;
  min-height: 240px;
  align-content: center;
  justify-items: center;
  gap: 8px;
  padding: 26px;
  border: 1px dashed var(--line);
  border-radius: 8px;
  background: var(--panel-soft);
  color: var(--muted);
  text-align: center;
}

.parser-preview-empty strong {
  color: var(--strong);
  font-size: 15px;
}

.parser-preview-empty span {
  max-width: 360px;
  font-size: 13px;
  line-height: 1.6;
}

@media (max-width: 900px) {
  .parser-layout {
    grid-template-columns: 1fr;
  }
}
</style>
