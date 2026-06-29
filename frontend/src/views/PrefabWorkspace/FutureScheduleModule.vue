<script setup>
import { computed, ref, watch } from 'vue'
import DataVTable from '../../components/DataVTable.vue'
import InfoTooltip from '../../components/InfoTooltip.vue'
import ScheduleCalendar from '../../components/ScheduleCalendar.vue'
import { localizedActionName, localizedModuleDescription } from '../../services/navigationLabels'
import { t } from '../../services/pipecloudState'

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
  scheduleCalendarStart: { type: String, required: true },
  scheduleCalendarEnd: { type: String, required: true },
  manualWeldDateList: { type: Array, default: () => [] },
  holidayCalendarDateList: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits([
  'execute-future-schedule',
  'refresh-status',
  'update-weld-start-date',
  'update-manual-weld-date-list',
  'update-holiday-date-list',
  'preview-pending-file',
  'change-pending-preview-sheet',
  'save-pending-stage',
])

const configPanels = ref(['config'])
const weldStartDateMenu = ref(false)
const manualWeldDatesMenu = ref(false)
const holidayDatesMenu = ref(false)
const pendingDatePanels = ref([])
const selectedPendingPlanType = ref('')

const futurePendingStagePlanGroups = computed(() => {
  const planGroups = new Map()
  ;(props.futurePendingStage?.files || []).forEach((file) => {
    const planType = file.planType || '-'
    const date = file.planDate || ''
    if (!planGroups.has(planType)) {
      planGroups.set(planType, {
        planType,
        dateGroups: new Map(),
      })
    }
    const planGroup = planGroups.get(planType)
    if (!planGroup.dateGroups.has(date)) {
      planGroup.dateGroups.set(date, {
        date,
        title: formatPlanDate(date),
        files: [],
      })
    }
    planGroup.dateGroups.get(date).files.push(file)
  })
  return Array.from(planGroups.values())
    .map((group) => ({
      planType: group.planType,
      dateGroups: Array.from(group.dateGroups.values()).sort(compareDateGroups),
    }))
    .sort((a, b) => a.planType.localeCompare(b.planType, 'zh-CN'))
})

const pendingPlanTypeOptions = computed(() => {
  return futurePendingStagePlanGroups.value.map((group) => ({
    title: group.planType,
    value: group.planType,
  }))
})

const selectedPendingPlanGroup = computed(() => {
  return futurePendingStagePlanGroups.value.find((group) => group.planType === selectedPendingPlanType.value)
    || futurePendingStagePlanGroups.value[0]
    || null
})

function formatPlanDate(value) {
  const text = String(value || '').trim()
  const match = text.match(/^(\d{4})(\d{2})(\d{2})$/)
  if (match) {
    return `${match[1]}-${match[2]}-${match[3]}`
  }
  return text || '-'
}

function compareDateGroups(a, b) {
  if (!a.date) return 1
  if (!b.date) return -1
  return a.date.localeCompare(b.date)
}

function updateWeldStartDate(value) {
  emit('update-weld-start-date', value)
  weldStartDateMenu.value = false
}

watch(() => props.futurePendingStage?.token, () => {
  pendingDatePanels.value = []
  selectedPendingPlanType.value = futurePendingStagePlanGroups.value[0]?.planType || ''
})

watch(futurePendingStagePlanGroups, (groups) => {
  if (!groups.length) {
    selectedPendingPlanType.value = ''
    return
  }
  if (!groups.some((group) => group.planType === selectedPendingPlanType.value)) {
    selectedPendingPlanType.value = groups[0].planType
  }
}, { immediate: true })

watch(selectedPendingPlanType, () => {
  pendingDatePanels.value = []
})
</script>

