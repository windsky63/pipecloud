<script setup>
import { computed, ref } from 'vue'
import DataVTable from './DataVTable.vue'
import { formatTime, t } from '../services/pipecloudState'

const props = defineProps({
  dashboard: {
    type: Object,
    default: () => ({}),
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: '',
  },
  title: {
    type: String,
    default: '',
  },
  description: {
    type: String,
    default: '',
  },
  showRefresh: {
    type: Boolean,
    default: false,
  },
  collapsible: {
    type: Boolean,
    default: false,
  },
  collapsed: {
    type: Boolean,
    default: false,
  },
  panel: {
    type: Boolean,
    default: true,
  },
})

const emit = defineEmits(['refresh', 'toggle', 'hide'])
const activeView = ref('data')

const viewItems = computed(() => [
  { value: 'data', label: t('dashboardDataView'), icon: 'mdi-view-dashboard-outline' },
  { value: 'table', label: t('dashboardTableView'), icon: 'mdi-table' },
  { value: 'chart', label: t('dashboardChartView'), icon: 'mdi-chart-bar' },
])

const tableColumns = computed(() => [
  { field: 'planDate', title: t('planDate'), width: 120 },
  { field: 'planFolder', title: t('scheduleFolder'), width: 160 },
  { field: 'fileName', title: t('primaryFile'), width: 180 },
  { field: 'completedRows', title: t('completedWelds'), width: 110 },
  { field: 'totalRows', title: t('plannedWelds'), width: 110 },
  { field: 'completionRateText', title: t('completionRate'), width: 110 },
  { field: 'updatedText', title: t('updatedAt'), width: 180 },
])

const recentPlanRows = computed(() => {
  return (props.dashboard.recentPlans || []).map((row) => ({
    ...row,
    completionRateText: formatPercent(row.completionRate),
    updatedText: formatTime(row.updatedAt),
  }))
})

const summaryChartRows = computed(() => [
  {
    label: t('historyPlan'),
    rate: Number(props.dashboard.historyCompletionRate) || 0,
    completed: props.dashboard.historyCompletedRows || 0,
    total: props.dashboard.historyTotalRows || 0,
  },
  {
    label: t('allPlans'),
    rate: Number(props.dashboard.completionRate) || 0,
    completed: props.dashboard.completedRows || 0,
    total: props.dashboard.totalRows || 0,
  },
  {
    label: t('todayPlan'),
    rate: Number(props.dashboard.todayCompletionRate) || 0,
    completed: props.dashboard.todayCompletedRows || 0,
    total: props.dashboard.todayTotalRows || 0,
  },
])

function formatPercent(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '0%'
  return `${number.toFixed(number % 1 === 0 ? 0 : 2)}%`
}

function clampPercent(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return 0
  return Math.max(0, Math.min(number, 100))
}
</script>

<template>
  <component
    :is="panel ? 'v-card' : 'div'"
    class="welding-dashboard-panel"
    :class="{ 'module-panel': panel }"
    v-bind="panel ? { loading, variant: 'flat' } : {}"
  >
    <div v-if="title || showRefresh || collapsible || !collapsed" class="section-head welding-dashboard-head">
      <div>
        <div class="section-title-with-tip">
          <h2>{{ title }}</h2>
          <InfoTooltip v-if="description" :text="description" />
        </div>
      </div>
      <div class="welding-dashboard-actions">
        <v-btn-toggle
          v-if="!collapsed"
          v-model="activeView"
          class="dashboard-icon-toggle"
          mandatory
          density="compact"
          color="primary"
          variant="text"
        >
          <v-btn
            v-for="item in viewItems"
            :key="item.value"
            :value="item.value"
            :icon="item.icon"
            variant="text"
            :aria-label="item.label"
            :title="item.label"
          />
        </v-btn-toggle>
        <span
          v-if="!collapsed && (showRefresh || collapsible)"
          class="dashboard-action-divider"
          aria-hidden="true"
        />
        <slot name="header-extra" />
        <v-btn
          v-if="showRefresh"
          :loading="loading"
          icon="mdi-refresh"
          variant="text"
          :aria-label="t('refreshDashboard')"
          :title="t('refreshDashboard')"
          @click="emit('refresh')"
        />
        <v-btn
          v-if="collapsible"
          icon="mdi-eye-off-outline"
          variant="text"
          :aria-label="t('hideDashboard')"
          :title="t('hideDashboard')"
          @click="emit('hide')"
        />
        <v-btn
          v-if="collapsible"
          :icon="collapsed ? 'mdi-chevron-down' : 'mdi-chevron-up'"
          variant="text"
          :aria-label="collapsed ? t('expandDashboard') : t('collapseDashboard')"
          @click="emit('toggle')"
        />
      </div>
    </div>

    <slot name="actions" />

    <template v-if="!collapsed">
      <v-alert v-if="error" :text="error" type="error" density="compact" class="status-alert" />

      <template v-if="activeView === 'data'">
        <v-sheet class="welding-dashboard" color="transparent">
          <div class="welding-stat-card is-primary">
            <span>{{ t('historyCompletionRate') }}</span>
            <strong>{{ formatPercent(props.dashboard.historyCompletionRate) }}</strong>
            <small>{{ t('weldCountRatio', { completed: props.dashboard.historyCompletedRows || 0, total: props.dashboard.historyTotalRows || 0 }) }}</small>
          </div>
          <div class="welding-stat-card">
            <span>{{ t('historyPlanCount') }}</span>
            <strong>{{ props.dashboard.historyPlanCount || 0 }}</strong>
            <small>{{ t('totalAndTodayPlans', { total: props.dashboard.planCount || 0, today: props.dashboard.todayPlanCount || 0 }) }}</small>
          </div>
          <div class="welding-stat-card">
            <span>{{ t('totalCompletionRate') }}</span>
            <strong>{{ formatPercent(props.dashboard.completionRate) }}</strong>
            <small>{{ t('weldCountRatio', { completed: props.dashboard.completedRows || 0, total: props.dashboard.totalRows || 0 }) }}</small>
          </div>
          <div class="welding-stat-card">
            <span>{{ t('todayCompletionRate') }}</span>
            <strong>{{ formatPercent(props.dashboard.todayCompletionRate) }}</strong>
            <small>{{ t('weldCountRatio', { completed: props.dashboard.todayCompletedRows || 0, total: props.dashboard.todayTotalRows || 0 }) }}</small>
          </div>
        </v-sheet>
      </template>

      <template v-else-if="activeView === 'table'">
        <div class="welding-table-head">
          <div class="section-title-with-tip">
            <h3>{{ t('recentWeldingSchedules') }}</h3>
            <InfoTooltip :text="t('recentWeldingSchedulesTip')" />
          </div>
        </div>
        <DataVTable
          :records="recentPlanRows"
          :columns="tableColumns"
          :height="320"
          :empty-text="t('noWeldingSchedules')"
        />
      </template>

      <template v-else>
        <div class="welding-chart-view">
          <div
            v-for="row in summaryChartRows"
            :key="row.label"
            class="welding-chart-row"
          >
            <div class="welding-chart-label">
              <strong>{{ row.label }}</strong>
              <span>{{ t('weldCountRatio', { completed: row.completed, total: row.total }) }}</span>
            </div>
            <div class="welding-chart-track">
              <div class="welding-chart-fill" :style="{ width: `${clampPercent(row.rate)}%` }" />
            </div>
            <strong class="welding-chart-rate">{{ formatPercent(row.rate) }}</strong>
          </div>

          <div class="welding-recent-chart">
            <strong>{{ t('recentPlanCompletionRate') }}</strong>
            <div v-if="recentPlanRows.length" class="welding-recent-bars">
              <div
                v-for="row in recentPlanRows"
                :key="`${row.planDate}-${row.planFolder}-${row.fileName}`"
                class="welding-recent-bar"
              >
                <span>{{ row.planDate || row.planFolder || '-' }}</span>
                <div class="welding-chart-track">
                  <div class="welding-chart-fill is-secondary" :style="{ width: `${clampPercent(row.completionRate)}%` }" />
                </div>
                <small>{{ row.completionRateText }}</small>
              </div>
            </div>
            <div v-else class="welding-chart-empty">{{ t('noWeldingSchedules') }}</div>
          </div>
        </div>
      </template>

    </template>
  </component>
