<script setup>
import { ref } from 'vue'
import DataVTable from '../../components/DataVTable.vue'
import InfoTooltip from '../../components/InfoTooltip.vue'
import ScheduleCalendar from '../../components/ScheduleCalendar.vue'
import StagedPlanPreview from '../../components/StagedPlanPreview.vue'
import WeldingDashboardPanel from '../../components/WeldingDashboardPanel.vue'
import { localizedActionName, localizedModuleDescription } from '../../services/navigationLabels'
import { dashboardVisibility, displayDataPath, setDashboardVisibility, t } from '../../services/pipecloudState'

const props = defineProps({
  activeModule: { type: Object, required: true },
  activeModuleTitle: { type: String, required: true },
  weldingDashboardLoading: { type: Boolean, default: false },
  weldingDashboard: { type: Object, required: true },
  weldingDashboardError: { type: String, default: '' },
  weldingScheduleMessage: { type: String, default: '' },
  weldingScheduleError: { type: String, default: '' },
  weldingPendingStage: { type: Object, default: null },
  weldingStageSaving: { type: Boolean, default: false },
  weldingPreviewLoading: { type: Boolean, default: false },
  weldingPreviewError: { type: String, default: '' },
  weldingPreviewData: { type: Object, default: () => ({ sheets: [], rows: [], columns: [], total: 0 }) },
  weldingPreviewColumns: { type: Array, default: () => [] },
  weldingScheduleConfig: { type: Object, required: true },
  weldingScheduleDefaults: { type: Object, default: () => ({}) },
  dateModeOptions: { type: Array, default: () => [] },
  scheduleCalendarStart: { type: String, default: '' },
  scheduleCalendarEnd: { type: String, default: '' },
  manualDateList: { type: Array, default: () => [] },
  holidayCalendarDateList: { type: Array, default: () => [] },
  weldingPreScheduleLoading: { type: Boolean, default: false },
  weldingPreScheduleError: { type: String, default: '' },
  weldingPreScheduleData: { type: Object, required: true },
  weldingPreScheduleActiveSheet: { type: String, default: '' },
  weldingPreScheduleTableColumns: { type: Array, default: () => [] },
  runningKey: { type: String, default: '' },
})

defineEmits([
  'execute-action',
  'refresh-dashboard',
  'update-welding-start-date',
  'update-welding-manual-date-list',
  'update-welding-holiday-date-list',
  'save-pending-stage',
  'preview-welding-file',
  'change-welding-preview-sheet',
  'change-welding-pre-schedule-sheet',
])

const configPanels = ref(['config'])
const dashboardCollapsed = ref(false)
const weldStartDateMenu = ref(false)
const manualWeldDatesMenu = ref(false)
const holidayDatesMenu = ref(false)

</script>

