<script setup>
import { ref } from 'vue'
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
  dashboard: { type: Object, required: true },
  dashboardLoading: { type: Boolean, default: false },
  dashboardError: { type: String, default: '' },
  preScheduleAction: { type: Object, default: null },
  commissionOptions: { type: Object, required: true },
  selectionModeOptions: { type: Array, default: () => [] },
  selectedPreScheduleCount: { type: Number, default: 0 },
  dateModeOptions: { type: Array, default: () => [] },
  scheduleCalendarStart: { type: String, default: '' },
  scheduleCalendarEnd: { type: String, default: '' },
  manualDateList: { type: Array, default: () => [] },
  holidayCalendarDateList: { type: Array, default: () => [] },
  overviewActions: { type: Array, default: () => [] },
  commissionMessage: { type: String, default: '' },
  commissionError: { type: String, default: '' },
  commissionPendingStage: { type: Object, default: null },
  commissionStageSaving: { type: Boolean, default: false },
  commissionPreviewLoading: { type: Boolean, default: false },
  commissionPreviewError: { type: String, default: '' },
  commissionPreviewData: { type: Object, default: () => ({ sheets: [], rows: [], columns: [], total: 0 }) },
  commissionPreviewColumns: { type: Array, default: () => [] },
  preScheduleLoading: { type: Boolean, default: false },
  preScheduleError: { type: String, default: '' },
  preScheduleData: { type: Object, required: true },
  preScheduleActiveSheet: { type: String, default: '' },
  preScheduleTableColumns: { type: Array, default: () => [] },
  runningKey: { type: String, default: '' },
})

const emit = defineEmits([
  'execute-action',
  'change-pre-schedule-sheet',
  'change-commission-preview-sheet',
  'selection-change',
  'save-commission-stage',
  'preview-commission-file',
  'update-start-date',
  'update-manual-date-list',
  'update-holiday-date-list',
])

const commissionStartDateMenu = ref(false)
const dashboardCollapsed = ref(false)
const manualCommissionDatesMenu = ref(false)
const commissionHolidayDatesMenu = ref(false)

function updateStartDate(value) {
  emit('update-start-date', value)
  commissionStartDateMenu.value = false
}
</script>

