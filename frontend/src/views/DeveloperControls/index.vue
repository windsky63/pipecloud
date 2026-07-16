<script setup>
import { computed, onMounted, ref } from 'vue'
import DataVTable from '../../components/DataVTable.vue'
import InfoTooltip from '../../components/InfoTooltip.vue'
import PageHeader from '../../components/PageHeader.vue'
import {
  clearDatabase,
  fetchDatabaseOverview,
  fetchOperationLogs,
  fetchScheduledTasks,
  runScheduledTask,
} from '../../api/developer'
import { loadSummary, runAction, runningKey, summary, t } from '../../services/pipecloudState'
import { localizedActionName } from '../../services/navigationLabels'

const materialLibraryRunning = ref(false)
const activeControlTab = ref('database')
const databaseLoading = ref(false)
const databaseClearing = ref(false)
const scheduledTasksLoading = ref(false)
const operationLogsLoading = ref(false)
const operationLogs = ref([])
const scheduledTaskRunningKey = ref('')
const message = ref('')
const errorMessage = ref('')
const scheduledTaskLogs = ref([])
const databaseOverview = ref({
  totalTables: 0,
  totalRows: 0,
  tables: [],
})
const scheduledTasks = ref({
  jobs: [],
  misfireGraceSeconds: 0,
})
const selectedDatabaseTables = ref([])
const clearDatabaseDialog = ref(false)
const materialLibraryConfirmDialog = ref(false)
const materialLibraryFiles = computed(() => {
  const module = summary.value.modules.find((item) => item.key === 'arrival')
  return (module?.files || [])
    .filter((file) => file.exists && ['库管理/管子材料库.xlsx', '库管理/管件法兰材料库.xlsx'].includes(file.label))
    .map((file) => file.label)
})
const materialLibraryAction = computed(() => {
  return summary.value.actions.find((item) => item.key === 'arrival-library') || {
    key: 'arrival-library',
    name: t('actionArrivalLibrary'),
  }
})

const databaseColumns = computed(() => [
  { field: 'verboseName', title: t('databaseTableName'), width: 220 },
  { field: 'model', title: t('databaseModelName'), width: 220 },
  { field: 'tableName', title: t('databasePhysicalTable'), width: 280 },
  { field: 'count', title: t('databaseRowCount'), width: 140 },
])
const operationLogColumns = computed(() => [
  { field: 'createdAtText', title: t('operationTime'), width: 190 },
  { field: 'userName', title: t('operationUser'), width: 140 },
  { field: 'projectName', title: t('project'), width: 180 },
  { field: 'action', title: t('operationAction'), width: 250 },
  { field: 'method', title: t('requestMethod'), width: 100 },
  { field: 'statusText', title: t('executionStatus'), width: 120 },
  { field: 'path', title: t('requestPath'), width: 360 },
  { field: 'detailText', title: t('operationDetail'), width: 420 },
  { field: 'ipAddress', title: t('ipAddress'), width: 150 },
])
const operationLogRows = computed(() => operationLogs.value.map((row) => ({
  ...row,
  createdAtText: row.createdAt ? new Date(row.createdAt).toLocaleString('zh-CN', { hour12: false }) : '',
  statusText: row.succeeded ? t('succeeded') : t('failed'),
  detailText: Object.keys(row.detail || {}).length ? JSON.stringify(row.detail) : '-',
})))
const selectedDatabaseRowCount = computed(() => {
  return selectedDatabaseTables.value.reduce((total, row) => total + Number(row.count || 0), 0)
})
const scheduledTasksTooltip = computed(() => [
  t('scheduledTasksDescription'),
  t('scheduledTaskConfigTip', { seconds: scheduledTasks.value.misfireGraceSeconds || 0 }),
].join('；'))

function scheduledTaskTooltip(job) {
  return [
    t('scheduledTaskTime', {
      time: `${String(job.hour).padStart(2, '0')}:${String(job.minute).padStart(2, '0')}`,
      timezone: job.timezone,
    }),
    `${t(job.enabled ? 'enabled' : 'disabled')} · ${job.command}`,
  ].join('；')
}