<template>
  <v-card v-if="dashboardVisibility.welding" class="module-panel" :loading="weldingDashboardLoading">
    <WeldingDashboardPanel
      :title="t('weldingDashboardTitle')"
      :description="t('weldingDashboardDescription')"
      :dashboard="weldingDashboard"
      :error="weldingDashboardError"
      :panel="false"
      collapsible
      :collapsed="dashboardCollapsed"
      @hide="setDashboardVisibility('welding', false)"
      @toggle="dashboardCollapsed = !dashboardCollapsed"
    />
  </v-card>

  <v-card class="module-panel" :loading="weldingPreScheduleLoading">
    <div class="section-head">
      <div>
        <div class="section-title-with-tip">
          <h2>{{ t('weldingPreSchedule') }}</h2>
          <InfoTooltip :text="t('weldingPreScheduleDescription')" />
        </div>
        <span>{{ displayDataPath(weldingPreScheduleData.path, t('weldingPreScheduleDefaultPath')) }}</span>
      </div>
      <div class="module-actions">
        <v-btn
          v-for="action in activeModule.actions.filter((item) => item.key === 'welding-pre-schedule')"
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

    <v-alert v-if="weldingPreScheduleError" :text="weldingPreScheduleError" type="error" density="compact" class="status-alert" />

    <div class="library-toolbar">
      <v-tabs
        :model-value="weldingPreScheduleActiveSheet"
        color="primary"
        @update:model-value="$emit('change-welding-pre-schedule-sheet', $event)"
      >
        <v-tab v-for="sheet in weldingPreScheduleData.sheets" :key="sheet" :value="sheet">{{ sheet }}</v-tab>
      </v-tabs>
    </div>

    <div class="library-meta">
      <span>{{ t('currentSheet') }}：{{ weldingPreScheduleActiveSheet || t('unselected') }}</span>
      <span>{{ t('totalRows') }}：{{ weldingPreScheduleData.total }}</span>
      <span>{{ t('columnCount') }}：{{ weldingPreScheduleData.columns.length }}</span>
    </div>

    <DataVTable
      :records="weldingPreScheduleData.rows"
      :columns="weldingPreScheduleTableColumns"
      :height="420"
      :empty-text="t('noWeldingPreScheduleResult')"
      filterable
      selectable
      row-key="库序号"
    />
    <v-divider class="schedule-section-divider" />

    <section class="schedule-generation-section welding-actions-card">
    <div class="section-head">
      <div>
        <div class="section-title-with-tip">
          <h2>{{ activeModuleTitle }}</h2>
          <InfoTooltip :text="localizedModuleDescription(activeModule)" />
        </div>
      </div>
      <div class="module-actions welding-dashboard-module-actions">
        <v-btn
          v-for="action in activeModule.actions.filter((item) => item.key !== 'welding-pre-schedule')"
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

    <v-alert v-if="weldingScheduleError" :text="weldingScheduleError" type="error" density="compact" class="status-alert" />
    <v-alert v-if="weldingScheduleMessage" :text="weldingScheduleMessage" type="success" density="compact" class="status-alert" />
    <v-expansion-panels v-model="configPanels" class="welding-schedule-config" variant="accordion">
      <v-expansion-panel value="config">
        <v-expansion-panel-title>
          {{ t('generatedConfig') }}
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <div class="welding-schedule-config-grid">
            <label class="welding-schedule-field">
              <span>{{ t('dateGenerationMode') }}</span>
              <v-select
                v-model="weldingScheduleConfig.dateMode"
                :items="dateModeOptions"
                density="compact"
                hide-details
              />
              <small>{{ t('dateGenerationModeHint') }}</small>
            </label>
            <label v-if="weldingScheduleConfig.dateMode !== 'manual'" class="welding-schedule-field">
              <span>{{ t('firstWeldDate') }}</span>
              <v-menu v-model="weldStartDateMenu" :close-on-content-click="false" location="bottom">
                <template #activator="{ props }">
                  <v-text-field
                    v-bind="props"
                    :model-value="weldingScheduleConfig.weldStartDate"
                    density="compact"
                    hide-details
                    readonly
                    append-inner-icon="mdi-calendar"
                    :placeholder="weldingScheduleDefaults.weldStartDate || weldingScheduleDefaults.weldDate || t('today')"
                  />
                </template>
                <ScheduleCalendar
                  :model-value="weldingScheduleConfig.weldStartDate"
                  :min="scheduleCalendarStart"
                  :max="scheduleCalendarEnd"
                  @update:model-value="$emit('update-welding-start-date', $event); weldStartDateMenu = false"
                />
              </v-menu>
              <small>{{ t('defaultValue', { value: weldingScheduleDefaults.weldStartDate || weldingScheduleDefaults.weldDate || t('today') }) }}</small>
            </label>
            <label v-if="weldingScheduleConfig.dateMode === 'manual'" class="welding-schedule-field is-wide">
              <span>{{ t('manualWeldDates') }}</span>
              <v-menu v-model="manualWeldDatesMenu" :close-on-content-click="false" location="bottom">
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
                  :model-value="manualDateList"
                  multiple
                  :min="scheduleCalendarStart"
                  :max="scheduleCalendarEnd"
                  :highlighted-dates="holidayCalendarDateList"
                  @update:model-value="$emit('update-welding-manual-date-list', $event)"
                />
              </v-menu>
              <small>{{ t('manualWeldDatesHint') }}</small>
            </label>
            <label v-if="weldingScheduleConfig.dateMode !== 'manual'" class="welding-schedule-field">
              <span>{{ t('maxGeneratedDays') }}</span>
              <v-text-field
                v-model="weldingScheduleConfig.maxDays"
                type="number"
                min="1"
                density="compact"
                hide-details
                :placeholder="weldingScheduleDefaults.maxDays || t('untilAllScheduled')"
              />
              <small>{{ t('defaultValue', { value: weldingScheduleDefaults.maxDays || t('untilAllScheduled') }) }}</small>
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
            <label class="welding-schedule-field welding-schedule-switch-field">
              <span>{{ t('skipHolidays') }}</span>
              <v-switch
                v-model="weldingScheduleConfig.skipHolidays"
                color="primary"
                density="compact"
                hide-details
                inset
              />
              <small>{{ t('skipHolidaysHint') }}</small>
            </label>
            <label v-if="weldingScheduleConfig.skipHolidays" class="welding-schedule-field is-wide">
              <span>{{ t('holidayDates') }}</span>
              <v-menu v-model="holidayDatesMenu" :close-on-content-click="false" location="bottom">
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
                  @update:model-value="$emit('update-welding-holiday-date-list', $event)"
                />
              </v-menu>
              <small>{{ t('holidayDatesHint') }}</small>
            </label>
          </div>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>

    <StagedPlanPreview
      :stage="weldingPendingStage"
      :preview="weldingPreviewData"
      :columns="weldingPreviewColumns"
      :title="t('weldingSchedulePreview')"
      :save-label="t('saveToPlanFile')"
      :empty-text="t('noWeldingSchedulePreview')"
      :loading="weldingPreviewLoading"
      :error="weldingPreviewError"
      :saving="weldingStageSaving"
      @save="$emit('save-pending-stage')"
      @preview-file="$emit('preview-welding-file', $event)"
      @change-sheet="$emit('change-welding-preview-sheet', $event)"
    />

    </section>
  </v-card>
