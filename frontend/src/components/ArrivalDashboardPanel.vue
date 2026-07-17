<script setup>
import { computed, ref } from 'vue'
import DataVTable from './DataVTable.vue'
import InfoTooltip from './InfoTooltip.vue'
import { t } from '../services/pipecloudState'

const props = defineProps({
  dashboard: { type: Object, default: () => ({}) },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  title: { type: String, default: '' },
  description: { type: String, default: '' },
  showRefresh: { type: Boolean, default: false },
  collapsible: { type: Boolean, default: false },
  collapsed: { type: Boolean, default: false },
  panel: { type: Boolean, default: true },
})

const emit = defineEmits(['refresh', 'toggle', 'hide'])
const activeView = ref('data')
const summaries = computed(() => props.dashboard.summaries || {})
const rows = computed(() => (props.dashboard.rows || []).map((row) => ({
  ...row,
  materialTypeText: row.materialType === 'pipe' ? t('pipeMaterial') : t('otherMaterial'),
  arrivalRateText: formatPercent(row.arrivalRate),
})))
const viewItems = computed(() => [
  { value: 'data', label: t('dashboardDataView'), icon: 'mdi-view-dashboard-outline' },
  { value: 'table', label: t('dashboardTableView'), icon: 'mdi-table' },
])
const tableColumns = computed(() => [
  { field: 'materialTypeText', title: t('materialType'), width: 120 },
  { field: 'materialCode', title: t('materialCode'), width: 170 },
  { field: 'description', title: t('description'), width: 260 },
  { field: 'unit', title: t('unit'), width: 80 },
  { field: 'expectedQty', title: t('expectedArrivalQty'), width: 120 },
  { field: 'actualQty', title: t('actualArrivalQty'), width: 120 },
  { field: 'requiredActualQty', title: t('requiredActualArrivalQty'), width: 140 },
  { field: 'extraQty', title: t('extraArrivalQty'), width: 120 },
  { field: 'differenceQty', title: t('arrivalDifferenceQty'), width: 150 },
  { field: 'arrivalRateText', title: t('actualArrivalRate'), width: 110 },
])
const categoryCards = computed(() => [
  { key: 'pipe', title: t('pipeMaterial'), unit: t('meterUnit'), data: summaries.value.pipe || {} },
  { key: 'other', title: t('otherMaterial'), unit: t('materialOwnUnit'), data: summaries.value.other || {} },
])

function formatNumber(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '0'
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 }).format(number)
}

function formatPercent(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '0%'
  return `${number.toFixed(number % 1 === 0 ? 0 : 2)}%`
}
</script>

<template>
  <component
    :is="panel ? 'v-card' : 'div'"
    class="arrival-dashboard-panel"
    :class="{ 'module-panel': panel }"
    v-bind="panel ? { loading, variant: 'flat' } : {}"
  >
    <div class="section-head arrival-dashboard-head">
      <div class="section-title-with-tip">
        <h2>{{ title }}</h2>
        <InfoTooltip v-if="description" :text="description" />
      </div>
      <div class="arrival-dashboard-actions">
        <v-btn-toggle
          v-if="!collapsed"
          v-model="activeView"
          mandatory
          density="compact"
          color="primary"
          variant="text"
        >
          <v-btn
            v-for="item in viewItems"
            :key="item.value"
            :value="item.value"
            icon
            variant="text"
            :aria-label="item.label"
          >
            <v-icon :icon="item.icon" />
            <v-tooltip activator="parent" location="top">{{ item.label }}</v-tooltip>
          </v-btn>
        </v-btn-toggle>
        <span v-if="!collapsed && (showRefresh || collapsible)" class="dashboard-action-divider" />
        <v-btn
          v-if="showRefresh"
          :loading="loading"
          icon
          variant="text"
          :aria-label="t('refreshDashboard')"
          @click="emit('refresh')"
        >
          <v-icon icon="mdi-refresh" />
          <v-tooltip activator="parent" location="top">{{ t('refreshDashboard') }}</v-tooltip>
        </v-btn>
        <v-btn
          v-if="collapsible"
          icon
          variant="text"
          :aria-label="t('hideDashboard')"
          @click="emit('hide')"
        >
          <v-icon icon="mdi-eye-off-outline" />
          <v-tooltip activator="parent" location="top">{{ t('hideDashboard') }}</v-tooltip>
        </v-btn>
        <v-btn
          v-if="collapsible"
          icon
          variant="text"
          :aria-label="collapsed ? t('expandDashboard') : t('collapseDashboard')"
          @click="emit('toggle')"
        >
          <v-icon :icon="collapsed ? 'mdi-chevron-down' : 'mdi-chevron-up'" />
          <v-tooltip activator="parent" location="top">
            {{ collapsed ? t('expandDashboard') : t('collapseDashboard') }}
          </v-tooltip>
        </v-btn>
      </div>
    </div>

    <template v-if="!collapsed">
      <div v-if="activeView === 'data'" class="arrival-summary-grid">
        <section v-for="card in categoryCards" :key="card.key" class="arrival-summary-card" :class="`is-${card.key}`">
          <div class="arrival-summary-title">
            <div>
              <span>{{ card.title }}</span>
              <small>{{ t('materialCodeCount', { count: card.data.materialCount || 0 }) }} · {{ card.unit }}</small>
            </div>
            <strong>{{ formatPercent(card.data.arrivalRate) }}</strong>
          </div>
          <div class="arrival-quantity-grid">
            <div>
              <span>{{ t('expectedArrivalQty') }}</span>
              <strong>{{ formatNumber(card.data.expectedQty) }}</strong>
            </div>
            <div>
              <span>{{ t('actualArrivalQty') }}</span>
              <strong>{{ formatNumber(card.data.actualQty) }}</strong>
            </div>
            <div>
              <span>{{ t('requiredActualArrivalQty') }}</span>
              <strong>{{ formatNumber(card.data.requiredActualQty) }}</strong>
            </div>
            <div>
              <span>{{ t('extraArrivalQty') }}</span>
              <strong>{{ formatNumber(card.data.extraQty) }}</strong>
            </div>
            <div class="is-difference">
              <span>{{ t('arrivalDifferenceQty') }}</span>
              <strong>{{ formatNumber(card.data.differenceQty) }}</strong>
            </div>
          </div>
        </section>
      </div>

      <div v-else>
        <div class="arrival-table-head">
          <h3>{{ t('arrivalMaterialByCode') }}</h3>
          <span>{{ t('arrivalDifferenceFormula') }}</span>
        </div>
        <DataVTable
          :records="rows"
          :columns="tableColumns"
          :height="380"
          :empty-text="t('noArrivalDashboardData')"
        />
      </div>
    </template>
  </component>
