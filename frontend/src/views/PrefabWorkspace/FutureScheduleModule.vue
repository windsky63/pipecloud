<script setup>
import { ref } from 'vue'
import DataVTable from '../../components/DataVTable.vue'
import InfoTooltip from '../../components/InfoTooltip.vue'
import ScheduleCalendar from '../../components/ScheduleCalendar.vue'
import ScheduleDashboardPanel from '../../components/ScheduleDashboardPanel.vue'
import StagedPlanPreview from '../../components/StagedPlanPreview.vue'
import WeldingDashboardPanel from '../../components/WeldingDashboardPanel.vue'
import { localizedActionName, localizedModuleDescription } from '../../services/navigationLabels'
import { dashboardVisibility, setDashboardVisibility, t } from '../../services/pipecloudState'

const props = defineProps({
  activeModule: { type: Object, required: true },
  activeModuleTitle: { type: String, required: true },
  futureScheduleLoading: { type: Boolean, default: false },
  futureScheduleError: { type: String, default: '' },
  futureScheduleMessage: { type: String, default: '' },
  futurePendingStage: { type: Object, default: null },
  futureStageSaving: { type: Boolean, default: false },
  futurePendingPreviewLoading: { type: Boolean, default: false },
  futurePendingPreviewError: { type: String, default: '' },
  futurePendingPreview: { type: Object, default: () => ({}) },
  futurePendingPreviewColumns: { type: Array, default: () => [] },
  selectedFuturePendingFilePath: { type: String, default: '' },
  futureScheduleAction: { type: Object, default: null },
  futureScheduleConfig: { type: Object, required: true },
  futureScheduleDefaults: { type: Object, default: () => ({}) },
  futureScheduleDateModeOptions: { type: Array, default: () => [] },
  selectionModeOptions: { type: Array, default: () => [] },
  manualSelectionLoading: { type: Boolean, default: false },
  manualSelectionError: { type: String, default: '' },
  manualSelectionRows: { type: Array, default: () => [] },
  manualSelectionColumns: { type: Array, default: () => [] },
  manualSelectionSelectedCount: { type: Number, default: 0 },
  scheduleCalendarStart: { type: String, required: true },
  scheduleCalendarEnd: { type: String, required: true },
  manualWeldDateList: { type: Array, default: () => [] },
  holidayCalendarDateList: { type: Array, default: () => [] },
  antiCorrosionDashboard: { type: Object, default: () => ({}) },
  antiCorrosionDashboardLoading: { type: Boolean, default: false },
  antiCorrosionDashboardError: { type: String, default: '' },
  cuttingDashboard: { type: Object, default: () => ({}) },
  cuttingDashboardLoading: { type: Boolean, default: false },
  cuttingDashboardError: { type: String, default: '' },
  weldingDashboard: { type: Object, default: () => ({}) },
  weldingDashboardLoading: { type: Boolean, default: false },
  weldingDashboardError: { type: String, default: '' },
})

const emit = defineEmits([
  'execute-future-schedule',
  'update-weld-start-date',
  'update-manual-weld-date-list',
  'update-holiday-date-list',
  'manual-selection-change',
  'preview-pending-file',
  'change-pending-preview-sheet',
  'save-pending-stage',
])

const configPanels = ref(['config'])
const dashboardCollapsed = ref({ antiCorrosion: false, cutting: false, welding: false })
const weldStartDateMenu = ref(false)
const manualWeldDatesMenu = ref(false)
const holidayDatesMenu = ref(false)

function updateWeldStartDate(value) {
  emit('update-weld-start-date', value)
  weldStartDateMenu.value = false
}
</script>

