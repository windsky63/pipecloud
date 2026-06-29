<script setup>
import { ref } from 'vue'
import InfoTooltip from '../../components/InfoTooltip.vue'
import WeldingDashboardPanel from '../../components/WeldingDashboardPanel.vue'
import { localizedActionName, localizedModuleDescription } from '../../services/navigationLabels'
import { t } from '../../services/pipecloudState'

defineProps({
  activeModule: { type: Object, required: true },
  activeModuleTitle: { type: String, required: true },
  weldingDashboardLoading: { type: Boolean, default: false },
  weldingDashboard: { type: Object, required: true },
  weldingDashboardError: { type: String, default: '' },
  weldingScheduleMessage: { type: String, default: '' },
  weldingScheduleError: { type: String, default: '' },
  weldingPendingStage: { type: Object, default: null },
  weldingStageSaving: { type: Boolean, default: false },
  weldingScheduleConfig: { type: Object, required: true },
  weldingScheduleDefaults: { type: Object, default: () => ({}) },
  runningKey: { type: String, default: '' },
})

defineEmits(['execute-action', 'refresh-dashboard', 'update-welding-date', 'save-pending-stage'])

const configPanels = ref(['config'])
</script>

<template>
  <v-card class="module-panel" :loading="weldingDashboardLoading">
    <WeldingDashboardPanel
      :title="t('weldingDashboardTitle')"
      :description="t('weldingDashboardDescription')"
      :dashboard="weldingDashboard"
      :error="weldingDashboardError"
      :panel="false"
    />
  </v-card>

  <v-card class="module-panel welding-actions-card">
    <div class="section-head">
      <div>
        <div class="section-title-with-tip">
          <h2>{{ activeModuleTitle }}</h2>
          <InfoTooltip :text="localizedModuleDescription(activeModule)" />
        </div>
      </div>
    </div>

    <div class="module-actions welding-dashboard-module-actions">
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
    </div>

    <v-alert v-if="weldingScheduleError" :text="weldingScheduleError" type="error" density="compact" class="status-alert" />
    <v-alert v-if="weldingScheduleMessage" :text="weldingScheduleMessage" type="success" density="compact" class="status-alert" />
    <div v-if="weldingPendingStage" class="pending-stage-actions">
      <div class="pending-stage-head">
        <span>{{ t('pendingStagedFiles', { count: weldingPendingStage.files?.length || 0 }) }}</span>
        <v-btn
          color="primary"
          prepend-icon="mdi-content-save-outline"
          :loading="weldingStageSaving"
          :disabled="weldingStageSaving"
          @click="$emit('save-pending-stage')"
        >
          {{ t('saveToPlanFile') }}
        </v-btn>
      </div>
      <div class="pending-stage-files">
        <div v-for="file in weldingPendingStage.files" :key="file.path" class="pending-stage-file">
          <strong>{{ file.name }}</strong>
          <span>{{ file.planType }} / {{ file.planDate || '-' }}</span>
          <small>{{ file.sizeText }} · {{ file.updatedText }}</small>
          <small>{{ file.path }}</small>
        </div>
      </div>
    </div>

    <v-expansion-panels v-model="configPanels" class="welding-schedule-config" variant="accordion">
      <v-expansion-panel value="config">
        <v-expansion-panel-title>
          {{ t('generatedConfig') }}
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <div class="welding-schedule-config-grid">
            <label class="welding-schedule-field">
              <span>{{ t('planDate') }}</span>
              <v-text-field
                :model-value="weldingScheduleConfig.weldDate"
                type="date"
                density="compact"
                hide-details
                :placeholder="weldingScheduleDefaults.weldDate || ''"
                @update:model-value="$emit('update-welding-date', $event)"
              />
              <small>{{ t('defaultValue', { value: weldingScheduleDefaults.weldDate || t('today') }) }}</small>
            </label>
            <label class="welding-schedule-field">
              <span>{{ t('targetDiameterPerOrder') }}</span>
              <v-text-field
                v-model="weldingScheduleConfig.targetDiameter"
                type="number"
                min="1"
                step="0.1"
                density="compact"
                hide-details
                :placeholder="String(weldingScheduleDefaults.targetDiameter || '')"
              />
              <small>{{ t('defaultValue', { value: weldingScheduleDefaults.targetDiameter || '-' }) }}</small>
            </label>
            <label class="welding-schedule-field">
              <span>{{ t('ordersPerDay') }}</span>
              <v-text-field
                v-model="weldingScheduleConfig.ordersPerDay"
                type="number"
                min="1"
                density="compact"
                hide-details
                :placeholder="String(weldingScheduleDefaults.ordersPerDay || '')"
              />
              <small>{{ t('defaultValue', { value: weldingScheduleDefaults.ordersPerDay || '-' }) }}</small>
            </label>
          </div>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>

  </v-card>
</template>

<style scoped>
.welding-schedule-config {
  margin: 4px 0 16px;
}

.welding-actions-card {
  margin-top: 16px;
}

.pending-stage-actions {
  display: grid;
  gap: 10px;
  margin-bottom: 14px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel-soft);
  color: var(--muted);
  font-size: 13px;
}

.pending-stage-head {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
}

.pending-stage-files {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 8px;
}

.pending-stage-file {
  display: grid;
  gap: 3px;
  min-width: 0;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
}

.pending-stage-file strong,
.pending-stage-file span,
.pending-stage-file small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pending-stage-file strong {
  color: var(--strong);
}

.pending-stage-file small {
  color: var(--muted);
}

.welding-schedule-config :deep(.v-expansion-panel) {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
}

.welding-schedule-config :deep(.v-expansion-panel-title) {
  min-height: 42px;
  padding: 0 14px;
  color: var(--strong);
  font-size: 14px;
  font-weight: 800;
}

.welding-schedule-config-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(160px, 1fr));
  gap: 12px;
}

.welding-schedule-field {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.welding-schedule-field > span {
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}

.welding-schedule-field > small {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.35;
}

@media (max-width: 1100px) {
  .welding-schedule-config-grid {
    grid-template-columns: 1fr;
  }
}
</style>