</template>

<style scoped>
.arrival-dashboard-panel {
  min-width: 0;
}

.arrival-dashboard-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  min-height: 36px;
  margin-bottom: 14px;
}

.arrival-dashboard-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.arrival-dashboard-actions :deep(.v-btn) {
  min-width: 36px;
  width: 36px;
  height: 36px;
}

.dashboard-action-divider {
  width: 1px;
  height: 24px;
  background: var(--line);
}

.arrival-summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(280px, 1fr));
  gap: 12px;
}

.arrival-summary-card {
  display: grid;
  gap: 16px;
  padding: 16px;
  border: 1px solid color-mix(in srgb, var(--card-accent, var(--primary)) 40%, var(--line));
  border-radius: 8px;
  background: linear-gradient(145deg, color-mix(in srgb, var(--card-accent, var(--primary)) 8%, var(--panel)), var(--panel-soft));
  box-shadow: 0 8px 20px color-mix(in srgb, var(--card-accent, var(--primary)) 8%, transparent);
  transition: transform 160ms ease, box-shadow 160ms ease;
}

.arrival-summary-card.is-pipe {
  --card-accent: var(--primary);
}

.arrival-summary-card.is-other {
  --card-accent: #0f9f6e;
}

.arrival-summary-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 12px 26px color-mix(in srgb, var(--card-accent, var(--primary)) 13%, transparent);
}

.arrival-summary-title,
.arrival-quantity-grid {
  display: grid;
  align-items: center;
  gap: 12px;
}

.arrival-summary-title {
  grid-template-columns: minmax(0, 1fr) auto;
}

.arrival-summary-title > div {
  display: grid;
  gap: 3px;
}

.arrival-summary-title span,
.arrival-quantity-grid span {
  color: var(--muted);
  font-size: 12px;
}

.arrival-summary-title small {
  color: var(--muted);
}

.arrival-summary-title > strong {
  color: var(--strong);
  font-size: 30px;
}

.arrival-quantity-grid {
  grid-template-columns: repeat(5, minmax(0, 1fr));
  align-items: stretch;
}

.arrival-quantity-grid > div {
  display: grid;
  align-content: center;
  gap: 4px;
  padding: 10px;
  border-radius: 6px;
  background: var(--panel);
}

.arrival-quantity-grid strong {
  color: var(--strong);
  font-size: 20px;
}

.arrival-quantity-grid .is-difference strong {
  color: var(--primary);
}

.arrival-table-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 10px;
}

.arrival-table-head h3 {
  margin: 0;
  color: var(--strong);
  font-size: 16px;
}

.arrival-table-head span {
  color: var(--muted);
  font-size: 12px;
}

@media (max-width: 1100px) {
  .arrival-summary-grid,
  .arrival-quantity-grid {
    grid-template-columns: 1fr;
  }
}
</style>
