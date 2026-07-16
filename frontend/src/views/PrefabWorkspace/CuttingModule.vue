<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import DataVTable from '../../components/DataVTable.vue'
import InfoTooltip from '../../components/InfoTooltip.vue'
import ScheduleCalendar from '../../components/ScheduleCalendar.vue'
import ScheduleDashboardPanel from '../../components/ScheduleDashboardPanel.vue'
import StagedPlanPreview from '../../components/StagedPlanPreview.vue'
import { localizedActionName, localizedModuleDescription } from '../../services/navigationLabels'
import { dashboardVisibility, displayDataPath, setDashboardVisibility, t } from '../../services/pipecloudState'

const props = defineProps({
  activeModule: { type: Object, required: true },
  activeModuleTitle: { type: String, required: true },
  showDashboard: { type: Boolean, default: true },
  showVisualization: { type: Boolean, default: false },
  dashboard: { type: Object, required: true },
  dashboardLoading: { type: Boolean, default: false },
  dashboardError: { type: String, default: '' },
  preScheduleTitleKey: { type: String, default: 'cuttingPreSchedule' },
  preSchedulePathFallbackKey: { type: String, default: 'preScheduleResultDefaultPath' },
  resultTitleKey: { type: String, default: 'preScheduleResult' },
  resultTipKey: { type: String, default: 'preScheduleResultTip' },
  showResultHeader: { type: Boolean, default: true },
  preScheduleLoading: { type: Boolean, default: false },
  preScheduleData: { type: Object, required: true },
  preScheduleActiveSheet: { type: String, default: '' },
  preScheduleError: { type: String, default: '' },
  preScheduleTableColumns: { type: Array, default: () => [] },
  preScheduleResultSelectable: { type: Boolean, default: false },
  preScheduleResultSelectedCount: { type: Number, default: 0 },
  releaseMaterialsLoading: { type: Boolean, default: false },
  cuttingLoading: { type: Boolean, default: false },
  cuttingData: { type: Object, required: true },
  cuttingError: { type: String, default: '' },
  cuttingTooltip: { type: Object, required: true },
  cuttingPreScheduleAction: { type: Object, default: null },
  cuttingOverviewActions: { type: Array, default: () => [] },
  cuttingPendingStage: { type: Object, default: null },
  cuttingScheduleMessage: { type: String, default: '' },
  cuttingScheduleError: { type: String, default: '' },
  cuttingStageSaving: { type: Boolean, default: false },
  cuttingPreviewLoading: { type: Boolean, default: false },
  cuttingPreviewError: { type: String, default: '' },
  cuttingPreviewData: { type: Object, default: () => ({ sheets: [], rows: [], columns: [], total: 0 }) },
  cuttingPreviewColumns: { type: Array, default: () => [] },
  cuttingScheduleOptions: { type: Object, default: null },
  cuttingScheduleDefaults: { type: Object, default: () => ({}) },
  dateModeOptions: { type: Array, default: () => [] },
  scheduleCalendarStart: { type: String, default: '' },
  scheduleCalendarEnd: { type: String, default: '' },
  manualDateList: { type: Array, default: () => [] },
  holidayCalendarDateList: { type: Array, default: () => [] },
  showPreScheduleOptions: { type: Boolean, default: false },
  preScheduleOptions: { type: Object, default: null },
  concentrationDimensionOptions: { type: Array, default: () => [] },
  selectionModeOptions: { type: Array, default: () => [] },
  manualSelectionLoading: { type: Boolean, default: false },
  manualSelectionError: { type: String, default: '' },
  manualSelectionRows: { type: Array, default: () => [] },
  manualSelectionColumns: { type: Array, default: () => [] },
  manualSelectionSelectedCount: { type: Number, default: 0 },
  runningKey: { type: String, default: '' },
  formatLength: { type: Function, required: true },
})

const emit = defineEmits([
  'execute-action',
  'refresh-match-result',
  'refresh-visualization',
  'change-pre-schedule-sheet',
  'table-container-ready',
  'manual-selection-change',
  'result-selection-change',
  'release-selected-materials',
  'save-cutting-stage',
  'preview-cutting-file',
  'change-cutting-preview-sheet',
  'update-cutting-start-date',
  'update-cutting-manual-date-list',
  'update-cutting-holiday-date-list',
])

