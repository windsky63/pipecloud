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
  runningKey: { type: String, default: '' },
})

defineEmits(['execute-action', 'refresh-stats'])
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
        :disabled="Boolean(runningKey)"
        @click="$emit('execute-action', action.key)"
      >
        {{ localizedActionName(action) }}
      </v-btn>
      <v-btn :loading="initializationLoading" prepend-icon="mdi-refresh" @click="$emit('refresh-stats')">{{ t('refreshStats') }}</v-btn>
    </div>
  </v-card>
</template>

<style scoped>
.initialization-actions-card {
  margin-top: 16px;
}
</style>
