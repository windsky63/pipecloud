<script setup>
import { computed, onMounted, ref } from 'vue'
import DataVTable from '../../components/DataVTable.vue'
import PageHeader from '../../components/PageHeader.vue'
import { clearDatabase, fetchDatabaseOverview, runPlanRollover } from '../../api/developer'
import { t } from '../../services/pipecloudState'

const running = ref(false)
const databaseLoading = ref(false)
const databaseClearing = ref(false)
const message = ref('')
const errorMessage = ref('')
const results = ref([])
const databaseOverview = ref({
  totalTables: 0,
  totalRows: 0,
  tables: [],
})
const selectedDatabaseTables = ref([])
const clearDatabaseDialog = ref(false)

const columns = computed(() => [
  { field: 'projectName', title: t('project'), width: 220 },
  { field: 'statusText', title: t('executionStatus'), width: 120 },
  { field: 'summaryText', title: t('rolloverSummary'), width: 520 },
])

const databaseColumns = computed(() => [
  { field: 'verboseName', title: t('databaseTableName'), width: 220 },
  { field: 'model', title: t('databaseModelName'), width: 220 },
  { field: 'tableName', title: t('databasePhysicalTable'), width: 280 },
  { field: 'count', title: t('databaseRowCount'), width: 140 },
])
const selectedDatabaseRowCount = computed(() => {
  return selectedDatabaseTables.value.reduce((total, row) => total + Number(row.count || 0), 0)
})

const rows = computed(() => results.value.map((result) => {
  let statusText = t('succeeded')
  let summaryText = t('rolloverResultSummary', {
    today: result.todayWeldCount || 0,
    completed: result.completedWeldCount || 0,
    rolled: result.rolledWeldCount || 0,
    dates: result.affectedPlanDates?.length || 0,
  })
  if (result.error) {
    statusText = t('failed')
    summaryText = result.error
  } else if (result.skipped) {
    statusText = t('skipped')
    summaryText = result.reason || t('skipped')
  } else if (result.alreadyExecuted) {
    statusText = t('alreadyExecuted')
  }
  return { ...result, statusText, summaryText }
}))

async function executeRollover() {
  running.value = true
  message.value = ''
  errorMessage.value = ''
  try {
    const payload = await runPlanRollover()
    results.value = payload.results || []
    message.value = t('planRolloverSucceeded', payload.summary || {
      succeeded: 0,
      skipped: 0,
      failed: 0,
    })
  } catch (error) {
    errorMessage.value = t('planRolloverFailed', { message: error.message })
  } finally {
    running.value = false
  }
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

onMounted(loadDatabaseOverview)
</script>

<template>
  <PageHeader :title="t('developerControls')" :description="t('developerControlsDescription')" />

  <v-alert v-if="message" :text="message" type="success" density="compact" class="status-alert" />
  <v-alert v-if="errorMessage" :text="errorMessage" type="error" density="compact" class="status-alert" />

  <v-card class="module-panel developer-control-card" :loading="running">
    <div class="section-head">
      <div>
        <h2>{{ t('planRollover') }}</h2>
        <p>{{ t('planRolloverDescription') }}</p>
      </div>
      <v-btn
        color="primary"
        prepend-icon="mdi-calendar-sync"
        :loading="running"
        @click="executeRollover"
      >
        {{ running ? t('runningPlanRollover') : t('runPlanRollover') }}
      </v-btn>
    </div>
    <DataVTable
      v-if="rows.length"
      :records="rows"
      :columns="columns"
      :height="Math.max(160, Math.min(420, rows.length * 46 + 46))"
    />
  </v-card>

  <v-card class="module-panel developer-control-card" :loading="databaseLoading || databaseClearing">
    <div class="section-head">
      <div>
        <h2>{{ t('databaseControls') }}</h2>
        <p>{{ t('databaseControlsDescription') }}</p>
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
</template>

<style scoped>
.developer-control-card .section-head {
  align-items: flex-start;
}

.developer-control-card p {
  max-width: 760px;
  margin: 8px 0 0;
  color: var(--muted);
  line-height: 1.6;
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

.developer-confirm-dialog {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
}
</style>