const tableContainer = ref(null)
const dashboardCollapsed = ref(false)
const cuttingStartDateMenu = ref(false)
const manualCuttingDatesMenu = ref(false)
const cuttingHolidayDatesMenu = ref(false)

const resultSelectedCount = computed(() => (
  props.preScheduleResultSelectable
    ? props.preScheduleResultSelectedCount
    : props.manualSelectionSelectedCount
))

function handleResultSelection(event) {
  emit('result-selection-change', event)
  if (props.cuttingScheduleOptions) {
    emit('manual-selection-change', event)
  }
}

function updateCuttingStartDate(value) {
  emit('update-cutting-start-date', value)
  cuttingStartDateMenu.value = false
}

function emitTableContainer() {
  if (!props.showVisualization) return
  emit('table-container-ready', tableContainer.value)
}

onMounted(async () => {
  await nextTick()
  emitTableContainer()
})

onBeforeUnmount(() => {
  if (props.showVisualization) {
    emit('table-container-ready', null)
  }
})
</script>

<template>
    <v-card v-if="showDashboard && dashboardVisibility.cutting" class="module-panel" :loading="dashboardLoading">
      <ScheduleDashboardPanel
        mode="cutting"
        :title="t('cuttingDashboardTitle')"
        :description="t('cuttingDashboardDescription')"
        :dashboard="dashboard"
        :error="dashboardError"
        :panel="false"
        collapsible
        :collapsed="dashboardCollapsed"
        @hide="setDashboardVisibility('cutting', false)"
        @toggle="dashboardCollapsed = !dashboardCollapsed"
      />
    </v-card>

    <v-card class="module-panel cutting-pre-schedule-card" :loading="preScheduleLoading">
      <div class="section-head">
        <div>
          <h2>{{ t(preScheduleTitleKey) }}</h2>
          <span>{{ displayDataPath(preScheduleData.path, t(preSchedulePathFallbackKey)) }}</span>
        </div>
        <div class="module-actions pre-schedule-actions">
          <v-btn
            v-if="cuttingPreScheduleAction"
            color="primary"
            variant="tonal"
            :loading="runningKey === cuttingPreScheduleAction.key"
            :disabled="Boolean(runningKey)"
            @click="$emit('execute-action', cuttingPreScheduleAction.key)"
          >
            {{ localizedActionName(cuttingPreScheduleAction) }}
          </v-btn>
          <v-btn :loading="preScheduleLoading" prepend-icon="mdi-refresh" @click="$emit('refresh-match-result')">{{ t('refreshMatchResult') }}</v-btn>
          <v-btn v-if="showVisualization" :loading="cuttingLoading" prepend-icon="mdi-refresh" @click="$emit('refresh-visualization')">{{ t('refreshVisualization') }}</v-btn>
        </div>
      </div>

      <v-expansion-panels
        v-if="showPreScheduleOptions && preScheduleOptions"
        class="pre-schedule-config future-schedule-config"
        variant="accordion"
      >
        <v-expansion-panel value="options">
          <v-expansion-panel-title>
            <div>
              <strong>{{ t('materialLockingParams') }}</strong>
            </div>
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <div class="pre-schedule-config-grid">
              <label class="future-schedule-field pre-schedule-control-field">
                <span>{{ t('materialLockingSelectionMode') }}</span>
                <v-select
                  v-model="preScheduleOptions.selectionMode"
                  :items="selectionModeOptions"
                  density="compact"
                  variant="outlined"
                  hide-details
                  :disabled="runningKey === cuttingPreScheduleAction?.key"
                />
                <small>{{ preScheduleOptions.selectionMode === 'manual' ? t('manualSelectWeldsHint') : t('autoSelectWeldsHint') }}</small>
              </label>
              <label class="future-schedule-field pre-schedule-control-field">
                <span>{{ t('pipelineConcentrationDimension') }}</span>
                <v-select
                  v-model="preScheduleOptions.concentrationDimension"
                  :items="concentrationDimensionOptions"
                  density="compact"
                  variant="outlined"
                  hide-details
                  :disabled="runningKey === cuttingPreScheduleAction?.key"
                />
              </label>
              <label class="future-schedule-field pre-schedule-control-field">
                <span>{{ t('pipelineConcentrationThreshold') }}</span>
                <v-text-field
                  v-model.number="preScheduleOptions.concentrationThresholdPercent"
                  type="number"
                  min="0"
                  max="100"
                  step="1"
                  suffix="%"
                  density="compact"
                  variant="outlined"
                  hide-details
                  :disabled="runningKey === cuttingPreScheduleAction?.key"
                />
                <small>{{ t('pipelineConcentrationHint') }}</small>
              </label>
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
            <div v-if="preScheduleOptions.selectionMode === 'manual'" class="manual-selection-panel">
              <div class="manual-selection-head">
                <div>
                  <strong>{{ t('manualMaterialLockingTitle') }}</strong>
                  <span>{{ t('manualMaterialLockingHint') }}</span>
                </div>
                <v-chip color="primary" variant="tonal">
                  {{ t('selectedRows') }}：{{ manualSelectionSelectedCount }}
                </v-chip>
              </div>
              <v-alert
                v-if="manualSelectionError"
                :text="manualSelectionError"
                type="error"
                density="compact"
                class="status-alert"
              />
              <DataVTable
                :records="manualSelectionRows"
                :columns="manualSelectionColumns"
                :height="420"
                :empty-text="t('noPrefabWeldLibraryRows')"
                filterable
                selectable
                row-key="库序号"
                @selection-change="$emit('manual-selection-change', $event)"
              />
              <v-progress-linear
                v-if="manualSelectionLoading"
                indeterminate
                color="primary"
                height="2"
              />
            </div>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>

      <v-alert v-if="preScheduleError" :text="preScheduleError" type="error" density="compact" class="status-alert" />

      <v-sheet class="pre-schedule-result-section" color="transparent">
        <div v-if="showResultHeader" class="section-head compact-section-head">
          <div>
            <div class="section-title-with-tip">
              <h2>{{ t(resultTitleKey) }}</h2>
              <InfoTooltip :text="t(resultTipKey)" />
            </div>
          </div>
          <div v-if="preScheduleResultSelectable" class="module-actions">
            <v-btn
              color="warning"
              variant="tonal"
              :loading="releaseMaterialsLoading"
              :disabled="releaseMaterialsLoading || !preScheduleResultSelectedCount"
              @click="$emit('release-selected-materials')"
            >
              {{ t('releaseSelectedMaterials') }}
            </v-btn>
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
          <span>{{ t('selectedRows') }}：{{ resultSelectedCount }}</span>
        </div>

        <DataVTable
          :records="preScheduleData.rows"
          :columns="preScheduleTableColumns"
          :height="420"
          :empty-text="t('noPreScheduleResult')"
          filterable
          selectable
          row-key="库序号"
          @selection-change="handleResultSelection"
        />
      </v-sheet>

      <v-sheet v-if="showVisualization" class="cutting-visualization-section" color="transparent">
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
      <v-divider v-if="cuttingOverviewActions.length" class="schedule-section-divider" />

      <section v-if="cuttingOverviewActions.length" class="schedule-generation-section cutting-overview-card">
      <div class="section-head">
        <div>
          <div class="section-title-with-tip">
            <h2>{{ activeModuleTitle }}</h2>
            <InfoTooltip :text="localizedModuleDescription(activeModule)" />
          </div>
        </div>
        <div class="module-actions">
          <v-btn
            v-for="action in cuttingOverviewActions"
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

      <v-expansion-panels
        v-if="cuttingScheduleOptions"
        class="pre-schedule-config future-schedule-config"
        variant="accordion"
      >
        <v-expansion-panel value="cutting-schedule-options">
          <v-expansion-panel-title>
            <div>
              <strong>{{ t('cuttingScheduleParams') }}</strong>
            </div>
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <div class="pre-schedule-config-grid">
              <label class="future-schedule-field pre-schedule-control-field">
                <span>{{ t('cuttingScheduleSelectionMode') }}</span>
                <v-select
                  v-model="cuttingScheduleOptions.selectionMode"
                  :items="selectionModeOptions"
                  density="compact"
                  variant="outlined"
                  hide-details
                  :disabled="runningKey === 'cutting-schedule'"
                />
                <small>{{ cuttingScheduleOptions.selectionMode === 'manual' ? t('manualCuttingScheduleHint') : t('autoCuttingScheduleHint') }}</small>
              </label>
              <label class="future-schedule-field pre-schedule-control-field">
                <span>{{ t('targetDiameterPerOrder') }}</span>
                <v-text-field
                  v-model="cuttingScheduleOptions.targetDiameter"
                  type="number"
                  min="1"
                  step="0.1"
                  density="compact"
                  variant="outlined"
                  hide-details
                  :placeholder="String(cuttingScheduleDefaults.targetDiameter || '')"
                  :disabled="runningKey === 'cutting-schedule'"
                />
                <small>{{ t('defaultValue', { value: cuttingScheduleDefaults.targetDiameter || '-' }) }}</small>
              </label>
              <label class="future-schedule-field pre-schedule-control-field">
                <span>{{ t('ordersPerDay') }}</span>
                <v-text-field
                  v-model="cuttingScheduleOptions.ordersPerDay"
                  type="number"
                  min="1"
                  density="compact"
                  variant="outlined"
                  hide-details
                  :placeholder="String(cuttingScheduleDefaults.ordersPerDay || '')"
                  :disabled="runningKey === 'cutting-schedule'"
                />
                <small>{{ t('defaultValue', { value: cuttingScheduleDefaults.ordersPerDay || '-' }) }}</small>
              </label>
              <label class="future-schedule-field pre-schedule-control-field">
                <span>{{ t('dateGenerationMode') }}</span>
                <v-select
                  v-model="cuttingScheduleOptions.dateMode"
                  :items="dateModeOptions"
                  density="compact"
                  variant="outlined"
                  hide-details
                  :disabled="runningKey === 'cutting-schedule'"
                />
                <small>{{ t('cuttingScheduleDateModeHint') }}</small>
              </label>
              <label v-if="cuttingScheduleOptions.dateMode !== 'manual'" class="future-schedule-field pre-schedule-control-field">
                <span>{{ t('cuttingScheduleStartDate') }}</span>
                <v-menu v-model="cuttingStartDateMenu" :close-on-content-click="false" location="bottom">
                  <template #activator="{ props }">
                    <v-text-field
                      v-bind="props"
                      :model-value="cuttingScheduleOptions.weldStartDate"
                      density="compact"
                      variant="outlined"
                      hide-details
                      readonly
                      append-inner-icon="mdi-calendar"
                      :disabled="runningKey === 'cutting-schedule'"
                      :placeholder="t('today')"
                    />
                  </template>
                  <ScheduleCalendar
                    :model-value="cuttingScheduleOptions.weldStartDate"
                    :min="scheduleCalendarStart"
                    :max="scheduleCalendarEnd"
                    @update:model-value="updateCuttingStartDate"
                  />
                </v-menu>
                <small>{{ t('cuttingScheduleStartDateHint') }}</small>
              </label>
              <label v-if="cuttingScheduleOptions.dateMode === 'manual'" class="future-schedule-field pre-schedule-control-field is-wide">
                <span>{{ t('cuttingScheduleManualDates') }}</span>
                <v-menu v-model="manualCuttingDatesMenu" :close-on-content-click="false" location="bottom">
                  <template #activator="{ props }">
                    <v-text-field
                      v-bind="props"
                      :model-value="t('openManualWeldCalendar')"
                      density="compact"
                      variant="outlined"
                      hide-details
                      readonly
                      append-inner-icon="mdi-calendar-multiselect"
                      :disabled="runningKey === 'cutting-schedule'"
                    />
                  </template>
                  <ScheduleCalendar
                    :model-value="manualDateList"
                    multiple
                    :min="scheduleCalendarStart"
                    :max="scheduleCalendarEnd"
                    :highlighted-dates="holidayCalendarDateList"
                    @update:model-value="$emit('update-cutting-manual-date-list', $event)"
                  />
                </v-menu>
                <small>{{ t('cuttingScheduleManualDatesHint') }}</small>
              </label>
              <label v-if="cuttingScheduleOptions.dateMode !== 'manual'" class="future-schedule-field pre-schedule-control-field">
                <span>{{ t('maxGeneratedDays') }}</span>
                <v-text-field
                  v-model="cuttingScheduleOptions.maxDays"
                  type="number"
                  min="1"
                  density="compact"
                  variant="outlined"
                  hide-details
                  :disabled="runningKey === 'cutting-schedule'"
                  :placeholder="t('untilAllScheduled')"
                />
                <small>{{ t('cuttingScheduleMaxDaysHint') }}</small>
              </label>
              <label class="future-schedule-field pre-schedule-switch-field">
                <span>{{ t('skipHolidays') }}</span>
                <v-switch
                  v-model="cuttingScheduleOptions.skipHolidays"
                  color="primary"
                  density="compact"
                  hide-details
                  inset
                  :disabled="runningKey === 'cutting-schedule'"
                />
                <small>{{ t('skipHolidaysHint') }}</small>
              </label>
              <label v-if="cuttingScheduleOptions.skipHolidays" class="future-schedule-field pre-schedule-control-field is-wide">
                <span>{{ t('holidayDates') }}</span>
                <v-menu v-model="cuttingHolidayDatesMenu" :close-on-content-click="false" location="bottom">
                  <template #activator="{ props }">
                    <v-text-field
                      v-bind="props"
                      :model-value="t('openHolidayCalendar')"
                      density="compact"
                      variant="outlined"
                      hide-details
                      readonly
                      append-inner-icon="mdi-calendar-remove"
                      :disabled="runningKey === 'cutting-schedule'"
                    />
                  </template>
                  <ScheduleCalendar
                    :model-value="holidayCalendarDateList"
                    multiple
                    :min="scheduleCalendarStart"
                    :max="scheduleCalendarEnd"
                    @update:model-value="$emit('update-cutting-holiday-date-list', $event)"
                  />
                </v-menu>
                <small>{{ t('holidayDatesHint') }}</small>
              </label>
            </div>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>

      <v-alert v-if="cuttingScheduleError" :text="cuttingScheduleError" type="error" density="compact" class="status-alert" />
      <v-alert v-if="cuttingScheduleMessage" :text="cuttingScheduleMessage" type="success" density="compact" class="status-alert" />

      <StagedPlanPreview
        :stage="cuttingPendingStage"
        :preview="cuttingPreviewData"
        :columns="cuttingPreviewColumns"
        :title="t('cuttingSchedulePreview')"
        :save-label="t('saveToPlanFile')"
        :empty-text="t('noCuttingSchedulePreview')"
        :loading="cuttingPreviewLoading"
        :error="cuttingPreviewError"
        :saving="cuttingStageSaving"
        @save="$emit('save-cutting-stage')"
        @preview-file="$emit('preview-cutting-file', $event)"
        @change-sheet="$emit('change-cutting-preview-sheet', $event)"
      />
      </section>
    </v-card>
