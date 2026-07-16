<script setup>
import { computed, ref } from 'vue'
import InfoTooltip from '../../components/InfoTooltip.vue'
import InitializationDashboardPanel from '../../components/InitializationDashboardPanel.vue'
import { localizedActionName, localizedModuleDescription } from '../../services/navigationLabels'
import { dashboardVisibility, setDashboardVisibility, t } from '../../services/pipecloudState'

const props = defineProps({
  activeModule: { type: Object, required: true },
  activeModuleTitle: { type: String, required: true },
  initializationLoading: { type: Boolean, default: false },
  initializationStats: { type: Object, required: true },
  initializationError: { type: String, default: '' },
  initializationOptions: { type: Object, required: true },
  runningKey: { type: String, default: '' },
})

defineEmits(['execute-action'])

const openPanels = ref(['initialization-options'])
const dashboardCollapsed = ref(false)
const initializationFilters = computed(() => {
  return props.activeModule.actions?.find((action) => action.key === 'prefab-weld-library')?.initializationFilters || []
})
</script>

<template>
  <v-card v-if="dashboardVisibility.initialization" class="module-panel" :loading="initializationLoading">
    <InitializationDashboardPanel
      :title="t('initializationDashboardTitle')"
      :description="t('initializationDashboardDescription')"
      :dashboard="initializationStats"
      :error="initializationError"
      :panel="false"
      collapsible
      :collapsed="dashboardCollapsed"
      @hide="setDashboardVisibility('initialization', false)"
      @toggle="dashboardCollapsed = !dashboardCollapsed"
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
      </div>
    </div>

    <v-expansion-panels v-model="openPanels" class="initialization-config" variant="accordion" multiple>
      <v-expansion-panel value="initialization-options">
        <v-expansion-panel-title>
          <strong>{{ t('initializationParams') }}</strong>
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <div class="initialization-options-grid">
            <label class="initialization-field initialization-switch-field">
              <span>{{ t('fillMaterialUnits') }}</span>
              <v-switch
                v-model="initializationOptions.fillMaterialUnits"
                color="primary"
                density="compact"
                hide-details
                inset
              />
              <small>{{ t('fillMaterialUnitsHint') }}</small>
            </label>
            <div class="initialization-filter-section">
              <div class="initialization-filter-head">
                <strong>{{ t('initializationFilterLogic') }}</strong>
                <small>{{ t('initializationFilterLogicHint') }}</small>
              </div>
              <div class="initialization-filter-grid">
                <label v-for="(filter, index) in initializationFilters" :key="filter.key || `${filter.stage}-${filter.field}-${index}`" class="initialization-filter-item">
                  <span>{{ filter.stage }}</span>
                  <strong>{{ filter.field }} {{ filter.operator }} {{ filter.value }}</strong>
                  <v-switch
                    v-model="initializationOptions.initializationFilters[filter.key]"
                    class="initialization-filter-switch"
                    color="primary"
                    density="compact"
                    hide-details
                    inset
                  />
                </label>
              </div>
            </div>
          </div>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>
  </v-card>
</template>

<style scoped>
.initialization-actions-card {
  margin-top: 16px;
}

.initialization-config {
  margin-top: 16px;
}

.initialization-config :deep(.v-expansion-panel) {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
}

.initialization-config :deep(.v-expansion-panel-title) {
  min-height: 42px;
  padding: 0 14px;
  color: var(--strong);
  font-size: 14px;
  font-weight: 800;
}

.initialization-options-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.initialization-field {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 6px 16px;
  align-items: center;
  padding: 10px 0;
}

.initialization-field > span,
.initialization-filter-section strong,
.initialization-filter-item strong {
  color: var(--strong);
  font-size: 14px;
}

.initialization-field small,
.initialization-filter-section small {
  color: var(--muted);
  font-size: 12px;
}

.initialization-field small {
  grid-column: 1 / -1;
}

.initialization-filter-section {
  grid-column: 1 / -1;
  display: grid;
  gap: 12px;
  padding-top: 4px;
  border-top: 1px solid var(--line);
}

.initialization-filter-head {
  display: grid;
  gap: 4px;
}

.initialization-filter-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.initialization-filter-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 4px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface-soft);
}

.initialization-filter-item > span,
.initialization-filter-item > strong {
  grid-column: 1;
}

.initialization-filter-switch {
  grid-column: 2;
  grid-row: 1 / span 2;
  align-self: center;
}

.initialization-filter-item span {
  color: var(--muted);
  font-size: 12px;
}

@media (max-width: 760px) {
  .initialization-options-grid,
  .initialization-filter-grid {
    grid-template-columns: 1fr;
  }
}
</style>