<template>
  <div class="future-dashboard-stack">
    <ScheduleDashboardPanel
      v-if="dashboardVisibility.futureAntiCorrosion"
      mode="anti-corrosion"
      :title="t('antiCorrosionDashboardTitle')"
      :description="t('antiCorrosionDashboardDescription')"
      :dashboard="antiCorrosionDashboard"
      :loading="antiCorrosionDashboardLoading"
      :error="antiCorrosionDashboardError"
      collapsible
      :collapsed="dashboardCollapsed.antiCorrosion"
      @hide="setDashboardVisibility('futureAntiCorrosion', false)"
      @toggle="dashboardCollapsed.antiCorrosion = !dashboardCollapsed.antiCorrosion"
    />
    <ScheduleDashboardPanel
      v-if="dashboardVisibility.futureCutting"
      mode="cutting"
      :title="t('cuttingDashboardTitle')"
      :description="t('cuttingDashboardDescription')"
      :dashboard="cuttingDashboard"
      :loading="cuttingDashboardLoading"
      :error="cuttingDashboardError"
      collapsible
      :collapsed="dashboardCollapsed.cutting"
      @hide="setDashboardVisibility('futureCutting', false)"
      @toggle="dashboardCollapsed.cutting = !dashboardCollapsed.cutting"
    />
    <WeldingDashboardPanel
      v-if="dashboardVisibility.futureWelding"
      :title="t('weldingDashboardTitle')"
      :description="t('weldingDashboardDescription')"
      :dashboard="weldingDashboard"
      :loading="weldingDashboardLoading"
      :error="weldingDashboardError"
      collapsible
      :collapsed="dashboardCollapsed.welding"
      @hide="setDashboardVisibility('futureWelding', false)"
      @toggle="dashboardCollapsed.welding = !dashboardCollapsed.welding"
    />
  </div>

  <v-card class="module-panel" :loading="futureScheduleLoading">
    <div class="section-head">
      <div>
        <div class="section-title-with-tip">
          <h2>{{ activeModuleTitle }}</h2>
          <InfoTooltip :text="localizedModuleDescription(activeModule)" />
        </div>
      </div>
      <div class="module-actions">
        <v-btn
          v-if="futureScheduleAction"
          color="primary"
          variant="tonal"
          prepend-icon="mdi-calendar-sync"
          :loading="futureScheduleLoading"
          @click="$emit('execute-future-schedule')"
        >
          {{ localizedActionName(futureScheduleAction) }}
        </v-btn>
      </div>
    </div>

    <v-alert v-if="futureScheduleError" :text="futureScheduleError" type="error" density="compact" class="status-alert" />
    <v-alert v-if="futureScheduleMessage" :text="futureScheduleMessage" type="success" density="compact" class="status-alert" />

    <v-expansion-panels v-model="configPanels" class="future-schedule-config" variant="accordion">
      <v-expansion-panel value="config">
        <v-expansion-panel-title>
          {{ t('generatedConfig') }}
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <div class="future-schedule-config-grid">
            <label class="future-schedule-field">
              <span>{{ t('futureScheduleSelectionMode') }}</span>
              <v-select
                v-model="futureScheduleConfig.selectionMode"
                :items="selectionModeOptions"
                density="compact"
                hide-details
              />
              <small>{{ futureScheduleConfig.selectionMode === 'manual' ? t('futureManualSelectionHint') : t('futureAutoSelectionHint') }}</small>
            </label>
            <label class="future-schedule-field">
              <span>{{ t('dateGenerationMode') }}</span>
              <v-select
                v-model="futureScheduleConfig.dateMode"
                :items="futureScheduleDateModeOptions"
                density="compact"
                hide-details
              />
              <small>{{ t('dateGenerationModeHint') }}</small>
            </label>
            <label v-if="futureScheduleConfig.dateMode !== 'manual'" class="future-schedule-field">
              <span>{{ t('firstWeldDate') }}</span>
              <v-menu
                v-model="weldStartDateMenu"
                :close-on-content-click="false"
                location="bottom"
              >
                <template #activator="{ props }">
                  <v-text-field
                    v-bind="props"
                    :model-value="futureScheduleConfig.weldStartDate"
                    density="compact"
                    hide-details
                    readonly
                    append-inner-icon="mdi-calendar"
                    :placeholder="futureScheduleDefaults.weldStartDate || t('defaultTomorrow')"
                  />
                </template>
                <ScheduleCalendar
                  :model-value="futureScheduleConfig.weldStartDate"
                  :min="scheduleCalendarStart"
                  :max="scheduleCalendarEnd"
                  @update:model-value="updateWeldStartDate"
                />
              </v-menu>
              <small>{{ t('defaultValue', { value: futureScheduleDefaults.weldStartDate || t('tomorrow') }) }}</small>
            </label>
            <label v-if="futureScheduleConfig.dateMode === 'manual'" class="future-schedule-field is-wide">
              <span>{{ t('manualWeldDates') }}</span>
              <v-menu
                v-model="manualWeldDatesMenu"
                :close-on-content-click="false"
                location="bottom"
              >
                <template #activator="{ props }">
                  <v-text-field
                    v-bind="props"
                    :model-value="t('openManualWeldCalendar')"
                    density="compact"
                    hide-details
                    readonly
                    append-inner-icon="mdi-calendar-multiselect"
                  />
                </template>
                <ScheduleCalendar
                  :model-value="manualWeldDateList"
                  multiple
                  :min="scheduleCalendarStart"
                  :max="scheduleCalendarEnd"
                  :highlighted-dates="holidayCalendarDateList"
                  @update:model-value="$emit('update-manual-weld-date-list', $event)"
                />
              </v-menu>
              <small>{{ t('manualWeldDatesHint') }}</small>
            </label>
            <label v-if="futureScheduleConfig.dateMode !== 'manual'" class="future-schedule-field">
              <span>{{ t('maxGeneratedDays') }}</span>
              <v-text-field
                v-model="futureScheduleConfig.maxDays"
                type="number"
                min="1"
                density="compact"
                hide-details
                :placeholder="futureScheduleDefaults.maxDays || t('untilAllScheduled')"
              />
              <small>{{ t('defaultValue', { value: futureScheduleDefaults.maxDays || t('untilAllScheduled') }) }}</small>
            </label>
            <label class="future-schedule-field">
              <span>{{ t('targetDiameterPerOrder') }}</span>
              <v-text-field
                v-model="futureScheduleConfig.targetDiameter"
                type="number"
                min="1"
                step="0.1"
                density="compact"
                hide-details
                :placeholder="String(futureScheduleDefaults.targetDiameter || '')"
              />
              <small>{{ t('defaultValue', { value: futureScheduleDefaults.targetDiameter || '-' }) }}</small>
            </label>
            <label class="future-schedule-field">
              <span>{{ t('ordersPerDay') }}</span>
              <v-text-field
                v-model="futureScheduleConfig.ordersPerDay"
                type="number"
                min="1"
                density="compact"
                hide-details
                :placeholder="String(futureScheduleDefaults.ordersPerDay || '')"
              />
              <small>{{ t('defaultValue', { value: futureScheduleDefaults.ordersPerDay || '-' }) }}</small>
            </label>
            <label class="future-schedule-field">
              <span>{{ t('cuttingLeadDays') }}</span>
              <v-text-field
                v-model="futureScheduleConfig.cuttingLeadDays"
                type="number"
                min="0"
                density="compact"
                hide-details
                :placeholder="String(futureScheduleDefaults.cuttingLeadDays ?? 1)"
              />
              <small>{{ t('defaultValue', { value: futureScheduleDefaults.cuttingLeadDays ?? 1 }) }}</small>
            </label>
            <label class="future-schedule-field">
              <span>{{ t('antiCorrosionLeadDays') }}</span>
              <v-text-field
                v-model="futureScheduleConfig.antiCorrosionLeadDays"
                type="number"
                min="0"
                density="compact"
                hide-details
                :placeholder="String(futureScheduleDefaults.antiCorrosionLeadDays ?? 1)"
              />
              <small>{{ t('defaultValue', { value: futureScheduleDefaults.antiCorrosionLeadDays ?? 1 }) }}</small>
            </label>
            <label class="future-schedule-field">
              <span>{{ t('antiCorrosionCommissionArea') }}</span>
              <v-text-field
                v-model.number="futureScheduleConfig.commissionArea"
                type="number"
                min="1"
                step="1"
                density="compact"
                hide-details
                :placeholder="String(futureScheduleDefaults.commissionArea || 1500)"
              />
              <small>{{ t('antiCorrosionCommissionAreaHint') }}</small>
            </label>
            <label class="future-schedule-field future-schedule-switch-field">
              <span>{{ t('skipHolidays') }}</span>
              <v-switch
                v-model="futureScheduleConfig.skipHolidays"
                color="primary"
                density="compact"
                hide-details
                inset
              />
              <small>{{ t('skipHolidaysHint') }}</small>
            </label>
            <label v-if="futureScheduleConfig.skipHolidays" class="future-schedule-field is-wide">
              <span>{{ t('holidayDates') }}</span>
              <v-menu
                v-model="holidayDatesMenu"
                :close-on-content-click="false"
                location="bottom"
              >
                <template #activator="{ props }">
                  <v-text-field
                    v-bind="props"
                    :model-value="t('openHolidayCalendar')"
                    density="compact"
                    hide-details
                    readonly
                    append-inner-icon="mdi-calendar-remove"
                  />
                </template>
                <ScheduleCalendar
                  :model-value="holidayCalendarDateList"
                  multiple
                  :min="scheduleCalendarStart"
                  :max="scheduleCalendarEnd"
                  @update:model-value="$emit('update-holiday-date-list', $event)"
                />
              </v-menu>
              <small>{{ t('holidayDatesHint') }}</small>
            </label>
          </div>
          <div v-if="futureScheduleConfig.selectionMode === 'manual'" class="future-manual-selection-panel">
            <div class="future-manual-selection-head">
              <div>
                <strong>{{ t('futureManualSelectionTitle') }}</strong>
                <span>{{ t('futureManualSelectionDescription') }}</span>
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
              :empty-text="manualSelectionLoading ? t('loading') : t('noFutureSelectableWelds')"
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

    <StagedPlanPreview
      :stage="futurePendingStage"
      :preview="futurePendingPreview"
      :columns="futurePendingPreviewColumns"
      :title="t('totalSchedulingPlan')"
      :save-label="t('saveToPlanFile')"
      :empty-text="t('currentSheetNoData')"
      :loading="futurePendingPreviewLoading"
      :error="futurePendingPreviewError"
      :saving="futureStageSaving"
      group-by-type
      @save="$emit('save-pending-stage')"
      @preview-file="$emit('preview-pending-file', $event)"
      @change-sheet="$emit('change-pending-preview-sheet', $event)"
    />

  </v-card>
