<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import {
  downloadProjectFileExport,
  fetchProjectFileExportStatus,
  fetchProjectFileTree,
  startProjectFileExport,
} from '../../api/fileExports'
import PageHeader from '../../components/PageHeader.vue'
import { t } from '../../services/pipecloudState'
import { selectedProjectId, selectedProjectParams } from '../../services/projectState'
import { publishUiMessage, watchUiMessageSources } from '../../services/uiMessages'

const loading = ref(false)
const exporting = ref(false)
const errorMessage = ref('')
const tree = ref([])
const selected = ref([])
const opened = ref([])
const projectName = ref('')
const exportProgress = ref(0)
const exportProgressMessage = ref('')
watchUiMessageSources([
  ['file-export-error', 'error', errorMessage],
])
let exportRunToken = 0

function collectFileIds(nodes, result = []) {
  for (const node of nodes || []) {
    if (node.type === 'file') result.push(node.id)
    collectFileIds(node.children, result)
  }
  return result
}

const allFileIds = computed(() => collectFileIds(tree.value))
const fileIdSet = computed(() => new Set(allFileIds.value))
const selectedFileIds = computed(() => selected.value.filter((id) => fileIdSet.value.has(id)))
const allSelected = computed(() => (
  allFileIds.value.length > 0 && selectedFileIds.value.length === allFileIds.value.length
))

async function loadTree() {
  loading.value = true
  errorMessage.value = ''
  try {
    const payload = await fetchProjectFileTree(selectedProjectParams())
    tree.value = payload.tree || []
    projectName.value = payload.projectName || ''
    const nextFileIds = new Set(collectFileIds(tree.value))
    selected.value = selected.value.filter((id) => nextFileIds.has(id))
    // 大项目默认折叠目录，避免一次挂载数百个树节点拖慢勾选响应。
    opened.value = []
  } catch (error) {
    tree.value = []
    selected.value = []
    errorMessage.value = error.message
  } finally {
    loading.value = false
  }
}

function toggleAll() {
  selected.value = allSelected.value ? [] : [...allFileIds.value]
}

