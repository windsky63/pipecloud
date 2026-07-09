<script setup>
import { computed, ref } from 'vue'
import DataVTable from './DataVTable.vue'
import InfoTooltip from './InfoTooltip.vue'
import { formatTime, t } from '../services/pipecloudState'

const props = defineProps({
  mode: { type: String, required: true },
  dashboard: { type: Object, default: () => ({}) },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  title: { type: String, default: '' },
  description: { type: String, default: '' },
  panel: { type: Boolean, default: true },
})

const activeView = ref('data')

const viewItems = computed(() => [
  { value: 'data', label: t('dashboardDataView'), icon: 'mdi-view-dashboard-outline' },
  { value: 'table', label: t('dashboardTableView'), icon: 'mdi-table' },
])

const isAntiCorrosion = computed(() => props.mode === 'anti-corrosion')
const preSchedule = computed(() => props.dashboard.preSchedule || {})

const statCards = computed(() => {
  if (isAntiCorrosion.value) {
    return [
      { key: 'commissionCount', label: t('antiCorrosionCommissionCount'), value: props.dashboard.commissionCount || 0, hint: t('antiCorrosionSegmentCountHint', { count: props.dashboard.segmentCount || 0 }) },
      { key: 'totalArea', label: t('antiCorrosionTotalArea'), value: formatNumber(props.dashboard.totalArea), hint: t('squareMeterUnit') },
      { key: 'preSchedule', label: t('schedulablePreScheduleRows'), value: preSchedule.value.schedulableRows || 0, hint: t('preScheduleRowsRatio', { total: preSchedule.value.totalRows || 0, rejected: preSchedule.value.rejectedRows || 0 }) },
      { key: 'plans', label: t('schedulePlanCount'), value: props.dashboard.planCount || 0, hint: t('todayPlansCount', { count: props.dashboard.todayPlanCount || 0 }) },
    ]
  }
  return [
    { key: 'orderCount', label: t('cuttingOrderCount'), value: props.dashboard.orderCount || 0, hint: t('todayOrdersCount', { count: props.dashboard.todayOrderCount || 0 }) },
    { key: 'weldCount', label: t('cuttingScheduledWeldCount'), value: props.dashboard.weldCount || 0, hint: t('todayWeldsCount', { count: props.dashboard.todayWeldCount || 0 }) },
    { key: 'diameterTotal', label: t('planDiameterTotal'), value: formatNumber(props.dashboard.diameterTotal), hint: t('diameterUnit') },
    { key: 'preSchedule', label: t('schedulablePreScheduleRows'), value: preSchedule.value.schedulableRows || 0, hint: t('preScheduleRowsRatio', { total: preSchedule.value.totalRows || 0, rejected: preSchedule.value.rejectedRows || 0 }) },
  ]
})

const tableRows = computed(() => {
  return (props.dashboard.rows || []).map((row) => ({
    ...row,
    totalAreaText: formatNumber(row.totalArea),
    diameterTotalText: formatNumber(row.diameterTotal),
    updatedText: formatTime(row.updatedAt),
  }))
})

const tableColumns = computed(() => {
  if (isAntiCorrosion.value) {
    return [
      { field: 'commissionNo', title: t('antiCorrosionCommissionNo'), width: 180 },
      { field: 'commissionDate', title: t('commissionDate'), width: 120 },
      { field: 'segmentCount', title: t('segmentCount'), width: 100 },
      { field: 'totalAreaText', title: t('antiCorrosionArea'), width: 120 },
      { field: 'commissionLimitArea', title: t('commissionLimitArea'), width: 140 },
      { field: 'unitCount', title: t('unitCount'), width: 100 },
      { field: 'pipelineCount', title: t('pipelineCount'), width: 110 },
      { field: 'updatedText', title: t('updatedAt'), width: 180 },
    ]
  }
  return [
    { field: 'planDate', title: t('planDate'), width: 120 },
    { field: 'planFolder', title: t('scheduleFolder'), width: 150 },
    { field: 'orderCount', title: t('cuttingOrderCount'), width: 110 },
    { field: 'weldCount', title: t('plannedWelds'), width: 110 },
    { field: 'diameterTotalText', title: t('planDiameterTotal'), width: 120 },
    { field: 'orderNumbersText', title: t('cuttingOrderNumbers'), width: 260 },
    { field: 'relatedOrderNumbersText', title: t('relatedWeldingOrderNumbers'), width: 260 },
    { field: 'fileCount', title: t('planFileCount'), width: 100 },
    { field: 'updatedText', title: t('updatedAt'), width: 180 },
  ]
})

const emptyText = computed(() => isAntiCorrosion.value ? t('noAntiCorrosionDashboardData') : t('noCuttingDashboardData'))

function formatNumber(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '0'
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 }).format(number)
}
</script>

<template>
  <component
    :is="panel ? 'v-card' : 'div'"
    class="schedule-dashboard-panel"
    :class="{ 'module-panel': panel }"
    v-bind="panel ? { loading, variant: 'flat' } : {}"
  >
    <div class="section-head schedule-dashboard-head">
      <div class="section-title-with-tip">
        <h2>{{ title }}</h2>
        <InfoTooltip v-if="description" :text="description" />
      </div>
      <v-btn-toggle
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
    </div>

    <v-alert v-if="error" :text="error" type="error" density="compact" class="status-alert" />

    <div v-if="activeView === 'data'" class="schedule-stat-grid">
      <section v-for="card in statCards" :key="card.key" class="schedule-stat-card">
        <span>{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
        <small>{{ card.hint }}</small>
      </section>
    </div>

    <DataVTable
      v-else
      :records="tableRows"
      :columns="tableColumns"
      :height="360"
      :empty-text="emptyText"
    />
  </component>
</template>

<style scoped>
.schedule-dashboard-panel {
  min-width: 0;
}

.schedule-dashboard-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  min-height: 36px;
  margin-bottom: 14px;
}

.dashboard-icon-toggle {
  flex-shrink: 0;
}

.dashboard-icon-toggle :deep(.v-btn) {
  min-width: 36px;
  width: 36px;
  height: 36px;
}

.schedule-stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(160px, 1fr));
  gap: 12px;
}

.schedule-stat-card {
  display: grid;
  gap: 6px;
  min-height: 108px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel-soft);
}

.schedule-stat-card:first-child {
  border-color: color-mix(in srgb, var(--primary) 35%, var(--line));
}

.schedule-stat-card span,
.schedule-stat-card small {
  color: var(--muted);
  font-size: 12px;
}

.schedule-stat-card strong {
  color: var(--strong);
  font-size: 30px;
  line-height: 1;
}

@media (max-width: 1100px) {
  .schedule-stat-grid {
    grid-template-columns: 1fr;
  }
}
</style>
