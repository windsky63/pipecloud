<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import DataVTable from '../../components/DataVTable.vue'
import InfoTooltip from '../../components/InfoTooltip.vue'
import { localizedActionName, localizedModuleDescription } from '../../services/navigationLabels'
import { t } from '../../services/pipecloudState'

defineProps({
  activeModule: { type: Object, required: true },
  activeModuleTitle: { type: String, required: true },
  preScheduleLoading: { type: Boolean, default: false },
  cuttingLoading: { type: Boolean, default: false },
  preScheduleData: { type: Object, required: true },
  preScheduleOptions: { type: Object, required: true },
  preScheduleActiveSheet: { type: String, default: '' },
  preScheduleError: { type: String, default: '' },
  preScheduleTableColumns: { type: Array, default: () => [] },
  cuttingData: { type: Object, required: true },
  cuttingError: { type: String, default: '' },
  cuttingTooltip: { type: Object, required: true },
  cuttingPreScheduleAction: { type: Object, default: null },
  cuttingConfirmAction: { type: Object, default: null },
  cuttingOverviewActions: { type: Array, default: () => [] },
  runningKey: { type: String, default: '' },
  formatLength: { type: Function, required: true },
})

const emit = defineEmits([
  'execute-action',
  'refresh-match-result',
  'refresh-visualization',
  'change-pre-schedule-sheet',
  'table-container-ready',
])

const tableContainer = ref(null)
const preScheduleConfigPanels = ref([])

function emitTableContainer() {
  emit('table-container-ready', tableContainer.value)
}

onMounted(async () => {
  await nextTick()
  emitTableContainer()
})

onBeforeUnmount(() => {
  emit('table-container-ready', null)
})
</script>