</template>

<style scoped>
.future-dashboard-stack {
  display: grid;
  gap: 16px;
  margin-bottom: 16px;
}

.future-schedule-config {
  margin: 4px 0 16px;
}

.pending-stage-actions {
  display: grid;
  gap: 10px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
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

.pending-stage-browser {
  display: grid;
  grid-template-columns: minmax(260px, 340px) minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}

.pending-stage-left,
.pending-stage-preview {
  min-width: 0;
}

.pending-stage-left {
  height: clamp(280px, 52vh, 480px);
}

.pending-stage-scroll {
  height: 100%;
  overflow-y: auto;
  padding-right: 6px;
  scrollbar-color: var(--scrollbar-thumb) var(--scrollbar-track);
  scrollbar-width: thin;
}

.pending-stage-scroll::-webkit-scrollbar {
  width: 10px;
}

.pending-stage-scroll::-webkit-scrollbar-thumb {
  border: 2px solid transparent;
  border-radius: 999px;
  background: var(--scrollbar-thumb);
  background-clip: padding-box;
}

.pending-stage-scroll::-webkit-scrollbar-track {
  background: var(--scrollbar-track);
}

.pending-stage-preview-head h3 {
  margin: 0;
  color: var(--strong);
  font-size: 14px;
  font-weight: 800;
}

.pending-stage-files {
  display: grid;
  gap: 8px;
}

.pending-stage-date-files,
.pending-stage-type-group {
  display: grid;
  gap: 8px;
}

.pending-stage-type-group.has-divider {
  margin-top: 4px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}

.pending-stage-type-title {
  color: #475569;
  font-size: 12px;
  font-weight: 800;
}

.pending-stage-file {
  appearance: none;
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr);
  grid-template-rows: auto;
  column-gap: 8px;
  row-gap: 5px;
  align-items: start;
  width: 100%;
  min-width: 0;
  min-height: 50px;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
  color: #334155;
  text-align: left;
  cursor: pointer;
  font: inherit;
  transition: border-color .16s ease, background .16s ease, box-shadow .16s ease;
}