</template>

<style scoped>
.cutting-overview-card {
  min-width: 0;
}

.schedule-section-divider {
  margin: 24px 0 20px;
  border-color: var(--line);
}

.schedule-generation-section {
  min-width: 0;
}

.cutting-preview {
  display: grid;
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}

.cutting-preview-browser {
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
  gap: 14px;
  min-width: 0;
}

.cutting-preview-left,
.cutting-preview-right {
  min-width: 0;
}

.cutting-preview-left {
  height: clamp(280px, 52vh, 480px);
  padding-right: 4px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.cutting-date-title {
  display: grid;
  gap: 3px;
}

.cutting-date-title span {
  color: var(--muted);
  font-size: 12px;
}

.cutting-file-list {
  display: grid;
  gap: 8px;
}

.cutting-file-button {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  gap: 2px 8px;
  align-items: center;
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
  color: var(--text);
  text-align: left;
  cursor: pointer;
}

.cutting-file-button span,
.cutting-file-button small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cutting-file-button small {
  grid-column: 2;
  color: var(--muted);
  font-size: 11px;
}

.cutting-file-button.is-active {
  border-color: var(--primary);
  background: var(--panel-soft);
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
  grid-template-columns: repeat(2, minmax(240px, 1fr));
  align-items: start;
  gap: 12px;
}

.pre-schedule-switch-field {
  grid-template-columns: minmax(0, 1fr) 64px;
  align-items: center;
}

.pre-schedule-control-field :deep(.v-field) {
  min-height: 40px;
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

.future-schedule-field.is-wide {
  grid-column: auto;
}

.pre-schedule-switch-field > small {
  grid-column: 1 / -1;
}

.manual-selection-panel {
  display: grid;
  gap: 10px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}

.manual-selection-head {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.manual-selection-head > div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.manual-selection-head strong {
  color: var(--strong);
  font-size: 14px;
  font-weight: 800;
}

.manual-selection-head span {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.4;
}

@media (max-width: 1280px) {
  .pre-schedule-config-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 720px) {
  .pre-schedule-config-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .manual-selection-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .cutting-preview-browser {
    grid-template-columns: minmax(0, 1fr);
  }

  .cutting-preview-left {
    height: min(340px, 48vh);
  }
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