async function exportSelected() {
  if (!selectedFileIds.value.length) return
  const runToken = ++exportRunToken
  const exportParams = selectedProjectParams()
  const exportProjectName = projectName.value
  exporting.value = true
  exportProgress.value = 0
  exportProgressMessage.value = t('batchExportStarting')
  errorMessage.value = ''
  try {
    const task = await startProjectFileExport(exportParams, selectedFileIds.value)
    let status = task
    while (runToken === exportRunToken && !['completed', 'failed'].includes(status.status)) {
      await new Promise((resolve) => window.setTimeout(resolve, 400))
      status = await fetchProjectFileExportStatus(exportParams, task.jobId)
      exportProgress.value = Number(status.progress) || 0
      exportProgressMessage.value = status.message || t('batchExportInProgress')
    }
    if (runToken !== exportRunToken) return
    if (status.status === 'failed') {
      throw new Error(status.error || status.message || t('batchExportFailed'))
    }
    exportProgress.value = 100
    exportProgressMessage.value = status.message || t('batchExportCompleted')
    publishUiMessage('file-export-success', 'success', exportProgressMessage.value)
    const blob = await downloadProjectFileExport(exportParams, task.jobId)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${exportProjectName || t('projectFiles')}.zip`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    if (runToken === exportRunToken) {
      exporting.value = false
    }
  }
}

watch(selectedProjectId, loadTree)
onMounted(loadTree)
onBeforeUnmount(() => {
  exportRunToken += 1
})
</script>

<template>
  <main class="file-export-page">
    <PageHeader :title="t('batchFileExport')" :description="t('batchFileExportDescription')">
      <template #actions>
        <v-btn
          icon="mdi-refresh"
          variant="text"
          :loading="loading"
          :title="t('refresh')"
          @click="loadTree"
        />
      </template>
    </PageHeader>

    <v-alert
      v-if="errorMessage"
      type="error"
      variant="tonal"
      density="compact"
      closable
      class="file-export-alert"
      @click:close="errorMessage = ''"
    >
      {{ errorMessage }}
    </v-alert>

    <section class="file-export-toolbar">
      <div>
        <strong>{{ projectName || t('currentProject') }}</strong>
        <span>{{ t('selectedFilesCount', { selected: selectedFileIds.length, total: allFileIds.length }) }}</span>
      </div>
      <div class="file-export-actions">
        <v-btn
          :prepend-icon="allSelected ? 'mdi-checkbox-blank-outline' : 'mdi-checkbox-multiple-marked-outline'"
          variant="text"
          :disabled="!allFileIds.length"
          @click="toggleAll"
        >
          {{ allSelected ? t('clearSelection') : t('selectAll') }}
        </v-btn>
        <v-btn
          color="primary"
          prepend-icon="mdi-folder-zip-outline"
          :loading="exporting"
          :disabled="!selectedFileIds.length"
          @click="exportSelected"
        >
          {{ t('exportSelectedFiles') }}
        </v-btn>
      </div>
    </section>

    <section v-if="exporting" class="file-export-progress">
      <div>
        <strong>{{ exportProgressMessage }}</strong>
        <span>{{ exportProgress }}%</span>
      </div>
      <v-progress-linear
        :model-value="exportProgress"
        color="primary"
        height="8"
        rounded
      />
    </section>

    <section class="file-tree-panel">
      <div class="file-tree-heading">
        <h2>{{ t('projectFileTree') }}</h2>
        <v-progress-circular v-if="loading" indeterminate size="22" width="2" />
      </div>

      <v-treeview
        v-if="tree.length"
        v-model:selected="selected"
        v-model:opened="opened"
        :items="tree"
        item-title="name"
        item-value="id"
        item-children="children"
        items-registration="props"
        select-strategy="classic"
        selectable
        density="compact"
        class="project-file-tree"
      >
        <template #prepend="{ item }">
          <v-icon
            :icon="(item.raw?.type || item.type) === 'file' ? 'mdi-file-excel-outline' : 'mdi-folder-outline'"
            :color="(item.raw?.type || item.type) === 'file' ? 'success' : 'primary'"
            size="20"
          />
        </template>
        <template #append="{ item }">
          <span
            v-if="(item.raw?.type || item.type) === 'file' && (item.raw?.sheets || item.sheets)?.length"
            class="file-sheet-count"
          >
            {{ t('sheetCount', { value: (item.raw?.sheets || item.sheets).length }) }}
          </span>
        </template>
      </v-treeview>

      <div v-else-if="!loading" class="file-tree-empty">
        <v-icon icon="mdi-folder-open-outline" size="42" />
        <span>{{ t('noProjectFiles') }}</span>
      </div>
    </section>
  </main>
</template>

<style scoped>
.file-export-page {
  width: 100%;
}

.file-export-alert {
  margin-bottom: 14px;
}

.file-export-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  min-height: 58px;
  padding: 10px 0 14px;
  border-bottom: 1px solid var(--line);
}

.file-export-toolbar > div:first-child {
  display: grid;
  gap: 3px;
}

.file-export-toolbar strong {
  font-size: 15px;
}

.file-export-toolbar span,
.file-sheet-count {
  color: var(--muted);
  font-size: 12px;
}

.file-export-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.file-tree-panel {
  padding-top: 18px;
}

.file-export-progress {
  display: grid;
  gap: 8px;
  padding: 14px 0 4px;
}

.file-export-progress > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  font-size: 13px;
}

.file-tree-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 36px;
  margin-bottom: 8px;
}

.file-tree-heading h2 {
  margin: 0;
  font-size: 16px;
}

.project-file-tree {
  min-height: 360px;
  padding: 6px 0;
  background: transparent;
}

.project-file-tree :deep(.v-list-item) {
  min-height: 38px;
  border-radius: 6px;
}

.project-file-tree :deep(.v-list-item:hover) {
  background: var(--soft);
}

.file-tree-empty {
  display: grid;
  place-items: center;
  align-content: center;
  gap: 10px;
  min-height: 360px;
  color: var(--muted);
}

@media (max-width: 760px) {
  .file-export-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .file-export-actions {
    justify-content: space-between;
  }
}
</style>