</template>

<style scoped>
.welding-dashboard-panel {
  min-width: 0;
}

.welding-dashboard-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  min-height: 36px;
  margin-bottom: 14px;
}

.welding-dashboard-head > div:first-child,
.welding-dashboard-head .section-title-with-tip {
  min-height: 36px;
  align-items: center;
}

.welding-dashboard-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  min-height: 36px;
  align-self: center;
}

.dashboard-icon-toggle {
  flex-shrink: 0;
}

.dashboard-icon-toggle :deep(.v-btn),
.welding-dashboard-actions > .v-btn {
  min-width: 36px;
  width: 36px;
  height: 36px;
}

.dashboard-action-divider {
  width: 1px;
  height: 24px;
  flex: 0 0 1px;
  background: var(--line);
}

.welding-dashboard {
  display: grid;
  grid-template-columns: repeat(4, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.welding-stat-card {
  display: grid;
  gap: 6px;
  min-height: 108px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel-soft);
}

.welding-stat-card.is-primary {
  border-color: color-mix(in srgb, var(--primary) 35%, var(--line));
}

.welding-stat-card span,
.welding-stat-card small {
  color: var(--muted);
  font-size: 12px;
}

.welding-stat-card strong {
  color: var(--strong);
  font-size: 30px;
  line-height: 1;
}

.welding-table-head {
  margin-bottom: 10px;
}

.welding-table-head h3 {
  margin: 0;
  color: var(--strong);
  font-size: 16px;
}

.welding-chart-view {
  display: grid;
  gap: 14px;
  margin-bottom: 14px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel-soft);
}

.welding-chart-row,
.welding-recent-bar {
  display: grid;
  grid-template-columns: 150px minmax(0, 1fr) 72px;
  align-items: center;
  gap: 12px;
}

.welding-chart-label {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.welding-chart-label strong,
.welding-recent-chart > strong {
  color: var(--strong);
  font-size: 13px;
}

.welding-chart-label span,
.welding-recent-bar span,
.welding-recent-bar small {
  color: var(--muted);
  font-size: 12px;
}

.welding-chart-track {
  height: 12px;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--line) 70%, var(--panel));
}

.welding-chart-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--primary), #0f9f6e);
}

.welding-chart-fill.is-secondary {
  background: linear-gradient(90deg, #38bdf8, #2563eb);
}

.welding-chart-rate {
  color: var(--strong);
  font-size: 13px;
  text-align: right;
}

.welding-recent-chart {
  display: grid;
  gap: 10px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}

.welding-recent-bars {
  display: grid;
  gap: 8px;
}

.welding-recent-bar span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.welding-chart-empty {
  padding: 18px;
  border: 1px dashed var(--line);
  border-radius: 8px;
  color: var(--muted);
  text-align: center;
}

@media (max-width: 1100px) {
  .welding-dashboard {
    grid-template-columns: 1fr;
  }

  .welding-chart-row,
  .welding-recent-bar {
    grid-template-columns: 1fr;
  }

  .welding-chart-rate {
    text-align: left;
  }
}
</style>