.pending-stage-file:hover,
.pending-stage-file.is-active {
  border-color: #93b4ff;
  background: #eaf1ff;
  color: #1d4ed8;
}

.pending-stage-file :deep(.v-icon) {
  grid-column: 1;
  grid-row: 1;
  align-self: start;
  margin-top: 1px;
  color: #64748b;
}

.pending-stage-file.is-active :deep(.v-icon),
.pending-stage-file:hover :deep(.v-icon) {
  color: #64748b;
}

.pending-stage-file-main {
  display: grid;
  grid-column: 2;
  grid-row: 1;
  gap: 5px;
  min-width: 0;
}

.pending-stage-file-main strong,
.pending-stage-file-main span,
.pending-stage-file-main small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pending-stage-file-main strong {
  color: #25324a;
  font-size: 13px;
  line-height: 1.35;
}

.pending-stage-file-main span {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.35;
}

.pending-stage-file-main small {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.35;
}

.pending-stage-preview {
  min-height: 0;
}

.pending-stage-group-title {
  display: grid;
  gap: 2px;
}

.pending-stage-group-title span {
  color: var(--muted);
  font-size: 12px;
}

.pending-stage-preview-head {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  justify-content: space-between;
}

.pending-stage-preview-head span {
  display: block;
  max-width: 100%;
  overflow: hidden;
  color: var(--muted);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pending-stage-empty {
  display: grid;
  min-height: 220px;
  place-items: center;
  border: 1px dashed var(--line);
  border-radius: 6px;
  color: var(--muted);
  font-size: 13px;
}

.library-toolbar {
  min-width: 0;
  overflow-x: auto;
}

.library-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  color: var(--muted);
  font-size: 12px;
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

.future-schedule-config-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(240px, 1fr));
  gap: 12px;
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

.future-schedule-switch-field {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
}

.future-schedule-switch-field > small {
  grid-column: 1 / -1;
}

.future-manual-selection-panel {
  display: grid;
  gap: 10px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}

.future-manual-selection-head {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.future-manual-selection-head > div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.future-manual-selection-head strong {
  color: var(--strong);
  font-size: 14px;
  font-weight: 800;
}

.future-manual-selection-head span {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.4;
}

@media (max-width: 1100px) {
  .pending-stage-browser {
    grid-template-columns: 1fr;
  }

  .future-schedule-config-grid {
    grid-template-columns: 1fr;
  }

  .future-schedule-field.is-wide {
    grid-column: auto;
  }
}
</style>