</template>

<style scoped>
.welding-schedule-config {
  margin: 4px 0 16px;
}

.welding-actions-card {
  min-width: 0;
}

.schedule-section-divider {
  margin: 24px 0 20px;
  border-color: var(--line);
}

.schedule-generation-section {
  min-width: 0;
}

.welding-preview {
  display: grid;
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}

.welding-preview-browser {
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
  gap: 14px;
  min-width: 0;
}

.welding-preview-left,
.welding-preview-right {
  min-width: 0;
}

.welding-preview-left {
  height: clamp(280px, 52vh, 480px);
  padding-right: 4px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.welding-date-title {
  display: grid;
  gap: 3px;
}

.welding-date-title span {
  color: var(--muted);
  font-size: 12px;
}

.welding-file-list {
  display: grid;
  gap: 8px;
}

.welding-file-button {
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

.welding-file-button span,
.welding-file-button small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.welding-file-button small {
  grid-column: 2;
  color: var(--muted);
  font-size: 11px;
}

.welding-file-button.is-active {
  border-color: var(--primary);
  background: var(--panel-soft);
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
  grid-template-columns: repeat(2, minmax(240px, 1fr));
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

.welding-schedule-field.is-wide {
  grid-column: auto;
}

.welding-schedule-switch-field {
  grid-template-columns: minmax(0, 1fr) 64px;
  align-items: center;
}

.welding-schedule-switch-field > small {
  grid-column: 1 / -1;
}

@media (max-width: 1100px) {
  .welding-schedule-config-grid {
    grid-template-columns: 1fr;
  }

  .welding-preview-browser {
    grid-template-columns: 1fr;
  }

  .welding-preview-left {
    height: auto;
    max-height: 300px;
  }
}
</style>
