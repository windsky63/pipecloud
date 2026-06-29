<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import {
  confirmInitializationFile,
  fetchParserJobStatus,
  fetchParserPreview,
  fetchParserProjectList,
  mergeParserResults,
  parseUploadedFiles,
  uploadInitializationFile,
} from '../../api/fileParser'
import FileParserHeader from './FileParserHeader.vue'
import FileUploadDropzone from '../../components/FileUploadDropzone.vue'
import UnsavedChangesDialog from '../../components/UnsavedChangesDialog.vue'
import { t } from '../../services/pipecloudState'
import { selectedProjectId, selectedProjectParams, setSelectedProjectId } from '../../services/projectState'

const parsing = ref(false)
const confirming = ref(false)
const loadingProject = ref(false)
const selectedFiles = ref([])
const parseError = ref('')
const results = ref([])
const activeResultIndex = ref(0)
const activePreviewSheet = ref('')
const previewLoading = ref(false)
const currentProject = ref(null)
const mode = ref('parse')
const unsavedChangesDialog = ref(null)
const uploadDropzone = ref(null)
const parserJob = ref(null)
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

const selectedFileType = computed(() => {
  const files = Array.from(selectedFiles.value || [])
  const types = new Set(files.map((file) => fileExtension(file.name)).filter(Boolean))
  return types.size === 1 ? Array.from(types)[0].toUpperCase() : ''
})

const acceptedFileTypes = computed(() => (mode.value === 'parse' ? '.idf,.pcf' : '.xlsx,.xlsm'))
const modeTitle = computed(() => (mode.value === 'parse' ? t('parseIdfPcf') : t('uploadInitializationData')))
const modeDescription = computed(() => (
  mode.value === 'parse'
    ? t('parseModeDescription')
    : t('uploadModeDescription')
))
const result = computed(() => results.value[activeResultIndex.value] || null)
const pendingResults = computed(() => results.value.filter((item) => item?.stagedPath && !item?.confirmed))
const previewRows = computed(() => result.value?.preview?.rows || [])
const previewColumns = computed(() => result.value?.preview?.columns || [])
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
      detail: idf?.modelFile?.name || idf?.message || '解析 IDF 后生成 IDF模型数据.json',
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
    if (payload.status === 'completed' || payload.status === 'failed') {
      results.value = normalizeParserResults(payload)
      activeResultIndex.value = 0
      syncActivePreviewSheet()
      parsing.value = false
      if (payload.status === 'completed' && results.value.length) {
        loadCurrentProject()
        notify('success', payload.reused ? t('parserJobReused') : t('parseCompletedConfirmImport'))
      } else if (payload.errors?.length) {
        parseError.value = t('parserJobFailed', { message: payload.message || payload.errors[0]?.error || '-' })
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
      ? await parseUploadedFiles(selectedProjectParams(), files)
      : await uploadInitializationFile(selectedProjectParams(), files)

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
    parsing.value = false
  }
}

