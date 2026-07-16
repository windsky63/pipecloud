<script setup>
import { computed, ref } from 'vue'
import DataVTable from './DataVTable.vue'
import { t } from '../services/pipecloudState'

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
  { value: 'source', label: t('unitWeldTypeComparison'), icon: 'mdi-chart-bar' },
])

const unitTableColumns = computed(() => [
  { field: 'unit', title: t('unitNo'), width: 140 },
  { field: 'totalWeldCount', title: t('fieldWeldCount'), width: 120 },
  { field: 'prefabWeldCount', title: t('prefabWeldCount'), width: 130 },
  { field: 'prefabRateText', title: t('prefabRate'), width: 130 },
  { field: 'autoWeldCount', title: t('autoWeldCount'), width: 120 },
  { field: 'autoRateText', title: t('autoWeldRate'), width: 130 },
])

const unitRows = computed(() => {
  return (props.dashboard.units || []).map((row) => ({
    ...row,
    prefabRateText: formatPercent(row.prefabRate),
    autoRateText: formatPercent(row.autoRate),
  }))
})

const maxUnitWeldCount = computed(() => Math.max(
  1,
  ...unitRows.value.flatMap((row) => [row.totalWeldCount || 0, row.prefabWeldCount || 0, row.autoWeldCount || 0]),
))

function unitBarWidth(value) {
  return `${Math.max(0, Number(value) || 0) / maxUnitWeldCount.value * 100}%`
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
    class="initialization-dashboard-panel"
    :class="{ 'module-panel': panel }"
    v-bind="panel ? { loading, variant: 'flat' } : {}"
  >
    <div v-if="title || showRefresh || collapsible || !collapsed" class="section-head initialization-dashboard-head">
      <div>
        <div class="section-title-with-tip">
          <h2>{{ title }}</h2>
          <InfoTooltip v-if="description" :text="description" />
        </div>
      </div>
      <div class="initialization-dashboard-actions">
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
            icon
            variant="text"
            :aria-label="item.label"
          >
            <v-icon :icon="item.icon" />
            <v-tooltip activator="parent" location="top">{{ item.label }}</v-tooltip>
          </v-btn>
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
          icon
          variant="text"
          :aria-label="t('refreshStats')"
          @click="emit('refresh')"
        >
          <v-icon icon="mdi-refresh" />
          <v-tooltip activator="parent" location="top">{{ t('refreshStats') }}</v-tooltip>
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

    <slot name="actions" />

    <template v-if="!collapsed">
      <v-alert v-if="error" :text="error" type="error" density="compact" class="status-alert" />

      <template v-if="activeView === 'data'">
        <v-sheet class="initialization-stats" color="transparent">
          <div class="initialization-stat-card is-prefab">
            <span>{{ t('prefabVsFieldWelds') }}</span>
            <strong>{{ formatPercent(props.dashboard.prefabRate) }}</strong>
            <small>{{ props.dashboard.prefabWeldCount || 0 }} / {{ props.dashboard.totalWeldCount || 0 }}</small>
          </div>
          <div class="initialization-stat-card is-auto">
            <span>{{ t('autoVsPrefabWelds') }}</span>
            <strong>{{ formatPercent(props.dashboard.autoRate) }}</strong>
            <small>{{ props.dashboard.autoWeldCount || 0 }} / {{ props.dashboard.prefabWeldCount || 0 }}</small>
          </div>
          <div class="initialization-stat-card is-unit">
            <span>{{ t('statisticalUnits') }}</span>
            <strong>{{ props.dashboard.unitCount || 0 }}</strong>
            <small>{{ t('groupedByUnitNo') }}</small>
          </div>
        </v-sheet>
      </template>

      <template v-else-if="activeView === 'table'">
        <div class="initialization-table-head">
          <div class="section-title-with-tip">
            <h3>{{ t('unitWeldRatio') }}</h3>
            <InfoTooltip :text="t('unitWeldRatioTip')" />
          </div>
        </div>
        <DataVTable
          :records="unitRows"
          :columns="unitTableColumns"
          :height="360"
          :empty-text="t('noInitializationStats')"
        />
      </template>

      <template v-else>
        <div class="initialization-table-head">
          <div class="section-title-with-tip">
            <h3>{{ t('unitWeldTypeComparison') }}</h3>
            <InfoTooltip :text="t('unitWeldTypeComparisonTip')" />
          </div>
        </div>
        <div v-if="unitRows.length" class="unit-weld-chart">
          <div class="unit-weld-legend">
            <span class="is-total">{{ t('fieldWelds') }}</span>
            <span class="is-prefab">{{ t('prefabWelds') }}</span>
            <span class="is-auto">{{ t('autoWelds') }}</span>
          </div>
          <div v-for="row in unitRows" :key="row.unit" class="unit-weld-chart-row">
            <strong>{{ row.unit || '-' }}</strong>
            <div class="unit-weld-bars">
              <div class="unit-weld-track"><span class="is-total" :style="{ width: unitBarWidth(row.totalWeldCount) }" /><b>{{ row.totalWeldCount || 0 }}</b></div>
              <div class="unit-weld-track"><span class="is-prefab" :style="{ width: unitBarWidth(row.prefabWeldCount) }" /><b>{{ row.prefabWeldCount || 0 }}</b></div>
              <div class="unit-weld-track"><span class="is-auto" :style="{ width: unitBarWidth(row.autoWeldCount) }" /><b>{{ row.autoWeldCount || 0 }}</b></div>
            </div>
          </div>
        </div>
        <div v-else class="unit-weld-empty">{{ t('noInitializationStats') }}</div>
      </template>
    </template>
  </component>
</template>

<style scoped>
.initialization-dashboard-panel {
  min-width: 0;
}

.initialization-dashboard-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  min-height: 36px;
  margin-bottom: 14px;
}