const scheduledTaskRows = computed(() => scheduledTaskLogs.value.map((log) => {
  const result = { ...(log.stats || {}), ...log }
  let statusText = t(log.status || 'succeeded')
  let summaryText = t('scheduledTaskResultSummary', {
    sources: result.sourceCount || 0,
    matched: result.matchedCount || 0,
    completed: result.completedCount || 0,
    changed: result.updatedCount ?? result.changedStatusRows ?? ((result.changedMasterRows || 0) + (result.changedLibraryRows || 0)),
  })
  if (result.affectedPlanDates || result.rolledWeldCount !== undefined || result.rolledCuttingCount !== undefined) {
    summaryText = t('rolloverResultSummary', {
      today: result.todayCuttingCount ?? result.todayWeldCount ?? 0,
      completed: result.completedCuttingCount ?? result.completedWeldCount ?? 0,
      rolled: result.rolledCuttingCount ?? result.rolledWeldCount ?? 0,
      dates: result.affectedPlanDates?.length || 0,
    })
  }
  if (log.error) {
    statusText = t('failed')
    summaryText = log.error
  } else if (log.status === 'skipped' || result.skipped) {
    statusText = t('skipped')
    summaryText = result.reason || t('skipped')
  } else if (result.alreadyExecuted) {
    statusText = t('alreadyExecuted')
  }
  return { ...result, statusText, summaryText }
}))

async function loadScheduledTasks() {
  scheduledTasksLoading.value = true
  errorMessage.value = ''
  try {
    scheduledTasks.value = await fetchScheduledTasks()
    scheduledTaskLogs.value = scheduledTasks.value.logs || []
  } catch (error) {
    errorMessage.value = t('scheduledTasksLoadFailed', { message: error.message })
  } finally {
    scheduledTasksLoading.value = false
  }
}

async function executeScheduledTask(job) {
  scheduledTaskRunningKey.value = job.key
  message.value = ''
  errorMessage.value = ''
  try {
    const payload = await runScheduledTask(job.key)
    await loadScheduledTasks()
    message.value = t('scheduledTaskRunSucceeded', {
      task: job.name,
      succeeded: payload.summary?.succeeded || 0,
      skipped: payload.summary?.skipped || 0,
      failed: payload.summary?.failed || 0,
    })
  } catch (error) {
    errorMessage.value = t('scheduledTaskRunFailed', { task: job.name, message: error.message })
  } finally {
    scheduledTaskRunningKey.value = ''
  }
}

async function executeMaterialLibrary() {
  materialLibraryRunning.value = true
  message.value = ''
  errorMessage.value = ''
  try {
    const started = await runAction('arrival-library')
    if (started) {
      message.value = t('actionRunSucceeded', { action: localizedActionName(materialLibraryAction.value) })
      await loadDatabaseOverview()
    }
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    materialLibraryRunning.value = false
    materialLibraryConfirmDialog.value = false
  }
}

function requestMaterialLibrary() {
  if (materialLibraryFiles.value.length) {
    materialLibraryConfirmDialog.value = true
    return
  }
  executeMaterialLibrary()
}

async function loadDatabaseOverview() {
  databaseLoading.value = true
  errorMessage.value = ''
  try {
    databaseOverview.value = await fetchDatabaseOverview()
    selectedDatabaseTables.value = selectedDatabaseTables.value.filter((row) => {
      return (databaseOverview.value.tables || []).some((table) => table.tableName === row.tableName)
    })
  } catch (error) {
    errorMessage.value = t('databaseOverviewFailed', { message: error.message })
  } finally {
    databaseLoading.value = false
  }
}

async function loadOperationLogs() {
  operationLogsLoading.value = true
  errorMessage.value = ''
  try {
    const payload = await fetchOperationLogs()
    operationLogs.value = payload.logs || []
  } catch (error) {
    errorMessage.value = t('operationLogsLoadFailed', { message: error.message })
  } finally {
    operationLogsLoading.value = false
  }
}

async function executeClearDatabase() {
  databaseClearing.value = true
  message.value = ''
  errorMessage.value = ''
  try {
    const payload = await clearDatabase(selectedDatabaseTables.value.map((row) => row.tableName))
    message.value = t('databaseClearSucceeded', { count: payload.deletedRows || 0 })
    clearDatabaseDialog.value = false
    selectedDatabaseTables.value = []
    await loadDatabaseOverview()
  } catch (error) {
    errorMessage.value = t('databaseClearFailed', { message: error.message })
  } finally {
    databaseClearing.value = false
  }
}