<template>
  <v-card class="module-panel" :loading="futureScheduleLoading">
    <div class="section-head">
      <div>
        <div class="section-title-with-tip">
          <h2>{{ activeModuleTitle }}</h2>
          <InfoTooltip :text="localizedModuleDescription(activeModule)" />
        </div>
      </div>
    </div>

    <v-alert v-if="futureScheduleError" :text="futureScheduleError" type="error" density="compact" class="status-alert" />
    <v-alert v-if="futureScheduleMessage" :text="futureScheduleMessage" type="success" density="compact" class="status-alert" />
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
      <v-btn :loading="loading" prepend-icon="mdi-refresh" @click="$emit('refresh-status')">{{ t('refreshStatus') }}</v-btn>
    </div>

    <v-expansion-panels v-model="configPanels" class="future-schedule-config" variant="accordion">
      <v-expansion-panel value="config">
        <v-expansion-panel-title>
          {{ t('generatedConfig') }}
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <div class="future-schedule-config-grid">
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
            <label class="future-schedule-field">
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
                    :disabled="futureScheduleConfig.dateMode === 'manual'"
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
            <label class="future-schedule-field is-wide">
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
                    :disabled="futureScheduleConfig.dateMode !== 'manual'"
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
            <label class="future-schedule-field">
              <span>{{ t('maxGeneratedDays') }}</span>
              <v-text-field
                v-model="futureScheduleConfig.maxDays"
                type="number"
                min="1"
                density="compact"
                hide-details
                :disabled="futureScheduleConfig.dateMode === 'manual'"
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
            <label class="future-schedule-field is-wide">
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
                    :disabled="!futureScheduleConfig.skipHolidays"
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

    <div class="pending-stage-actions">
      <div class="pending-stage-head">
        <span>{{ t('pendingStagedFiles', { count: futurePendingStage?.files?.length || 0 }) }}</span>
        <v-btn
          color="primary"
          prepend-icon="mdi-content-save-outline"
          :loading="futureStageSaving"
          :disabled="!futurePendingStage?.token || futureStageSaving"
          @click="$emit('save-pending-stage')"
        >
          {{ t('saveToPlanFile') }}
        </v-btn>
      </div>
      <div class="pending-stage-browser">
        <div class="pending-stage-left">
          <div class="pending-stage-type-select">
            <span>{{ t('planType') }}</span>
            <v-select
              v-model="selectedPendingPlanType"
              :items="pendingPlanTypeOptions"
              :placeholder="t('planType')"
              density="compact"
              hide-details
              :disabled="!pendingPlanTypeOptions.length"
            />
          </div>
          <div class="pending-stage-scroll">
            <section v-if="selectedPendingPlanGroup" class="pending-stage-plan-group">
              <v-expansion-panels
                v-model="pendingDatePanels"
                class="pending-stage-date-groups"
                multiple
                variant="accordion"
              >
                <v-expansion-panel
                  v-for="group in selectedPendingPlanGroup.dateGroups"
                  :key="`${selectedPendingPlanGroup.planType}:${group.date || 'undated'}`"
                  :value="`${selectedPendingPlanGroup.planType}:${group.date || 'undated'}`"
                >
                  <v-expansion-panel-title>
                    <span>{{ t('planDate') }}：{{ group.title }}</span>
                    <small>{{ t('pendingStagedFiles', { count: group.files.length }) }}</small>
                  </v-expansion-panel-title>
                  <v-expansion-panel-text>
                    <div class="pending-stage-files">
                      <button
                        v-for="file in group.files"
                        :key="file.path"
                        :class="['pending-stage-file', { 'is-active': selectedFuturePendingFilePath === file.path }]"
                        type="button"
                        @click="$emit('preview-pending-file', file)"
                      >
                        <v-icon icon="mdi-file-table-outline" size="18" />
                        <div class="pending-stage-file-main">
                          <strong>{{ file.name }}</strong>
                          <span>{{ formatPlanDate(file.planDate) }} · {{ file.sizeText }} · {{ file.updatedText }}</span>
                          <small>{{ file.path }}</small>
                        </div>
                      </button>
                    </div>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>
            </section>
            <div v-else class="pending-stage-empty">{{ t('noPendingStagedPlans') }}</div>
          </div>
        </div>

        <div class="pending-stage-preview">
          <div class="pending-stage-preview-head">
            <div>
              <h3>{{ futurePendingPreview.file?.name || t('selectPendingPlanFile') }}</h3>
              <span v-if="futurePendingPreview.file">{{ futurePendingPreview.file.path }}</span>
            </div>
          </div>
          <v-alert
            v-if="futurePendingPreviewError"
            :text="futurePendingPreviewError"
            type="error"
            density="compact"
            class="status-alert"
          />
          <div v-if="futurePendingPreview.sheets?.length" class="library-toolbar">
            <v-tabs
              :model-value="futurePendingPreview.sheet"
              color="primary"
              @update:model-value="$emit('change-pending-preview-sheet', $event)"
            >
              <v-tab v-for="sheet in futurePendingPreview.sheets" :key="sheet" :value="sheet">{{ sheet }}</v-tab>
            </v-tabs>
          </div>
          <div v-if="futurePendingPreview.file" class="library-meta">
            <span>{{ t('currentSheet') }}：{{ futurePendingPreview.sheet || t('unselected') }}</span>
            <span>{{ t('totalRows') }}：{{ futurePendingPreview.total || 0 }}</span>
            <span>{{ t('columnCount') }}：{{ futurePendingPreview.columns?.length || 0 }}</span>
          </div>
          <DataVTable
            v-if="futurePendingPreview.file"
            :records="futurePendingPreview.rows || []"
            :columns="futurePendingPreviewColumns"
            height="420"
            :empty-text="futurePendingPreviewLoading ? t('loading') : t('currentSheetNoData')"
          />
          <div v-else class="pending-stage-empty">{{ t('selectPendingPlanFile') }}</div>
        </div>
      </div>
    </div>

  </v-card>