.initialization-dashboard-head > div:first-child,
.initialization-dashboard-head .section-title-with-tip {
  min-height: 36px;
  align-items: center;
}

.initialization-dashboard-actions {
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
.initialization-dashboard-actions > .v-btn {
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

.initialization-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.initialization-stat-card {
  display: grid;
  gap: 6px;
  min-height: 108px;
  padding: 14px 16px;
  border: 1px solid color-mix(in srgb, var(--card-accent, var(--primary)) 38%, var(--line));
  border-radius: 8px;
  background: linear-gradient(145deg, color-mix(in srgb, var(--card-accent, var(--primary)) 8%, var(--panel)), var(--panel-soft));
  box-shadow: 0 8px 20px color-mix(in srgb, var(--card-accent, var(--primary)) 8%, transparent);
  transition: transform 160ms ease, box-shadow 160ms ease;
}

.initialization-stat-card.is-prefab {
  --card-accent: var(--primary);
}

.initialization-stat-card.is-auto {
  --card-accent: #0f9f6e;
}

.initialization-stat-card.is-unit {
  --card-accent: #d98b18;
}

.initialization-stat-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 12px 26px color-mix(in srgb, var(--card-accent, var(--primary)) 13%, transparent);
}

.initialization-stat-card span,
.initialization-stat-card small {
  color: var(--muted);
  font-size: 12px;
}

.initialization-stat-card strong {
  color: var(--strong);
  font-size: 30px;
  line-height: 1;
}

.initialization-table-head {
  margin-bottom: 10px;
}

.initialization-table-head h3 {
  margin: 0;
  color: var(--strong);
  font-size: 16px;
}

.unit-weld-chart {
  display: grid;
  gap: 12px;
  max-height: 430px;
  padding: 14px;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel-soft);
}

.unit-weld-legend {
  display: flex;
  justify-content: flex-end;
  gap: 18px;
  color: var(--muted);
  font-size: 12px;
}

.unit-weld-legend span::before {
  display: inline-block;
  width: 9px;
  height: 9px;
  margin-right: 6px;
  border-radius: 2px;
  background: currentColor;
  content: '';
}

.unit-weld-chart-row {
  display: grid;
  grid-template-columns: minmax(90px, 140px) minmax(260px, 1fr);
  gap: 14px;
  align-items: center;
}

.unit-weld-chart-row > strong {
  overflow: hidden;
  color: var(--strong);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.unit-weld-bars {
  display: grid;
  gap: 5px;
}

.unit-weld-track {
  position: relative;
  height: 17px;
  overflow: hidden;
  border-radius: 4px;
  background: color-mix(in srgb, var(--line) 45%, transparent);
}

.unit-weld-track > span {
  display: block;
  height: 100%;
  min-width: 2px;
  border-radius: inherit;
}

.unit-weld-track > b {
  position: absolute;
  top: 0;
  right: 6px;
  color: var(--strong);
  font-size: 11px;
  line-height: 17px;
}

.unit-weld-legend .is-total { color: var(--primary); }
.unit-weld-legend .is-prefab { color: #0f9f6e; }
.unit-weld-legend .is-auto { color: #d98b18; }
.unit-weld-track > .is-total { background: var(--primary); }
.unit-weld-track > .is-prefab { background: #0f9f6e; }
.unit-weld-track > .is-auto { background: #d98b18; }

.unit-weld-empty {
  padding: 48px 16px;
  color: var(--muted);
  text-align: center;
}

@media (max-width: 1100px) {
  .initialization-stats {
    grid-template-columns: 1fr;
  }
}
</style>