async function confirmImport(importMode) {
  if (!result.value?.stagedPath) {
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

async function mergeResults() {
  const mergeSources = results.value.filter((item) => item?.stagedPath && !item?.confirmed && item.source !== 'merge')
  if (mergeSources.length < 2) {
    notify('warning', t('parserMergeNeedTwo'))
    return
  }

  parsing.value = true
  parseError.value = ''
  try {
    const payload = await mergeParserResults(selectedProjectParams(), {
      stagedPaths: mergeSources.map((item) => item.stagedPath),
    })
    results.value = [
      ...results.value,
      {
        ...payload,
        id: payload.stagedPath || `${Date.now()}-merge`,
        confirmed: false,
      },
    ]
    activeResultIndex.value = results.value.length - 1
    syncActivePreviewSheet()
    notify('success', t('parserMergeCompleted'))
  } catch (error) {
    parseError.value = t('parserMergeFailed', { message: error.message })
  } finally {
    parsing.value = false
  }
}

function downloadExcel() {
  if (!result.value?.downloadUrl) {
    notify('warning', t('noDownloadableExcel'))
    return
  }

  const link = document.createElement('a')
  link.href = result.value.downloadUrl
  link.download = result.value.filename || 'parsed.xlsx'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

function resetFilesNow() {
  selectedFiles.value = []
  clearResult()
}

async function resetFiles() {
  if (!(await confirmDiscardParserResult(t('parserUnsavedClearText')))) return
  resetFilesNow()
}

async function changeMode(nextMode) {
  if (nextMode === mode.value) return
  if (!(await confirmDiscardParserResult(t('parserUnsavedModeText')))) return
  mode.value = nextMode
  resetFilesNow()
}

async function setFiles(files) {
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

watch(activeResultIndex, syncActivePreviewSheet)
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

    <v-card class="module-panel parser-upload-panel" :loading="parsing">
      <div class="section-head">
        <div>
          <h2>
            {{ modeTitle }}
            <InfoTooltip :text="modeDescription" location="bottom" />
          </h2>
        </div>
        <v-chip color="primary" variant="flat">
          {{ t('fileCount', { count: selectedFiles?.length || 0 }) }}{{ selectedFileType ? ` / ${selectedFileType}` : '' }}
        </v-chip>
      </div>

      <v-btn-toggle
        :model-value="mode"
        color="primary"
        density="compact"
        mandatory
        class="parser-mode-toggle"
        @update:model-value="changeMode"
      >
        <v-btn value="parse" prepend-icon="mdi-file-search-outline">{{ t('fileParse') }}</v-btn>
        <v-btn value="upload" prepend-icon="mdi-upload">{{ t('initializationUpload') }}</v-btn>
      </v-btn-toggle>

      <FileUploadDropzone
        ref="uploadDropzone"
        :files="selectedFiles"
        :accept="acceptedFileTypes"
        multiple
        :disabled="parsing"
        @files-selected="setFiles"
      />

      <v-alert
        v-if="parserJob"
        :type="parserJob.status === 'failed' ? 'error' : (parserJob.status === 'completed' ? 'success' : 'info')"
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
          :disabled="parsing"
          @click="selectFolder"
        >
          {{ t('selectFolder') }}
        </v-btn>

        <v-btn
          color="primary"
          prepend-icon="mdi-cog-play"
          :loading="parsing"
          :disabled="!selectedFiles?.length"
          @click="submitFiles"
        >
          {{ mode === 'parse' ? t('parseToExcel') : t('uploadAndPreview') }}
        </v-btn>

        <v-btn
          prepend-icon="mdi-refresh"
          :disabled="parsing"
          @click="resetFiles"
        >
          {{ t('clear') }}
        </v-btn>

        <v-btn
          prepend-icon="mdi-call-merge"
          color="secondary"
          variant="tonal"
          :loading="parsing"
          :disabled="results.length < 2 || pendingResults.length < 2"
          @click="mergeResults"
        >
          {{ t('mergeResults') }}
        </v-btn>

        <v-btn
          color="success"
          prepend-icon="mdi-file-sync-outline"
          :loading="confirming"
          :disabled="!result?.stagedPath || result?.confirmed || !canImportResult"
          @click="confirmImport('replace')"
        >
          {{ t('replaceImport') }}
        </v-btn>

        <v-btn
          color="primary"
          variant="tonal"
          prepend-icon="mdi-table-row-plus-after"
          :loading="confirming"
          :disabled="!result?.stagedPath || result?.confirmed || !canImportResult"
          @click="confirmImport('append')"
        >
          {{ t('appendImport') }}
        </v-btn>

        <v-btn
          prepend-icon="mdi-download"
          :disabled="!result?.downloadUrl"
          @click="downloadExcel"
        >
          {{ t('downloadPreviewFile') }}
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
          <v-chip v-if="result" :color="result.confirmed ? 'success' : 'warning'" variant="tonal">
            {{ result.confirmed ? t('confirmedImported') : t('waitingForConfirm') }}
          </v-chip>
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

        <div v-if="hasPreview" class="parser-preview-table-wrap">
          <table class="parser-preview-table">
            <thead>
              <tr>
                <th v-for="column in previewColumns" :key="column">{{ column }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in previewRows" :key="index">
                <td v-for="column in previewColumns" :key="column">{{ row[column] }}</td>
              </tr>
            </tbody>
          </table>
        </div>
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

.parser-sheet-select {
  width: min(280px, 100%);
  flex: 0 1 280px;
}

.parser-preview-alert {
  margin-top: 12px;
  margin-bottom: 12px;
}

.parser-preview-table-wrap {
  max-height: 360px;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
}

.parser-preview-table {
  width: 100%;
  min-width: 780px;
  border-collapse: collapse;
  font-size: 12px;
}

.parser-preview-table th,
.parser-preview-table td {
  max-width: 220px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--line);
  border-right: 1px solid var(--line);
  color: var(--text);
  text-align: left;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.parser-preview-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--panel-soft);
  color: var(--strong);
  font-weight: 800;
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