<template>
    <v-card class="module-panel cutting-pre-schedule-card" :loading="preScheduleLoading || cuttingLoading">
      <div class="section-head">
        <div>
          <h2>{{ t('cuttingPreSchedule') }}</h2>
          <span>{{ preScheduleData.path || t('preScheduleResultDefaultPath') }}</span>
        </div>
        <div class="module-actions pre-schedule-actions">
          <v-btn
            v-if="cuttingPreScheduleAction"
            color="primary"
            variant="tonal"
            :loading="runningKey === cuttingPreScheduleAction.key"
            @click="$emit('execute-action', cuttingPreScheduleAction.key)"
          >
            {{ localizedActionName(cuttingPreScheduleAction) }}
          </v-btn>
          <v-btn :loading="preScheduleLoading" prepend-icon="mdi-refresh" @click="$emit('refresh-match-result')">{{ t('refreshMatchResult') }}</v-btn>
          <v-btn :loading="cuttingLoading" prepend-icon="mdi-refresh" @click="$emit('refresh-visualization')">{{ t('refreshVisualization') }}</v-btn>
          <v-btn
            v-if="cuttingConfirmAction"
            color="primary"
            variant="tonal"
            :loading="runningKey === cuttingConfirmAction.key"
            @click="$emit('execute-action', cuttingConfirmAction.key)"
          >
            {{ localizedActionName(cuttingConfirmAction) }}
          </v-btn>
        </div>
      </div>

      <v-expansion-panels v-model="preScheduleConfigPanels" class="pre-schedule-config future-schedule-config" variant="accordion">
        <v-expansion-panel value="options">
          <v-expansion-panel-title>
            <div>
              <strong>{{ t('cuttingPreScheduleParams') }}</strong>
            </div>
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <div class="pre-schedule-config-grid">
              <label class="future-schedule-field pre-schedule-switch-field">
                <span>{{ t('onlyAutoWeld') }}</span>
                <v-switch
                  v-model="preScheduleOptions.onlyAutoWeld"
                  color="primary"
                  density="compact"
                  hide-details
                  inset
                  :disabled="runningKey === cuttingPreScheduleAction?.key"
                />
                <small>{{ preScheduleOptions.onlyAutoWeld ? t('onlyAutoWeldHint') : t('allUnfinishedHint') }}</small>
              </label>
            </div>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>

      <v-alert v-if="preScheduleError" :text="preScheduleError" type="error" density="compact" class="status-alert" />

      <v-sheet class="pre-schedule-result-section" color="transparent">
        <div class="section-head compact-section-head">
          <div>
            <div class="section-title-with-tip">
              <h2>{{ t('preScheduleResult') }}</h2>
              <InfoTooltip :text="t('preScheduleResultTip')" />
            </div>
          </div>
        </div>

        <div class="library-toolbar">
          <v-tabs :model-value="preScheduleActiveSheet" color="primary" @update:model-value="$emit('change-pre-schedule-sheet', $event)">
            <v-tab v-for="sheet in preScheduleData.sheets" :key="sheet" :value="sheet">{{ sheet }}</v-tab>
          </v-tabs>
        </div>

        <div class="library-meta">
          <span>{{ t('currentSheet') }}：{{ preScheduleActiveSheet || t('unselected') }}</span>
          <span>{{ t('totalRows') }}：{{ preScheduleData.total }}</span>
          <span>{{ t('columnCount') }}：{{ preScheduleData.columns.length }}</span>
        </div>

        <DataVTable
          :records="preScheduleData.rows"
          :columns="preScheduleTableColumns"
          :height="420"
          :empty-text="t('noPreScheduleResult')"
        />
      </v-sheet>

      <v-sheet class="cutting-visualization-section" color="transparent">
        <div class="section-head compact-section-head">
          <div>
            <div class="section-title-with-tip">
              <h2>{{ t('pipeCuttingVisualization') }}</h2>
              <InfoTooltip :text="t('pipeCuttingVisualizationTip')" />
            </div>
          </div>
          <v-chip color="secondary" variant="tonal">{{ t('pipeCount', { count: cuttingData.total }) }}</v-chip>
        </div>

        <v-alert v-if="cuttingError" :text="cuttingError" type="error" density="compact" class="status-alert" />

        <div class="cutting-summary">
          <div>
            <span>{{ t('originalTotalLength') }}</span>
            <strong>{{ formatLength(cuttingData.totalOriginalLength) }}</strong>
          </div>
          <div>
            <span>{{ t('usedLength') }}</span>
            <strong>{{ formatLength(cuttingData.totalUsedLength) }}</strong>
          </div>
          <div>
            <span>{{ t('remainingLength') }}</span>
            <strong>{{ formatLength(cuttingData.totalRemainingLength) }}</strong>
          </div>
          <div>
            <span>{{ t('averageUtilization') }}</span>
            <strong>{{ cuttingData.averageUtilization }}%</strong>
          </div>
        </div>

        <div v-if="!cuttingData.rows.length && !cuttingError" class="empty-cutting">{{ t('noCuttingVisualization') }}</div>
        <div ref="tableContainer" class="cutting-vtable-host" @wheel.stop @touchmove.stop />
        <div
          v-if="cuttingTooltip.visible"
          class="cutting-tooltip"
          :style="{ left: `${cuttingTooltip.x}px`, top: `${cuttingTooltip.y}px` }"
        >
          <strong>{{ cuttingTooltip.title }}</strong>
          <span v-for="line in cuttingTooltip.lines" :key="line">{{ line }}</span>
        </div>
      </v-sheet>
    </v-card>

    <v-card v-if="cuttingOverviewActions.length" class="module-panel cutting-overview-card">
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
          v-for="action in cuttingOverviewActions"
          :key="action.key"
          color="primary"
          variant="tonal"
          :loading="runningKey === action.key"
          @click="$emit('execute-action', action.key)"
        >
          {{ localizedActionName(action) }}
        </v-btn>
      </div>
    </v-card>
</template>

<style scoped>
.cutting-overview-card {
  margin-top: 16px;
}

.pre-schedule-config {
  margin-bottom: 14px;
}

.future-schedule-config :deep(.v-expansion-panel) {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
}

.future-schedule-config :deep(.v-expansion-panel-title) {
  min-height: 42px;
  padding: 0 14px;
  color: var(--strong);
  font-size: 14px;
  font-weight: 800;
}

.pre-schedule-config-grid {
  display: grid;
  grid-template-columns: minmax(220px, 360px);
  gap: 12px;
}

.pre-schedule-switch-field {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
}

.future-schedule-field {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.future-schedule-field > span {
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}

.future-schedule-field > small {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.35;
}

.pre-schedule-switch-field > small {
  grid-column: 1 / -1;
}

.pre-schedule-result-section,
.cutting-visualization-section {
  min-width: 0;
}

.cutting-visualization-section {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}

.compact-section-head {
  margin-bottom: 10px;
}

.compact-section-head h2 {
  font-size: 16px;
}
</style>