<template>
  <v-card v-if="dashboardVisibility.antiCorrosion" class="module-panel" :loading="dashboardLoading">
    <ScheduleDashboardPanel
      mode="anti-corrosion"
      :title="t('antiCorrosionDashboardTitle')"
      :description="t('antiCorrosionDashboardDescription')"
      :dashboard="dashboard"
      :error="dashboardError"
      :panel="false"
      collapsible
      :collapsed="dashboardCollapsed"
      @hide="setDashboardVisibility('antiCorrosion', false)"
      @toggle="dashboardCollapsed = !dashboardCollapsed"
    />
  </v-card>

  <v-card class="module-panel" :loading="preScheduleLoading">
    <div class="section-head">
      <div>
        <div class="section-title-with-tip">
          <h2>{{ t('antiCorrosionPreSchedule') }}</h2>
          <InfoTooltip :text="localizedModuleDescription(activeModule)" />
        </div>
        <span>{{ displayDataPath(preScheduleData.path, t('antiCorrosionPreScheduleDefaultPath')) }}</span>
      </div>
      <div class="module-actions">
        <v-btn
          v-if="preScheduleAction"
          color="primary"
          variant="tonal"
          :loading="runningKey === preScheduleAction.key"
          :disabled="Boolean(runningKey)"
          @click="$emit('execute-action', preScheduleAction.key)"
        >
          {{ localizedActionName(preScheduleAction) }}
        </v-btn>
      </div>
    </div>

    <v-alert
      v-if="preScheduleError"
      :text="preScheduleError"
      type="error"
      density="compact"
      class="status-alert"
    />

    <div class="library-toolbar">
      <v-tabs
        :model-value="preScheduleActiveSheet"
        color="primary"
        @update:model-value="$emit('change-pre-schedule-sheet', $event)"
      >
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
      :height="520"
      :empty-text="t('noAntiCorrosionPreScheduleResult')"
      filterable
      selectable
      row-key="库序号"
      @selection-change="$emit('selection-change', $event)"
    />
    <v-divider class="schedule-section-divider" />

    <section class="schedule-generation-section commission-panel">
    <div class="section-head">
      <div>
        <div class="section-title-with-tip">
          <h2>{{ t('antiCorrosionCommissionConfig') }}</h2>
          <InfoTooltip :text="t('antiCorrosionCommissionConfigHint')" />
        </div>
      </div>
      <div class="module-actions">
        <v-btn
          v-for="action in overviewActions"
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

    <v-expansion-panels class="pre-schedule-config future-schedule-config" variant="accordion">
      <v-expansion-panel value="commission-options">
        <v-expansion-panel-title>
          <div>
            <strong>{{ t('antiCorrosionCommissionParams') }}</strong>
          </div>
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <div class="commission-config-grid">
            <label class="future-schedule-field pre-schedule-control-field">
              <span>{{ t('antiCorrosionCommissionSelectionMode') }}</span>
              <v-select
                v-model="commissionOptions.selectionMode"
                :items="selectionModeOptions"
                density="compact"
                variant="outlined"
                hide-details
                :disabled="runningKey === 'anti-corrosion-schedule'"
              />
              <small>
                {{ commissionOptions.selectionMode === 'manual'
                  ? t('manualAntiCorrosionCommissionHint', { count: selectedPreScheduleCount })
                  : t('autoAntiCorrosionCommissionHint') }}
              </small>
            </label>
            <label class="future-schedule-field pre-schedule-control-field">
              <span>{{ t('antiCorrosionCommissionArea') }}</span>
              <v-text-field
                v-model.number="commissionOptions.commissionArea"
                type="number"
                min="0"
                step="0.01"
                density="compact"
                variant="outlined"
                hide-details
                :disabled="runningKey === 'anti-corrosion-schedule'"
              />
              <small>{{ t('antiCorrosionCommissionAreaHint') }}</small>
            </label>
            <label class="future-schedule-field pre-schedule-control-field">
              <span>{{ t('dateGenerationMode') }}</span>
              <v-select
                v-model="commissionOptions.dateMode"
                :items="dateModeOptions"
                density="compact"
                variant="outlined"
                hide-details
                :disabled="runningKey === 'anti-corrosion-schedule'"
              />
              <small>{{ t('antiCorrosionCommissionDateModeHint') }}</small>
            </label>
            <label v-if="commissionOptions.dateMode !== 'manual'" class="future-schedule-field pre-schedule-control-field">
              <span>{{ t('antiCorrosionCommissionStartDate') }}</span>
              <v-menu
                v-model="commissionStartDateMenu"
                :close-on-content-click="false"
                location="bottom"
              >
                <template #activator="{ props }">
                  <v-text-field
                    v-bind="props"
                    :model-value="commissionOptions.weldStartDate"
                    density="compact"
                    variant="outlined"
                    hide-details
                    readonly
                    append-inner-icon="mdi-calendar"
                    :disabled="runningKey === 'anti-corrosion-schedule'"
                    :placeholder="t('today')"
                  />
                </template>
                <ScheduleCalendar
                  :model-value="commissionOptions.weldStartDate"
                  :min="scheduleCalendarStart"
                  :max="scheduleCalendarEnd"
                  @update:model-value="updateStartDate"
                />
              </v-menu>
              <small>{{ t('antiCorrosionCommissionStartDateHint') }}</small>
            </label>
            <label v-if="commissionOptions.dateMode === 'manual'" class="future-schedule-field pre-schedule-control-field is-wide">
              <span>{{ t('antiCorrosionCommissionManualDates') }}</span>
              <v-menu
                v-model="manualCommissionDatesMenu"
                :close-on-content-click="false"
                location="bottom"
              >
                <template #activator="{ props }">
                  <v-text-field
                    v-bind="props"
                    :model-value="t('openManualWeldCalendar')"
                    density="compact"
                    variant="outlined"
                    hide-details
                    readonly
                    append-inner-icon="mdi-calendar-multiselect"
                    :disabled="runningKey === 'anti-corrosion-schedule'"
                  />
                </template>
                <ScheduleCalendar
                  :model-value="manualDateList"
                  multiple
                  :min="scheduleCalendarStart"
                  :max="scheduleCalendarEnd"
                  :highlighted-dates="holidayCalendarDateList"
                  @update:model-value="$emit('update-manual-date-list', $event)"
                />
              </v-menu>
              <small>{{ t('antiCorrosionCommissionManualDatesHint') }}</small>
            </label>
            <label v-if="commissionOptions.dateMode !== 'manual'" class="future-schedule-field pre-schedule-control-field">
              <span>{{ t('maxGeneratedDays') }}</span>
              <v-text-field
                v-model="commissionOptions.maxDays"
                type="number"
                min="1"
                density="compact"
                variant="outlined"
                hide-details
                :disabled="runningKey === 'anti-corrosion-schedule'"
                :placeholder="t('untilAllScheduled')"
              />
              <small>{{ t('antiCorrosionCommissionMaxDaysHint') }}</small>
            </label>
            <label class="future-schedule-field pre-schedule-switch-field">
              <span>{{ t('skipHolidays') }}</span>
              <v-switch
                v-model="commissionOptions.skipHolidays"
                color="primary"
                density="compact"
                hide-details
                inset
                :disabled="runningKey === 'anti-corrosion-schedule'"
              />
              <small>{{ t('skipHolidaysHint') }}</small>
            </label>
            <label v-if="commissionOptions.skipHolidays" class="future-schedule-field pre-schedule-control-field is-wide">
              <span>{{ t('holidayDates') }}</span>
              <v-menu
                v-model="commissionHolidayDatesMenu"
                :close-on-content-click="false"
                location="bottom"
              >
                <template #activator="{ props }">
                  <v-text-field
                    v-bind="props"
                    :model-value="t('openHolidayCalendar')"
                    density="compact"
                    variant="outlined"
                    hide-details
                    readonly
                    append-inner-icon="mdi-calendar-remove"
                    :disabled="runningKey === 'anti-corrosion-schedule'"
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
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>

    <v-alert
      v-if="commissionError"
      :text="commissionError"
      type="error"
      density="compact"
      class="status-alert"
    />
    <v-alert
      v-if="commissionMessage"
      :text="commissionMessage"
      type="success"
      density="compact"
      class="status-alert"
    />

    <StagedPlanPreview
      :stage="commissionPendingStage"
      :preview="commissionPreviewData"
      :columns="commissionPreviewColumns"
      :title="t('antiCorrosionCommissionPreview')"
      :save-label="t('confirmSaveCommission')"
      :empty-text="t('noAntiCorrosionCommissionPreview')"
      :loading="commissionPreviewLoading"
      :error="commissionPreviewError"
      :saving="commissionStageSaving"
      @save="$emit('save-commission-stage')"
      @preview-file="$emit('preview-commission-file', $event)"
      @change-sheet="$emit('change-commission-preview-sheet', $event)"
    />
    </section>
  </v-card>