</template>

<style scoped>
.future-schedule-config {
  margin: 4px 0 16px;
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

.pending-stage-browser {
  display: grid;
  grid-template-columns: minmax(280px, 34%) minmax(0, 1fr);
  gap: 12px;
  align-items: stretch;
}

.pending-stage-left,
.pending-stage-preview {
  min-width: 0;
}

.pending-stage-left {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 8px;
  height: 560px;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
}

.pending-stage-type-select {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.pending-stage-type-select > span {
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}

.pending-stage-scroll {
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
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

.pending-stage-plan-group {
  display: grid;
  gap: 8px;
}

.pending-stage-plan-group + .pending-stage-plan-group {
  margin-top: 10px;
}

.pending-stage-plan-group h3,
.pending-stage-preview-head h3 {
  margin: 0;
  color: var(--strong);
  font-size: 14px;
  font-weight: 800;
}

.pending-stage-files {
  display: grid;
  gap: 5px;
}

.pending-stage-date-groups {
  display: grid;
  gap: 8px;
}

.pending-stage-date-groups :deep(.v-expansion-panel) {
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
  color: var(--text);
}

.pending-stage-date-groups :deep(.v-expansion-panel-title) {
  min-height: 40px;
  padding: 0 12px;
  color: var(--strong);
  font-size: 13px;
  font-weight: 800;
}

.pending-stage-date-groups :deep(.v-expansion-panel-title__overlay) {
  display: none;
}

.pending-stage-date-groups :deep(.v-expansion-panel-title small) {
  margin-left: 10px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 600;
}

.pending-stage-date-groups :deep(.v-expansion-panel-text__wrapper) {
  padding: 0 10px 10px;
}

.pending-stage-file {
  appearance: none;
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  grid-template-rows: auto auto;
  column-gap: 8px;
  row-gap: 5px;
  align-items: start;
  width: 100%;
  min-width: 0;
  min-height: 64px;
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
  grid-row: 1 / span 2;
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
  grid-row: 1 / span 2;
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
  display: grid;
  gap: 10px;
  min-height: 560px;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
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
  grid-template-columns: repeat(4, minmax(160px, 1fr));
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
  grid-column: span 2;
}

.future-schedule-switch-field {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
}

.future-schedule-switch-field > small {
  grid-column: 1 / -1;
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
