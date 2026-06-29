<script setup>
import InfoTooltip from '../../components/InfoTooltip.vue'
import InitializationDashboardPanel from '../../components/InitializationDashboardPanel.vue'
import { localizedActionName, localizedModuleDescription } from '../../services/navigationLabels'
import { t } from '../../services/pipecloudState'

defineProps({
  activeModule: { type: Object, required: true },
  activeModuleTitle: { type: String, required: true },
  initializationLoading: { type: Boolean, default: false },
  initializationStats: { type: Object, required: true },
  initializationError: { type: String, default: '' },
  initializationSyncLoading: { type: Boolean, default: false },
  initializationSyncMessage: { type: String, default: '' },
  initializationSyncError: { type: String, default: '' },
  projectMetricsLoading: { type: Boolean, default: false },
  projectMetricsMessage: { type: String, default: '' },
  projectMetricsError: { type: String, default: '' },
  runningKey: { type: String, default: '' },
})

defineEmits(['execute-action', 'refresh-stats', 'sync-initialization', 'update-project-metrics'])
</script>

<template>
  <v-card class="module-panel" :loading="initializationLoading">
    <InitializationDashboardPanel
      :title="t('initializationDashboardTitle')"
      :description="t('initializationDashboardDescription')"
      :dashboard="initializationStats"
      :error="initializationError"
      :panel="false"
    />
  </v-card>

  <v-card class="module-panel initialization-actions-card">
    <div class="section-head">
      <div>
        <div class="section-title-with-tip">
          <h2>{{ activeModuleTitle }}</h2>
          <InfoTooltip :text="localizedModuleDescription(activeModule)" />
        </div>
      </div>
    </div>

    <div class="module-actions">
      <v-btn
        v-for="action in activeModule.actions"
        :key="action.key"
        color="primary"
        variant="tonal"
        :loading="runningKey === action.key"
        @click="$emit('execute-action', action.key)"
      >
        {{ localizedActionName(action) }}
      </v-btn>
      <v-btn
        color="secondary"
        variant="tonal"
        prepend-icon="mdi-database-sync-outline"
        :loading="initializationSyncLoading"
        @click="$emit('sync-initialization')"
      >
        {{ t('syncInitializationToMysql') }}
      </v-btn>
      <v-btn
        color="secondary"
        variant="tonal"
        prepend-icon="mdi-table-sync"
        :loading="projectMetricsLoading"
        @click="$emit('update-project-metrics')"
      >
        {{ t('updateProjectMetrics') }}
      </v-btn>
      <v-btn :loading="initializationLoading" prepend-icon="mdi-refresh" @click="$emit('refresh-stats')">{{ t('refreshStats') }}</v-btn>
    </div>
    <v-alert
      v-if="initializationSyncMessage"
      class="initialization-sync-alert"
      :text="initializationSyncMessage"
      type="success"
      density="compact"
    />
    <v-alert
      v-if="initializationSyncError"
      class="initialization-sync-alert"
      :text="initializationSyncError"
      type="error"
      density="compact"
    />
    <v-alert
      v-if="projectMetricsMessage"
      class="initialization-sync-alert"
      :text="projectMetricsMessage"
      type="success"
      density="compact"
    />
    <v-alert
      v-if="projectMetricsError"
      class="initialization-sync-alert"
      :text="projectMetricsError"
      type="error"
      density="compact"
    />
  </v-card>
</template>

<style scoped>
.initialization-actions-card {
  margin-top: 16px;
}

.initialization-sync-alert {
  margin-top: 12px;
}
</style>