</template>

<style scoped>
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

.commission-config-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(240px, 1fr));
  align-items: start;
  gap: 12px;
  width: 100%;
}

.commission-panel {
  min-width: 0;
}

.schedule-section-divider {
  margin: 24px 0 20px;
  border-color: var(--line);
}

.schedule-generation-section {
  min-width: 0;
}

.commission-preview {
  display: grid;
  gap: 12px;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}

.commission-preview-browser {
  display: grid;
  grid-template-columns: minmax(260px, 340px) minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}

.commission-preview-left,
.commission-preview-right {
  min-width: 0;
}

.commission-preview-left {
  height: clamp(280px, 52vh, 480px);
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  padding-right: 4px;
}

.commission-date-panels :deep(.v-expansion-panel) {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
}

.commission-date-title {
  display: grid;
  gap: 2px;
}

.commission-date-title strong {
  color: var(--strong);
  font-size: 13px;
  font-weight: 800;
}

.commission-date-title span {
  color: var(--muted);
  font-size: 12px;
}

.commission-file-list {
  display: grid;
  gap: 8px;
}

.commission-file-button {
  appearance: none;
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  gap: 4px 8px;
  align-items: center;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
  color: var(--text);
  text-align: left;
  cursor: pointer;
}

.commission-preview-empty {
  padding: 18px;
  border: 1px dashed var(--line);
  border-radius: 8px;
  color: var(--muted);
  text-align: center;
}

.commission-file-button:hover,
.commission-file-button.is-active {
  border-color: #93b4ff;
  background: #eaf1ff;
  color: #1d4ed8;
}

.commission-file-button :deep(.v-icon) {
  grid-row: 1 / span 2;
  color: #64748b;
}

.commission-file-button span,
.commission-file-button small {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.commission-file-button span {
  color: var(--strong);
  font-size: 13px;
  font-weight: 700;
}

.commission-file-button small {
  color: var(--muted);
  font-size: 12px;
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

.commission-config-grid .future-schedule-field.is-wide {
  grid-column: auto;
}

.pre-schedule-switch-field {
  grid-template-columns: minmax(0, 1fr) 64px;
  align-items: center;
}

.pre-schedule-control-field :deep(.v-field) {
  min-height: 40px;
}

.pre-schedule-switch-field > small {
  grid-column: 1 / -1;
}

@media (max-width: 1120px) {
  .pre-schedule-config-grid,
  .commission-config-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .commission-preview-browser {
    grid-template-columns: minmax(220px, 300px) minmax(0, 1fr);
  }
}

@media (max-width: 720px) {
  .pre-schedule-config-grid,
  .commission-config-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .future-schedule-field.is-wide {
    grid-column: auto;
  }

  .commission-preview-browser {
    grid-template-columns: minmax(0, 1fr);
  }

  .commission-preview-left {
    height: min(340px, 48vh);
  }
}
</style>