onMounted(() => {
  loadSummary()
  loadScheduledTasks()
  loadDatabaseOverview()
  loadOperationLogs()
})
</script>

<template>
  <PageHeader :title="t('developerControls')" :description="t('developerControlsDescription')" />

  <v-alert v-if="message" :text="message" type="success" density="compact" class="status-alert" />
  <v-alert v-if="errorMessage" :text="errorMessage" type="error" density="compact" class="status-alert" />

  <v-tabs v-model="activeControlTab" class="developer-control-tabs" color="primary">
    <v-tab value="database" prepend-icon="mdi-database-outline">{{ t('databaseOperations') }}</v-tab>
    <v-tab value="scheduled" prepend-icon="mdi-clock-outline">{{ t('scheduledTasks') }}</v-tab>
    <v-tab value="logs" prepend-icon="mdi-text-box-search-outline">{{ t('operationLogs') }}</v-tab>
    <v-tab value="other" prepend-icon="mdi-tools">{{ t('otherOperations') }}</v-tab>
  </v-tabs>

  <v-window v-model="activeControlTab" class="developer-control-window">
    <v-window-item value="database">
      <v-card class="module-panel developer-control-card" :loading="databaseLoading || databaseClearing">
        <div class="section-head">
          <div class="section-title-with-tip">
            <h2>{{ t('databaseControls') }}</h2>
            <InfoTooltip :text="t('databaseControlsDescription')" />
          </div>
          <div class="module-actions">
            <v-btn
              variant="tonal"
              prepend-icon="mdi-refresh"
              :loading="databaseLoading"
              :disabled="databaseClearing"
              @click="loadDatabaseOverview"
            >
              {{ t('refreshDatabaseOverview') }}
            </v-btn>
            <v-btn
              color="error"
              variant="tonal"
              prepend-icon="mdi-database-remove-outline"
              :loading="databaseClearing"
              :disabled="databaseLoading || selectedDatabaseTables.length <= 0"
              @click="clearDatabaseDialog = true"
            >
              {{ t('clearDatabase') }}
            </v-btn>
          </div>
        </div>

        <div class="database-summary">
          <span>{{ t('databaseTableCount', { count: databaseOverview.totalTables || 0 }) }}</span>
          <strong>{{ t('databaseTotalRows', { count: databaseOverview.totalRows || 0 }) }}</strong>
          <span>{{ t('selectedDatabaseTables', { count: selectedDatabaseTables.length, rows: selectedDatabaseRowCount }) }}</span>
        </div>

        <DataVTable
          :records="databaseOverview.tables || []"
          :columns="databaseColumns"
          :height="Math.max(220, Math.min(560, (databaseOverview.tables?.length || 0) * 40 + 46))"
          :empty-text="t('noDatabaseTables')"
          filterable
          selectable
          row-key="tableName"
          @selection-change="selectedDatabaseTables = $event.rows || []"
        />
      </v-card>
    </v-window-item>

    <v-window-item value="scheduled">
      <v-card class="module-panel developer-control-card" :loading="scheduledTasksLoading">
        <div class="section-head">
          <div class="section-title-with-tip">
            <h2>{{ t('scheduledTasks') }}</h2>
            <InfoTooltip :text="scheduledTasksTooltip" />
          </div>
          <v-btn
            variant="tonal"
            prepend-icon="mdi-refresh"
            :loading="scheduledTasksLoading"
            :disabled="Boolean(scheduledTaskRunningKey)"
            @click="loadScheduledTasks"
          >
            {{ t('refreshScheduledTasks') }}
          </v-btn>
        </div>

        <div class="scheduled-task-grid">
          <div v-for="job in scheduledTasks.jobs" :key="job.key" class="scheduled-task-item">
            <div class="section-title-with-tip">
              <h3>{{ job.name }}</h3>
              <InfoTooltip :text="scheduledTaskTooltip(job)" />
            </div>
            <v-btn
              color="primary"
              variant="tonal"
              prepend-icon="mdi-play-circle-outline"
              :loading="scheduledTaskRunningKey === job.key"
              :disabled="Boolean(scheduledTaskRunningKey) || !job.enabled"
              @click="executeScheduledTask(job)"
            >
              {{ t('runNow') }}
            </v-btn>
          </div>
        </div>

        <DataVTable
          :records="scheduledTaskRows"
          :columns="[
            { field: 'businessDate', title: t('businessDate'), width: 130 },
            { field: 'taskDisplayName', title: t('scheduledTaskName'), width: 260 },
            { field: 'projectName', title: t('project'), width: 220 },
            { field: 'planName', title: t('planType'), width: 120 },
            { field: 'statusText', title: t('executionStatus'), width: 120 },
            { field: 'summaryText', title: t('syncSummary'), width: 520 },
          ]"
          :height="Math.max(160, Math.min(420, scheduledTaskRows.length * 46 + 46))"
          :empty-text="t('noScheduledTaskLogs')"
          filterable
        />
      </v-card>
    </v-window-item>

    <v-window-item value="logs">
      <v-card class="module-panel developer-control-card" :loading="operationLogsLoading">
        <div class="section-head">
          <div class="section-title-with-tip">
            <h2>{{ t('operationLogs') }}</h2>
            <InfoTooltip :text="t('operationLogsDescription')" />
          </div>
          <v-btn variant="tonal" prepend-icon="mdi-refresh" :loading="operationLogsLoading" @click="loadOperationLogs">
            {{ t('refreshOperationLogs') }}
          </v-btn>
        </div>
        <DataVTable
          :records="operationLogRows"
          :columns="operationLogColumns"
          :height="Math.max(260, Math.min(650, operationLogRows.length * 42 + 46))"
          :empty-text="t('noOperationLogs')"
          filterable
          row-key="id"
        />
      </v-card>
    </v-window-item>

    <v-window-item value="other">
      <v-card class="module-panel developer-control-card" :loading="materialLibraryRunning">
        <div class="section-head">
          <div class="section-title-with-tip">
            <h2>{{ t('actionArrivalLibrary') }}</h2>
            <InfoTooltip :text="t('arrivalFileStatusTip')" />
          </div>
          <v-btn
            color="primary"
            prepend-icon="mdi-database-sync-outline"
            :loading="materialLibraryRunning || runningKey === 'arrival-library'"
            :disabled="Boolean(runningKey) && runningKey !== 'arrival-library'"
            @click="requestMaterialLibrary"
          >
            {{ localizedActionName(materialLibraryAction) }}
          </v-btn>
        </div>
      </v-card>
    </v-window-item>
  </v-window>

  <v-dialog v-model="clearDatabaseDialog" max-width="520" persistent>
    <v-card class="developer-confirm-dialog" variant="flat">
      <v-card-title>{{ t('clearDatabase') }}</v-card-title>
      <v-card-text>
        {{ t('clearDatabaseConfirmText', {
          count: selectedDatabaseRowCount,
          tables: selectedDatabaseTables.length,
        }) }}
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="clearDatabaseDialog = false">
          {{ t('cancel') }}
        </v-btn>
        <v-btn color="error" :loading="databaseClearing" @click="executeClearDatabase">
          {{ t('clearDatabase') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <v-dialog v-model="materialLibraryConfirmDialog" max-width="520" persistent>
    <v-card class="developer-confirm-dialog" variant="flat">
      <v-card-title>{{ t('actionArrivalLibrary') }}</v-card-title>
      <v-card-text>
        {{ t('materialLibraryExistsText', { files: materialLibraryFiles.join('、') }) }}
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn :disabled="materialLibraryRunning" @click="materialLibraryConfirmDialog = false">{{ t('cancel') }}</v-btn>
        <v-btn color="primary" :loading="materialLibraryRunning" @click="executeMaterialLibrary">{{ t('confirm') }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.developer-control-card .section-head {
  align-items: flex-start;
}

.developer-control-tabs {
  margin-bottom: 12px;
  border-bottom: 1px solid var(--line);
}

.developer-control-window {
  overflow: visible;
}

.database-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
  color: var(--muted);
  font-size: 13px;
}

.database-summary strong {
  color: var(--strong);
}

.scheduled-task-grid {
  display: grid;
  gap: 12px;
  margin-bottom: 12px;
}

.scheduled-task-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
}

.scheduled-task-item h3 {
  margin: 0;
  color: var(--strong);
  font-size: 15px;
}

.developer-confirm-dialog {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
}
</style>
